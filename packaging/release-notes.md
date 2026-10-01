Installable NetBox Community 4.7.2 agent tools. No source checkout or local build is needed.

- `netbox-readwrite-mcp.pyz`: standalone MCP application for Python 3.11+ on POSIX; run `python3 netbox-readwrite-mcp.pyz configure` for private setup and client configuration.
- `netbox_readwrite_mcp-0.4.0-py3-none-any.whl`: MCP package for pipx/uv or an existing virtualenv.
- `netbox_agent_api-0.4.0-py3-none-any.whl`: companion package for NetBox's Python environment. Includes `netbox-agent-api-enable --config PATH`.
- `compose.agent-api.yaml`: override for an existing netbox-docker Compose installation. Uses the prebuilt `ghcr.io/reliable-collaboration/netbox-agent-api:0.4.0-netbox4.7.2` image for web and worker (Linux amd64).
- Source distributions, `SHA256SUMS`, and `release.json`: source, download integrity, and exact build revision.

The MCP supplies instructions during initialization and through `capabilities` and `get_guidance`. An operator does not need to inject an agent guide into the client's prompt.

The container image delegates existing configuration and adds the companion to the plugin list; it does not create a NetBox database or provision credentials. Traditional installations must restart web and worker after enabling the plugin. Supply a dedicated NetBox API identity and keep the journal private. Branching/commercial features remain excluded; external side effects have no universal rollback.

See the release-tagged README for setup and qualification details. CI gates publication on unit/build checks and the real NetBox suite.
