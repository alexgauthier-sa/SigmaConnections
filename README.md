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

## Use the Databricks notebook

The notebook is intended to run inside a Databricks workspace and update the first writeback location for a Sigma Databricks OAuth connection.

### 1. Import and attach the notebook

Import `connection-writeback/update-connection-writeback.ipynb` into your Databricks workspace and attach it to running compute with network access to the Sigma API. The notebook uses `dbutils`, so it is not designed to run as a local Jupyter notebook without modification.

The compute environment must have the `requests` Python package. It is normally available in Databricks runtimes; if it is missing, install it on the compute before continuing.

### 2. Store credentials in a Databricks secret scope

Create or use a Databricks secret scope and add these four secrets:

| Default secret key | Value |
| --- | --- |
| `sigma_client_id` | Sigma API client ID |
| `sigma_client_secret` | Sigma API client secret |
| `databricks_oauth_client_id` | OAuth client ID used by the Sigma connection to access Databricks |
| `databricks_oauth_client_secret` | OAuth client secret used by the Sigma connection to access Databricks |

The default scope name is `sigma`. You can use a different scope or different key names by changing the corresponding notebook widgets.

The Sigma API client must be able to list and update connections. The Databricks OAuth credentials must have the access required by the existing connection and its writeback destination.

### 3. Complete `CONNECTION_PAYLOAD`

In the **Existing connection payload** cell, replace the placeholders with the existing connection's values:

- `YOUR_DATABRICKS_HOST`
- `YOUR_SQL_WAREHOUSE_ID`
- `YOUR_DATABRICKS_OIDC_METADATA_URL`
- `CURRENT_CATALOG`
- `CURRENT_SCHEMA`

Keep every other property required by the existing Sigma connection. The notebook submits this object with `PUT`, so omitted connection properties may not be preserved. The connection name is populated from the `connection_name` widget, and the four credentials are loaded from the configured secret scope.

### 4. Set the notebook widgets

Run the widget cell, then provide values at the top of the notebook:

| Widget | Required value |
| --- | --- |
| `connection_name` | Exact name of one active Sigma connection |
| `catalog` | New Databricks writeback catalog |
| `schema` | New Databricks writeback schema |
| `secret_scope` | Scope containing all four secrets; defaults to `sigma` |
| `client_id_secret_key` | Sigma client ID key; defaults to `sigma_client_id` |
| `client_secret_secret_key` | Sigma client secret key; defaults to `sigma_client_secret` |
| `databricks_oauth_client_id_secret_key` | Databricks OAuth client ID key |
| `databricks_oauth_client_secret_secret_key` | Databricks OAuth client secret key |
| `sigma_base_url` | Sigma API host; defaults to the AWS Sigma API |
| `dry_run` | Keep this set to `true` for the first run |

### 5. Run and review the dry run

Run all cells with `dry_run` set to `true`. The final cell builds and prints the payload but does not authenticate to Sigma or update the connection. Confirm that:

- The connection name is correct.
- `writeCatalog` and `writeSchema` contain the intended destination.
- The rest of the connection payload is complete and unchanged.

The printed payload can contain sensitive connection configuration. Treat notebook output as confidential, restrict notebook permissions, and clear the output before sharing or exporting the notebook.

### 6. Apply the update

Change `dry_run` to `false` and rerun the notebook. It authenticates to Sigma, finds one active connection with an exact name match, and submits the updated payload. A successful run prints an `[OK]` message with the connection ID.

The notebook stops without updating anything if the connection name has no exact active match or matches multiple active connections. After a successful update, verify the connection and writeback destination in Sigma before relying on it for production writes.

> **Note:** The notebook updates only the first entry in `details.writebackSchemas`. Use the command-line utility with `--writeback-index` if you need to update another entry.

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
