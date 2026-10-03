# Reproducing validation

Use Python 3.11+ and install `.[test,dev]`. Runtime uses the standard library;
tests use pytest, Hypothesis and the official MCP SDK.

```sh
ruff check src tests scripts companion/netbox_agent_api
ruff format --check src tests scripts companion/netbox_agent_api
pytest tests/unit
```

The offline suite exercises journal invariants, generated edit sequences,
concurrency, HTTP boundaries, both MCP transports, and the bounded workflow
interpreter. It is separate from real NetBox qualification.

## Real NetBox 4.7.2

Prerequisites: rootless Podman, free loopback port 18872, approximately 4 GiB RAM
and 8 GiB disk plus room for retained test evidence. Images are pinned in
scripts/images.lock.json. The lab never reuses an existing home-lab deployment.

```sh
python scripts/lab.py up
python scripts/lab.py ready
python scripts/lab.py bootstrap
python scripts/seed.py
NETBOX_RW_LIVE=1 pytest tests/unit tests/integration --cov=netbox_readwrite_mcp --cov-fail-under=85 --junitxml=.lab/4.7.2/results.xml
python scripts/lab.py stop
```

Only NETBOX_RW_TEST_VERSION=4.7.2 is accepted; omitting it selects the same version.
Tests require explicit opt-in and verify the exact lab URL/version before writes.
The broad test identity is not a superuser. The separate restricted identity
checks native denials and the original guarded device contract. Script storage
is shared between web and worker containers through a dedicated lab volume.

Live tests cover greenfield dependency creation; hardware, cables, IP/VLAN and
virtual inventory; filtered discovery; schemas; GraphQL; CRUD across resource
types; native and resumable bulk; custom fields and tags; website CSRF/form
validation; scripts/uploads/jobs; rendering; allocations; compensation and ABA;
response loss; crash boundaries; native denials; journal corruption and backup.
The original device suite retains its transport-loss, hard-exit and race tests.

GET/OPTIONS sweeps produce .lab/4.7.2/resource-coverage.json. They establish route
reachability/metadata, not successful CRUD semantics for every NetBox model.
Registered GUI/API inventory is generated separately with scripts/inventory_surface.py.

Evidence, tokens and transcripts remain in ignored .lab/4.7.2/. Do not publish
this directory. CI publishes synthetic JUnit reports only. The validation record
states what was actually run; passing representative tests is not universal GUI
or plugin certification.

## Cleanup

Stop preserves data and evidence. Remove only these exact disposable resources
when evidence is no longer needed:

```sh
podman rm nbrw-audit-4-7-2-worker nbrw-audit-4-7-2-netbox nbrw-audit-4-7-2-valkey nbrw-audit-4-7-2-postgres
podman volume rm nbrw-audit-4-7-2-db nbrw-audit-4-7-2-scripts
podman network rm nbrw-audit-4-7-2
```

## Real consuming-agent evaluation

The optional [Claude Code, Codex and OpenCode evaluation](agent-evaluation.md)
uses LiteLLM/DeepInfra for natural-language tasks through Reliable Collaboration's
unofficial NetBox read/write MCP server and independently verifies NetBox state.
It incurs provider usage, requires `NETBOX_RW_AGENT_EVAL=1`, and runs locally only.
GitHub CI never runs agent clients or calls model providers.

The lab includes the companion filter-metadata plugin. Its integration tests run
inside real NetBox through HTTP and check native permissions and dynamic filters.
The pytest percentage measures MCP package coverage; it does not measure Python
line coverage inside the NetBox container.
The companion schema test uses a unique schema URL to force cold OpenAPI
generation despite NetBox's one-day response cache.

## Stock operation audit and combined agent acceptance

Run `python scripts/parity_audit.py` to check the pinned website route map; use
`--write docs/netbox-4.7-parity.json` after deliberately updating its mappings.
The offline test rejects unknown routes and missing mapped native CRUD verbs.
This audit is not counted as successful lifecycle execution.

The live suite includes all native component pattern forms, nested imports,
constrained permissions, bulk deltas/deletion/disconnection, source worker sync,
account state, queue administration, real signed webhook delivery and binary
file exports. Device/VM rendering requires the native `render_config` permission;
the lab grants it explicitly without making the inventory actor a superuser.

Use `scripts/agent_eval.py --scenario community` with the documented OpenCode,
LiteLLM and private-key arguments for combined physical/virtual inventory,
nested templates, multi-parent creation, topology, chassis swaps, self-service
state and exports. The oracle verifies both final state and required operation
usage. `--scenario feedback` separately qualifies GitHub publication, duplicate
prevention and reading a maintainer reply. Do not run mutating integration tests
against the same lab during an agent evaluation.

## Deterministic test timing

The entire `tests/unit` and `tests/integration` collection uses no LLMs. Tests of
client/proxy adapters use synthetic transcripts and local protocol fixtures, not
paid model calls. Integration tests use real NetBox, PostgreSQL, Redis-compatible
queues and a worker; deterministic does not mean in-memory or instantaneous.

On 2026-10-02, Python 3.14.4 against the already-running, persistent local NetBox
4.7.2 lab passed 634 tests plus six subtests with 92.23% MCP runtime coverage:

| Work | Measured time |
| --- | ---: |
| 400 unit tests, summed JUnit durations | 21.98 seconds |
| 234 integration tests, summed JUnit durations | 55 minutes 41.08 seconds |
| Full pytest process, wall time | 56 minutes 5.54 seconds |
| Lint, two package builds, assets and upstream companion check | 12.68 seconds |
| Same full test suite in release CI | 34 minutes 15.45 seconds |

These are individual measurements, not a benchmark distribution. Local timing
excludes lab startup/downloads and uses a populated, persistent lab on a shared
workstation; CI uses a fresh lab. The slowest local test body was the complete
physical/virtual inventory lifecycle at 90.03 seconds. Multiple recovery tests
took 30–43 seconds. A later read-only probe retrieved 7,098 native history rows
in a median 1.17 seconds; outcome verification repeatedly reads native history.

A small fixture improvement creates both fresh test users in one Django process
instead of starting Django twice. Median setup dropped from 8.64 to 4.15 seconds
across three measurements per variant. All 37 affected tests passed unchanged;
their summed durations fell from 786.21 to 647.43 seconds. Users, tokens,
permissions and journals remain separate and fresh per test. No assertion,
endpoint, failure case, or coverage requirement was removed. This is a modest
saving; the full optimized suite has not been re-timed locally.
The [complete post-change CI run](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/37022455057)
passed the same 634 tests plus six subtests with unchanged 92.23% runtime coverage
in 28 minutes 49.75 seconds. Runner variability means that the whole CI reduction
cannot be attributed solely to fixture batching.

Use `--durations=40` and `--junitxml=...` on the full live command above to repeat
the measurement. Keep raw evidence under `.lab/`; reviewed counts and timings are
in [the timing record](deterministic-timing-0.4.3.json).
