from __future__ import annotations
import glob
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from .models import ProjectInfo, Finding

IGNORED_DIRS = {".git", ".vs", "bin", "obj", "packages", "node_modules"}
_WEB_GUIDS = {"349c5851-65df-11da-9384-00065b846f21", "e24c65dc-7377-472b-9aba-bc803b73c61a", "e53f8fea-eae0-44a6-8774-ffd645390401", "e3e379df-f4c6-4180-9b81-6769533abe47"}
_WPF_GUID = "60dc8134-eba5-43b8-bcc9-bb4bc16c2548"


def _is_ignored(rel_parts: tuple[str, ...]) -> bool:
    return any(part.lower() in IGNORED_DIRS for part in rel_parts)


def find_projects(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() == ".vbproj" else []
    found = []
    for p in sorted(root.rglob("*.vbproj")):
        if not _is_ignored(p.relative_to(root).parts[:-1]):
            found.append(p)
    return found


def choose_project(projects: list[Path], root: Path) -> Path:
    if len(projects) > 1:
        named = [p for p in projects if p.stem.lower() == root.name.lower()]
        if named:
            return named[0]
    return projects[0]


def discover_project(root: Path) -> Path:
    projects = find_projects(root)
    if not projects:
        raise FileNotFoundError(f"No .vbproj found under {root}")
    return choose_project(projects, root)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _prop(root: ET.Element, name: str) -> str | None:
    for e in root.iter():
        if _local(e.tag) == name and e.text:
            return e.text.strip()
    return None


def read_properties(root: ET.Element) -> tuple[dict[str, str], list[dict]]:
    plain: dict[str, str] = {}
    conditional: list[dict] = []
    for pg in root.iter():
        if _local(pg.tag) != "PropertyGroup":
            continue
        group_cond = pg.attrib.get("Condition")
        cond_props: dict[str, str] = {}
        for child in pg:
            if not isinstance(child.tag, str):
                continue
            value = (child.text or "").strip()
            if not value:
                continue
            name = _local(child.tag)
            cond = group_cond or child.attrib.get("Condition")
            if cond:
                cond_props[name] = value
            else:
                plain[name] = value
        if cond_props:
            conditional.append({"condition": group_cond or "(per-property condition)", "properties": cond_props})
    return plain, conditional


def _reference_names(root: ET.Element) -> list[str]:
    names = []
    for e in root.iter():
        if _local(e.tag) == "Reference":
            inc = e.attrib.get("Include", "").split(",", 1)[0].strip()
            if inc:
                names.append(inc)
    return names


def _split_include(value: str) -> list[str]:
    return [v.strip() for v in value.split(";") if v.strip()]


def classify_project(sdk: str | None, props: dict[str, str], references: list[str], imports: list[str]) -> str:
    p = {k.lower(): v for k, v in props.items()}
    sdk_l = (sdk or "").lower()
    guids = {g.strip("{} ").lower() for g in p.get("projecttypeguids", "").split(";") if g.strip()}
    mytype = p.get("mytype", "").lower()
    refs = {r.lower() for r in references}
    output = p.get("outputtype", "").lower()
    if (sdk_l.endswith(".web") or guids & _WEB_GUIDS or mytype == "web" or any("webapplication" in i.lower() for i in imports)):
        return "VB.NET Web"
    if p.get("usewpf", "").lower() == "true" or _WPF_GUID in guids or "presentationframework" in refs:
        return "VB.NET WPF"
    if (p.get("usewindowsforms", "").lower() == "true" or mytype.startswith("windowsforms") or "system.windows.forms" in refs):
        return "VB.NET Windows Forms"
    if output == "library":
        return "VB.NET Class Library"
    if output == "exe":
        return "VB.NET Console Application"
    if output in ("winexe", "appcontainerexe"):
        return "VB.NET Windows Application"
    return "VB.NET"


def parse_project(project_path: Path) -> tuple[ProjectInfo, ET.Element, list[Finding]]:
    findings: list[Finding] = []
    try:
        tree = ET.parse(project_path)
        root = tree.getroot()
    except (ET.ParseError, OSError) as exc:
        info = ProjectInfo(project_path.stem, project_path.name)
        findings.append(Finding("INT-001", "integrity", "CRITICAL", "Invalid project file", str(exc), project_path.name, is_migration_blocker=True))
        return info, ET.Element("Project"), findings
    sdk = root.attrib.get("Sdk")
    if not sdk:
        for child in root:
            if _local(child.tag) == "Sdk" and child.attrib.get("Name"):
                sdk = child.attrib["Name"]
                break
    props, _ = read_properties(root)
    framework = (props.get("TargetFramework") or props.get("TargetFrameworks") or props.get("TargetFrameworkVersion") or _prop(root, "TargetFramework") or _prop(root, "TargetFrameworks") or _prop(root, "TargetFrameworkVersion"))
    root_ns = props.get("RootNamespace") or _prop(root, "RootNamespace")
    assembly = props.get("AssemblyName") or _prop(root, "AssemblyName")
    output_type = props.get("OutputType") or _prop(root, "OutputType")
    imports = [e.attrib.get("Project", "") for e in root.iter() if _local(e.tag) == "Import"]
    project_type = classify_project(sdk, props, _reference_names(root), imports)
    info = ProjectInfo(project_path.stem, project_path.name, project_type, framework, root_ns, assembly, sdk, output_type)
    return info, root, findings


def project_items(root: ET.Element) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"Compile": [], "EmbeddedResource": [], "Content": [], "None": [], "Reference": [], "ProjectReference": [], "COMReference": [], "COMFileReference": [], "Import": [], "ImportGuarded": []}
    for e in root.iter():
        tag = _local(e.tag)
        if tag not in result or tag == "ImportGuarded":
            continue
        if tag == "Import":
            value = e.attrib.get("Project")
            if value:
                guarded = "exists(" in e.attrib.get("Condition", "").lower()
                result["ImportGuarded" if guarded else "Import"].append(value)
            continue
        value = e.attrib.get("Include")
        if value:
            result[tag].extend(_split_include(value))
    return result


def all_files(root_dir: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = sorted(d for d in dirnames if d.lower() not in IGNORED_DIRS)
        files.extend(Path(dirpath) / f for f in sorted(filenames))
    return files


def _solution_dir(project_dir: Path) -> Path | None:
    for d in [project_dir, *project_dir.parents]:
        try:
            if any(n.lower().endswith(".sln") for n in os.listdir(d)):
                return d
        except OSError:
            pass
    return None


def resolve_item_path(value: str, project_dir: Path, for_glob: bool = False) -> str | None:
    base = project_dir.as_posix()
    sol = _solution_dir(project_dir)
    def sub(m: re.Match) -> str:
        name = m.group(1).lower()
        if name in ("projectdir", "msbuildthisfiledirectory"):
            return base + "/"
        if name == "msbuildprojectdirectory":
            return base
        if name == "solutiondir" and sol is not None:
            return sol.as_posix() + "/"
        return m.group(0)
    v = re.sub(r"\$\(([^)]+)\)", sub, value.strip()).replace("\\", "/")
    if "$(" in v:
        return None
    if re.match(r"^([A-Za-z]:)?/", v):
        return v
    prefix = glob.escape(base) if for_glob else base
    return f"{prefix}/{v}"


def find_path(path_str: str) -> Path | None:
    p = Path(os.path.normpath(path_str))
    if p.exists():
        return p
    parts = p.parts
    if not parts:
        return None
    cur = Path(parts[0]) if p.is_absolute() else Path(".")
    rest = parts[1:] if p.is_absolute() else parts
    for part in rest:
        try:
            match = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
        except OSError:
            return None
        if match is None:
            return None
        cur = cur / match
    return cur


def read_source_text(path: Path) -> tuple[str | None, str, str | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, "unreadable", (exc.strerror or str(exc))
    if not raw:
        return "", "empty", None
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "ok", None
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16"), "ok", None
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8"), "ok", None
    except UnicodeDecodeError:
        pass
    return raw.decode("cp1252", errors="replace"), "encoding_fallback", "decoded as Windows-1252 (not valid UTF-8)"


def expand_item_patterns(root_dir: Path, patterns: list[str]) -> set[Path]:
    found: set[Path] = set()
    for pattern in patterns:
        if "*" in pattern or "?" in pattern:
            resolved = resolve_item_path(pattern, root_dir, for_glob=True)
            if resolved is None:
                continue
            try:
                matches = glob.glob(resolved, recursive=True)
            except (OSError, ValueError):
                continue
            found.update(Path(m).resolve() for m in matches if os.path.isfile(m))
        else:
            resolved = resolve_item_path(pattern, root_dir)
            if resolved is None:
                continue
            real = find_path(resolved)
            if real is not None and real.is_file():
                found.add(real.resolve())
    return found
