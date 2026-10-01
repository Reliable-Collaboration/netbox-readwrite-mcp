Open-source read/write agent integration for your existing NetBox installation.
Supports NetBox Community 4.7.x and later; integration-tested on 4.7.2. Later
versions are accepted, not yet qualified by the recorded suite.

- `netbox-readwrite-mcp.pyz`: standalone MCP application for Python 3.11+ on POSIX. Run `python3 netbox-readwrite-mcp.pyz configure` for private setup and client configuration.
- `netbox_readwrite_mcp-0.4.0-py3-none-any.whl`: MCP package for pipx/uv or a virtualenv.
- `netbox_agent_api-0.4.0-py3-none-any.whl`: companion for NetBox's Python environment; includes `netbox-agent-api-enable --config PATH`.
- `netbox-agent-api-container.tar.gz`: prebuilt plugin and Compose override. Mounts into your existing upstream NetBox image; no replacement image or local build.
- Source distributions, `SHA256SUMS` and `release.json`: source, download integrity and exact revision.

MCP initialization, `capabilities` and `get_guidance` deliver the instructions;
operators do not need to inject an agent guide. Native NetBox permissions remain
authoritative. Keep the journal private; external side effects have no universal
rollback. Branching and commercial integrations are excluded.

See the release-tagged README for traditional, Compose, Kubernetes and Helm
integration recipes. CI gates publishing on unit/build checks and the real NetBox
suite, including a plugin-bundle check on an unmodified upstream image.
