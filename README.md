# The Reliable Collaboration Company's unofficial read/write MCP Server for NetBox

**Built with an open-source feature focus bias.**

Great for home labs or small businesses that are priced out of
[NetBox's official enterprise offerings](https://netboxlabs.com/netbox-enterprise/).
For the official managed agent integration, see the
[Platform MCP Server](https://netboxlabs.com/docs/platform-mcp/).
This is an independent Reliable Collaboration Company project, not a NetBox or
NetBox Labs product.

The existing [read-only community MCP implementation](https://github.com/netboxlabs/netbox-mcp-server)
lets agents query NetBox. This unofficial server adds writes and broader
open-source Community workflows so agents can maintain existing inventory,
record new assets, connect hardware and virtual resources, run jobs, and verify
results. It keeps a history of agent changes and supports GitHub issue reports
when something needs investigation.

Use it with **your existing NetBox installation**, obtained and maintained through
NetBox's own repository, images or package distribution. This project distributes
the MCP server and a companion plugin; it does not distribute NetBox.

**Compatibility: NetBox Community 4.7.x and later. Tested on 4.7.2.** Later versions
are accepted but have not yet passed the recorded integration suite; changes to
NetBox APIs or internals may require a compatibility update. Branching and
commercial features are outside scope. Both packages are Apache-2.0 licensed.

## What you can do

Connect Claude Code, Codex or OpenCode to NetBox, then describe the inventory work
you want done in plain language. Your agent can:

- **Maintain equipment records:** add, update or remove sites, racks, devices,
  interfaces, virtual machines and other inventory, using your existing records
  or creating the records needed for a new installation.
- **Document how everything connects:** record cables, trace connections, assign
  IP addresses and manage network prefixes and VLANs.
- **Handle routine administration:** import or export inventory, make changes to
  multiple records, manage contacts and notes, and run NetBox jobs.
- **Check its work and explain changes:** read back results and keep an operation
  history that helps diagnose failures or interrupted requests.

For example: “Use this equipment list to update our rack inventory, preserve
existing serial numbers, and tell me which details are missing.” Or: “Find an
available address in this subnet and assign it to this server's management port.”

The server supplies its own tool instructions and examples through MCP. You do
not need to give the agent a separate guide. Access follows the permissions of
its NetBox account. The companion plugin adds APIs for supported Community
workflows that would otherwise require website forms.

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
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v1.0.0/netbox-readwrite-mcp.pyz -o netbox-readwrite-mcp.pyz
python3 netbox-readwrite-mcp.pyz configure
```

Keep the application at its installed path. Setup asks for the NetBox base URL,
username and API token (hidden input), creates private configuration and a stable
journal identity. It also prints a generic client configuration; use the
client-specific connection instructions below. Existing configuration and tokens
are preserved. The default directory is
`~/.config/netbox-readwrite-mcp/`, or under `XDG_CONFIG_HOME` when set.

If you already use pipx, you can install the wheel instead:

```sh
pipx install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v1.0.0/netbox_readwrite_mcp-1.0.0-py3-none-any.whl
netbox-readwrite-mcp configure
```

[Release downloads](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v1.0.0)
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
/opt/netbox/venv/bin/python -m pip install https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v1.0.0/netbox_agent_api-1.0.0-py3-none-any.whl
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
curl -fL https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v1.0.0/netbox-agent-api-container.tar.gz -o agent-api.tar.gz && tar -xzf agent-api.tar.gz
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

## 3. Connect your agent

Choose your client below. Run its command from the directory containing the
application you downloaded; `"$PWD/netbox-readwrite-mcp.pyz"` records its absolute
path so the client can start it from any project. Keep that file in place.
The NetBox token stays in the private server configuration.

### Claude Code

```sh
claude mcp add --transport stdio --scope user netbox -- python3 "$PWD/netbox-readwrite-mcp.pyz"
claude mcp get netbox
```

Restart Claude Code and use `/mcp` to check the connection. The user scope makes
it available across projects. See [Claude Code's MCP documentation](https://code.claude.com/docs/en/mcp).

### Codex

```sh
codex mcp add netbox -- python3 "$PWD/netbox-readwrite-mcp.pyz"
codex mcp get netbox
```

Start a new Codex session and use `/mcp` to check the connection. For an
already-authorized unattended job, explicitly allow this server's tools for that
invocation:

```sh
codex exec -c 'mcp_servers.netbox.default_tools_approval_mode="approve"' "Your NetBox task"
```

This leaves your saved approval settings unchanged. See
[Codex's MCP documentation](https://developers.openai.com/codex/mcp/).

### OpenCode

For OpenCode 2:

```sh
opencode mcp add netbox --global -- python3 "$PWD/netbox-readwrite-mcp.pyz"
opencode mcp list
```

For OpenCode 1, including **1.18.33 used in our agent evaluation**, run
`python3 netbox-readwrite-mcp.pyz client-config --client opencode` and merge the
printed `mcp.netbox` entry into your `opencode.json`. Then run `opencode mcp list`.
The released helper prints the version 1 format; version 2 uses `mcp.servers`
instead. See [OpenCode's MCP documentation](https://opencode.ai/v2/docs/mcp-servers).

For a pipx installation, replace `python3 "$PWD/netbox-readwrite-mcp.pyz"` in the
commands above with the absolute path printed by `command -v netbox-readwrite-mcp`.
If you configured a custom server configuration, append `--config /absolute/path/config.json`
to the server command. Other MCP clients can use the generic configuration
printed by `client-config`.

All three clients use this unofficial read/write server's tools and built-in
instructions. Local agent tests passed 24 Community workflow checks in each of
OpenCode, Claude Code and Codex using GLM through LiteLLM.
See the [evaluation record](docs/agent-evaluation.md) for tested workflows,
failed attempts and limits.

## 4. Check the connection and give the agent a task

Provision a dedicated NetBox user with view/add/change/delete/run permissions for
the record types it will manage, plus full read access to `core.view_objectchange`.
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

> Check my NetBox connection and summarize the inventory I can access. Do not change anything.

Then give it your inventory task. For a small authorized trial:

> Create a site named MCP Getting Started, slug mcp-getting-started, status active,
> if it does not already exist. Verify it and summarize what you changed.
> Repeat the check and confirm that no additional writes are needed.

The server delivers instructions at initialization and through `capabilities`;
`get_guidance` supplies detailed, version-matched examples when needed. The tool
catalog directs clients that omit initialization instructions to `capabilities`.
[The readable guide](docs/agent-guide.md) is a documentation copy, not a setup step.
Supply observed hardware facts or an authorized discovery source for a physical
inventory; the agent cannot know which equipment you own without that input.

## Configuration and operations

- `client-config --client opencode` reprints OpenCode 1 settings without changing
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
| Codex refuses MCP writes because approval is required | Allow the intended NetBox tools in the client's MCP approval settings. Noninteractive `approval_policy="never"` does not grant write approval. |
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
