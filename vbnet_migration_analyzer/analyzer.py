from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from .build import verify_build
from .guidance import apply_guidance
from .models import AnalysisResult, Finding
from .project import all_files, choose_project, discover_project, expand_item_patterns, find_path, find_projects, parse_project, project_items, read_source_text, resolve_item_path
from .roslyn import relative_semantic_paths, run_semantic_analysis
from .rules import analyze_vb_file

SOURCE_EXTENSIONS = {".vb", ".bas", ".cls", ".frm"}


def norm(path: str) -> str:
    return path.replace("\\", "/")


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _add_unique(items: list[str], value: str) -> None:
    value = norm(value)
    if value not in items:
        items.append(value)


def _legacy_framework_finding(target_framework: str | None) -> Finding | None:
    """Flag classic .NET Framework targets as migration work, not as a parse/build error."""
    framework = (target_framework or "").strip()
    if not framework:
        return Finding(
            "MIG-013", "migration", "HIGH", "Target framework is not declared",
            "The project target framework could not be determined from the project file.",
            is_migration_blocker=True,
        )
    if re.match(r"^v[1-4](?:\.\d+){1,2}$", framework, re.I):
        return Finding(
            "MIG-013", "migration", "HIGH", "Legacy .NET Framework target",
            f"Project targets legacy .NET Framework {framework}; a modern .NET migration requires a target-framework and dependency compatibility plan.",
            evidence=framework,
            is_migration_blocker=True,
        )
    return None


def analyze(root: str | Path, run_build: bool = True, roslyn_mode: str = "auto") -> AnalysisResult:
    root_path = Path(root).resolve()
    projects = find_projects(root_path)
    if not projects:
        raise FileNotFoundError(f"No .vbproj found under {root_path}")
    project_path = choose_project(projects, root_path)
    root_dir = project_path.parent
    info, xml_root, parse_findings = parse_project(project_path)
    items = project_items(xml_root)
    files = all_files(root_dir)
    file_types = Counter((p.suffix.lower() or "[no extension]") for p in files)
    blockers: list[Finding] = []
    risks: list[Finding] = []
    integrity: list[Finding] = []
    attention: list[str] = []

    def add(f: Finding) -> None:
        (blockers if f.is_migration_blocker else risks).append(f)
        if f.path:
            _add_unique(attention, f.path)

    for f in parse_findings:
        add(f)

    framework_finding = _legacy_framework_finding(info.target_framework)
    if framework_finding:
        add(framework_finding)

    if len(projects) > 1:
        integrity.append(Finding("INT-007", "integrity", "MEDIUM", "Multiple projects found", f"{len(projects)} projects were found; only {project_path.name} was analyzed.", rel(project_path, root_path)))

    def resolve(item: str) -> str | None:
        return resolve_item_path(item, root_dir)

    for kind in ("Compile", "EmbeddedResource", "Content", "None"):
        for item in items[kind]:
            if "*" in item or "?" in item:
                continue
            resolved = resolve(item)
            if resolved and find_path(resolved) is None:
                add(Finding("INT-002", "integrity", "CRITICAL", "Missing project file", f"{kind} item is declared but the file does not exist.", item, is_migration_blocker=True))

    for item in items["ProjectReference"]:
        resolved = resolve(item)
        if resolved and find_path(resolved) is None:
            add(Finding("INT-003", "integrity", "CRITICAL", "Broken project reference", "ProjectReference points to a missing project.", item, is_migration_blocker=True))

    assembly_refs: list[dict] = []
    for e in xml_root.iter():
        if e.tag.rsplit("}", 1)[-1] != "Reference":
            continue
        include = e.attrib.get("Include", "")
        hint = None
        for child in e:
            if child.tag.rsplit("}", 1)[-1] == "HintPath" and child.text:
                hint = child.text.strip()
        exists = None
        if hint:
            resolved = resolve(hint)
            exists = bool(resolved and find_path(resolved))
            if not exists:
                add(Finding("INT-004", "integrity", "CRITICAL", "Missing assembly", f"Reference '{include}' has a missing HintPath assembly.", hint, is_migration_blocker=True))
        name = include.split(",", 1)[0].strip()
        assembly_refs.append({"name": name, "include": include, "hintPath": hint, "hintPathExists": exists})
        if name and not re.match(r"^(System|Microsoft|mscorlib|netstandard|PresentationFramework|PresentationCore|WindowsBase)\b", name, re.I):
            risks.append(Finding("MIG-008", "migration", "HIGH", "Third-party assembly dependency", f"Non-framework assembly reference '{name}' requires target-platform compatibility review.", name))

    for item in items["Import"]:
        if "*" in item or "?" in item:
            continue
        resolved = resolve(item)
        if resolved and find_path(resolved) is None:
            add(Finding("INT-005", "integrity", "HIGH", "Missing imported build file", "An imported .props/.targets file could not be found.", item, is_migration_blocker=True))

    for kind in ("COMReference", "COMFileReference"):
        for item in items[kind]:
            add(Finding("MIG-001", "migration", "HIGH", "COM dependency", f"{kind} detected in the project; target compatibility must be established.", item, is_migration_blocker=True))

    source_cache: dict[Path, str] = {}
    for path in files:
        if path.suffix.lower() != ".vb":
            continue
        text, status, detail = read_source_text(path)
        display = rel(path, root_dir)
        if status == "unreadable":
            integrity.append(Finding("INT-011", "integrity", "HIGH", "Unreadable file", f"Could not read this file: {detail}.", display))
            _add_unique(attention, display)
            continue
        if status == "encoding_fallback":
            integrity.append(Finding("INT-012", "integrity", "LOW", "Non-UTF-8 source file", detail or "Legacy encoding detected.", display))
        elif status == "empty":
            integrity.append(Finding("INT-013", "integrity", "LOW", "Empty file", "File exists but contains no content.", display))
        source_cache[path] = text or ""
        for finding in analyze_vb_file(path, text or "", display):
            add(finding)

    roslyn_data = {"available": False, "reason": "Roslyn analysis disabled."}
    if roslyn_mode != "off":
        roslyn_data = run_semantic_analysis(info.name, list(source_cache), assembly_refs)
        roslyn_data = relative_semantic_paths(roslyn_data, root_dir)
        if roslyn_mode == "on" and not roslyn_data.get("available"):
            add(Finding("ROS-000", "semantic", "HIGH", "Roslyn semantic analysis unavailable", str(roslyn_data.get("reason") or "The local Roslyn sidecar could not be used.")))

    if run_build:
        build_findings, build_verified, build_tool = verify_build(project_path)
    else:
        build_findings, build_verified, build_tool = [], False, None
    for f in build_findings:
        add(f)

    all_findings = _dedupe(blockers + risks + integrity)
    blockers, risks, integrity = [], [], []
    for finding in all_findings:
        apply_guidance(finding)
        if finding.blocks_ir:
            blockers.append(finding)
        elif finding.category == "integrity":
            integrity.append(finding)
        else:
            risks.append(finding)

    project_key = hashlib.sha256(str(project_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return AnalysisResult(info, len(files), dict(sorted(file_types.items())), blockers, risks, integrity,
                          sorted(set(attention), key=str.lower), build_verified, build_tool, project_key,
                          semantic_analysis=roslyn_data)


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen = set()
    out = []
    for f in findings:
        key = (f.id, f.title, f.path, f.message)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _finding_key(f: Finding) -> tuple:
    return (f.category, f.title, f.path, f.evidence)


def _old_key(item: dict) -> tuple:
    return (item.get("category"), item.get("title"), item.get("path"), item.get("evidence"))


def verify_resolution(result: AnalysisResult, previous: dict | None) -> AnalysisResult:
    current = result.blockers + result.risks + result.integrity_issues
    if not previous:
        result.new_findings = current
        for f in current:
            f.status = "NEW"
        return result
    health = previous.get("health", {})
    if health.get("projectKey") != result.project_key:
        result.new_findings = current
        for f in current:
            f.status = "NEW"
        return result
    old: list[dict] = []
    for group in ("blockingPrerequisites", "risks", "integrityIssues"):
        old.extend(health.get(group, []))
    old_by_key = {_old_key(item): item for item in old}
    current_keys = {_finding_key(f) for f in current}
    for f in current:
        if _finding_key(f) in old_by_key:
            f.status = "PERSISTING"
            result.persisting_findings.append(f)
        else:
            f.status = "NEW"
            result.new_findings.append(f)
    for item in old:
        if _old_key(item) not in current_keys:
            f = Finding(item.get("id", "UNKNOWN"), item.get("category", "unknown"), item.get("severity", "UNKNOWN"), item.get("title", "Previous finding"), item.get("message", ""), item.get("path"), item.get("evidence"), item.get("is_migration_blocker", False), item.get("line"), item.get("occurrences"), item.get("explanation"), item.get("recommendation"), item.get("verification"), "RESOLVED")
            apply_guidance(f)
            result.resolved_findings.append(f)
    return result
