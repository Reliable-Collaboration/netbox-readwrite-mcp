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
