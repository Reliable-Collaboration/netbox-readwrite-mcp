# NetBox Read/Write MCP

An agent interface for discovering and maintaining a greenfield NetBox inventory,
with durable operation receipts and recovery evidence.

**Compatibility: NetBox 4.7.2 only**, the latest stable 4.7 release checked on
2026-10-01 against the [upstream release](https://github.com/netbox-community/netbox/releases/tag/v4.7.2). Python 3.11+ on POSIX. No pre-known device IDs or application-level
model allowlist is required: NetBox permissions define the agent's scope.

The server provides object discovery, filtered/paginated reads, live schemas,
GraphQL, CRUD, bulk workflows, IPAM allocation, native API actions, file uploads,
script/job tracking, and typed companion APIs for stock Community website operations
missing from REST. The mapped workflows need no HTML session. An optional HTML
adapter remains experimental. Installed open-source plugin APIs can use the same
discovery and action tools.
Branching and commercial integrations are explicitly outside the product scope.
See the [feature matrix](docs/feature-matrix.md) and [validation](docs/validation.md).

Writes retain intent before dispatch, request/operation IDs, prior values where
available, native change records including cascades, and authoritative outcomes.
Lost responses are reconciled without blindly repeating writes. General PATCH
compensation checks current values and intervening history; unsupported graph
restoration remains explicit. Website form submission is not a transaction or
universal undo. External effects such as webhooks cannot be reversed.

## How the pieces fit together

Your MCP client starts the Python server on the agent host. The server calls
NetBox using a dedicated API token and records tasks and write receipts in a
local SQLite journal. NetBox permissions govern what it can see and change.
The companion plugin runs inside NetBox and its worker, exposing typed APIs
for operations missing from native REST. It uses NetBox's own validation and
permission checks. No browser session is needed for the covered workflows.

The optional feedback MCP is a separate process with GitHub credentials. It lets
an agent publish a structured issue and read the maintainer's reply without
receiving those credentials. Model/provider credentials belong to your MCP client;
the inventory server does not require a particular model or provider.

## Quickstart: choose a lab or your own NetBox

You need Git, Python 3.11+ with venv support, and an MCP client that can launch a
local stdio server. Run these commands on the host where the client will start it.
The implementation currently lives on `feat/community-inventory` ([PR #2](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/pull/2)).

```sh
git clone --branch feat/community-inventory https://github.com/Reliable-Collaboration/netbox-readwrite-mcp.git
cd netbox-readwrite-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
```

### Option A: try the disposable lab

This is the shortest path to a working NetBox plus companion. You also need
rootless Podman, free loopback port 18872, about 4 GiB RAM and 8 GiB disk plus
space for evidence. Initial image downloads and startup can take several minutes.

```sh
python scripts/lab.py up
python scripts/lab.py ready
python scripts/lab.py bootstrap
python scripts/seed.py
```

The lab is available at `http://127.0.0.1:18872`. It creates synthetic fixtures and
a non-superuser inventory identity. Use the generated
`.lab/4.7.2/broad-config.json` for your agent; `config.json` in that directory is
the deliberately restricted regression-test identity. The lab includes the
companion on both web and worker processes. Continue to **Connect an agent** below.

Keep `.lab/` private: it contains credentials and journals. `python scripts/lab.py stop`
stops only this project's lab and preserves its data. See [testing](docs/testing.md)
for lifecycle and cleanup instructions.

### Option B: connect your own NetBox

Use **NetBox Community 4.7.2**. Install and enable the
[companion plugin](companion/README.md#install) in NetBox and its worker for full
stock Community operation coverage. Native REST alone provides a smaller surface.

Create a dedicated NetBox identity with view/add/change/delete/run permissions
for the models it will manage, plus full view access to native change history
(`core.view_objectchange`). Add `render_config` for device/VM configuration
rendering and `sync` for synchronized data actions when needed. Give it a
write-enabled API token. Do not default to a superuser; administrative operations
remain limited by their native permissions. Set `CHANGELOG_RETENTION = 0` in
NetBox and disable independent history purge jobs.

Create a private directory outside this checkout and the agent's general file
access. Save the token alone in `token`, and save this as `config.json` in that
same directory. Replace the URL, actor and instance ID:

```json
{
  "netbox_url": "https://netbox.example.org",
  "token_file": "token",
  "journal": "state/journal.sqlite",
  "instance_id": "REPLACE-WITH-A-GENERATED-UUID",
  "actor": "inventory-agent"
}
```

Use the base URL without `/api/`; HTTPS is required except on loopback. `actor`
is the token owner's NetBox username. Generate the instance ID once with
`python -c 'import uuid; print(uuid.uuid4())'` and retain it with this journal;
restarts must not generate a new ID. See [operations](docs/operations.md) before
changing database lineage or moving an existing journal.

Paths in JSON are relative to the config file. Create its `state` directory and
restrict access, replacing `/absolute/private/netbox-mcp` with your directory:

```sh
mkdir -p /absolute/private/netbox-mcp/state
chmod 700 /absolute/private/netbox-mcp /absolute/private/netbox-mcp/state
chmod 600 /absolute/private/netbox-mcp/token /absolute/private/netbox-mcp/config.json
```

Add `"read_only": true` to disable mutation tools if desired. No device ID
allowlist is needed for greenfield work. Existing restricted journals need the
explicit [migration procedure](docs/operations.md) to expand scope.

## Connect an agent

Add this entry to your client's MCP configuration, replacing both absolute paths.
For the lab, use `/absolute/path/netbox-readwrite-mcp/.lab/4.7.2/broad-config.json`.
For your own deployment, use the private `config.json` created above. The exact
settings file and wrapper keys depend on the client; the command and arguments
are the same. The client starts and keeps the stdio process running.

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

Restart or reconnect the MCP client, then give it [the agent guide](docs/agent-guide.md)
and this read-only connection check:

> Use the NetBox MCP. Read capabilities, discover_models, and the schema for
> dcim/sites/. Read plugins/agent-support/ with query to verify the companion is
> available, then list up to five sites. Report the version, available tools and
> any permission errors. Do not change inventory.

Success means the agent sees NetBox 4.7.2, reads the companion API root and returns
a site list (an empty list is valid). `capabilities` alone is local metadata and
does not prove the NetBox connection works. Once that check passes, try this
small write task in the disposable lab:

> Create a site named MCP Getting Started with slug mcp-getting-started and status
> active, only if it does not already exist. Discover its ID yourself. Follow the
> agent guide, verify the final state, and report the task and operation receipts.
> Run the same task again and confirm it needs no additional writes.

For a physical inventory, supply observed hardware facts or a discovery source;
the agent cannot infer what equipment you actually own. It can create dependencies
and relationships from those facts without preassigned NetBox IDs.

### Optional HTTP transport

Authenticated Streamable HTTP is also available:

```sh
netbox-readwrite-mcp --config config.json --http 8000 --mcp-token-file mcp-token
```

Use a separate random MCP bearer token of at least 32 characters. The endpoint
binds to `http://127.0.0.1:8000/mcp`; remote use requires a trusted TLS reverse
proxy. The server supports JSON responses rather than an SSE event stream.

### How an inventory task proceeds

A typical task:

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

## Run the qualification suite

After starting and seeding the disposable lab above:

```sh
python -m pip install -e '.[test,dev]'
NETBOX_RW_LIVE=1 pytest tests/unit tests/integration --cov=netbox_readwrite_mcp --cov-fail-under=85
```

The full run takes roughly 35–40 minutes in the recorded environments. It passed
585 tests plus six subtests, including 231 live cases. See [validation](docs/validation.md)
for exact revisions and [agent evaluation](docs/agent-evaluation.md) for the
separate GLM/OpenCode acceptance runs. A paid model provider is not needed for
the deterministic suite.

The digest-pinned Podman lab uses port 18872, synthetic inventory, an ordinary
inventory identity, a separately restricted regression identity, PostgreSQL,
Valkey, and a worker. It is isolated from existing NetBox containers. Test
transcripts and journals stay under ignored `.lab/4.7.2/`. See [testing](docs/testing.md).

## If the connection check fails

| Symptom | Check |
| --- | --- |
| Client cannot start the server | Use the absolute executable path in this checkout's `.venv/bin/`; check that the client host can read the config and token files. |
| A manually started stdio command waits silently | It is waiting for MCP protocol input. Connect through the client; it is not an interactive shell. |
| Version rejected | Both packages support exactly NetBox Community 4.7.2. |
| HTTP 401/403 or missing objects | Check token validity, write enablement and the identity's model/object permissions. Restricted views may legitimately be empty. |
| Companion root missing or stale schema | Install/enable the plugin, restart web and worker, and follow its cache-refresh instructions. |
| Unknown filter | Inspect the live schema; install the companion for native/custom-field filter metadata. Do not drop the intended constraint and act on unrelated results. |
| Legacy device allowlist error | Use the lab's `broad-config.json`, or explicitly migrate the restricted journal. |
| Uncertain write outcome | Preserve the original operation key, inspect/reconcile its receipt, and follow the agent guide before attempting another write. |

## Observe and report problems

`get_task`, `get_operation`, `find_operation`, `observability`, and `recovery_bundle`
retain local evidence. MCP tool telemetry includes timing, outcome and operation
ID. `diagnostic_report` produces an inventory-free issue attachment. Consuming
agents can use the optional [feedback MCP](docs/agent-issues.md#optional-structured-feedback-mcp),
their GitHub tools or [scripts/issues.py](scripts/issues.py). GitHub authentication
is separate from NetBox authentication. Maintainers can read and respond in this
repository; the feedback MCP lets the agent read that reply. See [issue workflow](docs/agent-issues.md).

Back up the journal and NetBox database independently. No automatic evidence
expiration is configured. Native history completeness and local storage remain
operational requirements. Small home labs are the qualification target; distributed
failover and large-estate performance are outside this release.

Licensed Apache-2.0. Runtime Python code uses the standard library. The NetBox
project is separate and this server is not endorsed by its maintainers.
