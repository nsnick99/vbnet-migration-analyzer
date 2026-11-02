from __future__ import annotations

import json
from typing import Any

from .models import AnalysisResult, Finding


def _finding_dict(f: Finding) -> dict[str, Any]:
    item = f.to_dict()
    item["required_change"] = f.recommendation or f.message
    item["why_critical"] = f.explanation or f.classification_reason or f.message
    return item


def _critical_findings(result: AnalysisResult) -> list[Finding]:
    """Return findings that can block migration/build or require substantive work."""
    selected: list[Finding] = []
    for finding in result.all_findings:
        if (
            finding.blocks_ir
            or finding.is_migration_blocker
            or str(finding.severity).upper() == "CRITICAL"
            or (
                str(finding.severity).upper() == "HIGH"
                and finding.category == "migration"
            )
        ):
            selected.append(finding)
    seen: set[tuple[str, str | None, str]] = set()
    out: list[Finding] = []
    for finding in selected:
        key = (finding.title, finding.path, finding.message)
        if key not in seen:
            seen.add(key)
            out.append(finding)
    return out


def _target_recommendation(result: AnalysisResult) -> dict[str, str]:
    project_type = (result.project.project_type or "").lower()
    framework = result.project.target_framework or "unknown"

    if "web forms" in project_type:
        target = "ASP.NET Core"
        rationale = "ASP.NET Web Forms has no direct modern .NET equivalent; plan a web UI/application migration rather than a simple retarget."
    elif "mvc" in project_type or "webapi" in project_type or "web api" in project_type:
        target = "ASP.NET Core"
        rationale = "The application should be evaluated for migration from the legacy ASP.NET stack to ASP.NET Core."
    elif "windows forms" in project_type or "winforms" in project_type or "wpf" in project_type:
        target = "modern .NET for Windows (for example net8.0-windows or the current supported LTS)"
        rationale = "The desktop UI can remain Windows-specific while moving from .NET Framework to modern .NET."
    elif "class library" in project_type:
        target = "modern .NET (or netstandard2.0 when broad legacy consumer compatibility is required)"
        rationale = "Choose the target based on the consuming applications and required API surface."
    else:
        target = "modern .NET / ASP.NET Core based on application type"
        rationale = "The project type should determine the final target framework; avoid a blind framework retarget."

    return {
        "current_framework": framework,
        "recommended_target": target,
        "rationale": rationale,
    }


def build_critical_report(result: AnalysisResult) -> dict[str, Any]:
    findings = _critical_findings(result)
    migration_blockers = [f for f in findings if f.is_migration_blocker or f.blocks_ir]
    migration_risks = [
        f for f in findings
        if f not in migration_blockers and f.category == "migration"
    ]
    build_or_integrity = [
        f for f in findings
        if f.category in {"integrity", "build", "semantic"}
    ]

    migration_required: list[dict[str, Any]] = []
    seen_actions: set[str] = set()

    def add_action(action: str, reason: str, priority: str = "HIGH") -> None:
        key = action.strip().lower()
        if not key or key in seen_actions:
            return
        seen_actions.add(key)
        migration_required.append({
            "priority": priority,
            "action": action,
            "reason": reason,
        })

    for f in findings:
        if f.is_migration_blocker or f.blocks_ir:
            add_action(f.recommendation or f.message, f.explanation or f.message, "CRITICAL")
        elif f.category == "migration" and str(f.severity).upper() == "HIGH":
            add_action(f.recommendation or f.message, f.explanation or f.message, "HIGH")

    ordered_actions: list[dict[str, str]] = []
    if migration_blockers:
        ordered_actions.append({
            "step": "1",
            "action": "Resolve project/build/integrity blockers before attempting framework migration.",
        })
    ordered_actions.append({
        "step": str(len(ordered_actions) + 1),
        "action": "Confirm the intended modern .NET target for the detected application type.",
    })
    if any(f.title == "COM dependency" for f in migration_risks):
        ordered_actions.append({
            "step": str(len(ordered_actions) + 1),
            "action": "Assess COM/ActiveX dependencies and decide whether to retain, isolate, or replace them.",
        })
    if any(f.title in {"Third-party assembly dependency", "Third-party reference with no direct semantic usage observed"} for f in migration_risks):
        ordered_actions.append({
            "step": str(len(ordered_actions) + 1),
            "action": "Verify every third-party assembly is available and compatible with the target runtime before retargeting.",
        })
    if any(f.title == "Windows-specific API" for f in migration_risks):
        ordered_actions.append({
            "step": str(len(ordered_actions) + 1),
            "action": "Isolate or replace Windows-specific APIs where the target architecture requires portability.",
        })
    if any(f.title == "Legacy database provider" for f in result.risks):
        ordered_actions.append({
            "step": str(len(ordered_actions) + 1),
            "action": "Review legacy database provider usage and migrate or explicitly retain it with a compatibility plan.",
        })
    ordered_actions.append({
        "step": str(len(ordered_actions) + 1),
        "action": "Run a clean build and tests on the target framework before closing migration findings.",
    })

    routine = [f for f in result.all_findings if f not in findings]

    return {
        "report_type": "critical_updates_only",
        "project_name": result.project.name,
        "project_type": result.project.project_type,
        "current_framework": result.project.target_framework,
        "health_status": result.status,
        "build_verified": result.build_verified,
        "critical_updates": [_finding_dict(f) for f in findings],
        "summary": {
            "critical_count": len(findings),
            "migration_blockers": len(migration_blockers),
            "migration_risks": len(migration_risks),
            "build_or_integrity_issues": len(build_or_integrity),
            "routine_items_excluded": len(routine),
            "manual_reviews_among_critical": sum(1 for f in findings if f.manual_review_required),
        },
        "target_framework_recommendation": _target_recommendation(result),
        "migration_required": migration_required,
        "migration_order": ordered_actions,
        "excluded": {
            "reason": "Lower-severity technical debt and routine review items remain in project-health.json and are intentionally excluded from this action-oriented report.",
            "count": len(routine),
            "examples": [f.title for f in routine[:10]],
        },
    }


def critical_json_report(result: AnalysisResult) -> str:
    return json.dumps(build_critical_report(result), indent=2)
