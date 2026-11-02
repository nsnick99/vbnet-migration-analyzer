param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $root "bin\$Configuration"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    "$env:ProgramFiles\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\Roslyn\csc.exe",
    "$env:ProgramFiles\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\Roslyn\csc.exe",
    "$env:ProgramFiles\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\Roslyn\csc.exe",
    "$env:ProgramFiles\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\Roslyn\csc.exe",
    "$env:ProgramFiles\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\amd64\Roslyn\csc.exe"
)
$csc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $csc) {
    $csc = Get-ChildItem "$env:ProgramFiles\Microsoft Visual Studio" -Filter csc.exe -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match "MSBuild\\Current\\Bin\\Roslyn" } |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $csc) { throw "Roslyn C# compiler (csc.exe) was not found. Install/enable Visual Studio Build Tools with MSBuild." }

$roslynDir = Split-Path -Parent $csc
$codeAnalysis = Join-Path $roslynDir "Microsoft.CodeAnalysis.dll"
$vbAnalysis = Join-Path $roslynDir "Microsoft.CodeAnalysis.VisualBasic.dll"
if (-not (Test-Path $codeAnalysis)) { throw "Microsoft.CodeAnalysis.dll not found next to csc.exe: $roslynDir" }
if (-not (Test-Path $vbAnalysis)) { throw "Microsoft.CodeAnalysis.VisualBasic.dll not found next to csc.exe: $roslynDir" }

$output = Join-Path $outDir "RoslynAnalyzer.exe"
$source = Join-Path $root "RoslynAnalyzer.cs"
$refs = @(
    "System.dll",
    "System.Core.dll",
    "System.Runtime.Serialization.dll",
    $codeAnalysis,
    $vbAnalysis
)

& $csc /nologo /target:exe /optimize+ /out:$output $source ($refs | ForEach-Object { "/reference:`"$_`"" })
if ($LASTEXITCODE -ne 0) { throw "csc.exe failed with exit code $LASTEXITCODE" }
Write-Host "Built: $output"
Write-Host "Roslyn: $roslynDir"
