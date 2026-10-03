# Receipt reporting qualification

Reliable Collaboration's unofficial NetBox read/write MCP server now supplies
the journal accounting that agents previously had to reconstruct. `get_task`
returns a deterministic `summary_text`, whole-task state and evidence counts,
and explanations in `outcome_details`. Agents can quote the accounting and
describe independently verified inventory outcomes separately.

This work is part of PR #2. It is not included in the previously published
v0.4.3 assets. Journal states and persisted receipts retain their existing
meaning; explanations are derived when a tool response is produced.

## Deterministic verification

[Full CI on `5d4f15f`](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/37049632366)
passed **662 tests plus six subtests**: **428 unit tests** and **234 real-NetBox
integration tests**, with **92.29% MCP runtime coverage**, in **31m52.22s** for
the test step. Python 3.11–3.14, package builds, standalone checks and companion
bundle loading on an unmodified upstream NetBox image passed. Coverage excludes
the companion. Local unit testing passed 428 tests in 21.35 seconds; local
package checks and focused live receipt/path/schema checks also passed.

## Local agent qualification

All three clients used the same standalone candidate built from `5d4f15f`, GLM
`zai-org/GLM-5.3-Flash` through LiteLLM/DeepInfra, and the owned NetBox 4.7.2 lab.
The [reviewed evidence](reporting-agent-evaluations.json) records artifact/source/
harness hashes, original verdicts, final answers and manual review for all
**22 development evaluations**. Raw transcripts and journals remain private.

| Client | Qualified run | Time | Automated checks | Manual outcome review |
| --- | --- | --- | --- | --- |
| Claude Code 2.1.287 | `5a6e037ecb` | 7m08.07s | 32 passed | Passed |
| OpenCode 1.18.33 | `b3c5d00fa0` | 8m28.10s | 31 passed | Passed, including outside-tool inspection |
| Codex 0.159.2 | `c366b709a8` | 10m54.99s | 32 passed | Passed |

There were **nine runs on this final artifact**: one Claude Code pass, one
OpenCode pass, and **six failed Codex attempts before the seventh passed**.
The failed Codex attempts included inaccurate receipt lists/prohibited tool calls,
two empty terminal responses, an omitted native trace, malformed JSON, and an
object where a prose summary string was required. No failed verdict was erased,
no output was repaired, and no acceptance assertion was relaxed. The final
artifact, task prompt and oracle were unchanged across these nine runs.

The qualifying runs correctly reported HTTP-exchange semantics and bookmark
creation, retained historical failures, and met all original workflow checks.
They demonstrate achievable task completion and reporting, not dependable
unattended execution with this model/client combination.

Provider-key scans found no matches in tracked files, the candidate archive,
reviewed evidence or the latest completed CI log. Repository Actions secrets
were zero at verification. No new assets were published for this PR work.

## Findings and disposition

| Finding | Change and verification |
| --- | --- |
| A model described `completed` as read-only/no mutation, despite a successful bookmark creation | Responses now explicitly distinguish a finished HTTP exchange from mutation evidence. An HTTP 201 receipt is identified as server-reported creation. Live tests create bookmarks, subscriptions and notifications without native changelog records and verify the objects through independent reads. |
| Accurate structured fields could accompany inaccurate narrative accounting | `get_task.summary_text` provides deterministic counts and definitions. Acceptance requires an exact quotation in `journal_summary`, keeps inventory prose separate, and includes manual review of outcome claims. One earlier run passed all structured checks but failed manual review; it remains unqualified. |
| Recovered requests were easy to conflate with an error-free task | Historical failed operations remain in the counts. The summary distinguishes journal failures from MCP errors rejected before journaling. A successful correction does not erase an earlier attempt. |
| The first implementation of explanations overwrote the legacy `outcome` string | The new field is `outcome_details`. A regression checks direct legacy updates, operation reads and full task summaries, preserving the original string and stored receipt. |
| Compact summaries reported zero native changes for legacy operations with a `native_id` | Evidence counts now support both the legacy single ID and the general-operation ID list. The regression reproduced zero before the fix and verifies one afterward. |
| Valid relative paths without trailing slashes caused misleading validation errors and a model loop | A missing trailing slash is canonicalized before reads, writes and operation-key fingerprints. A regression verifies a single write across replay with both spellings. URL, prefix, query-string and traversal restrictions remain enforced; a real NetBox read verifies the accepted spelling. |
| Double-escaped ETags and guessed schema paths caused avoidable confusion | Diagnostics identify literal backslashes without rewriting the ETag or weakening stale-state protection. Missing schema routes can suggest discovered alternatives; the live route test recovers the bookmark endpoint without substituting a different missing object. |
| Models confused literal bracket names with native range expansion | Model-specific pattern schema responses and built-in guidance now explain one entry per parent, full ranges, literal brackets, and exact count/name readback. Failed runs remain failed; the native API continues to honor the supplied names, and the acceptance criteria are unchanged. |
| A zero client exit code could conceal an unfinished task or empty report | State and report checks still fail incomplete runs. The local Responses observer records terminal output types and text length without retaining generated text, tool arguments, response IDs or credentials. A later failed run captured a terminal proxy response with no text or function call and no transport error, narrowing the observation to that boundary. The underlying provider/proxy cause remains unestablished; this is diagnostic evidence, not a fix for early stops. |

## What the acceptance checks establish

The Community scenario verifies physical and virtual inventory, nested interface
templates, multi-parent components, cable tracing and disconnection, chassis
membership, primary MAC assignment, contacts, journal entries, a site bookmark,
search and exact CSV export. Existing inventory must remain unchanged within the
oracle's scope, with no unresolved operations and no website tool calls.

Eight reporting checks cover the final report's presence, task identity, exact
state counts, `completed` semantics, exact completed-receipt claims, bookmark
readback, a nonempty inventory summary, and exact quotation of the server's
journal summary. Only final client text is graded, not tool output or interim
reasoning. Deterministic regressions cover all three client transcript formats
and misleading field values, including boolean IDs/counts, wrong targets and
duplicate/missing receipts.

Manual review is an additional qualification step. It caught a narrative that
incorrectly ruled out read-only successes and overstated historical failures
despite passing structured checks. Earlier reports, their actual verdicts, and
the resulting changes are retained in the evidence record rather than relabeled
as successes after an oracle or prompt change.

The evaluation asks for a report format and explicit API-only behavior. Usage
guidance comes from MCP initialization and built-in tools; no separate guide is
injected. Model tests run locally through LiteLLM and DeepInfra, never in CI.
The deterministic suite uses synthetic protocol fixtures and real NetBox 4.7.2.

Repeated GLM/Codex attempts showed substantial variability: correct database state
could accompany an empty answer, malformed JSON, wrong receipt entries or an
omitted workflow. A later passing retry does not resolve those model/provider
behaviors. The new checks detect them and preserve their failed verdicts.

These are targeted task and reporting qualifications, not a model reliability
rate or a guarantee about arbitrary prose. Rejected calls and provider/client
variability remain possible. Native Anthropic/OpenAI models, later NetBox
versions and arbitrary third-party plugins are not qualified by these GLM runs.
