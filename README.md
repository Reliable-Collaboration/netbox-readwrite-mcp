# NetBox Read/Write MCP

An agent interface for discovering and maintaining a greenfield NetBox inventory,
with durable operation receipts and recovery evidence.

**Compatibility: NetBox 4.7.2 only**, the latest stable 4.7 release checked on
2026-09-30. Python 3.11+ on POSIX. No pre-known device IDs or application-level
model allowlist is required: NetBox permissions define the agent's scope.

The server provides object discovery, filtered/paginated reads, live schemas,
GraphQL, CRUD, bulk workflows, IPAM allocation, native API actions, file uploads,
script/job tracking, and an experimental authenticated HTML-form fallback. Installed open-source plugin APIs can use the same discovery and action tools.
Branching and commercial integrations are explicitly outside the product scope.
See the [feature matrix](docs/feature-matrix.md) and [validation](docs/validation.md).

Writes retain intent before dispatch, request/operation IDs, prior values where
available, native change records including cascades, and authoritative outcomes.
Lost responses are reconciled without blindly repeating writes. General PATCH
compensation checks current values and intervening history; unsupported graph
restoration remains explicit. Website form submission is not a transaction or
universal undo. External effects such as webhooks cannot be reversed.

## Install and configure

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,dev]'
```

Use a dedicated NetBox identity with the view/add/change/delete/run permissions
needed for inventory work and full view access to native change history. Do not
default to a superuser. Set `CHANGELOG_RETENTION = 0` and disable independent
purge jobs. Store its write-enabled API token in a protected file.

```json
{
  "netbox_url": "https://netbox.example.org",
  "token_file": "token",
  "journal": "state/journal.sqlite",
  "instance_id": "a-generated-uuid-for-this-netbox-lineage",
  "actor": "inventory-agent",
  "web_password_file": "web-password"
}
```

Generate the instance ID once with `python -c 'import uuid; print(uuid.uuid4())'`.
The optional website password must belong to the same actor; it enables native
experimental website forms. Prefer API tools; see [API-first completion](docs/api-completion.md). Keep credentials and the journal
outside the consuming agent's general filesystem access. Paths are relative to
the config file. `read_only: true` disables mutation tools.

The default configuration has no device ID restriction. Existing restricted
journals remain restricted; removing their configuration allowlist does not
silently expand them. See [migration](docs/operations.md).

## Connect an agent

```json
{
  "mcpServers": {
    "netbox-readwrite": {
      "command": "/absolute/path/.venv/bin/netbox-readwrite-mcp",
      "args": ["--config", "/absolute/path/config.json"]
    }
  }
}
```

Authenticated Streamable HTTP is also available:

```sh
netbox-readwrite-mcp --config config.json --http 8000 --mcp-token-file mcp-token
```

Use a separate random MCP bearer token of at least 32 characters. The endpoint
binds to `http://127.0.0.1:8000/mcp`; remote use requires a trusted TLS reverse
proxy. The server supports JSON responses rather than an SSE event stream.

Give the consuming agent [the agent guide](docs/agent-guide.md). A typical task:

1. Read `capabilities`, then `discover_models` and `get_schema` as needed.
2. Search by native filters with `get_objects`; IDs do not need to be supplied.
3. Begin a task and create dependencies with `create_object`.
4. Read an existing object and retain its ETag before `update_object` or `delete_object`.
5. Preserve operation keys and inspect every result. Reconcile uncertainty.
6. Use `preview_undo` before corrections; report conflicts and recovery limitations.

`query` and `execute_action` cover native allocation, trace, elevation, rendering,
script, bulk, and plugin endpoints. `web_read` exposes website forms and links;
`web_submit` submits them with native CSRF and permissions. `run_workflow` provides
a bounded Python-syntax interpreter with loops, conditions, JSON values and tool
calls, without exposing a Python process or host credentials.

## Test against real NetBox

```sh
python scripts/lab.py up
python scripts/lab.py ready
python scripts/lab.py bootstrap
python scripts/seed.py
NETBOX_RW_LIVE=1 pytest tests/unit tests/integration --cov=netbox_readwrite_mcp --cov-fail-under=85
python scripts/lab.py stop
```

The digest-pinned Podman lab uses port 18872, synthetic inventory, an ordinary
inventory identity, a separately restricted regression identity, PostgreSQL,
Valkey, and a worker. It is isolated from existing NetBox containers. Test
transcripts and journals stay under ignored `.lab/4.7.2/`. See [testing](docs/testing.md).

## Observe and report problems

`get_task`, `get_operation`, `find_operation`, `observability`, and `recovery_bundle`
retain local evidence. MCP tool telemetry includes timing, outcome and operation
ID. `diagnostic_report` produces an inventory-free issue attachment. Consuming
agents can submit issues with their GitHub tools or [scripts/issues.py](scripts/issues.py);
maintainers can read and respond using the same repository. See [issue workflow](docs/agent-issues.md).

Back up the journal and NetBox database independently. No automatic evidence
expiration is configured. Native history completeness and local storage remain
operational requirements. Small home labs are the qualification target; distributed
failover and large-estate performance are outside this release.

Licensed Apache-2.0. Runtime Python code uses the standard library. The NetBox
project is separate and this server is not endorsed by its maintainers.

For complete native filter discovery, install the optional Apache-2.0
[companion plugin](companion/README.md) in NetBox. It supplies custom-field filter
metadata omitted by OpenAPI. Unknown filters are rejected to prevent accidental
unfiltered inventory lookups. It also exposes guarded configuration-revision
APIs using native validation and activation, and personal dashboard APIs with
native widget validation and conditional writes, without HTML forms. The disposable
lab includes the plugin; see its contract for permissions and recovery limits.
