from __future__ import annotations
import json
from .models import AnalysisResult, Finding


def _location(f: Finding) -> str | None:
    if not f.path:
        return None
    loc = f"{f.path}:{f.line}" if f.line else f.path
    if f.occurrences and f.occurrences > 1:
        loc += f" ({f.occurrences} occurrences)"
    return loc


def _print_findings(title: str, findings: list[Finding]) -> str:
    lines = [title, "─" * 60]
    if not findings:
        lines.append("None")
        return "\n".join(lines)
    for i, f in enumerate(findings, 1):
        lines.append(f"[{f.severity}] {f.title}")
        lines.append(f"  Classification: {f.classification}")
        lines.append(f"  Resolution:     {f.resolution}")
        lines.append(f"  Blocks IR:      {'YES' if f.blocks_ir else 'NO'}")
        lines.append(f"  Manual review:  {'YES' if f.manual_review_required else 'NO'}")
        lines.append(f"  {f.message}")
        if f.classification_reason:
            lines.append(f"  Why this classification: {f.classification_reason}")
        loc = _location(f)
        if loc:
            lines.append(f"  Location: {loc}")
        if f.evidence:
            lines.append(f"  Evidence: {f.evidence}")
        if f.explanation:
            lines.append(f"  Explanation: {f.explanation}")
        if f.recommendation:
            lines.append(f"  Recommended action: {f.recommendation}")
        if f.verification:
            lines.append(f"  Verify: {f.verification}")
        lines.append(f"  Status: {f.status}")
        if i != len(findings):
            lines.append("")
    return "\n".join(lines)


def _classification_summary(r: AnalysisResult) -> str:
    counts = {}
    for f in r.all_findings:
        counts[f.classification] = counts.get(f.classification, 0) + 1
    ordered = ("REAL_BLOCKER", "WARNING", "TECHNICAL_DEBT", "INTENTIONAL_DEPENDENCY", "MANUAL_REVIEW")
    lines = ["FINDING DISPOSITION SUMMARY", "─" * 60]
    for key in ordered:
        lines.append(f"  {key:<24} {counts.get(key, 0)}")
    return "\n".join(lines)


def _verification_section(r: AnalysisResult) -> str:
    lines = ["RESOLUTION VERIFICATION", "─" * 60]
    lines.append(f"  New findings:        {len(r.new_findings)}")
    lines.append(f"  Persisting findings: {len(r.persisting_findings)}")
    lines.append(f"  Resolved findings:   {len(r.resolved_findings)}")
    if r.resolved_findings:
        lines.append("")
        lines.append("Resolved since previous run:")
        for f in r.resolved_findings:
            lines.append(f"  [RESOLVED] {f.title} ({_location(f) or 'project'})")
    elif not r.new_findings and not r.persisting_findings:
        lines.append("  No findings to verify.")
    return "\n".join(lines)


def _semantic_section(r: AnalysisResult) -> str:
    s = r.semantic_analysis or {}
    lines = ["ROSLYN SEMANTIC ANALYSIS", "─" * 60]
    if not s.get("available"):
        lines.append("  Status: NOT AVAILABLE")
        if s.get("reason"):
            lines.append(f"  Reason: {s.get('reason')}")
        return "\n".join(lines)
    lines.append("  Status: AVAILABLE")
    lines.append(f"  Tool: {s.get('tool') or 'Microsoft.CodeAnalysis.VisualBasic'}")
    lines.append(f"  Version: {s.get('version') or 'Unknown'}")
    lines.append(f"  Files analyzed semantically: {len(s.get('files', []))}")
    lines.append(f"  Syntax errors: {sum(1 for d in s.get('syntaxDiagnostics', []) if str(d.get('severity','')).upper() == 'ERROR')}")
    lines.append(f"  Semantic errors: {sum(1 for d in s.get('semanticDiagnostics', []) if str(d.get('severity','')).upper() == 'ERROR')}")
    lines.append(f"  Native dependencies: {len(s.get('nativeDependencies', []))}")
    return "\n".join(lines)


def _attention_section(r: AnalysisResult) -> str:
    lines = ["FILES REQUIRING ATTENTION", "─" * 60]
    lines.extend(f"  {f}" for f in r.attention_files) if r.attention_files else lines.append("None")
    return "\n".join(lines)


def text_report(r: AnalysisResult) -> str:
    types = "\n".join(f"  {k:<18} {v}" for k, v in r.file_types.items()) or "  None"
    build_status = f"VERIFIED ({r.build_tool})" if r.build_verified else "NOT VERIFIED"
    return "\n".join([
        "VB.NET PROJECT HEALTH ANALYSIS", "=" * 60, "",
        "PROJECT INFORMATION", "─" * 60,
        f"Project Name:        {r.project.name}",
        f"Project Type:        {r.project.project_type}",
        f"Output Type:         {r.project.output_type or 'Unknown'}",
        f"Target Framework:    {r.project.target_framework or 'Unknown'}",
        f"Project File:        {r.project.project_file}", "",
        "BUILD HEALTH", "─" * 60, f"Build Verification:  {build_status}", "",
        "FILE SUMMARY", "─" * 60, f"Total Files:         {r.total_files}", "", types, "",
        "PROJECT HEALTH", "─" * 60, f"Status:              {r.status}",
        f"Migration Blockers:  {len(r.migration_blockers)}",
        f"IR Blocking Prerequisites: {sum(1 for f in r.blockers if f.blocks_ir)}", "",
        _classification_summary(r), "",
        _print_findings("BLOCKERS / IR PREREQUISITES", r.blockers), "",
        _print_findings("ITEMS REQUIRING REVIEW", r.risks), "",
        _print_findings("PROJECT INTEGRITY ISSUES", r.integrity_issues), "",
        _semantic_section(r), "", _verification_section(r), "", _attention_section(r),
    ])


def json_report(r: AnalysisResult) -> str:
    return json.dumps(r.to_dict(), indent=2)
