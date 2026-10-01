# NetBox Read/Write MCP

**An open-source MCP server that lets agents maintain NetBox, not just query it.**

The [NetBox Labs open-source MCP server](https://github.com/netboxlabs/netbox-mcp-server)
provides read-only access. This project adds writes and broader Community workflows
so an agent can build an initial inventory, maintain existing assets, connect
hardware and virtual resources, run jobs, and verify the results. It includes
operation receipts, conditional edits, recovery evidence and a GitHub feedback
path for diagnosing problems encountered by consuming agents.

Use it with **your existing NetBox installation**, obtained and maintained through
NetBox's own repository, images or package distribution. This project distributes
the MCP server and a companion plugin; it does not distribute NetBox.

**Compatibility: NetBox Community 4.7.x and later. Tested on 4.7.2.** Later versions
are accepted but have not yet passed the recorded integration suite; changes to
NetBox APIs or internals may require a compatibility update. Branching and
commercial features are outside scope. Both packages are Apache-2.0 licensed.

## What it provides

- Discovery of models, fields, relationships, filters and native actions. Agents
  find IDs themselves, including when starting with an empty inventory.
- Read, create, update and delete operations across physical, virtual and network
  inventory, plus bulk operations, allocation, imports/exports and jobs.
- Typed companion APIs for Community operations missing from native REST, using
  NetBox's own validation and permissions instead of browser forms.
- Durable task/write receipts, ETag-guarded edits, response-loss reconciliation
  and conditional compensation where supported.
- Built-in MCP instructions and examples. No guide needs to be pasted into an
  agent's context, and no specific model/provider is required.

See the [operation map](docs/api-completion.md) and [qualification record](docs/validation.md)
for detailed coverage. Arbitrary third-party plugins need separate qualification.

## How it connects

Your MCP client starts the server on the agent host. The server uses a dedicated
NetBox API token and stores its journal locally. NetBox permissions govern what
the agent can see and change. The companion runs inside NetBox web and worker
processes to fill native API gaps. The optional feedback MCP uses a separate
GitHub login to publish structured issues and read maintainer replies.

## 1. Install the MCP server

Requires Python 3.11+ on POSIX and a client that can launch a local MCP process.
Download the CI-built application and run its setup wizard:

```sh
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox-readwrite-mcp.pyz -o netbox-readwrite-mcp.pyz
python3 netbox-readwrite-mcp.pyz configure
```

Keep the application at its installed path. Setup asks for the NetBox base URL,
username and API token (hidden input), creates private configuration and a stable
journal identity, and prints the client entry to paste into your MCP client.
Use `configure --client opencode` for OpenCode's format. Existing configuration
and tokens are preserved. The default directory is
`~/.config/netbox-readwrite-mcp/`, or under `XDG_CONFIG_HOME` when set.

If you already use pipx, you can install the wheel instead:

```sh
pipx install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox_readwrite_mcp-0.4.0-py3-none-any.whl
netbox-readwrite-mcp configure
```

[Release downloads](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.0)
include checksums, both wheels, the container plugin bundle, source distributions
and the exact build revision. No checkout or local build is required.

## 2. Add the companion to your existing NetBox

Native REST works without the companion, with a smaller operation surface.
Install the companion on **both web and worker** for full Community coverage.
Choose the integration matching your deployment; keep your upstream NetBox image
or package and existing database/configuration.

### Traditional source, virtualenv or package installation

Use the Python environment that actually runs NetBox and the file that defines
its effective `PLUGINS` setting. These are example paths; package-managed installs
may use different locations. Run as the environment/configuration owner:

```sh
/opt/netbox/venv/bin/python -m pip install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox_agent_api-0.4.0-py3-none-any.whl
/opt/netbox/venv/bin/netbox-agent-api-enable --config /opt/netbox/netbox/netbox/configuration.py
```

The enable command retains existing settings/plugins, makes a private backup and
is safe to repeat. Restart NetBox web and worker with your deployment manager
(for a standard systemd installation: `sudo systemctl restart netbox netbox-rq`).
Separate hosts need the package installed on each. If your package manager owns
an immutable Python environment, use its supported plugin mechanism with the
same wheel; do not bypass its environment protections.

### Docker or Podman Compose

From your existing netbox-docker deployment directory:

```sh
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v0.4.0/netbox-agent-api-container.tar.gz -o agent-api.tar.gz && tar -xzf agent-api.tar.gz
docker compose -f docker-compose.yml -f netbox-agent-api/compose.agent-api.yaml up -d netbox netbox-worker
```

Use your actual base Compose filename, retaining your usual override files before
our override. Podman can use its configured Compose provider. The override mounts
only the prebuilt plugin, enables it on web and worker, and **does not replace your
NetBox image**. It recreates those services while retaining the volumes and other
settings in your Compose configuration. Adjust service names if they differ.

Existing plugins remain enabled. If you already set `PYTHONPATH`, retain its
entries alongside `/opt/netbox/agent-api`. If you use a custom
`NETBOX_CONFIGURATION`, set `NETBOX_AGENT_BASE_CONFIGURATION` to that original
module. See [deployment details](companion/README.md#install).

### Kubernetes, Helm and other container managers

Use the same downloadable plugin bundle: mount its `plugin` directory at
`/opt/netbox/agent-api` in every web/worker workload, add that directory to
`PYTHONPATH`, and set `NETBOX_CONFIGURATION=netbox_agent_api_configuration`.
Retain your upstream image and set `NETBOX_AGENT_BASE_CONFIGURATION` if you use a
custom configuration module. Roll out the change with your normal controller.
Alternatively, use your chart's existing plugin-installation mechanism with the
released wheel. [Deployment details](companion/README.md#install) explain the
configuration overlay and upgrades. This is a deployment recipe, not a separately
qualified Helm chart or Kubernetes operator.

## 3. Check the connection and give the agent a task

Provision a dedicated NetBox user with view/add/change/delete/run permissions for
the models it will manage, plus full read access to `core.view_objectchange`.
Add `render_config` and `sync` when those actions are required. Use a write-enabled
API token for inventory management. Administrative operations still require
native permissions; the companion grants none. Set `CHANGELOG_RETENTION = 0` and
disable independent history purge jobs so recovery has complete evidence.

```sh
python3 netbox-readwrite-mcp.pyz doctor
```

This checks version acceptance, companion access and history reads without
changing inventory. It reports whether the connected version is tested; it does
not prove every model-specific permission. The URL must omit `/api/`; HTTPS is
required except on loopback. The configured username must match the token owner.

Reconnect your MCP client and ask:

> Inspect my NetBox connection and available models without changing anything.

Then give it your inventory task. For a small authorized trial:

> Create a site named MCP Getting Started, slug mcp-getting-started, status active,
> if it does not already exist. Verify it and report the operation receipts.
> Repeat the check and confirm that no additional writes are needed.

The server delivers instructions at initialization and through `capabilities`;
`get_guidance` supplies detailed, version-matched examples when needed. The tool
catalog directs clients that omit initialization instructions to `capabilities`.
[The readable guide](docs/agent-guide.md) is a documentation copy, not a setup step.
Supply observed hardware facts or an authorized discovery source for a physical
inventory; the agent cannot know which equipment you own without that input.

## Configuration and operations

- `client-config --client opencode` reprints client settings without changing
  identity; omit the client option for the common `mcpServers` format.
- `configure --read-only` disables mutation tools. `--token-file PATH` supports
  unattended setup without putting a token in shell arguments.
- `--config PATH` selects a private custom config. Paths inside it are relative
  to that file. Retain the instance ID and journal across restarts; consult
  [operations](docs/operations.md) before changing database lineage.
- Authenticated HTTP is available with `--http 8000 --mcp-token-file PATH`.
  Use a separate random bearer token of at least 32 characters. It binds to
  loopback `/mcp`; remote access requires a trusted TLS reverse proxy.
- Connect the optional [GitHub feedback MCP](docs/agent-issues.md) to let agents
  publish structured reports and read maintainer replies. NetBox and GitHub
  credentials are separate; no unattended response schedule is implied.

Back up the journal and NetBox database independently. Keep tokens, journals,
recovery bundles and raw transcripts private. Lost responses are reconciled using
original operation keys. Undo is conditional compensation: it cannot universally
restore deleted graphs or reverse webhook, queue and filesystem effects. The
experimental HTML adapter is unnecessary for mapped Community workflows.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Client cannot start the MCP | Reprint `client-config`; ensure the application, Python and private config remain at the configured paths. |
| A manually started stdio process waits silently | Connect it through the MCP client; it is waiting for protocol input. |
| HTTP 401/403 or missing objects | Check token validity, write enablement and model/object permissions. |
| Companion missing | Verify the package/mount and effective configuration on both web and worker; restart or roll out both. |
| Unknown filter or stale schema | Inspect live schema and companion metadata; follow the deployment's schema-cache refresh procedure after upgrades. |
| Legacy device allowlist | Explicitly migrate the restricted journal; see operations. |
| Uncertain write | Preserve the original key, inspect/reconcile its receipt, and report unresolved evidence before another write. |

## Testing and development

CI builds release assets and gates publication on the Python unit/build matrix
and real NetBox 4.7.2 integration suite. The [validation record](docs/validation.md)
and [agent evaluations](docs/agent-evaluation.md) distinguish deterministic tests,
actual GLM runs and untested combinations. Acceptance of a later NetBox version
does not imply that its full workflow surface has been tested.

Contributors can clone the repository and run the disposable Podman lab described
in [testing](docs/testing.md). That lab is development infrastructure, not the
user installation path. Small labs are the current qualification target;
large-estate performance and distributed failover are outside this release.

This independent Apache-2.0 project is not endorsed by NetBox's maintainers.
