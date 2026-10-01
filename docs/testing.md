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

The optional [OpenCode/LiteLLM/DeepInfra evaluation](agent-evaluation.md) exercises
natural-language tasks through MCP and independently verifies NetBox state. It
incurs provider usage and is not part of unauthenticated CI.

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
