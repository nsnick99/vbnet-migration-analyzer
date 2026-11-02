# Changelog

## 0.5.0 - Local Roslyn semantic layer

Added an optional, offline Roslyn sidecar for VB.NET semantic analysis.

### New capabilities
- VB.NET syntax diagnostics from Roslyn
- source-level semantic diagnostics
- semantic type inventory
- resolved import namespaces and symbol usage
- third-party assembly usage evidence
- target-sensitive API usage
- P/Invoke and VB `Declare` native dependency extraction
- semantic analysis embedded in `project-health.json`
- Roslyn summary embedded in `migration-report.txt`
- `--roslyn auto|on|off` CLI control
- explicit Roslyn-required gating for IR readiness
- action-oriented `critical_updates.json` migration report

### Air-gapped behavior
Roslyn is invoked only through a locally compiled executable. No package restore, API call, telemetry, or online service is used.
