# VB.NET Project Health & Migration Analyzer

Offline, target-independent preflight analysis for legacy VB.NET applications.

## What it does

- Discovers and classifies VB.NET projects.
- Checks project/file integrity, references, imports and configuration.
- Builds a third-party dependency inventory from project references, HintPath DLLs, local DLLs, `PackageReference`, `packages.config`, and COM references.
- Records dependency status, source, version when explicitly available, family, confidence and source-code usage information.
- Detects migration-impacting patterns such as COM, P/Invoke, legacy database providers, Windows APIs, BinaryFormatter, Enterprise Services, AppDomain, WCF and embedded credentials.
- Optionally runs a local Roslyn semantic-analysis sidecar.
- Optionally verifies a local build with MSBuild, dotnet or xbuild.
- Tracks findings as NEW, PERSISTING or RESOLVED between runs.

## Reports

Each analysis produces:

- `project-health.json` — complete machine-readable health report with project metadata, migration-readiness score, architecture, integrity, Roslyn/build data, detailed findings, recommendations, verification history and third-party dependency inventory.
- `migration-report.txt` — human-readable report.
- `critical_updates.json` — compact action-oriented report containing migration blockers, grouped missing dependencies, third-party dependency risks, migration actions and ordered remediation steps.

The critical report is generated from the same `AnalysisResult` as the full report, so the project is scanned only once.

### Third-party dependency detection

The dependency inventory is intentionally offline and conservative. It does not claim a package version or availability unless the project itself provides enough evidence.

Sources include:

- `<Reference>` and `HintPath` entries in `.vbproj` files.
- Local third-party `.dll` files outside `bin`, `obj`, `packages` and other generated directories.
- `PackageReference` entries.
- `packages.config` entries.
- `COMReference` and `COMFileReference` entries.
- Source-code usage counts for detected dependency names.

Known dependency families such as Accord.NET, AForge.NET, ADODB, DevExpress, Telerik, Infragistics, Crystal Reports and Newtonsoft.Json are grouped for readability, while individual assemblies remain available in the detailed report.

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

`project discovery -> project/build analysis -> dependency inventory -> source rules -> optional Roslyn -> guidance/classification -> full health report + critical migration report`

The analyzer does not modify the application being inspected.
