from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Finding:
    id: str
    category: str
    severity: str
    title: str
    message: str
    path: str | None = None
    evidence: str | None = None
    is_migration_blocker: bool = False
    line: int | None = None
    occurrences: int | None = None
    explanation: str | None = None
    recommendation: str | None = None
    verification: str | None = None
    status: str = "OPEN"
    classification: str = "MANUAL_REVIEW"
    resolution: str = "REVIEW"
    blocks_ir: bool = False
    manual_review_required: bool = False
    classification_reason: str | None = None
    blocker_scope: str = "NONE"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("id", None)
        return d


@dataclass
class ProjectInfo:
    name: str
    project_file: str
    project_type: str = "Unknown"
    target_framework: str | None = None
    root_namespace: str | None = None
    assembly_name: str | None = None
    sdk: str | None = None
    output_type: str | None = None


@dataclass
class AnalysisResult:
    project: ProjectInfo
    total_files: int
    file_types: dict[str, int]
    blockers: list[Finding] = field(default_factory=list)
    risks: list[Finding] = field(default_factory=list)
    integrity_issues: list[Finding] = field(default_factory=list)
    attention_files: list[str] = field(default_factory=list)
    build_verified: bool = False
    build_tool: str | None = None
    project_key: str | None = None
    new_findings: list[Finding] = field(default_factory=list)
    persisting_findings: list[Finding] = field(default_factory=list)
    resolved_findings: list[Finding] = field(default_factory=list)
    semantic_analysis: dict[str, Any] = field(default_factory=dict)
    third_party: dict[str, Any] = field(default_factory=dict)

    @property
    def all_findings(self) -> list[Finding]:
        return self.blockers + self.risks + self.integrity_issues

    @property
    def migration_blockers(self) -> list[Finding]:
        return [f for f in self.blockers if f.blocker_scope == "MIGRATION"]

    @property
    def status(self) -> str:
        if any(f.is_migration_blocker for f in self.blockers):
            return "UNHEALTHY"
        if self.blockers or self.risks or self.integrity_issues or not self.build_verified:
            return "REVIEW REQUIRED"
        return "HEALTHY"

    @property
    def migration_readiness(self) -> dict[str, Any]:
        total = len(self.all_findings)
        blockers = sum(1 for f in self.all_findings if f.is_migration_blocker or f.blocks_ir)
        high = sum(1 for f in self.all_findings if str(f.severity).upper() in {"CRITICAL", "HIGH"})
        score = 100
        score -= min(60, blockers * 8)
        score -= min(20, max(0, high - blockers) * 3)
        if not self.build_verified:
            score -= 10
        score = max(0, score)
        reasons = []
        if not self.build_verified:
            reasons.append("Build verification has not passed.")
        reasons.extend(f.title for f in self.all_findings if f.is_migration_blocker or f.blocks_ir)
        return {
            "score": score,
            "max_score": 100,
            "status": "BLOCKED" if blockers else ("REVIEW" if total or not self.build_verified else "READY"),
            "blocking_reasons": list(dict.fromkeys(reasons))[:20],
        }

    def _finding_records(self, findings: list[Finding], prefix: str) -> list[dict[str, Any]]:
        records = []
        for index, finding in enumerate(findings, 1):
            item = finding.to_dict()
            item["finding_id"] = f"{prefix}-{index:03d}"
            item["rule_id"] = finding.id
            item["impact"] = {
                "severity": finding.severity,
                "classification": finding.classification,
                "migration_blocker": finding.is_migration_blocker,
                "ir_readiness_blocker": finding.blocks_ir,
                "blocker_scope": finding.blocker_scope,
            }
            if finding.path or finding.line:
                item["evidence_detail"] = {
                    "path": finding.path,
                    "line": finding.line,
                    "value": finding.evidence,
                }
            records.append(item)
        return records

    def to_dict(self) -> dict[str, Any]:
        all_findings = self.all_findings
        critical = sum(1 for x in all_findings if str(x.severity).upper() == "CRITICAL")
        high = sum(1 for x in all_findings if str(x.severity).upper() == "HIGH")
        medium = sum(1 for x in all_findings if str(x.severity).upper() == "MEDIUM")
        low = sum(1 for x in all_findings if str(x.severity).upper() == "LOW")
        return {
            "report_type": "project_health_detailed",
            "project": asdict(self.project),
            "summary": {
                "health_status": self.status,
                "migration_readiness": self.migration_readiness["status"],
                "total_findings": len(all_findings),
                "critical": critical,
                "high": high,
                "medium": medium,
                "low": low,
                "real_blockers": sum(1 for x in all_findings if x.classification == "REAL_BLOCKER"),
                "manual_reviews": sum(1 for x in all_findings if x.classification == "MANUAL_REVIEW"),
                "files_scanned": self.total_files,
            },
            "migration_readiness": self.migration_readiness,
            "file_summary": {"total_files": self.total_files, "file_types": self.file_types},
            "framework": {
                "current": self.project.target_framework,
                "legacy": bool(self.project.target_framework and str(self.project.target_framework).lower().startswith("v")),
            },
            "dependencies": {
                "third_party": self.third_party,
                "missing_assemblies": [x.to_dict() for x in all_findings if x.id == "INT-004"],
            },
            "architecture": {
                "project_type": self.project.project_type,
                "output_type": self.project.output_type,
                "root_namespace": self.project.root_namespace,
                "assembly_name": self.project.assembly_name,
            },
            "integrity": {
                "issues": self._finding_records(self.integrity_issues, "INT"),
                "project_health_status": self.status,
            },
            "source_analysis": {
                "files_requiring_attention": self.attention_files,
            },
            "roslyn_analysis": self.semantic_analysis,
            "build_analysis": {
                "verified": self.build_verified,
                "tool": self.build_tool,
            },
            "findings": self._finding_records(all_findings, "FND"),
            "verification_history": {
                "new": self._finding_records(self.new_findings, "NEW"),
                "persisting": self._finding_records(self.persisting_findings, "PERSIST"),
                "resolved": self._finding_records(self.resolved_findings, "RESOLVED"),
            },
            "recommendations": [
                {
                    "priority": "P0" if f.is_migration_blocker or f.blocks_ir else "P1",
                    "action": f.recommendation or f.message,
                    "reason": f.explanation or f.classification_reason or f.message,
                }
                for f in all_findings
                if f.recommendation or f.is_migration_blocker or f.blocks_ir
            ],
            "scan_metadata": {
                "analyzer_version": "1.1.0",
                "project_key": self.project_key,
                "roslyn_enabled": bool(self.semantic_analysis.get("available")),
                "build_verified": self.build_verified,
            },
            "health": {
                "projectKey": self.project_key,
                "verification": {
                    "new": [x.to_dict() for x in self.new_findings],
                    "persisting": [x.to_dict() for x in self.persisting_findings],
                    "resolved": [x.to_dict() for x in self.resolved_findings],
                },
                "status": self.status,
                "buildVerified": self.build_verified,
                "buildTool": self.build_tool,
                "semanticAnalysis": self.semantic_analysis,
                "summary": {
                    "migrationBlockers": len(self.migration_blockers),
                    "irBlockingPrerequisites": sum(1 for x in self.blockers if x.blocks_ir),
                    "warnings": sum(1 for x in all_findings if x.classification == "WARNING"),
                    "technicalDebt": sum(1 for x in all_findings if x.classification == "TECHNICAL_DEBT"),
                    "intentionalDependencies": sum(1 for x in all_findings if x.classification == "INTENTIONAL_DEPENDENCY"),
                    "manualReviews": sum(1 for x in all_findings if x.classification == "MANUAL_REVIEW"),
                },
                "blockingPrerequisites": [x.to_dict() for x in self.blockers],
                "migrationBlockers": [x.to_dict() for x in self.migration_blockers],
                "risks": [x.to_dict() for x in self.risks],
                "integrityIssues": [x.to_dict() for x in self.integrity_issues],
                "filesRequiringAttention": self.attention_files,
            },
        }
