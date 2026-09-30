# Validation record

Version **0.3.0**, validated locally on **2026-09-30**, against **NetBox 4.7.2 only**.
This is observed test evidence, not a production certification or universal GUI coverage claim.
Exact source/test hashes and numeric coverage are in [validation.json](validation.json).

| Check | Observed result |
| --- | --- |
| Offline suite | 311 passed on Python 3.14.4 |
| Offline statement/branch coverage | 86.86% (minimum 85%) |
| Combined offline + real NetBox suite | 390 passed, plus 6 subtests |
| Live integration cases in that run | 79, using a newly recreated disposable database |
| Combined statement/branch coverage | 92.72% |
| API discovery sweep | 146 endpoints; 135 GET successes, with expected permission denials/action-only responses separately classified |
| Protocol interoperability | Official MCP SDK 1.30.0 over stdio and authenticated Streamable HTTP; concurrent HTTP clients tested |
| Packaging | sdist/wheel built; isolated wheel import and CLI launch checked |
| Lint and format | Ruff checks passed |
| GitHub issue workflow | Synthetic issue submitted, read, answered and closed: [issue #1](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/issues/1) |

The lab uses digest-pinned images from scripts/images.lock.json, a real NetBox
web process, PostgreSQL, Valkey and a worker. It was reset to a fresh database
for the final qualification run. The inventory identity is not a superuser;
a separate restricted actor exercises permission boundaries. No hosted AI
provider, Branching plugin or commercial integration participates in these tests.

The suite exercises greenfield dependency discovery/creation, physical and virtual
inventory, cables, IP/VLAN/prefix/ASN allocation, custom fields and tags, native
bulk writes, resumable workflows, GraphQL, configuration rendering, script upload
and job completion, website forms, conditional-write races, response loss,
conflicts, compensation, corruption, backups and durable issue diagnostics.
Workflow replay retains original read decisions. Malformed uploads are rejected
before dispatch. General observers use consistent SQLite snapshots.

Prior review runs are retained privately under .lab/4.7.2-review-evidence/;
final transcripts, JUnit, coverage and journals are under .lab/4.7.2/. These paths
contain synthetic credentials/evidence and are excluded from source distributions.
The GitHub workflow is configured to reproduce offline tests on Python 3.11–3.14
and real NetBox qualification on Python 3.12. Its remote result is separate from
this local record.

## Qualification limits

- The 146-endpoint GET/OPTIONS sweep establishes discovery and reachability,
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
