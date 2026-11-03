from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

FRAMEWORK_PREFIXES = (
    "system",
    "microsoft",
    "mscorlib",
    "netstandard",
    "presentationframework",
    "presentationcore",
    "windowsbase",
    "windowsformsintegration",
)

KNOWN_FAMILIES = {
    "accord": "Accord.NET",
    "aforge": "AForge.NET",
    "adodb": "ADODB",
    "devexpress": "DevExpress",
    "telerik": "Telerik",
    "infragistics": "Infragistics",
    "crystaldecisions": "SAP Crystal Reports",
    "newtonsoft": "Newtonsoft.Json",
    "entityframework": "Entity Framework",
    "nhibernate": "NHibernate",
    "log4net": "log4net",
    "nlog": "NLog",
}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _framework(name: str) -> bool:
    low = (name or "").strip().lower()
    return any(low == p or low.startswith(p + ".") for p in FRAMEWORK_PREFIXES)


def _family(name: str) -> str:
    low = (name or "").strip().lower()
    for prefix, family in KNOWN_FAMILIES.items():
        if low.startswith(prefix):
            return family
    return name or "Unknown"


def _version_from_include(include: str) -> str | None:
    match = re.search(r"(?:Version|version)\s*=\s*([0-9][^,\]]*)", include or "")
    return match.group(1).strip() if match else None


def _package_configs(root: Path) -> list[Path]:
    return sorted(root.rglob("packages.config"))


def _parse_packages_config(path: Path) -> list[dict[str, Any]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    out: list[dict[str, Any]] = []
    for package in root:
        if _local(package.tag) != "package":
            continue
        name = package.attrib.get("id", "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "version": package.attrib.get("version"),
            "type": "NUGET",
            "source": "packages.config",
            "source_file": path.as_posix(),
            "status": "DECLARED",
            "family": _family(name),
        })
    return out


def _project_package_references(xml_root: ET.Element, project_file: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in xml_root.iter():
        if _local(e.tag) != "PackageReference":
            continue
        name = e.attrib.get("Include", "").strip()
        if not name:
            continue
        version = e.attrib.get("Version")
        if not version:
            for child in e:
                if _local(child.tag) == "Version" and child.text:
                    version = child.text.strip()
                    break
        out.append({
            "name": name,
            "version": version,
            "type": "NUGET",
            "source": "PackageReference",
            "source_file": project_file,
            "status": "DECLARED",
            "family": _family(name),
        })
    return out


def _usage_info(name: str, source_cache: dict[Path, str], root: Path) -> dict[str, Any]:
    candidates = {name.lower(), name.split(",", 1)[0].strip().lower()}
    files: list[str] = []
    count = 0
    for path, text in source_cache.items():
        low = text.lower()
        hits = sum(low.count(candidate) for candidate in candidates if candidate and len(candidate) > 2)
        if hits:
            try:
                display = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                display = path.as_posix()
            files.append(display)
            count += hits
    return {"used": bool(files), "usage_count": count, "used_by": files}


def _local_dlls(root: Path) -> list[Path]:
    results: list[Path] = []
    ignored = {".git", ".vs", "bin", "obj", "packages", "node_modules"}
    for path in root.rglob("*.dll"):
        try:
            parts = {p.lower() for p in path.relative_to(root).parts[:-1]}
        except ValueError:
            continue
        if parts & ignored:
            continue
        results.append(path)
    return sorted(results)


def inventory_third_party(
    root: Path,
    xml_root: ET.Element,
    project_file: str,
    assembly_refs: list[dict[str, Any]],
    com_items: list[str],
    source_cache: dict[Path, str],
) -> dict[str, Any]:
    """Build a conservative dependency inventory without network access."""
    detected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(item: dict[str, Any]) -> None:
        key = (str(item.get("type")), str(item.get("name")), str(item.get("source")))
        if key not in seen:
            seen.add(key)
            detected.append(item)

    for ref in assembly_refs:
        name = str(ref.get("name") or "").strip()
        if not name or _framework(name):
            continue
        item = {
            "name": name,
            "family": _family(name),
            "version": _version_from_include(str(ref.get("include") or "")),
            "type": "DLL" if ref.get("hintPath") else "ASSEMBLY",
            "source": "HintPath" if ref.get("hintPath") else "ProjectReference",
            "path": ref.get("hintPath"),
            "status": "AVAILABLE" if ref.get("hintPathExists") else ("MISSING" if ref.get("hintPath") else "DECLARED"),
            "confidence": 1.0,
        }
        item["usage"] = _usage_info(name, source_cache, root)
        add(item)

    referenced_names = {str(x.get("name") or "").lower() for x in assembly_refs}
    for dll in _local_dlls(root):
        name = dll.stem
        if _framework(name):
            continue
        # Keep local DLLs as a separate inventory source even when they are not referenced.
        add({
            "name": name,
            "family": _family(name),
            "version": None,
            "type": "DLL",
            "source": "LOCAL_DLL",
            "path": dll.relative_to(root).as_posix(),
            "status": "PRESENT",
            "referenced": name.lower() in referenced_names,
            "confidence": 0.95,
            "usage": _usage_info(name, source_cache, root),
        })

    for package in _project_package_references(xml_root, project_file):
        package["confidence"] = 1.0
        package["usage"] = _usage_info(str(package["name"]), source_cache, root)
        add(package)

    for config in _package_configs(root):
        for package in _parse_packages_config(config):
            package["confidence"] = 1.0
            package["usage"] = _usage_info(str(package["name"]), source_cache, root)
            add(package)

    for name in com_items:
        name = str(name).strip()
        if not name:
            continue
        add({
            "name": name,
            "family": _family(name),
            "version": None,
            "type": "COM",
            "source": "COMReference",
            "path": None,
            "status": "DETECTED",
            "confidence": 1.0,
            "usage": _usage_info(name, source_cache, root),
        })

    families: dict[str, dict[str, Any]] = {}
    for item in detected:
        family = str(item.get("family") or item.get("name") or "Unknown")
        group = families.setdefault(family, {"name": family, "types": [], "dependencies": [], "statuses": []})
        if item.get("type") not in group["types"]:
            group["types"].append(item.get("type"))
        if item.get("name") not in group["dependencies"]:
            group["dependencies"].append(item.get("name"))
        if item.get("status") not in group["statuses"]:
            group["statuses"].append(item.get("status"))

    return {
        "detected": detected,
        "families": list(families.values()),
        "summary": {
            "total": len(detected),
            "nuget": sum(1 for x in detected if x.get("type") == "NUGET"),
            "dll": sum(1 for x in detected if x.get("type") == "DLL"),
            "assembly": sum(1 for x in detected if x.get("type") == "ASSEMBLY"),
            "com": sum(1 for x in detected if x.get("type") == "COM"),
            "missing": sum(1 for x in detected if x.get("status") == "MISSING"),
            "families": len(families),
        },
    }
