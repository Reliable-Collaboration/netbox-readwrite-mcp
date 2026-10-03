# Agent issue reporting and maintainer response

The repository is `Reliable-Collaboration/netbox-readwrite-mcp`. Issues are enabled.
The consuming agent needs its own GitHub connection with issue creation access;
the MCP's NetBox token does not provide GitHub access. The maintainer environment
has repository read/write/triage access. No unattended polling or automatic
response schedule is implied.

When an operation is confusing, failed, or uncertain:

1. Preserve its task ID, operation key and operation ID. Call find_operation and
   reconcile after lost responses. Stop writes while the outcome remains uncertain.
2. Call diagnostic_report with the operation ID. This output deliberately omits
   the NetBox URL, actor, names, field values, purposes, payloads and receipt bodies.
3. Search existing GitHub issues for the same tool/error before filing a duplicate.
4. Submit an issue describing the goal, sanitized reproduction, expected and
   observed results, mutation state, and diagnostic report. Use synthetic object
   names. Never publish tokens, web passwords, raw journals, recovery bundles or
   full MCP transcripts. Those stay in protected local storage.
5. Record the issue URL with the task. A maintainer can request an additional
   sanitized reproduction and reply with a fix and test evidence.

The host's GitHub connector can create/read/comment on issues. A CLI alternative
uses an already authenticated `gh` installation:

```sh
python scripts/issues.py submit --title '[agent] concise symptom' --body-file reproduction.txt --diagnostic diagnostic.json
python scripts/issues.py list
python scripts/issues.py view 123
python scripts/issues.py comment 123 --body-file response.txt
```

The helper accepts only the diagnostic_report field structure and rebuilds the
attachment; the author must still review the free-text reproduction for private
data. It does not read NetBox credentials or journals. Use the repository's
Agent integration issue template when filing through the website.

For triage, correlate local operation/native IDs, reproduce in the pinned lab,
add a regression test, implement the fix, run the affected live tests, and reply
with the commit/test evidence and any recovery action. Never tell an agent to
retry an uncertain mutation under a new key merely to close an issue.

The actual submission/read/comment/close loop was exercised with synthetic data
in [issue #1](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/1).

## Optional structured feedback MCP

An operator can install the released wheel with optional feedback dependencies
in a private virtualenv and connect the feedback server to the same journal:

```sh
python3 -m venv feedback-venv
feedback-venv/bin/python -m pip install 'netbox-readwrite-mcp[feedback] @ https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/download/v1.0.0/netbox_readwrite_mcp-1.0.0-py3-none-any.whl'
feedback-venv/bin/python -m netbox_readwrite_mcp.feedback --journal /private/netbox.sqlite --outbox /private/feedback.sqlite --enable-publish
```

Version 0.4.3 adds diagnostic references and device receipts to structured feedback.

It uses the operator's existing `gh` login and always targets this repository.
Without `--enable-publish` it returns a draft and performs no GitHub write. Its
three tools are `report_issue`, `reconcile_report`, and `read_report`. The agent
can supply an operation UUID from either write interface, or a tool response
`diagnostic_reference` (`event:<id>`), plus enum fields; it cannot supply
an issue body, credentials, an arbitrary repository or a filesystem path.
Publication includes only package/NetBox versions and the operation UUID, state
and HTTP status, or the diagnostic reference, tool name and error flag. Inventory, request bodies, receipt bodies and secrets stay local.

A separate private SQLite outbox records publication before dispatch. A lost
response stays uncertain; repeating the same key does not publish again. Marker
search can recover a successful publication. GitHub search may take time to
index a new issue, so an empty search is not evidence that publication failed.
Maintainers can use the CLI above to read/respond with sanitized reproduction
and fix evidence. Read, discovery and validation errors can be reported using their diagnostic
reference even when no mutation was dispatched. The reference is included in
both structured and text tool responses.

`scripts/agent_eval.py --scenario feedback` qualifies the actual consuming-agent
publication/replay/read flow and a maintainer reply in the real project repository.
Unit and official-SDK tests cover privacy, lost responses, duplicate suppression,
operator opt-in and malformed arguments. A live agent pass must be recorded
before claiming the consuming-agent feedback loop is qualified.

Clients such as OpenCode can isolate `XDG_CONFIG_HOME`. In that case the operator
must pass `--gh-config-dir /operator/config/gh` so the feedback process can use
the intended GitHub login. This is a host-side path, never a tool argument. The
GLM harness sets it explicitly and keeps provider credentials out of this process.

The actual GLM-authored structured publication, same-key replay, maintainer reply,
agent readback and close loop passed in
[issue #3](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/3).
See [the evaluation evidence](agent-evaluation.md#consuming-agent-github-feedback)
for the failed isolation run, correction, independent checks and exact source.
