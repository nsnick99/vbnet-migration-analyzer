from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .models import Finding

_ERROR_RE = re.compile(r"^(?P<path>.*?)(?:\((?P<line>\d+),(?P<col>\d+)\))?:\s*(?P<level>error|warning)\s+(?P<code>[A-Z]{2,}\d+)\s*:\s*(?P<msg>.*)$", re.I)


def _tool() -> tuple[str, list[str]] | None:
    msbuild = shutil.which("msbuild") or shutil.which("MSBuild.exe")
    if msbuild:
        return msbuild, [msbuild, "/nologo", "/v:minimal", "/t:Build"]
    dotnet = shutil.which("dotnet")
    if dotnet:
        return dotnet, [dotnet, "build", "--nologo", "--no-restore"]
    xbuild = shutil.which("xbuild")
    if xbuild:
        return xbuild, [xbuild, "/verbosity:minimal", "/target:Build"]
    return None


def verify_build(project: Path) -> tuple[list[Finding], bool, str | None]:
    selected = _tool()
    if selected is None:
        return [], False, None

    executable, command = selected
    command = command + [str(project)]
    try:
        proc = subprocess.run(
            command,
            cwd=project.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [Finding(
            "BLD-002", "build", "HIGH", "Build verification failed",
            f"The local build command could not complete: {exc}"
        )], False, executable

    errors: list[Finding] = []
    warnings: list[Finding] = []
    for raw in proc.stdout.splitlines():
        line = raw.strip()
        match = _ERROR_RE.match(line)
        if not match:
            continue
        level = match.group("level").lower()
        path = match.group("path").strip()
        try:
            p = Path(path)
            if p.is_absolute():
                path = p.resolve().relative_to(project.parent.resolve()).as_posix()
        except (ValueError, OSError):
            pass
        finding = Finding(
            f"BLD-{'ERR' if level == 'error' else 'WARN'}-{match.group('code').upper()}",
            "build",
            "CRITICAL" if level == "error" else "LOW",
            f"Compiler {level}",
            match.group("msg").strip(),
            path or None,
            match.group("code").upper(),
            level == "error",
            int(match.group("line")) if match.group("line") else None,
        )
        (errors if level == "error" else warnings).append(finding)

    if errors:
        return errors + warnings, False, executable

    if proc.returncode != 0:
        text = proc.stdout.strip().splitlines()
        evidence = text[-1][:300] if text else f"exit code {proc.returncode}"
        errors.append(Finding(
            "BLD-003", "build", "HIGH", "Build could not be completed",
            "The build process returned a non-zero exit code without a parsed compiler error. "
            "This commonly indicates a missing SDK/targeting pack, package, or build dependency.",
            project.name,
            evidence,
            False,
        ))
        return errors + warnings, False, executable

    return warnings, True, executable
