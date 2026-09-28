# NetBox Read/Write MCP

Give an AI agent permission to edit NetBox **and keep the evidence needed to understand and safely correct its work**.

This Apache-2.0 MCP server writes directly to the NetBox Community REST API. It records the intended change and previous values before dispatch, correlates the result with native change history, and provides optimistic undo. If someone has since changed an affected field, undo explains the conflict and leaves their work intact. Ordinary writes do not require approval.

**Release scope:** 0.2.0 implementation targeting stable NetBox **4.7.x** (qualified: **4.7.0 and 4.7.1**), retaining **4.6.10** compatibility, with Python **3.11+ on POSIX** and stdio MCP. Device **description, serial, and status** updates are supported. This is a tested, bounded implementation, not a claim of established production maturity or universal CRUD support. Later stable 4.7 patches are accepted, but must pass the live contract suite in your deployment before upgrading. Prereleases and other versions are refused. See [validation](docs/validation.md) for what was actually run.

## Problems this solves

| Problem | Behavior |
| --- | --- |
| A read-only MCP server cannot maintain inventory. | Conditional REST PATCH directly to NetBox; no upstream MCP server or paid service. |
| An HTTP response alone does not explain what changed. | Durable task/operation IDs, previous/resulting values, native change IDs, request IDs, and receipts connect intent to outcome. |
| Native history misses failed attempts and some no-ops. | A separate journal records these and retains archived native history without automatic expiration. |
| A connection fails after a possible commit. | An explicit uncertain outcome; reconciliation looks for matching evidence without blindly repeating the write. |
| Undo might overwrite someone else's work. | Field-aware compensation preserves unrelated changes and refuses same-field conflicts, including A→B→C→B history. |
| Several edits need correcting. | Reverse-order, resumable task compensation with explicit partial results. This is not an atomic database transaction. |
| An agent misreports success or improvises recovery. | Structured receipts, conflict evidence, recovery bundles, and [agent instructions](docs/agent-guide.md) give clients authoritative results to display. |

The distinction is the **write and recovery contract**, rather than the number of endpoints. The agent calls this server for supported writes; this server calls NetBox REST. It can sit alongside a broader read-only MCP server.

    Agent / MCP client
           │ stdio
           ▼
    NetBox Read/Write MCP ── conditional PATCH ──► NetBox Community
           │                      ◄── receipts and native history
           ▼
    Durable local SQLite journal ──► operator-managed off-host backups

## Install

Use Python 3.11 or newer on a POSIX system. The runtime uses only the Python standard library. No package-registry release is needed:

~~~sh
git clone https://github.com/reliable-collaboration/netbox-readwrite-mcp.git
cd netbox-readwrite-mcp
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
netbox-readwrite-mcp --help
~~~

Check out the commit your organization audited before installing. This project has not published a PyPI release.

## Configure NetBox and the server

1. Use NetBox 4.7.1 (4.7.0 and legacy 4.6.10 are also qualified). Configure **CHANGELOG_RETENTION = 0** and ensure no other process deletes history.
2. Create a dedicated non-superuser identity, such as **netbox-agent**. Grant **view/change on dcim.device**, constrained to intended device IDs, and **view on core.objectchange** with complete history visibility. Do not grant add/delete. See [permissions and operations](docs/operations.md).
3. Create a write-enabled API token. Put only the token in a file readable by the server's OS account (mode 600). Both v1 tokens and v2 tokens beginning with nbt_ are accepted.
4. Copy [examples/config.json](examples/config.json) to a protected configuration directory:

~~~json
{
  "netbox_url": "https://netbox.example.org",
  "token_file": "token",
  "journal": "state/journal.sqlite",
  "instance_id": "a-generated-uuid-for-this-netbox-lineage",
  "actor": "netbox-agent",
  "allowed_device_ids": [42, 43]
}
~~~

Generate the instance ID once:

~~~sh
python -c 'import uuid; print(uuid.uuid4())'
~~~

Preserve it with backups. The actor must exactly match the token owner's NetBox username. Paths are relative to the configuration file. Use the NetBox base URL **without /api**. HTTPS is required except for a loopback lab.

Upgrading from the initial implementation? Follow the [existing-journal upgrade steps](docs/operations.md#upgrading-from-010-to-011) before resuming edits.

Keep the journal on durable local storage. Every server process in this deployment must share the same journal; copies must not become independent active writers. Identity and scope are bound to the journal. Read the [operator guide](docs/operations.md) before changing them.

## Connect an MCP client

Use your client's stdio MCP configuration mechanism. A typical configuration is:

~~~json
{
  "mcpServers": {
    "netbox-readwrite": {
      "command": "/absolute/path/to/.venv/bin/netbox-readwrite-mcp",
      "args": ["--config", "/absolute/path/to/config.json"]
    }
  }
}
~~~

The process uses stdout only for MCP messages. There is no public HTTP listener.

A normal tool sequence:

1. **capabilities** — inspect the supported contract.
2. **begin_task** with a purpose — retain its task ID.
3. **read_device** with device_id — retain the returned ETag.
4. **update_device** with that task ID, a stable operation key, and the exact ETag:

~~~json
{
  "task_id": "<returned task ID>",
  "operation_key": "inventory-ticket-184-device42-serial",
  "device_id": 42,
  "expected_etag": "<exact ETag returned by read_device>",
  "changes": {"serial": "ABC123"}
}
~~~

5. Inspect state, id, requested, normalized_requested, before_values, after_values, native_id, last_receipt, and guidance. Display the authoritative receipt to the person supervising the agent.
6. If a response was lost, use **find_operation** with the same operation key. If uncertain, call **reconcile** and inspect again.

To correct a verified edit, call **preview_undo** with its operation_id, then **undo_operation** with that ID and a stable correction operation_key. Safety checks run again during application; a preview is not a reservation.

Description and serial input are normalized using the qualified NetBox serializer's whitespace rules. Both raw and normalized intent are retained. An existing value that cannot be restored exactly through REST is refused before editing. A legacy correction that restored a different value is reported as **incomplete_restore**, never as completed undo.

A conflict returns previous values, conflicting current values, evidence IDs, and a warning. There is no force flag. A person can investigate and authorize a **new forward edit against fresh state**, producing a separately observable operation.

## History and observability

Tools **get_task**, **get_operation**, **get_device_history**, **observability**, and **recovery_bundle** expose retained evidence. **reconcile** refreshes native history and resolves provable uncertain outcomes. See the [tool reference](docs/tools.md).

“Perpetual” means **no automatic history deletion policy**. It does not mean storage cannot fail. Guarantees depend on durable storage, complete native history, correct lineage, a qualified NetBox version, and tested off-host backups. Hash chains detect corruption and inconsistent projections; they cannot stop a privileged administrator from rewriting the journal.

~~~sh
netbox-readwrite-mcp --config /path/config.json --backup /safe/path/new-backup.sqlite
netbox-readwrite-mcp --config /path/config.json --export /safe/path/new-export.json
~~~

Existing destinations are refused. Exports include SHA-256 sidecars. Keep independent copies and rehearse restoration. Recovery does not retract webhooks, downstream actions, or physical network changes.

## Supported edits and boundaries

| Edit category | 0.1 behavior |
| --- | --- |
| Device description / serial / status, separately or together | Supported; strings only. NetBox validates choices, lengths, permissions, and deployment rules. Empty strings clear text. |
| No-op, identical replay, multiple edits in a task | Observable; task undo is resumable compensation. |
| Rename, asset tags, comments, foreign keys, placement, tags, custom fields, JSON context | Refused; require additional normalization, uniqueness, dependency, and recovery contracts. |
| Create, delete, clone, bulk writes, IP allocation, cables, interfaces, prefixes, VLANs, VMs, circuits | No write tools. Cascading deletion cannot honestly be represented as a simple inverse PATCH. |
| Arbitrary endpoint/method calls, force undo, redo | Not exposed. |

See the [edit coverage matrix](docs/edit-contract.md). This server does not grant blanket permission to mutate every NetBox model.

## Audit it yourself

Offline tests need no NetBox instance, AI provider, credentials, or paid service:

~~~sh
python -m pip install -e '.[test,dev]'
ruff check src tests scripts
ruff format --check src tests scripts
pytest --cov=netbox_readwrite_mcp --cov-fail-under=85
~~~

Tests include generated edit sequences, a real local HTTP server, and an official MCP SDK client. For integration tests, install **Podman**:

~~~sh
python scripts/lab.py up
python scripts/lab.py ready
python scripts/lab.py bootstrap
python scripts/seed.py
NETBOX_RW_LIVE=1 pytest tests/integration -v
python scripts/lab.py stop
~~~

This creates isolated **nbrw-audit-*** containers, pinned NetBox/PostgreSQL/Valkey images, synthetic inventory, and a restricted agent identity. NetBox binds to **127.0.0.1:18871** by default (NetBox 4.7.1). The lab does not reuse the research spikes. Allow 6–10 minutes for first startup and downloads. See [testing](docs/testing.md) for resources, evidence, cleanup, and fault-injection limits.

## Related work and project information

- [Operator guide](docs/operations.md), [architecture](docs/architecture.md), [agent instructions](docs/agent-guide.md).
- [Review findings and their resolution](docs/review-remediation.md).
- [Development journal](JOURNAL.md), [contributing](CONTRIBUTING.md), [security policy](SECURITY.md).
- [Related preliminary research spikes](https://github.com/reliable-collaboration/netbox-write-research), including candidate comparisons and evidence behind this contract.

Licensed under [Apache-2.0](LICENSE), with the [original research notice](third_party/research-MIT.txt) retained for derived code. NetBox is a separate project; this server is not affiliated with or endorsed by its maintainers.

Deletion recovery research: [original-ID restoration findings and proposed plugin](docs/deletion-recovery.md). This is follow-up research, not an additional supported write capability.
