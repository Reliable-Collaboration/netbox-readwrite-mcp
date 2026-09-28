# Validation record

Version **0.2.0**, validated on 2026-09-28. This records observed results, not a production certification.

| Check | Observed result |
| --- | --- |
| Local offline suite | 212 passed on Python 3.14.4 |
| Offline coverage | 91.96% combined statement/branch coverage; CI minimum 85% |
| Local fresh-NetBox integration | 36 passed, plus 6 subtests; each on NetBox 4.7.0 and 4.7.1, restricted actor, separate new databases |
| Independent GitHub CI | Passed: Python 3.11–3.14 and fresh NetBox 4.7.0/4.7.1 integration; legacy 4.6.10 setup timed out (see below) |
| Protocol interoperability | Official Python MCP SDK 1.30.0 client initialized, listed/called tools, read structured results and refusals |
| Packaging | sdist and wheel built; wheel installed into an isolated target and CLI launched |
| Lint and format | Ruff checks passed |
| Licensing | Runtime has no third-party Python dependencies; Apache-2.0 product with retained MIT research notice |

The 4.7 target and Python matrix passed independent validation at commit **1ee9740**:
[GitHub Actions run 36471841897](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36471841897).

The overall run failed because the legacy 4.6.10 fixture setup timed out on its first read-only API query, before integration tests. Commit **8ca5432** increases the disposable seeder timeout from 20 to 120 seconds without changing runtime/test timeouts or retrying writes. A [fresh full-matrix run](https://github.com/Reliable-Collaboration/netbox-readwrite-mcp/actions/runs/36472610494) is pending at the time of this record.

The 4.7 qualification reruns all six review regressions, including actual NetBox serializer normalization and the post-commit response re-query race. Version-policy tests cover rejected prereleases, malformed versions, other minor versions, and acceptance of future stable patches without claiming they are qualified. See [review decisions and resolution](review-remediation.md).

The 0.2.0 wheel was installed into a separate target and launched with Python site packages disabled. The source archive includes the audit dependency snapshot and regression tests; private lab state is excluded. The source-distribution manifest was also corrected to include the dependency snapshot linked from this document.

Pinned container digests are in [scripts/images.lock.json](../scripts/images.lock.json).
The exact local test/development dependency snapshot is in [test-dependencies.txt](test-dependencies.txt). These are audit inputs; no paid product or hosted AI service participates in testing.

## What these results establish

The suite checks supported field updates and compensation; explicit refusal of unsupported categories; current-value and ABA conflicts; preservation of unrelated work; durable no-op/failed/uncertain outcomes; crash/restart and concurrent writers; actual native permissions; correlation with native history; archive loss; journal corruption guards; backup restoration; HTTP boundaries; and interoperable MCP messages.

See [testing](testing.md) for commands and the distinction between real-server checks and injected faults.

## What remains unqualified

- Models or fields outside the published write contract.
- NetBox 4.7 patches after 4.7.1 (accepted by policy but not yet individually qualified), and deployment-specific plugins or custom validators.
- In-place NetBox database upgrades with existing archived native history; see the [upgrade procedure](operations.md#targeting-netbox-47-with-mcp-020).
- Hardware power loss, hostile administrator tampering, loss of all backups, or restoration from every possible inconsistent database/journal pair.
- Large-estate throughput, distributed deployment, multi-tenant isolation, and network filesystems.
- LLM judgment quality, downstream webhook reversal, and physical network rollback.
- Long-running production use or a published package-registry release.

The implementation deliberately reports conflicts and uncertainty instead of promising unconditional undo.
