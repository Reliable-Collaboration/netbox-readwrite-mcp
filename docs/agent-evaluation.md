# Consuming-agent evaluation

This is an opt-in, paid-provider test, separate from deterministic integration tests.
It runs OpenCode through a loopback LiteLLM proxy backed by DeepInfra, with the
real MCP server connected to the disposable Podman NetBox 4.7.2 lab.

The agent receives the normal agent guide, the MCP tool catalog and a natural
language task. Host shell/file/network/delegation tools are denied. It gets no
preselected NetBox IDs or recipe of tool calls. Credentials are never included in
the prompt. The provider receives synthetic lab inventory and tool results.

An independent REST reader checks final state. A correct-sounding final answer
alone cannot pass. Each phase starts a new OpenCode session against the same
persistent inventory and journal:

| Phase | Independent checks |
| --- | --- |
| Greenfield | Pre-existing inventory unchanged; site, 12U rack, two devices at correct positions, serial/description, connected interfaces/cable, first allocated IP assigned, VM/interface, no uncertain operations |
| Repeat | Same target state and zero additional mutation operations |
| Website fallback | Invalid and valid form submissions, one verified new site, diagnostics produced; final explanation reviewed separately |
| Conflicted undo | A fixture introduces a newer field edit; the agent previews undo, preserves the newer value and produces diagnostics |

This is a targeted acceptance exercise, not a statistical reliability benchmark.
The state oracle does not grade every sentence of the model's explanation. Review
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
limit. Idle termination is disabled by default (`--idle-timeout 0`). Quiet client
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

This evaluation does not cover every NetBox model, all web views, malicious prompt
injection campaigns, SSO/MFA, arbitrary third-party plugins, real discovery from
network equipment, or autonomous GitHub issue submission by the LLM. The existing
synthetic GitHub round trip tests the feedback plumbing separately. A realistic
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
