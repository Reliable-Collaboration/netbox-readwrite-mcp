# Validation record

Version **0.3.0**, validated locally on **2026-09-30**, against **NetBox 4.7.2 only**.
This is observed test evidence, not a production certification or universal GUI coverage claim.
Exact source/test hashes and numeric coverage are in [validation.json](validation.json).

| Check | Observed result |
| --- | --- |
| Offline suite | 334 passed on Python 3.14.4 |
| Offline statement/branch coverage | 86.83% (minimum 85%) |
| Combined offline + real NetBox suite | 425 passed |
| Live integration cases in that run | 91, using unique fixtures in the disposable lab |
| Combined statement/branch coverage | 92.68% |
| API discovery sweep | 147 endpoints; 135 GET successes, with expected permission denials/action-only responses separately classified |
| Protocol interoperability | Official MCP SDK 1.30.0 over stdio and authenticated Streamable HTTP; concurrent HTTP clients tested |
| Packaging | MCP and companion sdist/wheel built; isolated MCP wheel install and CLI launch checked |
| Lint and format | Ruff checks passed |
| GitHub issue workflow | Synthetic issue submitted, read, answered and closed: [issue #1](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/1) |

The lab uses digest-pinned images from scripts/images.lock.json, a real NetBox
web process, PostgreSQL, Valkey and a worker. The original 390-case qualification
used a newly recreated database. The 425-case follow-up reused that disposable
lab with uniquely named fixtures, alongside the consuming-agent evaluation. The inventory identity is not a superuser;
a separate restricted actor exercises permission boundaries. No hosted AI
provider, Branching plugin or commercial integration participates in these tests.

The companion's API discovery and cold OpenAPI generation are included in the
425-case run. Fresh CI exposed an earlier schema-generation defect hidden by
NetBox's one-day schema cache; the corrected plugin now has a unique-URL cold
schema regression. The plugin has no inventory mutation endpoint. Coverage
percentages measure the MCP package, not plugin Python execution inside the
NetBox container or the evaluation harness.

The suite exercises greenfield dependency discovery/creation, physical and virtual
inventory, cables, IP/VLAN/prefix/ASN allocation, custom fields and tags, native
bulk writes, resumable workflows, GraphQL, configuration rendering, script upload
and job completion, website forms, conditional-write races, response loss,
conflicts, compensation, corruption, backups and durable issue diagnostics.
Workflow replay retains original read decisions. Malformed uploads are rejected
before dispatch. General observers use consistent SQLite snapshots.

Prior review runs are retained privately under .lab/4.7.2-review-evidence/;
original transcripts, JUnit, coverage and journals are under .lab/4.7.2/.
Follow-up JUnit/coverage and private agent transcripts are under .lab/agent-e2e/. These paths
contain synthetic credentials/evidence and are excluded from source distributions.
The GitHub workflow is configured to reproduce offline tests on Python 3.11–3.14
and real NetBox qualification on Python 3.12. Its remote result is separate from
this local record. Code commit `5a953b6` passed both
[PR](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36781045301)
and [push](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36781039517)
workflows, including 425 tests on a freshly initialized NetBox database.

## Qualification limits

- The 147-endpoint GET/OPTIONS sweep establishes discovery and reachability,
  not successful CRUD semantics for every NetBox model or every website view.
- General REST and website transports expose native authorized actions. Detailed
  lifecycle tests cover representative resources/workflows, not universal GUI parity.
- Guarded field compensation is tested. Exact original-ID undelete and dependency
  graph restoration require the proposed recovery extension and are not implemented.
- Branching and commercial products are outside scope. Installed open-source
  plugins require their own qualification; no arbitrary plugin certification is implied.
- SSO/MFA website authentication, remote TLS proxy configuration, infrastructure
  disaster recovery and distributed/large-estate operation are unqualified.
- Deterministic tool tests do not establish an LLM's judgment or narration quality.

See [testing](testing.md) to reproduce the run and [feature matrix](feature-matrix.md)
for the implemented interfaces and exclusions.

## Consuming-agent evidence

Real OpenCode → LiteLLM → DeepInfra → MCP → NetBox tasks and independent
state checks are recorded in [agent evaluation](agent-evaluation.md). This is
separate from pytest counts and code coverage. An earlier DeepSeek run passed
greenfield inventory, repeat-without-mutations, website validation, and conflicted
undo with zero truncated tool outputs. It recovered from one invalid read filter
during the repeat phase. Supplemental checks verified all requested dependency
relationships.

Final-source GLM run `34e446a10a` passed all four phases with expanded relationship,
pre-existing-final-state and untruncated-task-history checks. There were zero
truncated outputs and no human completion of the inventory. GLM corrected a
mis-targeted allocation and correctly reported one historical rejection separately
from unresolved work. Earlier runs exposed oversized task history and inaccurate
history narration, both retained in the evaluation record. This demonstrates
recovery and correct final state, not absence of transient mistakes; precise
evidence attribution still comes from the structured receipts.
