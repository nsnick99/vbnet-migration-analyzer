from __future__ import annotations

import json
import re
from typing import Any
from .models import AnalysisResult, Finding


def _finding_dict(f: Finding) -> dict[str, Any]:
    item = f.to_dict()
    item["required_change"] = f.recommendation or f.message
    item["why_critical"] = f.explanation or f.classification_reason or f.message
    return item


def _critical_findings(result: AnalysisResult) -> list[Finding]:
    selected = [f for f in result.all_findings if f.blocks_ir or f.is_migration_blocker or str(f.severity).upper() == "CRITICAL" or (str(f.severity).upper() == "HIGH" and f.category == "migration")]
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
    return name or "Unknown assembly"


def _dependency_groups(findings: list[Finding]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for f in findings:
        if f.id != "INT-004":
            continue
        match = re.search(r"Reference '([^']+)'", f.message)
        reference = match.group(1) if match else (f.path or "Unknown assembly")
        family = _dependency_family(reference)
        group = groups.setdefault(family, {"dependency_family": family, "severity": "CRITICAL", "classification": "REAL_BLOCKER", "assembly_count": 0, "assemblies": [], "paths": []})
        group["assembly_count"] += 1
        if reference not in group["assemblies"]:
            group["assemblies"].append(reference)
        if f.path and f.path not in group["paths"]:
            group["paths"].append(f.path)
    return list(groups.values())


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
    actions: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(action: str, reason: str, priority: str = "HIGH") -> None:
        key = action.lower().strip()
        if key and key not in seen:
            seen.add(key)
            actions.append({"priority": priority, "action": action, "reason": reason})

    for g in groups:
        add("Restore or replace the missing " + g["dependency_family"] + " dependency family.", f"{g['assembly_count']} referenced assembly(ies) are missing.", "CRITICAL")
    for f in findings:
        if f.id == "INT-004":
            continue
        if f.is_migration_blocker or f.blocks_ir:
            add(f.recommendation or f.message, f.explanation or f.message, "CRITICAL")
        elif f.category == "migration" and str(f.severity).upper() == "HIGH":
            add(f.recommendation or f.message, f.explanation or f.message, "HIGH")

    order = [{"step": "1", "action": "Resolve project/build/integrity blockers before framework migration."}, {"step": "2", "action": "Confirm the intended modern .NET target."}]
    if groups:
        order.append({"step": str(len(order) + 1), "action": "Restore or replace grouped third-party dependencies and verify target compatibility."})
    if any(f.title == "COM dependency" for f in risks):
        order.append({"step": str(len(order) + 1), "action": "Assess COM/ActiveX dependencies and retain, isolate, or replace them."})
    if any(f.title == "Windows-specific API" for f in risks):
        order.append({"step": str(len(order) + 1), "action": "Isolate or replace Windows-specific APIs where required."})
    order.append({"step": str(len(order) + 1), "action": "Run a clean target-framework build and tests."})

    routine = [f for f in result.all_findings if f not in findings]
    return {"report_type": "critical_updates_only", "project_name": result.project.name, "project_type": result.project.project_type, "current_framework": result.project.target_framework, "health_status": result.status, "build_verified": result.build_verified, "critical_updates": [_finding_dict(f) for f in findings], "dependency_groups": groups, "summary": {"critical_count": len(findings), "migration_blockers": len(blockers), "migration_risks": len(risks), "missing_assembly_findings": sum(1 for f in findings if f.id == "INT-004"), "missing_assembly_dependency_groups": len(groups), "routine_items_excluded": len(routine), "manual_reviews_among_critical": sum(1 for f in findings if f.manual_review_required)}, "target_framework_recommendation": _target_recommendation(result), "migration_required": actions, "migration_order": order, "excluded": {"reason": "Lower-severity technical debt and routine review items remain in project-health.json.", "count": len(routine), "examples": [f.title for f in routine[:10]]}}


def critical_json_report(result: AnalysisResult) -> str:
    return json.dumps(build_critical_report(result), indent=2)
