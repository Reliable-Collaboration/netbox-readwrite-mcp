# Validation record

## Release 0.4.3: review fixes and renewed agent acceptance

[Release v0.4.3](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.3)
was built and published by [the gated CI workflow](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/37011423929)
from `0aa3b72`. The full test step passed **634 tests plus six subtests**:
**400 unit tests** and **234 real-NetBox integration tests**, with **92.23% MCP
runtime coverage**, in **34 minutes 15 seconds**. The Python 3.11–3.14 matrix,
standalone checks and companion bundle loading on an unmodified upstream NetBox
image also passed. The runtime coverage percentage excludes the companion.

Local GLM-5.3-Flash acceptance against the standalone candidate passed in Claude
Code, Codex and OpenCode. All required Community outcomes and outside-tool checks
passed; existing inventory was preserved within the oracle's scope and no
unresolved operations remained. The [agent record](client-agent-evaluations-0.4.3.json)
retains the initial failed Codex attempt, corrected search-oracle behavior,
autonomous recovery and narration limits. These are targeted acceptance checks,
not a model reliability rate. Guidance came from our MCP server, without a
separately injected guide. Model tests ran locally only, never in CI.

All nine public assets were downloaded without authentication and their checksums
verified. Application members match the locally tested candidate and wheel Python
modules match the release revision. Private setup and live `doctor` passed. The
provider key was absent from reachable Git objects, tracked files, unpacked public
assets and completed CI logs; the repository had no Actions secrets. Exact
measurements and boundaries are in [the release record](release-validation-0.4.3.json).

## Release 0.4.2: three-client qualification and clearer recovery

[Release v0.4.2](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.2)
was built and published by [the gated CI workflow](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36936421631)
from `3366fdf`. It passed **619 tests plus six subtests**: **387 unit tests** and
**232 real-NetBox integration tests**, with **91.99% MCP runtime coverage**.
The Python 3.11–3.14 matrix, standalone application checks and companion bundle
loading on the unmodified upstream NetBox image also passed.

Local GLM-5.3-Flash evaluations passed all **24 Community checks** in each of
Claude Code 2.1.287, Codex 0.159.2 and OpenCode 1.18.33. All used **Reliable
Collaboration's unofficial NetBox read/write MCP server**, its companion and the
NetBox 4.7.2 lab. No external guide was injected and no outside tools were used.
These targeted successes follow retained failed attempts; they do not establish
a model success rate. See the [client evaluation record](agent-evaluation.md).

All nine published assets were downloaded without authentication and their
checksums verified. Every application archive member matches the locally tested
candidate; the wheels' Python modules match the release revision. The downloaded
application passed private setup and live `doctor` checks. Archive metadata gives
the CI application a different SHA-256 from the local candidate; the code and
built-in guidance are identical.

Live agent/model tests run locally only. CI runs deterministic tests and packaging,
with no model-provider credentials. The provider key was absent from reachable
Git objects, tracked files, unpacked release assets and the completed release log.
Exact hashes, test counts and boundaries are in
[the 0.4.2 qualification record](release-validation-0.4.2.json). Previous release
and parity records remain below.

## Release installation and built-in guidance (0.4.1)

The [v0.4.1 release](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.1)
is built and published by [the gated release workflow](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36913025839)
on exact source `42b714a`. It distributes this project's MCP application and
companion plugin, not NetBox. The standalone application, wheels, checksums and
plugin-only container bundle require no source checkout or local build.

The release qualification passed **596 tests plus six subtests** (365 unit and
231 real-NetBox integration tests), **91.93% MCP runtime coverage**, the Python 3.11–3.14 matrix, standalone MCP
initialization/guidance checks, and loading the companion bundle on an unmodified
upstream NetBox image. The container check verifies automatic enablement and route
resolution; the full lifecycle suite uses the pinned development lab. Kubernetes
and Helm instructions are deployment recipes, not a separately qualified operator.

GLM run `d08a04442d` passed all **23 strict Community checks in 426.14 seconds**,
using MCP-delivered guidance with no guide injected into its client prompt. It
called `capabilities` and `get_guidance` itself. Its 54 tool calls included three
tool errors and six definite rejected writes, corrected without human assistance;
there were no output truncations or unresolved operations. Existing inventory
preservation is scoped to the oracle's 15 core collections and additional scenario
checks. Exact source/harness hashes and the narrative-status caveat are retained in
[the agent report](release-agent-evaluation.json).

The runtime and companion now accept stable **NetBox 4.7.x and later**; **4.7.2 is
the integration-tested release**. `doctor` and discovery distinguish the connected
version from tested versions. Later-version acceptance is not additional live
qualification. Release details and JUnit evidence are in
[release-validation.json](release-validation.json). Earlier parity evidence follows.

All nine public assets were downloaded without authentication and their checksums
verified. The 19 MCP and 22 companion Python modules in the published wheels
match the release tag. The downloaded standalone application passed private
configuration and live `doctor` checks.

**Stock NetBox Community 4.7.2 operation parity is implemented and qualified.**
The parity baseline below was qualified as version 0.3.0 on 2026-10-01. It supports a
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
