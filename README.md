# VB.NET Project Health & Migration Analyzer

Offline, target-independent preflight analysis for legacy VB.NET applications.

## What it does

- Discovers and classifies VB.NET projects.
- Checks project/file integrity, references, imports and configuration.
- Detects migration-impacting patterns such as COM, P/Invoke, legacy database providers, Windows APIs, BinaryFormatter, Enterprise Services, AppDomain, WCF and embedded credentials.
- Optionally runs a local Roslyn semantic-analysis sidecar.
- Optionally verifies a local build with MSBuild, dotnet or xbuild.
- Tracks findings as NEW, PERSISTING or RESOLVED between runs.

## Reports

Each analysis produces:

- `project-health.json` — complete machine-readable health report.
- `migration-report.txt` — human-readable report.
- `critical_updates.json` — action-oriented report containing only build/integrity blockers and high-impact migration risks, plus target-framework guidance and migration order.

The critical report is generated from the same `AnalysisResult` as the full report, so the project is scanned only once.

## Run

```bash
python -m vbnet_migration_analyzer /path/to/project --roslyn auto
```

Skip build verification:

```bash
python -m vbnet_migration_analyzer /path/to/project --no-build --roslyn off
```

Require Roslyn:

```bash
python -m vbnet_migration_analyzer /path/to/project --roslyn on
```

## Air-gapped operation

The Python analyzer uses the standard library only. Build verification relies on tools already installed on the machine. Roslyn is invoked only through a locally compiled sidecar; no package restore, API call or telemetry is required.

## Architecture

`project discovery -> project/build analysis -> source rules -> optional Roslyn -> guidance/classification -> full health report + critical migration report`

The analyzer does not modify the application being inspected.
