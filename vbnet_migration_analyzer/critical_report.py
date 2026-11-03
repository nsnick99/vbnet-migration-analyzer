from __future__ import annotations

import json
import re
from typing import Any
from .models import AnalysisResult, Finding


def _finding_dict(f: Finding, index: int) -> dict[str, Any]:
    item = f.to_dict()
    item["finding_id"] = f"FND-{index:03d}"
    item["rule_id"] = f.id
    item["required_change"] = f.recommendation or f.message
    item["why_critical"] = f.explanation or f.classification_reason or f.message
    item["impact"] = {
        "severity": f.severity,
        "classification": f.classification,
        "migration_blocker": f.is_migration_blocker,
        "ir_readiness_blocker": f.blocks_ir,
        "blocker_scope": f.blocker_scope,
    }
    if f.path or f.line:
        item["evidence_detail"] = {"path": f.path, "line": f.line, "value": f.evidence}
    return item


def _critical_findings(result: AnalysisResult) -> list[Finding]:
    selected = [
        f for f in result.all_findings
        if f.blocks_ir
        or f.is_migration_blocker
        or str(f.severity).upper() == "CRITICAL"
        or (str(f.severity).upper() == "HIGH" and f.category == "migration")
    ]
    seen: set[tuple[str, str | None, str]] = set()
    out: list[Finding] = []
    for f in selected:
        key = (f.title, f.path, f.message)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _dependency_family(reference: str) -> str:
    name = re.sub(r"\s*,.*$", "", reference or "").strip()
    low = name.lower()
    if low.startswith("accord"):
        return "Accord.NET"
    if low.startswith("aforge"):
        return "AForge.NET"
    if low.startswith("adodb"):
        return "ADODB"
    if low.startswith("devexpress"):
        return "DevExpress"
    if low.startswith("telerik"):
        return "Telerik"
    if low.startswith("infragistics"):
        return "Infragistics"
    if low.startswith("crystaldecisions"):
        return "SAP Crystal Reports"
    if low.startswith("newtonsoft"):
        return "Newtonsoft.Json"
    return name or "Unknown assembly"


def _dependency_groups(findings: list[Finding]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for f in findings:
        if f.id != "INT-004":
            continue
        match = re.search(r"Reference '([^']+)'", f.message)
        reference = match.group(1) if match else (f.path or "Unknown assembly")
        family = _dependency_family(reference)
        group = groups.setdefault(family, {
            "dependency_family": family,
            "severity": "CRITICAL",
            "classification": "REAL_BLOCKER",
            "assembly_count": 0,
            "assemblies": [],
            "paths": [],
            "action": "RESTORE_OR_REPLACE_DEPENDENCY",
        })
        group["assembly_count"] += 1
        if reference not in group["assemblies"]:
            group["assemblies"].append(reference)
        if f.path and f.path not in group["paths"]:
            group["paths"].append(f.path)
    return list(groups.values())


def _third_party_summary(result: AnalysisResult) -> dict[str, Any]:
    inventory = result.third_party or {}
    detected = inventory.get("detected", [])
    critical = [x for x in detected if x.get("status") == "MISSING"]
    return {
        "total_detected": len(detected),
        "missing": len(critical),
        "families": inventory.get("families", []),
        "critical_dependencies": critical,
    }


def _target_recommendation(result: AnalysisResult) -> dict[str, str]:
    project_type = (result.project.project_type or "").lower()
    framework = result.project.target_framework or "unknown"
    if "web forms" in project_type or "mvc" in project_type or "webapi" in project_type or "web api" in project_type:
        target = "ASP.NET Core"
        rationale = "Move from the legacy ASP.NET stack to ASP.NET Core; Web Forms requires application/UI redesign."
    elif "windows forms" in project_type or "winforms" in project_type or "wpf" in project_type:
        target = "modern .NET for Windows"
        rationale = "Retain the Windows desktop model while moving from .NET Framework to modern .NET."
    elif "class library" in project_type:
        target = "modern .NET or netstandard2.0"
        rationale = "Choose based on the consuming applications and required API surface."
    else:
        target = "modern .NET / ASP.NET Core based on application type"
        rationale = "Select the target from the detected application architecture."
    return {"current_framework": framework, "recommended_target": target, "rationale": rationale}


def build_critical_report(result: AnalysisResult) -> dict[str, Any]:
    findings = _critical_findings(result)
    blockers = [f for f in findings if f.is_migration_blocker or f.blocks_ir]
    risks = [f for f in findings if f not in blockers and f.category == "migration"]
    groups = _dependency_groups(findings)
    third_party = _third_party_summary(result)
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(action: str, reason: str, priority: str = "HIGH", automatable: bool = False) -> None:
        key = action.lower().strip()
        if key and key not in seen:
            seen.add(key)
            actions.append({
                "priority": priority,
                "action": action,
                "reason": reason,
                "automatable": automatable,
                "requires_manual_review": not automatable,
            })

    for g in groups:
        add(
            "Restore or replace the missing " + g["dependency_family"] + " dependency family.",
            f"{g['assembly_count']} referenced assembly(ies) are missing.",
            "P0",
        )

    for dep in third_party["critical_dependencies"]:
        name = dep.get("name") or "Unknown dependency"
        if dep.get("type") == "NUGET" and dep.get("status") == "MISSING":
            add(f"Restore NuGet package {name}.", "Package is declared but unavailable to the analyzer/project.", "P0")

    for f in findings:
        if f.id == "INT-004":
            continue
        if f.is_migration_blocker or f.blocks_ir:
            add(f.recommendation or f.message, f.explanation or f.message, "P0")
        elif f.category == "migration" and str(f.severity).upper() == "HIGH":
            add(f.recommendation or f.message, f.explanation or f.message, "P1")

    order = [
        {"step": "1", "action": "Resolve project/build/integrity blockers before framework migration."},
        {"step": "2", "action": "Confirm the intended modern .NET target."},
    ]
    if groups or third_party["critical_dependencies"]:
        order.append({"step": str(len(order) + 1), "action": "Restore or replace third-party dependencies and verify target compatibility."})
    if any(f.title == "COM dependency" for f in risks):
        order.append({"step": str(len(order) + 1), "action": "Assess COM/ActiveX dependencies and retain, isolate, or replace them."})
    if any(f.title == "Windows-specific API" for f in risks):
        order.append({"step": str(len(order) + 1), "action": "Isolate or replace Windows-specific APIs where required."})
    order.append({"step": str(len(order) + 1), "action": "Run a clean target-framework build and tests."})

    routine = [f for f in result.all_findings if f not in findings]
    score = result.migration_readiness
    return {
        "report_type": "critical_updates",
        "project": {
            "name": result.project.name,
            "project_file": result.project.project_file,
            "type": result.project.project_type,
            "target_framework": result.project.target_framework,
        },
        "health": {
            "status": result.status,
            "migration_status": score["status"],
            "score": score["score"],
            "max_score": score["max_score"],
            "critical_count": sum(1 for f in findings if str(f.severity).upper() == "CRITICAL"),
            "high_count": sum(1 for f in findings if str(f.severity).upper() == "HIGH"),
            "migration_blockers": len(blockers),
            "manual_review_count": sum(1 for f in findings if f.manual_review_required),
            "build_verified": result.build_verified,
        },
        "blocking_reasons": score["blocking_reasons"],
        "critical_dependencies": {
            "missing_assembly_groups": groups,
            "third_party": third_party,
        },
        "summary": {
            "critical_count": len(findings),
            "migration_blockers": len(blockers),
            "migration_risks": len(risks),
            "missing_assembly_findings": sum(1 for f in findings if f.id == "INT-004"),
            "missing_assembly_dependency_groups": len(groups),
            "third_party_detected": third_party["total_detected"],
            "third_party_missing": third_party["missing"],
            "routine_items_excluded": len(routine),
            "manual_reviews_among_critical": sum(1 for f in findings if f.manual_review_required),
        },
        "target_framework_recommendation": _target_recommendation(result),
        "migration_required": actions,
        "migration_order": order,
        "excluded": {
            "reason": "Lower-severity technical debt and routine review items remain in project-health.json.",
            "count": len(routine),
            "examples": [f.title for f in routine[:10]],
        },
        "scan_metadata": {
            "analyzer_version": "1.1.0",
            "roslyn_enabled": bool(result.semantic_analysis.get("available")),
            "build_verified": result.build_verified,
        },
    }


def critical_json_report(result: AnalysisResult) -> str:
    return json.dumps(build_critical_report(result), indent=2)
