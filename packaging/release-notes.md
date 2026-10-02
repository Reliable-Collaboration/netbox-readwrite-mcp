The Reliable Collaboration Company's unofficial read/write MCP Server for NetBox,
with an open-source feature focus bias. Built for existing NetBox installations,
home labs and small businesses priced out of
[NetBox's official enterprise offerings](https://netboxlabs.com/netbox-enterprise/).
For the official managed integration, see the
[Platform MCP Server](https://netboxlabs.com/docs/platform-mcp/).
Supports NetBox Community 4.7.x and later; integration-tested on 4.7.2. Later
versions are accepted, not yet qualified by the recorded suite.

- `netbox-readwrite-mcp.pyz`: standalone MCP application for Python 3.11+ on POSIX. Run `python3 netbox-readwrite-mcp.pyz configure` for private setup and client configuration.
- `netbox_readwrite_mcp-0.4.4-py3-none-any.whl`: MCP package for pipx/uv or a virtualenv.
- `netbox_agent_api-0.4.4-py3-none-any.whl`: companion for NetBox's Python environment; includes `netbox-agent-api-enable --config PATH`.
- `netbox-agent-api-container.tar.gz`: prebuilt plugin and Compose override. Mounts into your existing upstream NetBox image; no replacement image or local build.
- Source distributions, `SHA256SUMS` and `release.json`: source, download integrity and exact revision.

MCP initialization, `capabilities` and `get_guidance` deliver the instructions;
operators do not need to inject an agent guide. Native NetBox permissions remain
authoritative. Keep the journal private; external side effects have no universal
rollback. Branching and commercial integrations are excluded.

See the release-tagged README for traditional, Compose, Kubernetes and Helm
integration recipes. CI gates publishing on unit/build checks and the real NetBox
suite, including a plugin-bundle check on an unmodified upstream image.

Version 0.4.4 adds clearer receipt outcomes and deterministic task summaries,
reuses bounded export/media snapshots, protects new intent fingerprints with
salted scrypt, and fixes setup retries, prefixed website origins and rejected
HTTP request handling. See `docs/review-remediation.md` for findings and tests.

The behavioral revision preceding this version bump passed 688 tests plus six
subtests on NetBox 4.7.2, with 92.55% MCP runtime coverage. Version/package checks
are recorded separately in `docs/validation.md`; the release workflow reruns its
full gates before publishing.

Earlier local GLM-5.3-Flash evaluations used Claude Code, Codex and OpenCode with
this project's read/write MCP server. Their original artifact hashes, failures
and narration limits remain in the validation records. No new model qualification
is claimed for 0.4.4. Model tests run locally only, never in CI.
