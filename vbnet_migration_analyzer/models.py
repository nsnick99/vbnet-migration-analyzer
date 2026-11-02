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

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": asdict(self.project),
            "fileSummary": {"totalFiles": self.total_files, "fileTypes": self.file_types},
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
                    "warnings": sum(1 for x in self.all_findings if x.classification == "WARNING"),
                    "technicalDebt": sum(1 for x in self.all_findings if x.classification == "TECHNICAL_DEBT"),
                    "intentionalDependencies": sum(1 for x in self.all_findings if x.classification == "INTENTIONAL_DEPENDENCY"),
                    "manualReviews": sum(1 for x in self.all_findings if x.classification == "MANUAL_REVIEW"),
                },
                "blockingPrerequisites": [x.to_dict() for x in self.blockers],
                "migrationBlockers": [x.to_dict() for x in self.migration_blockers],
                "risks": [x.to_dict() for x in self.risks],
                "integrityIssues": [x.to_dict() for x in self.integrity_issues],
                "filesRequiringAttention": self.attention_files,
            },
        }
