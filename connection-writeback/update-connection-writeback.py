#!/usr/bin/env python3
"""Update the catalog and schema used for Sigma connection writeback.

Sigma's supported connection update endpoint uses PUT, so it requires the full
connection payload. Pass a JSON file containing the connection's existing
``name`` and ``details`` properties; this script changes only the writeback
location before submitting it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import requests
except ModuleNotFoundError:  # Give CLI users a useful message instead of an import traceback.
    requests = None  # type: ignore[assignment]


DEFAULT_BASE_URL = "https://aws-api.sigmacomputing.com"
CATALOG_CONNECTION_TYPES = {"databricks"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-name", required=True)
    parser.add_argument("--catalog", required=True, help="Catalog (database for non-Databricks connections)")
    parser.add_argument("--schema", required=True)
    parser.add_argument(
        "--payload-file",
        required=True,
        type=Path,
        help="JSON file containing the full existing Sigma connection update payload",
    )
    parser.add_argument(
        "--writeback-index",
        type=int,
        default=0,
        help="OAuth writebackSchemas entry to update (default: 0)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the updated payload only")
    return parser.parse_args()


def load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read payload file {path}: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("details"), dict):
        raise ValueError("Payload must be a JSON object containing a 'details' object.")
    if not isinstance(payload.get("name"), str) or not payload["name"].strip():
        raise ValueError("Payload must contain a non-empty connection 'name'.")
    return payload


def set_writeback_location(
    payload: dict[str, Any], catalog: str, schema: str, writeback_index: int = 0
) -> dict[str, Any]:
    """Return a copy of payload with its selected writeback location updated."""
    if writeback_index < 0:
        raise ValueError("--writeback-index cannot be negative.")
    if not catalog.strip() or not schema.strip():
        raise ValueError("Catalog and schema cannot be empty.")

    updated = deepcopy(payload)
    details = updated["details"]
    connection_type = str(details.get("type", "")).lower()
    if not connection_type:
        raise ValueError("Payload details must contain the connection 'type'.")

    database_key = "writeCatalog" if connection_type in CATALOG_CONNECTION_TYPES else "writeDatabase"
    location = {database_key: catalog, "writeSchema": schema}

    if details.get("useOauth"):
        schemas = details.setdefault("writebackSchemas", [])
        if not isinstance(schemas, list):
            raise ValueError("details.writebackSchemas must be an array.")
        if writeback_index > len(schemas):
            raise ValueError(
                f"writeback index {writeback_index} is out of range; next valid index is {len(schemas)}."
            )
        if writeback_index == len(schemas):
            schemas.append(location)
        else:
            if not isinstance(schemas[writeback_index], dict):
                raise ValueError("The selected writebackSchemas entry must be an object.")
            schemas[writeback_index].update(location)
    else:
        current = details.get("writeAccess")
        if current is not None and not isinstance(current, dict):
            raise ValueError("details.writeAccess must be an object for non-OAuth connections.")
        details["writeAccess"] = {**(current or {}), **location}

    return updated


def get_access_token(base_url: str, client_id: str, client_secret: str) -> str:
    if requests is None:
        raise RuntimeError("Missing dependency: install it with 'python -m pip install requests'.")
    response = requests.post(
        f"{base_url}/v2/auth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    response.raise_for_status()
    token = response.json().get("access_token") or response.json().get("accessToken")
    if not token:
        raise RuntimeError("Sigma authentication response did not include an access token.")
    return token


def resolve_connection_id(base_url: str, token: str, connection_name: str) -> str:
    """Resolve one exact, active connection name to its Sigma connection ID."""
    if requests is None:
        raise RuntimeError("Missing dependency: install it with 'python -m pip install requests'.")

    matches: list[dict[str, Any]] = []
    page: str | None = None
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        params: dict[str, Any] = {"limit": 1000, "search": connection_name}
        if page:
            params["page"] = page
        response = requests.get(
            f"{base_url}/v2/connections", headers=headers, params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        matches.extend(
            connection
            for connection in data.get("entries", [])
            if connection.get("name") == connection_name and not connection.get("isArchived", False)
        )
        page = data.get("nextPage")
        if not page:
            break

    if not matches:
        raise ValueError(f"No active Sigma connection found with name {connection_name!r}.")
    if len(matches) > 1:
        raise ValueError(
            f"Multiple active Sigma connections are named {connection_name!r}; names must be unique."
        )
    connection_id = matches[0].get("connectionId") or matches[0].get("id")
    if not connection_id:
        raise RuntimeError("Matched connection did not include a connection ID.")
    return str(connection_id)


def main() -> int:
    args = parse_args()
    try:
        payload = set_writeback_location(
            load_payload(args.payload_file), args.catalog, args.schema, args.writeback_index
        )
        if args.dry_run:
            print(json.dumps(payload, indent=2))
            return 0

        client_id = os.environ.get("SIGMA_CLIENT_ID", "")
        client_secret = os.environ.get("SIGMA_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise ValueError("Set SIGMA_CLIENT_ID and SIGMA_CLIENT_SECRET before running the update.")

        base_url = os.environ.get("SIGMA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        token = get_access_token(base_url, client_id, client_secret)
        connection_id = resolve_connection_id(base_url, token, args.connection_name)
        response = requests.put(
            f"{base_url}/v2/connections/{connection_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        writebacks = result.get("writebackSchemas") or result.get("writebacks") or []
        print(f"Updated connection {args.connection_name!r} ({connection_id}) writeback location.")
        print(json.dumps(writebacks, indent=2))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if requests is not None and isinstance(exc, requests.RequestException):
            print(f"Sigma API request failed: {exc}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(main())
