# Sigma Writeback Connection Updater

This repository contains a small utility for changing where a Sigma connection writes data. It updates the connection's **writeback catalog/database and schema** through the Sigma API.

The utility does not create a connection or change how Sigma reads data. It takes an existing connection update payload, changes only its writeback location, resolves the connection by name, and sends the complete payload to Sigma. A complete payload is required because Sigma's connection update endpoint uses `PUT`.

## What it changes

The script supports both OAuth and non-OAuth connections:

- For an OAuth connection (`details.useOauth` is `true`), it updates an entry in `details.writebackSchemas`.
- For a non-OAuth connection, it updates `details.writeAccess`.
- For Databricks, the destination uses `writeCatalog` and `writeSchema`.
- For other connection types, the destination uses `writeDatabase` and `writeSchema`.

All other fields from the supplied payload are preserved.

## Files

- `connection-writeback/update-connection-writeback.py` — command-line utility.
- `connection-writeback/update-connection-writeback.ipynb` — notebook version of the workflow.
- `connection-writeback/connection.json.example` — example Databricks OAuth payload.

## Requirements

- Python 3.9 or newer
- The `requests` Python package
- A Sigma API client ID and secret with permission to list and update connections
- The full current update payload for the connection

Install the Python dependency:

```bash
python -m pip install requests
```

## Prepare the connection payload

Copy the example file and replace every placeholder with the values for the existing connection:

```bash
cp connection-writeback/connection.json.example connection.json
```

The payload must contain at least a non-empty `name` and a `details` object with the connection `type`. In practice, include the full existing connection configuration because Sigma replaces the connection using the submitted payload.

> **Security:** A connection payload can contain credentials or OAuth secrets. Do not commit `connection.json`, print it in shared logs, or distribute it. The example file contains placeholders only.

## Preview the change

Use a dry run first. It prints the updated JSON without authenticating or making an API request:

```bash
python connection-writeback/update-connection-writeback.py \
  --connection-name "My Sigma Connection" \
  --catalog "TARGET_CATALOG" \
  --schema "TARGET_SCHEMA" \
  --payload-file connection.json \
  --dry-run
```

For non-Databricks connections, pass the target database to `--catalog`; the script writes it as `writeDatabase`.

## Apply the change

Set the Sigma API credentials in the environment, then run the command without `--dry-run`:

```bash
export SIGMA_CLIENT_ID="your-client-id"
export SIGMA_CLIENT_SECRET="your-client-secret"

python connection-writeback/update-connection-writeback.py \
  --connection-name "My Sigma Connection" \
  --catalog "TARGET_CATALOG" \
  --schema "TARGET_SCHEMA" \
  --payload-file connection.json
```

The script:

1. Authenticates with Sigma using client credentials.
2. Finds one active connection whose name exactly matches `--connection-name`.
3. Updates the writeback location in a copy of the supplied payload.
4. Sends the complete updated payload to `/v2/connections/{connectionId}`.

The command stops if no exact active match is found or if multiple active connections share the same name.

## Multiple OAuth writeback locations

By default, the first `writebackSchemas` entry is updated. Select another zero-based entry with `--writeback-index`:

```bash
python connection-writeback/update-connection-writeback.py \
  --connection-name "My Sigma Connection" \
  --catalog "TARGET_CATALOG" \
  --schema "TARGET_SCHEMA" \
  --payload-file connection.json \
  --writeback-index 1
```

If the index equals the current number of entries, a new location is appended. An index beyond the next available position is rejected.

## Optional API base URL

The default API host is `https://aws-api.sigmacomputing.com`. To use another Sigma deployment, set `SIGMA_BASE_URL`:

```bash
export SIGMA_BASE_URL="https://your-sigma-api-host"
```

## Important notes

- Back up or otherwise retain the current connection configuration before applying an update.
- Verify the generated payload with `--dry-run` before sending it.
- The script changes connection configuration only; it does not move existing data or create the target catalog, database, or schema.
- The target location and connection credentials must already have the permissions required for Sigma writeback operations.
