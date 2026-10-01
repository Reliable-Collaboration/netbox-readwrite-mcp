# Validation record

**Stock NetBox Community 4.7.2 operation parity is implemented and qualified.**
The current qualification is version 0.3.0, dated 2026-10-01. It supports a
controlled consuming-agent handoff for small labs. It is not a production
certification, a guarantee for every field combination, or universal automatic undo.

The pinned audit maps **1,543 website routes to 40 semantic operation families**,
with no unknown routes or missing mapped native CRUD verbs. The
[operation map](api-completion.md) explains the native REST and companion APIs;
[the closure table](parity-worklist.md) links families to live qualification.
Mapped inventory operations require no HTML session. Branching and commercial
integrations are excluded.

| Qualification | Result |
| --- | --- |
| Unit tests | 354 passed |
| Real-NetBox integration tests | 231 passed |
| Complete suite | **585 passed, plus 6 subtests** |
| MCP runtime statement/branch coverage | **91.75%**; minimum 85% |
| CI | Python 3.11–3.14, both package builds, and fresh-container live suites passed |
| Distribution checks | Both sdist/wheel pairs built; 17 MCP and 20 companion Python modules match source; isolated MCP wheel installation and CLI passed |
| Strict combined GLM workflow | **23 checks passed**, 56 MCP calls, 555.70 seconds |
| GitHub agent feedback | Real publish, same-key replay, maintainer reply and verified readback passed in [issue #3](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/3) |

The final qualification revision is `097f6cb`. Its
[push CI](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36899629421)
and [PR CI](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36899638753)
use independent fresh, digest-pinned NetBox/PostgreSQL/Valkey/worker deployments.
The complete local run used application-identical revision `45d405c` and passed
in 2408.33 seconds. That revision also passed both fresh CI workflows. The final
revision changes only the webhook fixture's network namespace; its full delivery,
HMAC, request-ID and cleanup assertions also passed in a focused local run.

CI exposed two issues during completion. Native history expansion of a live
`dcim.portmapping` returned HTTP 500; both synchronization and `get_changelogs`
now request the immutable audit fields already retained in the journal. The
webhook test's temporary network registration could interrupt Podman DNS during
cleanup; the receiver now shares the existing worker namespace. Cold REST
initialization is checked before fixture writes, with bounded read-only readiness
probes. Mutation retries were not introduced.

The strict GLM run `1ef1df9269` used exact source `80a6892`, OpenCode, LiteLLM and
DeepInfra `zai-org/GLM-5.3-Flash`. Its independent oracle checked nested template
imports, one multi-parent component request, native tracing and guarded
disconnection, chassis swaps, VM primary MAC, contacts/journal/bookmark state,
search, exact CSV export and task completion. It used no website calls and left
no unresolved operations. It recovered from three tool errors and eight definite
rejected writes without human intervention. The final narrative had a confused
device-count aside; the independent oracle verified the actual relationships.
Earlier inventory, configuration, dashboard and bulk scenarios retain their own
source revisions and results in [agent evaluation](agent-evaluation.md).

The companion is qualified by assertions inside the real NetBox deployment; it
is outside the MCP runtime coverage percentage. Browser identity establishment
and OAuth consent use the operator-provisioned API identity instead; browser
presentation and arbitrary third-party plugins are outside stock operation
qualification. Custom interactive authentication pipelines need separate testing.
Database transactions cannot undo queue, filesystem or webhook side effects.
Uncertain outcomes require reconciliation, and graph recreation is not exact undo.
The feedback proof uses one operator GitHub account for both publication and reply.

Exact source/test hashes, coverage totals, distribution hashes and historical
records are in [validation.json](validation.json). Agent reports retain separate
source, harness and instruction hashes in
[agent-evaluation-results.json](agent-evaluation-results.json). Reproduce the
checks using [testing.md](testing.md). Private tokens, journals and transcripts
remain in ignored `.lab/` directories; they are not release artifacts.
