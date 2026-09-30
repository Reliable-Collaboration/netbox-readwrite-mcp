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
| Greenfield | Site, 12U rack, two devices at correct positions, serial/description, connected interfaces/cable, first allocated IP assigned, VM/interface, no uncertain operations |
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
`--timeout` bounds each phase (default 900 seconds); the agent also has an 80-step
limit. The runner now also stops a client that emits no event for `--idle-timeout`
seconds (default 300); this watchdog was added after the initial model runs. The lab is intentionally preserved. Only the proxy receives the DeepInfra
credential. The client receives a separate ephemeral proxy credential, and its
local permissions deny filesystem and shell tools. This is client policy, not an
OS sandbox. Proxy logs are redacted while streaming, and text artifacts are
checked/redacted before the run exits. Keep all raw evidence private regardless.

Each run writes `.lab/agent-e2e/<run-id>/report.json`, per-phase prompts, JSONL
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
was stopped without grading, and conflict was not run; this model is unqualified.
This failure occurred on the intermediate source/instructions, not the final
DeepSeek-qualified source. A fresh GLM run would be needed to qualify it after
these changes.
