# Validation record

Version **0.1.1**, validated on 2026-09-28. This records observed results, not a production certification.

| Check | Observed result |
| --- | --- |
| Local offline suite | 188 passed on Python 3.14.4 |
| Offline coverage | 91.74% combined statement/branch coverage; CI minimum 85% |
| Local fresh-NetBox integration | 36 passed, plus 6 subtests; NetBox 4.6.10, restricted actor, new database |
| Independent GitHub CI | All five jobs passed: Python 3.11, 3.12, 3.13, 3.14 and fresh NetBox integration |
| Protocol interoperability | Official Python MCP SDK 1.30.0 client initialized, listed/called tools, read structured results and refusals |
| Packaging | sdist and wheel built; wheel installed into an isolated target and CLI launched |
| Lint and format | Ruff checks passed |
| Licensing | Runtime has no third-party Python dependencies; Apache-2.0 product with retained MIT research notice |

Executable code and tests were independently validated at commit **48e46fa**:
[GitHub Actions run 36469085494](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36469085494).

All five GitHub CI jobs passed for the remediation code. New regression tests cover all six review findings, including actual NetBox serializer normalization and the post-commit response re-query race. See [review decisions and resolution](review-remediation.md).

The 0.1.1 wheel was installed into a separate target and launched with Python site packages disabled. The source archive includes the audit dependency snapshot and regression tests; private lab state is excluded. The source-distribution manifest was also corrected to include the dependency snapshot linked from this document.

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
