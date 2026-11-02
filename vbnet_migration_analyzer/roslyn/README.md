# Local Roslyn semantic sidecar

The Python analyzer remains the main application and keeps the air-gapped, target-independent workflow. When a compiled `RoslynAnalyzer.exe` is present, it is invoked locally to add semantic VB.NET analysis.

The sidecar uses the Roslyn Visual Basic compiler APIs to extract syntax and semantic diagnostics, declared types, resolved imports, actual symbol usage, third-party assembly usage, known API usage, and native dependencies.

No source is uploaded anywhere. The sidecar reads project source locally and writes JSON back to the Python process.

## Build on Windows

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build-roslyn-worker.ps1
```

The script locates `csc.exe` and the Roslyn assemblies installed with Visual Studio/MSBuild. It does not download packages and does not require internet access.

The resulting executable is:

```text
bin\Release\RoslynAnalyzer.exe
```

Override discovery with:

```text
VBNET_ROSLYN_WORKER=C:\path\to\RoslynAnalyzer.exe
```
