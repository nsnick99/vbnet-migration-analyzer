from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

_WORKER_NAMES = ("RoslynAnalyzer.exe", "RoslynAnalyzer.dll")


def _candidate_workers() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("VBNET_ROSLYN_WORKER")
    if env:
        candidates.append(Path(env).expanduser())
    here = Path(__file__).resolve().parent
    candidates.extend(here.joinpath("roslyn", "bin", "Release", name) for name in _WORKER_NAMES)
    candidates.extend(here.joinpath("roslyn", "bin", "Debug", name) for name in _WORKER_NAMES)
    candidates.extend(here.joinpath("roslyn", name) for name in _WORKER_NAMES)
    return candidates


def find_roslyn_worker() -> Path | None:
    for candidate in _candidate_workers():
        if candidate.is_file():
            return candidate
    return None


def available() -> bool:
    return find_roslyn_worker() is not None


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def build_manifest(project_name: str, source_paths: list[Path], references: list[dict[str, Any]], path: Path) -> None:
    lines = [f"PROJECT_B64\t{_b64(project_name)}"]
    for source in source_paths:
        lines.append(f"SOURCE_B64\t{_b64(str(source.resolve()))}")
    for ref in references:
        name = str(ref.get("name") or "")
        hint = str(ref.get("hintPath") or "")
        lines.append(f"REF_B64\t{_b64(name)}\t{_b64(hint)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_semantic_analysis(project_name: str, source_paths: list[Path], references: list[dict[str, Any]], timeout: int = 180) -> dict[str, Any]:
    worker = find_roslyn_worker()
    if worker is None:
        return {"available": False, "tool": "Microsoft.CodeAnalysis.VisualBasic", "version": None,
                "reason": "Roslyn sidecar is not installed/compiled. Run roslyn/build-roslyn-worker.ps1 on a Windows machine with Visual Studio/MSBuild.",
                "syntaxDiagnostics": [], "semanticDiagnostics": [], "files": [], "dependencies": [], "apiUsage": [], "nativeDependencies": [], "callGraph": []}

    with tempfile.TemporaryDirectory(prefix="vbnet-roslyn-") as temp_dir:
        manifest = Path(temp_dir) / "manifest.txt"
        build_manifest(project_name, source_paths, references, manifest)
        if worker.suffix.lower() == ".dll":
            dotnet = os.environ.get("DOTNET_HOST_PATH", "dotnet")
            command = [dotnet, str(worker), str(manifest)]
        else:
            command = [str(worker), str(manifest)]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
        except (OSError, subprocess.SubprocessError) as exc:
            return {"available": False, "tool": "Microsoft.CodeAnalysis.VisualBasic", "version": None,
                    "reason": f"Roslyn sidecar could not be started: {exc}", "syntaxDiagnostics": [], "semanticDiagnostics": [], "files": [], "dependencies": [], "apiUsage": [], "nativeDependencies": [], "callGraph": []}
        stdout = (completed.stdout or "").strip()
        if not stdout:
            return {"available": False, "tool": "Microsoft.CodeAnalysis.VisualBasic", "version": None,
                    "reason": (completed.stderr or "Roslyn sidecar returned no JSON output.").strip(), "syntaxDiagnostics": [], "semanticDiagnostics": [], "files": [], "dependencies": [], "apiUsage": [], "nativeDependencies": [], "callGraph": []}
        try:
            data = json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError as exc:
            return {"available": False, "tool": "Microsoft.CodeAnalysis.VisualBasic", "version": None,
                    "reason": f"Roslyn sidecar returned invalid JSON: {exc}", "stdoutTail": stdout[-2000:], "stderr": (completed.stderr or "")[-2000:],
                    "syntaxDiagnostics": [], "semanticDiagnostics": [], "files": [], "dependencies": [], "apiUsage": [], "nativeDependencies": [], "callGraph": []}
        if completed.returncode != 0 and data.get("available") is not False:
            data["available"] = False
            data.setdefault("reason", f"Roslyn sidecar exited with code {completed.returncode}.")
        return data


def relative_semantic_paths(data: dict[str, Any], root_dir: Path) -> dict[str, Any]:
    def rel_path(value: Any) -> Any:
        if not isinstance(value, str) or not value:
            return value
        try:
            return Path(value).resolve().relative_to(root_dir.resolve()).as_posix()
        except (OSError, ValueError):
            return value.replace("\\", "/")

    for diag_key in ("syntaxDiagnostics", "semanticDiagnostics"):
        for item in data.get(diag_key, []):
            item["path"] = rel_path(item.get("path"))
    for item in data.get("files", []):
        item["path"] = rel_path(item.get("path"))
        for native in item.get("nativeDependencies", []):
            native["path"] = rel_path(native.get("path"))
    for item in data.get("dependencies", []):
        item["files"] = [rel_path(x) for x in item.get("files", [])]
    for item in data.get("apiUsage", []):
        item["files"] = [rel_path(x) for x in item.get("files", [])]
    for item in data.get("nativeDependencies", []):
        item["path"] = rel_path(item.get("path"))
    for item in data.get("callGraph", []):
        item["path"] = rel_path(item.get("path"))
    for item in data.get("files", []):
        for edge in item.get("callGraph", []):
            edge["path"] = rel_path(edge.get("path"))
    return data
