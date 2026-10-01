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

## Install the MCP server

You need Python 3.11+ on POSIX and an MCP client that can start a local process.
Download the CI-built application and run its setup wizard:

```sh
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox-readwrite-mcp.pyz -o netbox-readwrite-mcp.pyz
python3 netbox-readwrite-mcp.pyz configure
```

Keep the downloaded file at its installed path. Setup asks for your NetBox base
URL, username and API token (hidden input), stores a private configuration under
`~/.config/netbox-readwrite-mcp/` (or `XDG_CONFIG_HOME`), generates the journal
identity once, and prints the MCP client configuration to paste into your client.
Use `configure --client opencode` for OpenCode's configuration format. Setup
never overwrites an existing configuration or token.

Alternatively, with pipx already installed:

```sh
pipx install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox_readwrite_mcp-0.4.0-py3-none-any.whl
netbox-readwrite-mcp configure
```

[Release assets](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.0)
also include both wheels, source distributions, checksums and the exact build
revision. No checkout or build tools are needed for installation. Releases are
published only after CI passes the unit/build matrix and real-NetBox tests.

## Install and enable the companion

Full stock Community coverage needs the companion on both NetBox web and worker.
It is a separate package because these APIs run inside NetBox, not on the agent
host. Choose the path matching your existing **NetBox Community 4.7.2** deployment.

### Existing netbox-docker Compose deployment

From your deployment directory, download the override and recreate the web and
worker with the CI-built image:

```sh
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/compose.agent-api.yaml -o compose.agent-api.yaml
docker compose -f docker-compose.yml -f compose.agent-api.yaml up -d netbox netbox-worker
```

Use your existing base Compose filename and include any other override files you
normally use before `compose.agent-api.yaml`. Podman deployments can use their
configured Compose provider with the same override. Service names must be
`netbox` and `netbox-worker`; adapt them if your deployment differs. This restarts
those services while preserving the deployment's configured database and volumes.

The prebuilt image is
`ghcr.io/reliable-collaboration/netbox-agent-api:0.4.0-netbox4.7.2` (Linux amd64).
It includes and enables the plugin automatically, retains existing plugins, and
delegates other settings to the deployment's normal configuration. If you use a
custom `NETBOX_CONFIGURATION` module, set `NETBOX_AGENT_BASE_CONFIGURATION` to
that module. Deployments with additional packages in a custom image must include
the companion wheel in that image instead of replacing it with ours. See the
[companion installation details](companion/README.md#install).

### Traditional NetBox virtualenv

Run with permission to install into NetBox's environment and as the configuration
file owner. Replace paths for your deployment:

```sh
/opt/netbox/venv/bin/python -m pip install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox_agent_api-0.4.0-py3-none-any.whl
/opt/netbox/venv/bin/netbox-agent-api-enable --config /opt/netbox/netbox/netbox/configuration.py
```

The enable command preserves existing settings/plugins, saves a private backup,
and is safe to repeat. Restart web and worker using your deployment manager
(for a standard systemd install: `sudo systemctl restart netbox netbox-rq`).
Separate hosts need the wheel installed on each. No database migrations are added.

## NetBox identity and first connection

Provision a dedicated NetBox identity with view/add/change/delete/run permissions
for the models it will manage, plus full access to `core.view_objectchange`.
Add `render_config` for device/VM configuration rendering and `sync` for source
synchronization if needed. Use a write-enabled token for inventory management;
administrative operations still require their native permissions. Set
`CHANGELOG_RETENTION = 0` and disable independent history purge jobs so recovery
can inspect complete history. The companion does not grant permissions or create
credentials. Native REST works without it, with a smaller operation surface.

The wizard uses the base URL without `/api/`; HTTPS is required except on loopback.
The username must match the token owner. Use `configure --read-only` for a
connection that refuses mutations, or `--token-file PATH` for unattended setup
without a token in shell arguments. Use `--config PATH` to select a private custom
location. See [operations](docs/operations.md) before moving a journal or changing
database lineage.

Check connectivity after enabling the companion:

```sh
python3 netbox-readwrite-mcp.pyz doctor
```

This verifies the exact NetBox version, companion root and change-history access
without writing inventory. It does not prove every model-specific permission.
`client-config --client opencode` reprints client settings without changing the
identity; omit the client option for the common `mcpServers` format.

Reconnect your MCP client. **No agent guide needs to be attached or pasted.** The
server supplies core instructions at initialization, repeats them in `capabilities`,
and offers detailed, version-matched examples through `get_guidance`. Tool
schemas describe inputs. Client handling of initialization instructions varies,
so the tool catalog also tells the agent to start with `capabilities`.

Give the agent a task, for example:

> Inspect my NetBox connection and available permissions without changing anything.

Then, for an authorized test site:

> Create a site named MCP Getting Started with slug mcp-getting-started and status
> active if it does not exist. Verify it and report the operation receipts. Repeat
> the check and confirm no additional writes are needed.

For a physical inventory, supply observed hardware facts or a discovery source;
the agent discovers IDs and creates dependencies, but cannot infer what equipment
you own. [The readable guide](docs/agent-guide.md) is a documentation copy of the
packaged guidance, not a client setup requirement.

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

Contributors can clone the repository and run the disposable Podman lab. This
source checkout is for development/testing, not required for user installation.
See [testing](docs/testing.md) for prerequisites and all lab commands. The generated
`.lab/4.7.2/broad-config.json` connects an agent with the ordinary inventory identity;
`.lab/4.7.2/config.json` is intentionally restricted for regression tests.

After starting and seeding that lab:

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
| Client cannot start the server | Use the configuration printed by `client-config`; keep the downloaded application in place and check the client host can read the config/token. |
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
