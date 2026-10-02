# Consuming-agent evaluation

The server under test is **Reliable Collaboration's unofficial NetBox read/write
MCP server** ([repository](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp)),
registered in test clients with the short alias `netbox`. NetBox's official MCP
server is not used in these evaluations. Historical report keys such as
`used_mcp` refer to this project; original reports are preserved unchanged.

Live model evaluations run locally, with explicit opt-in and a private provider
key file under the Git-ignored `.lab/` directory. GitHub CI runs deterministic
tests against its own disposable NetBox plus package checks; it does not run
agent clients or call a model provider. Provider credentials and raw local
transcripts are not uploaded. Committed evaluation records contain reviewed
results and hashes, not credentials.

The latest [receipt-reporting qualification](reporting-validation.md) adds eight
final-report checks and manual review, retaining all failed attempts and the
observed GLM/Codex variability.

Current acceptance includes the strict combined Community workflow and the real
GitHub feedback loop recorded below. Earlier sections preserve development runs
and their limits at the time; [validation](validation.md) records the current
deterministic qualification.

This is an opt-in, paid-provider test, separate from deterministic integration tests.
It runs OpenCode, Claude Code or Codex through a loopback LiteLLM proxy backed by DeepInfra, with the
real MCP server connected to the disposable Podman NetBox 4.7.2 lab.

Current runs receive the MCP tool catalog and a natural-language task; usage
instructions come from MCP initialization and built-in tools. No guide is injected
into the client prompt. Earlier recorded runs used the guide injection explicitly
identified by their source/harness revisions. Host shell/file/network/delegation tools are denied. No scenario supplies preselected NetBox IDs. The inventory task describes the
desired records and relationships; the Community qualification names specific
API paths and actions to require coverage of those features. That targeted
scenario does not test whether an agent chooses those workflows from an open-ended request. Credentials are never included in
the prompt. The provider receives synthetic lab inventory and tool results.

An independent REST reader checks final state. A correct-sounding final answer
alone cannot pass. Each phase starts a new client session against the same
persistent inventory and journal:

| Phase | Independent checks |
| --- | --- |
| Greenfield | Pre-existing inventory unchanged; site, 12U rack, two devices at correct positions, serial/description, connected interfaces/cable, first allocated IP assigned, VM/interface, no uncertain operations |
| Repeat | Same target state and zero additional mutation operations |
| Website fallback | Invalid and valid form submissions, one verified new site, diagnostics produced; final explanation reviewed separately |
| Conflicted undo | A fixture introduces a newer field edit; the agent previews undo, preserves the newer value and produces diagnostics |

The Community scenario also requires a structured final report. Its eight reporting
checks compare task identity, exact state counts (including historical rejections),
the meaning of `completed`, every completed receipt's HTTP status and effect
evidence, and the bookmark target against the journal and an independent read.
The journal summary must exactly quote the server's deterministic `summary_text`;
the model's separate inventory summary must be nonempty and is reviewed for
unsupported outcome claims. Only the client's final answer is
graded; tool output cannot substitute for it. Deterministic regressions exercise
all three client transcript formats and reject misleading counts, targets and
receipt meanings. The report format is part of the evaluation task; guidance on
how to interpret receipts comes from the MCP server.

Journal `failed` counts and the harness's `tool_errors` measure different things.
A rejected NetBox request can return a durable failed-operation receipt in a
normal MCP result. `tool_errors` counts MCP error responses. Neither counter
erases an earlier rejection after a successful correction.

This is a targeted acceptance exercise, not a statistical reliability benchmark.
The structured report checks do not grade every sentence of the model's explanation. Review
transcripts for unsupported claims, wasted calls and misunderstood limits. A
provider/client failure or timeout is a failed/incomplete evaluation, never a pass.
The runner stops after a failed greenfield phase; later phases cannot turn that
failure into a successful qualification. The simulated intervening edit uses a second direct request under the lab actor;
it tests later-write handling, not multi-user authorization.

## Reproduce

Install OpenCode 1.18.33 and LiteLLM 1.103.1 in an isolated environment. These were
the versions used for the recorded evaluation; they are test dependencies only.
See [OpenCode provider configuration](https://opencode.ai/docs/providers/) and
[LiteLLM's DeepInfra adapter](https://docs.litellm.ai/docs/providers/deepinfra).
Start and seed the lab following [testing](testing.md). Save the provider key in
a private file outside source control; do not put it in a command argument.

```sh
NETBOX_RW_AGENT_EVAL=1 .venv/bin/python scripts/agent_eval.py \
  --opencode /path/to/opencode \
  --litellm /path/to/isolated-venv/bin/litellm \
  --key-file /private/path/deepinfra.key \
  --model deepseek-ai/DeepSeek-V4-Flash
```

The runner starts/stops its own loopback proxy. Use `--port` to choose a free port.
`--timeout` bounds each phase (default four hours); the agent also has a 160-step
limit. Idle termination is disabled by default (`--idle-timeout 0`). Twelve consecutive
failed MCP calls stop a run with `consecutive_tool_errors`; use
`--max-consecutive-tool-errors` to adjust this or `0` to disable it. Valid calls
reset that error streak, so slow generation alone does not trigger this limit. Quiet client
output alone is not treated as a stall. A loopback observation gateway records
stream byte/chunk counts, reasoning/content/tool fragment counts, active request
ages, and completed MCP calls once a minute in `progress.json`/`progress.jsonl`.
It forwards the model response unchanged and retains no prompts or generated
content in these activity counters. Keepalives are distinguished from generation.
Slow progress can continue; repeated errors and unchanged inventory require
inspection. A nonzero idle timeout is optional and includes wire activity. The lab is intentionally preserved. Only the proxy receives the DeepInfra
credential. The client receives a separate ephemeral proxy credential, and its
local permissions deny filesystem and shell tools. This is client policy, not an
OS sandbox. Proxy logs are redacted while streaming, and text artifacts are
checked/redacted before the run exits. Keep all raw evidence private regardless.

Each run writes `.lab/agent-e2e/<run-id>/report.json`, before-inventory snapshots,
activity counters, per-phase prompts, JSONL
client events, a durable MCP journal and redacted proxy logs. Reports include
source hashes, tool counts/errors, truncations, duration and client-reported token
usage. Token totals are cumulative across turns and can include cached input;
OpenCode's zero cost field is not evidence that provider usage was free.

## Claude Code and Codex evaluation

The same runner supports native Claude Code and Codex clients. Select `--client
claude` or `--client codex` and supply `--client-bin /absolute/path/to/client` in
place of `--opencode`. Use `--mcp-app /absolute/path/netbox-readwrite-mcp.pyz` to
exercise a downloaded release instead of the source checkout. For example:

```sh
NETBOX_RW_AGENT_EVAL=1 .venv/bin/python scripts/agent_eval.py \
  --client claude --client-bin /absolute/path/to/claude \
  --litellm /path/to/isolated-venv/bin/litellm \
  --key-file /private/path/deepinfra.key \
  --mcp-app /absolute/path/netbox-readwrite-mcp.pyz \
  --scenario inventory-core
```

`inventory-core` checks creation and a second pass with no additional writes;
`community` checks the combined companion workflow. Both use the same independent
REST assertions across clients. The `feedback` scenario currently requires OpenCode.

Claude Code uses LiteLLM's Messages endpoint; Codex uses its Responses endpoint.
The observation gateway counts incremental output for both protocols without
retaining content in activity counters. Native clients load the test MCP only;
Claude Code uses a private configuration directory, while Codex ignores user
configuration and uses invocation-scoped settings, including explicit write approval
for the disposable lab connection to our unofficial read/write MCP server. `approval_policy="never"` alone rejects MCP
writes that would need approval; it does not preapprove them. Neither adapter changes normal
client settings. Shell tools are disabled, and the task restricts work to NetBox
MCP. These are client policies, not an OS isolation boundary. Native-client
transcripts are also checked for host tool execution.

Native clients do not expose OpenCode's tool-output truncation metadata, so the
report records that measurement as unavailable rather than claiming zero.
Their runs use the phase time limit, without OpenCode's 160-step cap.

## Findings and changes

The initial DeepSeek run successfully built and rechecked inventory, but returned
14 truncated tool outputs. It also narrated website submissions as ETag-protected
with undo support, which was incorrect. A test-harness argument-order error
prevented that preliminary run's conflict phase; it is not counted as a complete
four-phase pass.

The evaluation led to these changes:

- Compact default write schemas, excluding the large response model graph.
- Named-action schema lookup (`action="available-ips"`) so the model need not
  request a large full schema merely to inspect one allocation action.
- Workflow syntax/ownership instructions and preflight rejection of unsupported
  assignment targets before any tool can write.
- Explicit website guarantee limits in both tool descriptions and persisted
  receipts: no ETag protection, pre-write snapshot guarantee or automatic undo.

The intermediate DeepSeek run passed all four state-oracle phases. Its website
explanation correctly acknowledged the absent concurrency/undo guarantees.
It still requested one truncated full action schema; named-action lookup addresses
that observed case. Final-source results are recorded separately in
[agent-evaluation-results.json](agent-evaluation-results.json).

The original four-phase evaluation does not cover every NetBox model, all web views, malicious prompt
injection campaigns, SSO/MFA, arbitrary third-party plugins, real discovery from
network equipment, or autonomous GitHub issue submission by the LLM. The later
consuming-agent GitHub evaluation below qualifies that feedback workflow. A realistic
physical inventory also requires the person or a discovery source to supply what
is actually present; an agent must not invent hardware facts.

The preliminary GLM-5.3-Flash greenfield run exceeded its 900-second limit and
failed the serial/description check. It supplied malformed action paths and
misreported a resulting 404 as an unavailable allocation capability, then created
an address directly. Its repeat phase was skipped. The subsequent website trial
was stopped without grading, and conflict was not run; that run did not qualify the model.
This failure occurred on the intermediate source/instructions, not the final
DeepSeek-qualified source. The extended evaluations below supersede that timeout.

## Extended GLM delivery evaluation

The user requested hours-long GLM trials with progress inspection. A monitored
trial exposed silently ignored unknown NetBox filters selecting unrelated objects.
The MCP now rejects unknown filters; the Apache-2.0 companion exposes native
custom-field filters missing from OpenAPI. The oracle now compares all pre-existing
objects in the evaluated inventory domains before and after every phase.

A subsequent trial exposed ambiguous bulk action names. The tool schema now lists
exact actions, and structural validation completes before any step writes. The
bounded workflow interpreter also supports short-circuit conditional expressions
and identifies unsupported syntax explicitly. These development attempts remain
private evidence; an interrupted run is never counted as a passing qualification.

Monitored run `0a0ef2e4dc` passed all four phases: greenfield 304.38s, repeat
196.43s, website 342.67s, conflict 41.39s. GLM recovered from a workflow failure
after an allocation, inspected the receipts, assigned the first IP and deleted its
extra allocation. The independent oracle verified no extra IP remained and no
pre-existing inventory changed. Repeat made no mutations. Website and conflict
narration acknowledged the relevant limits. No tool output was truncated.

This was not an error-free run: five workflows returned `partial_or_blocked`, and
the repeat session made 17 invalid read calls while using underscores instead of
hyphens in resource paths. These observations led to accurate resource-path
diagnostics and preflight rejection of unsupported named workflow functions before
any earlier write. The interpreter's available functions are now explicit in the
agent guide. The final confirmation uses these changes without relaxing the oracle.

## GLM confirmation before the cold-cache correction

Run `3959a7a3c7` passed all four phases against unchanged source, harness and
agent instructions (hashes recorded in the results JSON):

| Phase | Seconds | Result |
| --- | ---: | --- |
| Greenfield | 509.92 | All inventory, relationship and preservation checks passed |
| Repeat | 68.43 | Same state; zero mutations |
| Website fallback | 41.37 | Invalid form correctly interpreted; valid site created once; diagnostic produced |
| Conflicted undo | 22.05 | Newer value preserved; preview and diagnostic produced |

No tool outputs were truncated. No human completed or corrected the target
inventory. The run recovered from invalid filters, unsupported workflow syntax,
key reuse and native validation failures. Its final journal retains three
definite failed attempts, 19 applied operations (including the conflict fixture),
and one completed invalid form exchange. There are no uncertain operations.

Manual narration review found one incorrect statement: the greenfield summary
claimed no failed operations remained. Failed attempts correctly remain in the
immutable audit history even after successful correction. The desired final
state passed independently; the model's history claim did not. Receipts and
state checks remain authoritative. Website and conflict explanations correctly
described their outcomes. This evidence qualifies the tested inventory workflows,
not flawless model narration or all-feature website parity.

Fresh-database CI after this run exposed a companion schema-generation failure
masked locally by NetBox's one-day OpenAPI cache. Its model-aware schema generator
attempted to read a queryset for the metadata APIView. Explicit view descriptions
and exclusion of the discovery-only root from OpenAPI correct that integration.
A unique-URL live test now forces cold schema generation and checks that both
native resources and the companion filter endpoint are present. The recorded
earlier GLM results remain state evidence; the cold-cache correction receives
separate regression and consuming-agent confirmation.

Cold-schema-corrected run `c212535640` passed the four state checks (412.06s,
101.64s, 71.57s and 43.79s), but requesting the complete task history caused one
OpenCode output truncation. The MCP task view now defaults to compact, paginated
receipts and whole-task state counts; full receipts remain available by operation
ID or an explicitly expanded page. Internal recovery retains its complete task
view. The next acceptance run also requires the agent to inspect task history
before reporting write completion, without a truncated task response.

## Final qualification on the corrected implementation

Run `34e446a10a` passed with unchanged source, harness and agent-guide hashes:

| Phase | Seconds | Result |
| --- | ---: | --- |
| Greenfield | 472.40 | Inventory, relationships and pre-existing final state correct; compact task history inspected without truncation |
| Repeat | 175.92 | Zero mutations; same target state |
| Website fallback | 144.31 | Invalid and valid submissions correctly distinguished; exactly one site verified; diagnostics produced |
| Conflicted undo | 37.71 | Newer value preserved; guarded preview and diagnostic produced |

All four phases had zero truncated tool outputs. The final journal has 23 applied
operations (including the conflict fixture), one completed invalid form exchange,
and one historical failed cable request. No operations are uncertain. GLM's
greenfield report correctly distinguished the rejection from unresolved work.

This was still a recovery exercise, not flawless execution. GLM temporarily
allocated an IP from a prefix in the wrong VRF, recognized the mismatch, deleted
its own stray IP and allocated from the intended prefix. The independent oracle
confirmed the requested state and unchanged pre-existing final inventory. That
does not establish absence of transient mistakes or reverse external webhook
effects. Its conflict prose also grouped original and intervening changelog IDs
together; authoritative receipts retain their precise attribution.

No human completed or corrected the inventory. The same implementation passed
425 deterministic tests, including 91 live cases and fresh-database CI. Detailed
counts, rejected attempts, previous runs and exact hashes remain in the results
JSON. The evidence supports this controlled greenfield handoff; universal GUI
parity, all-feature lifecycle coverage and a reliability rate remain unestablished.


## Configuration API qualification

Use the same runner with `--scenario configuration --model zai-org/GLM-5.3-Flash`
to run the API-only configuration task separately from the four inventory phases.
It discovers the companion schema, changes a harmless banner, exercises a stale
revision guard, restores the original dynamic overrides and deletes only its own
temporary revisions. It leaves one new active reset revision. An independent
oracle checks receipts, final overrides, preserved pre-existing revision data
(apart from the expected active-flag transition), task-summary inspection and
unchanged inventory. It also rejects any use of website tools.

The first run, `f22156d6e0`, passed the state oracle in 166.54 seconds but failed
manual narrative review. GLM sent JSON-encoded strings twice, then incorrectly
called the resulting 400 responses intermittent transport failures. It also had
an ETag preflight rejection. The action tool's body schema was unconstrained;
it now explicitly describes structured JSON objects/arrays/null and rejects
strings/scalars before dispatch. ETag instructions now require the quoted header
verbatim and refer to the target object, rather than always saying device.

The final run, `2a96b46bb2`, passed in **163.88 seconds** on the corrected source:
15 MCP calls, zero tool errors, zero truncated outputs and one intended 409
rejection. GLM initially created an empty revision, noticed its missing banner,
created the corrected revision and deleted both temporary revisions after reset.
Its final report disclosed that mistake and accurately distinguished five
completed exchanges from the expected rejection. No human supplied the missing
work or corrected the configuration. Exact source, harness and guide hashes,
monitoring counters and both runs are retained in the results JSON.

This qualifies the tested creation/reset/cleanup workflow. The native privileged
restore action, object-constrained permissions, static/commercial-setting
preservation and lost-response handling have deterministic live tests; this LLM
scenario does not qualify those paths. PostgreSQL and the native configuration
cache are separate stores, and configuration revisions have no native ObjectChange
history or automatic undo. It remains a targeted acceptance test, not universal
GUI parity or a reliability rate.

## Personal dashboard scenario

Run `--scenario dashboard --model zai-org/GLM-5.3-Flash` with the same runner
and credentials arrangement. The agent discovers the companion dashboard and
widget schemas, retains the original state, submits an intentionally invalid
note, adds and verifies a valid note, exercises a stale ETag, and restores the
original state (including uninitialized state). The independent oracle checks
receipts, exact final dashboard equality, inventory preservation, task-summary
inspection, and absence of website calls and uncertain operations. Native
ObjectChange history and automatic undo do not apply to personal dashboards.
The deterministic suite separately covers all five widgets, multiple users,
concurrent first use, token restrictions and response loss.

The first dashboard attempt (`33f3e2742b`) was stopped after repeated rejected
payloads, with no successful dashboard mutation. It exposed two discovery gaps:
compact schemas expanded POST but omitted PUT request definitions, and widget
configuration was an untyped dictionary. Both are corrected: mutation request
definitions are expanded and widget entries expose their class/title/color/config
structure. The guide now includes a concrete payload example. The preliminary
oracle accepted any HTTP 400 as the intended validation test; the revised oracle
requires the native required-content error and also checks note dimensions/color
and preservation of original widgets in successful write receipts. The preliminary
run is retained as failure evidence, not qualification.

Full CI then caught oversized device/interface responses when expanding all bulk
mutation schemas by default. Compact discovery now expands object mutations and
POST bulk alternatives; `get_schema(method="PATCH")` expands the complete bulk
update contract without unrelated methods and filters. The existing 30 KB client
budget is retained and tested for both default and focused responses.

The subsequent PUT run `261f4939fb` passed the state oracle in 905.17 seconds,
including the intended native content error and a stale ETag, and reset the
originally absent dashboard. It recovered an unknown-task error and an invalid
UUID, and had no output truncations. Its final narrative overstated fresh reads
after rejections; the trace, not that wording, is authoritative. This run preceded
the method-focused schema size correction.

Existing-dashboard run `8e995f1149` preserved and restored all nine native widgets
in 583.06 seconds and verified its writes/rejections with reads. It nevertheless
failed the stricter oracle: its negative request omitted the new layout entry,
so validation stopped before testing required note content. This prompted a
smaller API operation: PATCH adds/replaces only specified widget entries or
removes IDs, preserving all other widgets on the server. The agent scenario now
uses PATCH and explicitly requires the intended native content validation error.
Neither failed run is counted as final qualification.

Final-source PATCH run **`4b4e4e36c8`** passed in **868.20 seconds** on `5c13c56`.
It initially sent a malformed UUID/scalar widget, recognized the unrelated error,
corrected it and reached the required-content rejection. It then added its note,
verified the stale guard, and removed only its note while preserving all nine
native widgets. Trace review confirms GETs after both intended rejections and
cleanup; canonical before/after JSON matches exactly. The later GET after the
stale rejection also verifies the saved note. There were 13 MCP calls, no MCP tool
errors, no truncated outputs and no uncertain operations. The three rejected
HTTP operations include the extra malformed request, so this is recovery evidence,
not flawless execution. No human completed or corrected the task. The native
default dashboard was prepared before the run and removed only as fixture cleanup
after the independent oracle passed. Exact source/harness/guide hashes and earlier
attempts are retained in [the results](agent-evaluation-results.json).

## Native bulk workflow qualification

Run **`6a0d7babb0`**, source **`2dbc6a8`**, passed in **258.26 seconds**.
GLM discovered and used CSV import, guarded native rename, guarded bulk editing,
and VLAN range expansion. The independent oracle confirmed two renamed/planned
sites with the requested description, exactly three correctly named VLANs,
a stale-rename 409, and atomic rejection of a two-item range request whose second
item had an invalid status. Existing inventory remained unchanged.

The run made 21 MCP calls with zero tool errors, zero output truncations and no
unresolved operations. Its nine operations comprise five applied writes, two
completed previews and two expected rejections. Final verification reads and a
task summary are present. There was no immediate GET between stale rename
rejection and bulk editing; the agent's broad statement that the sites were
re-verified unchanged should not be read as proof of that particular read order.
No human completed or corrected the task. This qualifies the scenario, not every
native form combination or full website parity. Exact hashes are retained in
[the results](agent-evaluation-results.json).

## Consuming-agent GitHub feedback

GLM-5.3-Flash run `9afd103efa`, on source commit
`bbd6886be96b04d1de19f09e67e9a8c46cfc2626`, passed both feedback phases through
OpenCode, LiteLLM, DeepInfra, the inventory MCP and the separate feedback MCP.
Publication/replay/read took 42.14 seconds; reading and reporting the maintainer's
response took 16.61 seconds. There were five NetBox tool calls and four feedback
tool calls, no tool errors, no truncated outputs and no unrelated inventory changes.

The agent deliberately caused a native site-validation rejection, published a
structured qualification report, repeated the exact report key, and received the
same issue receipt. The harness posted a maintainer reply through the operator's
GitHub login. A fresh agent session read that reply, checked the NetBox receipt,
and included the independently generated verification code in its answer.
[Issue #3](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/3)
was closed after the independent oracle passed. Publication and maintainer actions
used the same operator GitHub account; this is a functional workflow test, not
qualification of separate GitHub account permissions.

The preceding run `c3c05bcd4a` failed: OpenCode isolated `XDG_CONFIG_HOME`, so the
feedback process could not find the host's GitHub configuration. Its outbox
correctly stayed uncertain and suppressed repeated publication; an operator marker
search found no issue. Explicit host-side `--gh-config-dir` fixed the connection.
Both reports and exact source hashes are retained in the machine-readable results.
The bridge publishes enum fields and minimal receipt metadata only. Reviewed
free-text reproduction remains an operator/connector workflow.

## Combined Community workflow

Run `98fea39956` on `63f5ea6` completed in 582.97 seconds with all original
final-state checks passing, no unrelated changes and no unresolved operations.
It made 51 MCP calls, with one tool error and five definite rejected writes,
and recovered to the requested inventory state. Review found that it created
interface templates separately instead of using the requested nested import.
This is retained as development evidence, not combined-scenario acceptance.
The follow-up oracle explicitly checks correlated nested-import history, one
multi-parent pattern request and use of native tracing.

Strict run **`1ef1df9269` on `80a6892` passed all 23 checks in 555.70 seconds**.
Its 56 MCP calls completed the nested import (one device type plus two correlated
interface-template changes), one multi-parent component request, successful
interface trace, guarded disconnect, atomic chassis swap, VM primary MAC, contacts,
journal, own bookmark, search and exact two-device CSV export. Pre-existing
inventory remained unchanged; there were no truncated outputs, unresolved
operations or website calls. No human completed or corrected its task.

Preservation checks compare pre-existing objects in 15 core inventory collections
(DCIM, IPAM and virtualization). Scenario-specific assertions and receipt review
cover the additional requested objects and actions. This is not a comparison of
every table in the NetBox database.

This was autonomous recovery, not flawless execution: three tool errors and
eight definite HTTP 400 rejections preceded corrected requests. The journal ended
with 21 applied, eight failed and three completed operations. Manual review
confirmed the successful trace request, not just a textual mention of tracing.
The final answer contained a confused site device-count aside; independent state
checks establish the actual two-device/one-VM relationships. This remains a
targeted acceptance proof rather than a statistical reliability guarantee.

## MCP-delivered guidance (0.4.0 release work)

Run `d08a04442d` on `6525bc6` passed all 23 strict Community checks in
**426.14 seconds**, with no guide injected into the OpenCode agent prompt. The
client received only the task and execution constraints; the MCP supplied usage
instructions through initialization and tools. GLM called `capabilities`,
`discover_models` and `get_guidance` itself. There were 54 MCP calls, three tool
errors, zero output truncations and no unresolved operations. The independent
oracle verified the requested relationships and unchanged pre-existing inventory
in its 15 core collections, plus scenario-specific assertions.

The journal retained 21 applied operations, three completed exchanges and six
definite failed requests, all corrected or superseded without human assistance.
Its final narration incorrectly called the first import rejection 422 in one
place; the receipt and its final accounting identify the 400 rejections. This
qualifies the autonomous workflow and built-in guidance, not flawless narration.
[Exact source/harness hashes and results](release-agent-evaluation.json) preserve
that revision. Subsequent compatibility-policy changes accept later stable NetBox
versions but do not extend this 4.7.2 qualification to those versions.

## Native client release qualification

The initial native-client runs used the **published 0.4.1 `.pyz`**, with SHA-256
`e4197911c41b1a5fd5d480b2931ba87d3819a7dc1e9461a2c357fe15189e651b`,
and the existing Podman NetBox 4.7.2 test instance. Their model is
`zai-org/GLM-5.3-Flash` through LiteLLM 1.103.1. This tests the clients' actual
MCP integration and tool loops; it does not qualify Anthropic or OpenAI models.
No NetBox agent guide is injected into either client's prompt.

[Machine-readable results](client-agent-evaluations.json) retain both successful
and unsuccessful runs, artifact hashes, independent assertions and transcript
review. Raw transcripts and credentials remain private.

The first Codex attempt (`903e768b1f`) was an evaluation-configuration failure:
`approval_policy="never"` rejected MCP writes that needed approval. It created
no inventory and **failed the state oracle despite a zero client exit code**.
The runner now explicitly approves the disposable lab connection to our unofficial read/write MCP server through an
invocation-scoped setting, without changing the user's normal client configuration.

Claude Code run `236807be64` passed inventory creation and a fresh-session repeat
with zero additional writes. Its 19 applied operations included recovery from
three rejected attempts inside bulk/workflow results. The agent distinguished
those historical failures from unresolved operations in its final report.
Independent checks confirmed physical/virtual relationships and preservation of
pre-existing inventory; transcript review found no host tool calls.

Codex Community run `346d9e493b` is **not qualified**. The original oracle counted
an attempted trace path in the transcript, even though that request returned 404.
The agent subsequently claimed completion without a successful trace. The raw
report is retained, but `qualified_passed` is false after review. The oracle now
requires successful HTTP 200 trace/search responses and evidence for the run's
own cable/search results. Regression tests reject failed requests, other cables
and other interface IDs. Rechecking the original OpenCode and Claude Code runs
with these stricter checks confirmed their successful traces and searches.

The 0.4.2 candidate adds the interface trace endpoint directly to the `query` tool
description and built-in guide, including the requirement to inspect the successful
response before disconnecting. This is a server-supplied clarification, not extra
instructions added to the consuming agent's prompt.

The first Codex 0.4.2 candidate attempt (`cbd476a625`) successfully traced its own
cable and passed the corrected trace assertion, but ended its turn before the
remaining chassis/VM/contact/export work. It **failed** overall: nine assertions
were false. A zero exit code and a successful individual feature check do not
qualify an incomplete scenario. No transport error was observed. Later attempts
retain the same prompt and independent acceptance criteria.

These runs show a distinction between MCP feature coverage and model reliability.
The same GLM model made malformed requests, sometimes recovered autonomously, and
in Codex also produced an unsupported completion claim and an early stop. A later
successful run demonstrates the tested workflow, not an error-free success rate.
Operation receipts and independent state checks remain the evidence for completion;
model narration alone is insufficient.

Codex retry `1e952eba10` traced its cable successfully but entered a loop appending
`bookmark/` repeatedly to an invalid route, with no inventory progress. The
operator stopped it after repeated failed reads; the run is **failed**, and its
nonzero client exit is preserved. This led to the consecutive-error limit above.
It also exposed weak error recovery guidance: read failures mentioned write
receipts and offered no nearby route. The next candidate identifies read errors
as non-mutations and supplies up to five matching GET paths from the already-loaded
API schema. It performs no extra network requests while generating suggestions,
does not redirect missing-object or permission failures, and retains write
recovery semantics. Unit tests and a real NetBox bookmark/missing-device check
exercise those boundaries.

Codex run `03b33417c8` satisfied the NetBox state assertions but **failed** the
requirement to use only our unofficial read/write MCP server: it called an inherited Context7 App. Ignoring the user's
configuration alone did not disable Codex Apps. The runner now explicitly disables
Apps, plugins, hooks and host skill discovery for this disposable evaluation.
A local startup probe captured nine tool definitions (23,102 serialized bytes),
with no Apps, before any paid model request. Existing user settings are unchanged.

The isolated retry `dad0ddead0` used no outside tools and completed the final
inventory, but **failed** the required nested-import check. After a rejected CSV
import, it created interface templates separately instead of using the supported
nested JSON/YAML import. The compact `get_schema` response now carries import
instructions directly: inspect the model-specific GET metadata, use its related
keys, and serialize nested lists as JSON or YAML. The acceptance criterion remains
unchanged; matching final inventory alone does not prove the requested operation.

Codex run `2d208b74c6`, using the 0.4.2 candidate built from `3366fdf`, passed all
24 checks in 388.27 seconds. It imported the device type and both templates in
one JSON operation, successfully traced before disconnecting, completed the
remaining maintenance work, and preserved the checked existing inventory. It
used only Reliable Collaboration's unofficial NetBox read/write MCP server. Historical rejected requests and a no-change workflow
remain in the journal; no unresolved operations remained. This is a targeted
successful acceptance after the retained failures, not a claim that GLM always
completes correctly.

Claude Code run `a5badc9997` passed the same 24 checks on the same candidate in
249.61 seconds. Its journal retained five rejected operations; the agent
recovered and completed the workflow without outside tools or unresolved writes.

OpenCode run `1a4272a45c` passed all 24 checks in 357.65 seconds on the same
candidate. It recovered from six rejected write operations and left no unresolved
operations. No external tools or injected guide were used.

| Client | Version | 0.4.2 candidate Community result | Run |
| --- | --- | --- | --- |
| Claude Code | 2.1.287 | 24/24 passed; 249.61 seconds | `a5badc9997` |
| Codex | 0.159.2 | 24/24 passed; 388.27 seconds | `2d208b74c6` |
| OpenCode | 1.18.33 | 24/24 passed; 357.65 seconds | `1a4272a45c` |

All three used Reliable Collaboration's unofficial NetBox read/write MCP server,
NetBox Community 4.7.2, and GLM-5.3-Flash through a local LiteLLM proxy. These are
local model evaluations, separate from GitHub CI. The candidate application SHA-256
is `ec76c6ce1d3b1c3df62dccc40c4aa479349a100a12ab6acefa74a2ec7ae3613d`.


The CI-built [v0.4.2 application](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/releases/tag/v0.4.2)
was subsequently downloaded and all 22 archive members compared with the tested
candidate; their contents match. The published application SHA-256 is
`ce9fd21a67ccf1a2e4e155b2c8c03a25f6b064d181d34b841a48a877097eee15`.
The model runs used the local candidate, with published runtime/guidance equivalence
verified separately. [Release evidence](release-validation-0.4.2.json) records the
CI and public-download checks.

## Version 0.4.3 confirmation

The final candidate from `d1758af` includes the review fixes and clearer built-in
name-to-ID and relationship verification guidance. Local GLM-5.3-Flash runs used
the standalone application, the companion and real NetBox 4.7.2:

| Client | Run | Seconds | Result |
| --- | --- | ---: | --- |
| Claude Code 2.1.287 | `0fe913dfb3` | 301.73 | All 24 checks passed |
| Codex 0.159.2 | `f7262ba4df` | 506.47 | All 24 checks passed |
| OpenCode 1.18.33 | `9ccd9a9280` | 440.94 | 23 runner checks plus independent no-host-tools review passed |

No external guide was injected. Existing inventory was preserved within the
oracle's scope and no unresolved operations remained. OpenCode reported zero
output truncations; native-client truncation remains unmeasured.

The initial Codex attempt failed: it reversed the requested device ordering and
bookmarked a device instead of the site. A separate oracle defect failed to
recognize its successful `get_objects` search; the oracle now accepts verified
search results from either read tool, with regressions for all three clients.
The chassis and bookmark requirements were not relaxed. The failed attempt and
initial Claude success remain in the [complete record](client-agent-evaluations-0.4.3.json).

Final runs had 5, 16 and 2 top-level tool errors respectively. These are targeted
acceptance successes with autonomous recovery, not an error-free reliability
benchmark. Codex's final narration also mislabeled completed exchanges as
read-side with no mutation; the bookmark POST was verified independently.
Receipts and actual state remain authoritative. Paid model tests ran locally
only; CI continued to run deterministic qualification without provider keys.
