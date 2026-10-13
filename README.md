from __future__ import annotations
from pathlib import Path
from collections import Counter
import re
import hashlib
import xml.etree.ElementTree as ET
from .models import AnalysisResult, Finding
from .project import (find_projects, choose_project, parse_project, project_items, read_properties,
                      all_files, expand_item_patterns, resolve_item_path, find_path, read_source_text)
from .rules import analyze_vb_file
from .build import verify_build
from .guidance import apply_guidance

SOURCE_EXTENSIONS = {".vb", ".bas", ".cls", ".frm"}
_GENERIC_TYPES = {"VB.NET", "VB.NET Windows Application"}


def norm(path: str) -> str:
    """Display paths with forward slashes so the same file is never listed twice."""
    return path.replace("\\", "/")


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _add_unique(items: list[str], value: str):
    value = norm(value)
    if value not in items:
        items.append(value)


def _is_wildcard(item: str) -> bool:
    return "*" in item or "?" in item


def analyze(root: str | Path, run_build: bool = True) -> AnalysisResult:
    root_path = Path(root).resolve()
    scan_dir = root_path if root_path.is_dir() else root_path.parent
    all_projects = find_projects(root_path)
    if not all_projects:
        raise FileNotFoundError(f"No .vbproj found under {root_path}")
    project_path = choose_project(all_projects, root_path)
    root_dir = project_path.parent
    info, xml_root, parse_findings = parse_project(project_path)
    parse_failed = any(f.id == "INT-001" for f in parse_findings)
    items = project_items(xml_root)
    files = all_files(root_dir)
    file_types = Counter((p.suffix.lower() or "[no extension]") for p in files)

    blockers: list[Finding] = []
    risks: list[Finding] = []
    integrity: list[Finding] = [f for f in parse_findings if not f.is_migration_blocker]
    attention: list[str] = []          # files only (project-relative paths)
    unresolved: list[dict] = []        # paths we could not evaluate (unknown MSBuild variables)

    def record(f: Finding):
        (blockers if f.is_migration_blocker else risks).append(f)
        if f.path:
            _add_unique(attention, f.path)

    def resolve(item: str, kind: str) -> str | None:
        resolved = resolve_item_path(item, root_dir)
        if resolved is None:
            unresolved.append({"kind": kind, "value": item})
        return resolved

    for f in parse_findings:            # e.g. unparsable project file -> must be a blocker
        if f.is_migration_blocker:
            blockers.append(f)
            if f.path:
                _add_unique(attention, f.path)

    if len(all_projects) > 1:
        others = [rel(p, scan_dir) for p in all_projects if p != project_path]
        integrity.append(Finding("INT-007", "integrity", "MEDIUM", "Multiple projects found",
                                 f"{len(all_projects)} .vbproj files were found but only '{project_path.name}' was analyzed. "
                                 f"Run the analyzer separately for: {', '.join(others)}.", rel(project_path, scan_dir)))

    # Explicit and globbed project files.
    compile_files = expand_item_patterns(root_dir, items["Compile"])
    compile_keys = {str(p).lower() for p in compile_files}

    # Missing project items.
    for kind in ("Compile", "EmbeddedResource", "Content", "None"):
        for item in items[kind]:
            if _is_wildcard(item):
                continue
            resolved = resolve(item, kind)
            if resolved and find_path(resolved) is None:
                blockers.append(Finding("INT-002", "integrity", "CRITICAL", "Missing project file",
                                        f"{kind} item is declared but the file does not exist.", item, is_migration_blocker=True))
                _add_unique(attention, item)

    # Duplicate item declarations: the same physical file declared more than
    # once within the same item type. MSBuild's behavior here is inconsistent
    # (sometimes a double-compile error, sometimes silently tolerated), so
    # it's worth surfacing either way rather than guessing which applies.
    for kind in ("Compile", "EmbeddedResource", "Content", "None"):
        seen_items: dict[Path, list[str]] = {}
        for item in items[kind]:
            if _is_wildcard(item):
                continue
            resolved = resolve_item_path(item, root_dir)
            if resolved is None:
                continue
            real = find_path(resolved)
            if real is None:
                continue  # already reported above if genuinely missing
            seen_items.setdefault(real.resolve(), []).append(item)
        for real_path, raw_values in seen_items.items():
            if len(raw_values) > 1:
                integrity.append(Finding("INT-010", "integrity", "MEDIUM", "Duplicate item declaration",
                                         f"The same file is declared more than once as {kind} "
                                         f"({', '.join(sorted(set(raw_values)))}).",
                                         rel(real_path, root_dir), is_migration_blocker=False))
                _add_unique(attention, rel(real_path, root_dir))

    # Project references.
    for item in items["ProjectReference"]:
        resolved = resolve(item, "ProjectReference")
        if resolved and find_path(resolved) is None:
            blockers.append(Finding("INT-003", "integrity", "CRITICAL", "Broken project reference",
                                    "ProjectReference points to a missing project.", item, is_migration_blocker=True))
            _add_unique(attention, item)

    # Assembly references: existence of HintPath DLLs, plus a reference inventory.
    assembly_refs: list[dict] = []
    for e in xml_root.iter():
        if e.tag.rsplit("}", 1)[-1] != "Reference":
            continue
        include = e.attrib.get("Include", "")
        hint = None
        for child in e:
            if child.tag.rsplit("}", 1)[-1] == "HintPath" and child.text:
                hint = child.text.strip()
        exists: bool | None = None
        if hint:
            resolved = resolve(hint, "HintPath")
            if resolved:
                exists = find_path(resolved) is not None
                if not exists:
                    blockers.append(Finding("INT-004", "integrity", "CRITICAL", "Missing assembly",
                                            f"Reference '{include}' has a missing HintPath assembly.", hint, is_migration_blocker=True))
                    _add_unique(attention, hint)
        assembly_refs.append({"name": include.split(",", 1)[0].strip(), "include": include, "hintPath": hint, "hintPathExists": exists})

    # Imported .props/.targets. Imports guarded by Condition="Exists(...)" are optional by design.
    for item in items["Import"]:
        if _is_wildcard(item):
            continue
        resolved = resolve(item, "Import")
        if resolved and find_path(resolved) is None:
            blockers.append(Finding("INT-005", "integrity", "HIGH", "Missing imported build file",
                                    "An imported .props/.targets file could not be found.", item, is_migration_blocker=True))
            _add_unique(attention, item)

    # COM references: presence alone is a migration concern.
    for kind in ("COMReference", "COMFileReference"):
        for item in items[kind]:
            blockers.append(Finding("MIG-001", "migration", "HIGH", "COM dependency",
                                    f"{kind} detected in the project; target compatibility must be established.",
                                    item, is_migration_blocker=True))

    # Third-party assemblies are migration risks. Missing HintPath assemblies are handled above as blockers.
    for ref in assembly_refs:
        name = ref["name"]
        if name and not re.match(r"^(System|Microsoft|mscorlib|netstandard|PresentationFramework|PresentationCore|WindowsBase)\b", name, re.I):
            risks.append(Finding("MIG-008", "migration", "HIGH", "Third-party assembly dependency",
                                 f"Non-framework assembly reference '{name}' requires target-platform compatibility review.",
                                 name, is_migration_blocker=False))

    # Read each VB file exactly once, defensively. A file that cannot be
    # confidently read is a blind spot in every finding below it, so it is
    # reported rather than silently skipped.
    vb_files = [p for p in files if p.suffix.lower() == ".vb"]
    source_cache: dict[Path, str] = {}
    for path in vb_files:
        text, status, detail = read_source_text(path)
        display = rel(path, root_dir)
        if status == "unreadable":
            integrity.append(Finding("INT-011", "integrity", "HIGH", "Unreadable file",
                                     f"Could not read this file, so it was not scanned: {detail}.",
                                     display, is_migration_blocker=False))
            _add_unique(attention, display)
            continue
        if status == "encoding_fallback":
            integrity.append(Finding("INT-012", "integrity", "LOW", "Non-UTF-8 source file",
                                     f"File was not valid UTF-8 ({detail}); pattern matches from it should be spot-checked.",
                                     display, is_migration_blocker=False))
            _add_unique(attention, display)
        elif status == "empty":
            integrity.append(Finding("INT-013", "integrity", "LOW", "Empty file",
                                     "File exists but contains no content.", display, is_migration_blocker=False))
            _add_unique(attention, display)
        source_cache[path] = text

    if info.project_type in _GENERIC_TYPES:
        source_sample = "\n".join(text[:20000] for text in source_cache.values())
        if re.search(r"System\.Windows\.Forms|Inherits\s+Form\b|Class\s+Form\b", source_sample, re.I):
            info.project_type = "VB.NET Windows Forms"
        elif re.search(r"System\.Windows\.Controls|System\.Windows\.Markup", source_sample, re.I):
            info.project_type = "VB.NET WPF"
    if info.project_type in _GENERIC_TYPES | {"VB.NET Console Application", "VB.NET Class Library"} \
            and any(p.name.lower() == "web.config" for p in files):
        info.project_type = "VB.NET Web"

    # Analyze VB source. SDK-style (implicit glob, no explicit Compile items)
    # is only claimed when the project file actually parsed -- a project we
    # could not parse at all gets neither label, and skips orphan-detection
    # below rather than treating every .vb file on disk as an "orphan".
    sdk_style = bool(info.sdk) or (not items["Compile"] and not parse_failed)
    for path, text in source_cache.items():
        findings = analyze_vb_file(path, text, rel(path, root_dir))
        for f in findings:
            record(f)

    # Orphan source files: only meaningful for classic explicit-Compile projects
    # whose project file actually parsed.
    if not sdk_style and not parse_failed:
        for path in files:
            if path.suffix.lower() in SOURCE_EXTENSIONS and str(path.resolve()).lower() not in compile_keys:
                integrity.append(Finding("INT-006", "integrity", "MEDIUM", "Orphan source file",
                                         "Source file exists on disk but is not included by the project.",
                                         rel(path, root_dir), is_migration_blocker=False))
                _add_unique(attention, rel(path, root_dir))

    # Configuration integrity (App.config, Web.config, packages.config, and any
    # other *.config file). Malformed configuration should be fixed before a
    # semantic IR is generated because configuration is part of application behavior.
    for cfg in files:
        if cfg.suffix.lower() == ".config":
            try:
                ET.parse(cfg)
            except (ET.ParseError, OSError) as exc:
                blockers.append(Finding("INT-008", "integrity", "HIGH", "Invalid configuration file",
                                        f"Configuration XML could not be parsed: {exc}",
                                        rel(cfg, root_dir), is_migration_blocker=True))
                _add_unique(attention, rel(cfg, root_dir))

    # Files differing only by case can silently merge or collide on Windows
    # vs. case-sensitive build/CI environments.
    seen_case: dict[str, Path] = {}
    for path in files:
        key = rel(path, root_dir).lower()
        previous = seen_case.get(key)
        if previous and previous.resolve() != path.resolve():
            blockers.append(Finding("INT-009", "integrity", "HIGH", "Case-colliding files",
                                     "Two physical files differ only by case; this can cause cross-platform and build inconsistencies.",
                                     rel(path, root_dir), f"Also found: {rel(previous, root_dir)}", True))
            _add_unique(attention, rel(path, root_dir))
        else:
            seen_case[key] = path

    # One real build is stronger than regex-only source checks. On an
    # air-gapped machine the locally installed toolchain is used (if any) and
    # no network access is requested.
    if run_build:
        build_findings, build_verified, build_tool = verify_build(project_path)
    else:
        build_findings, build_verified, build_tool = [], False, None
    for f in build_findings:
        if f.is_migration_blocker:
            blockers.append(f)
        else:
            risks.append(f)
        if f.path and f.path != project_path.name:
            _add_unique(attention, f.path)

    # Enrich and classify every finding once all evidence has been collected.
    # `is_migration_blocker` answers "is this inherently blocking?" while
    # `blocks_ir` answers the stricter readiness question "can the next
    # semantic stage safely consume this project?". A build/toolchain failure
    # may block IR without being a defect in the application itself.
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

    blockers = _dedupe(blockers)
    risks = _dedupe(risks)
    integrity = _dedupe(integrity)
    attention = sorted(set(attention), key=str.lower)

    project_key = hashlib.sha256(str(project_path.resolve()).encode("utf-8")).hexdigest()[:16]
    return AnalysisResult(info, len(files), dict(sorted(file_types.items())),
                          blockers, risks, integrity, attention, build_verified, build_tool, project_key)


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen = set(); out = []
    for f in findings:
        key = (f.id, f.title, f.path, f.message)
        if key not in seen:
            seen.add(key); out.append(f)
    return out


def _finding_key(f: Finding) -> tuple:
    # Deliberately excludes `id` (not guaranteed to round-trip through a JSON
    # file written by an older version of the analyzer) and `line` (an
    # unrelated edit elsewhere in the file can shift a line number without
    # the underlying issue actually changing, which would otherwise show up
    # as a false RESOLVED+NEW pair instead of one PERSISTING finding).
    return (f.category, f.title, f.path, f.evidence)


def _old_key(item: dict) -> tuple:
    return (item.get("category"), item.get("title"), item.get("path"), item.get("evidence"))


def verify_resolution(result: AnalysisResult, previous: dict | None) -> AnalysisResult:
    """Compare the current scan with the previous health JSON for the same project."""
    if not previous:
        result.new_findings = result.blockers + result.risks + result.integrity_issues
        for f in result.new_findings:
            f.status = "NEW"
        return result

    health = previous.get("health", {})
    if health.get("projectKey") != result.project_key:
        result.new_findings = result.blockers + result.risks + result.integrity_issues
        for f in result.new_findings:
            f.status = "NEW"
        return result

    old = []
    # Newer health files keep every IR-blocking prerequisite together.
    # Fall back to the legacy migrationBlockers field for backward compatibility.
    groups = ("blockingPrerequisites", "risks", "integrityIssues") if "blockingPrerequisites" in health else ("migrationBlockers", "risks", "integrityIssues")
    for group in groups:
        old.extend(health.get(group, []))
    old_by_key = {_old_key(item): item for item in old}

    current = result.blockers + result.risks + result.integrity_issues
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
            f = Finding(
                item.get("id", "UNKNOWN"), item.get("category", "unknown"), item.get("severity", "UNKNOWN"),
                item.get("title", "Previous finding"), item.get("message", ""), item.get("path"),
                item.get("evidence"), item.get("is_migration_blocker", False), item.get("line"), item.get("occurrences"),
                item.get("explanation"), item.get("recommendation"), item.get("verification"), "RESOLVED"
            )
            apply_guidance(f)
            result.resolved_findings.append(f)
    return result
