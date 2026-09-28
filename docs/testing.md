# Reproducing the audit

## Offline suite

Install a local editable copy and optional test/dev dependencies:

~~~sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,dev]'
ruff check src tests scripts
ruff format --check src tests scripts
pytest --cov=netbox_readwrite_mcp --cov-fail-under=85
python -m build
~~~

The suite does not contact a real NetBox. HTTP transport tests use a loopback server; protocol tests launch subprocesses and an official MCP SDK client. Hypothesis generates edit sequences and verifies that reverse task compensation restores initial values. Additional regressions cover consistent observer/export snapshots during concurrent commits, descending/equal clocks, legacy receipt reconciliation, inexact historical corrections, and malformed initialization/nested JSON. Other tests cover scope, malformed/unsupported edits, native error receipts, ambiguous outcomes, corruption, archive loss, idempotency, and recovery conflicts.

The small independent NetBox model is deliberately not the authority for server semantics. Live tests establish those separately.

## Real NetBox integration

Prerequisites: Linux with rootless Podman, Python, network access to pull images, free port 18871 for the default NetBox 4.7.1 lab, approximately 4 GiB available RAM and 8 GiB disk. No cloud account or AI inference is involved.

~~~sh
export NETBOX_RW_TEST_VERSION=4.7.1  # alternatively: 4.7.0 or 4.6.10
python scripts/lab.py up
python scripts/lab.py ready
python scripts/lab.py bootstrap
python scripts/seed.py
NETBOX_RW_LIVE=1 pytest tests/integration -v --junitxml=.lab/$NETBOX_RW_TEST_VERSION/integration-results.xml
python scripts/lab.py stop
~~~

The selector must remain set for every command, including stop. Each version has independent containers, database volume, credentials and journals. Ports are 18860 (4.6.10), 18870 (4.7.0), and 18871 (4.7.1); omitting the selector defaults to 4.7.1. The integration suite checks the actual server version before modifying fixtures. Older unversioned labs are left intact.

Images are digest-pinned in scripts/images.lock.json. Startup migrates a fresh database. Bootstrap creates a lab-only administrator; seed creates synthetic devices plus a restricted agent with view/change only for two device IDs. A third device tests permission denial.

Tests use a new journal per case and reset only the two synthetic devices. They send actual conditional PATCH requests and verify actual native history. The suite requires explicit opt-in and refuses configuration pointing away from the lab's loopback URL. Do not route that port to a production server.

Each run retains journal exports and checksums under `.lab/<version>/evidence`. Tokens/configuration live under .lab and are ignored by Git. Do not publish this directory. CI uploads only synthetic JUnit reports.

Covered live scenarios include:

- Actual MCP edit/undo, native snapshots, and idempotent replay after restart.
- Qualified serializer normalization, normalized no-ops, and refusal of noncanonical pre-images.
- Normalized writes surviving response loss and hard exit.
- A real second HTTP writer between NetBox commit and response re-query; committed effects stay accurate.
- No-op with no PATCH, stale preconditions, last-moment server 412, unrelated-field preservation, ABA conflicts.
- Real commit followed by injected response loss; hard process exit before dispatch and after commit.
- Archive outage before/after commit, missing archived row, wrong correlation actor.
- Simulated disk-full transaction failure before dispatch.
- Repeated-field task recovery, partial conflict, resumed correction after hard exit.
- Two writer processes sharing an idempotency boundary.
- Actual restricted-token denial of out-of-scope edits and deletion.
- Native invalid status, scalar multi-field restoration, and unsupported fields.
- Verified backup restoration and local evidence/projection integrity guards.

Fault injection does not establish hardware power-loss durability, distributed failover correctness, high-volume scalability, webhook reversal, or arbitrary model recovery. Tests after a real commit simulate transport loss; they do not physically interrupt a network switch.

## Cleanup and isolation

Stop preserves evidence and data. Resource names use the `nbrw-audit-<version-with-dashes>` prefix and project label. The harness never prunes global resources or touches the preliminary research lab.

To remove only the default 4.7.1 disposable lab after stopping it (substitute the version in every name for a different lab):

~~~sh
podman rm nbrw-audit-4-7-1-worker nbrw-audit-4-7-1-netbox nbrw-audit-4-7-1-valkey nbrw-audit-4-7-1-postgres
podman volume rm nbrw-audit-4-7-1-db
podman network rm nbrw-audit-4-7-1
~~~

Archive any evidence needed first. Starting again with retained `.lab/<version>` credentials creates a fresh database with the same lab credentials; run bootstrap and seed again.

## CI and dependencies

GitHub Actions runs offline tests on Python 3.11–3.14 and the live suite on Python 3.12 against NetBox 4.6.10, 4.7.0, and 4.7.1. Actions are pinned by commit. Test dependencies have supported major-version bounds; runtime has no third-party Python dependencies. The checked-in validation report records the exact versions used locally. Auditors wanting exact replay can install the recorded dependency snapshot on the corresponding platform/Python version; ongoing CI intentionally tests resolution within the declared bounds.
