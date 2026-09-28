# Validation record

Validated on 2026-09-28. This records observed results, not a production certification.

| Check | Observed result |
| --- | --- |
| Local offline suite | 151 passed on Python 3.14.4 |
| Offline coverage | 90.00% combined statement/branch coverage; CI minimum 85% |
| Local fresh-NetBox integration | 30 passed; NetBox 4.6.10, restricted actor, new database |
| Independent GitHub CI | All five jobs passed: Python 3.11, 3.12, 3.13, 3.14 and fresh NetBox integration |
| Protocol interoperability | Official Python MCP SDK 1.30.0 client initialized, listed/called tools, read structured results and refusals |
| Packaging | sdist and wheel built; wheel installed into an isolated target and CLI launched |
| Lint and format | Ruff checks passed |
| Licensing | Runtime has no third-party Python dependencies; Apache-2.0 product with retained MIT research notice |

Executable code and tests were validated at commit **ac54426**:
[GitHub Actions run 36439066279](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36439066279).

The local original integration run occurred just before the conservative HTTP 408/429 classification change; the independent CI run at ac54426 validates the final classification and guarded loopback test configuration. Offline tests explicitly cover 408/429 as uncertain.

Pinned container digests are in [scripts/images.lock.json](../scripts/images.lock.json).
The exact local test/development dependency snapshot is in [test-dependencies.txt](test-dependencies.txt). These are audit inputs; no paid product or hosted AI service participates in testing.

## What these results establish

The suite checks supported field updates and compensation; explicit refusal of unsupported categories; current-value and ABA conflicts; preservation of unrelated work; durable no-op/failed/uncertain outcomes; crash/restart and concurrent writers; actual native permissions; correlation with native history; archive loss; journal corruption guards; backup restoration; HTTP boundaries; and interoperable MCP messages.

See [testing](testing.md) for commands and the distinction between real-server checks and injected faults.

## What remains unqualified

- Models or fields outside the published write contract.
- NetBox versions other than 4.6.10, including deployment-specific plugins and custom validators.
- Hardware power loss, hostile administrator tampering, loss of all backups, or restoration from every possible inconsistent database/journal pair.
- Large-estate throughput, distributed deployment, multi-tenant isolation, and network filesystems.
- LLM judgment quality, downstream webhook reversal, and physical network rollback.
- Long-running production use or a published package-registry release.

The implementation deliberately reports conflicts and uncertainty instead of promising unconditional undo.
