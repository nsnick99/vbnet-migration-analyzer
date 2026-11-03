from __future__ import annotations

from .models import Finding

_GUIDANCE = {
    "INT-001": ("REAL_BLOCKER", True, "Fix the project file XML before continuing.", "Re-run the analyzer and confirm the project parses."),
    "INT-002": ("REAL_BLOCKER", True, "Restore the missing file or remove the stale project item.", "Re-run the analyzer and confirm the missing-item finding is gone."),
    "INT-003": ("REAL_BLOCKER", True, "Restore the referenced project or correct the ProjectReference path.", "Re-run the analyzer and confirm the reference resolves."),
    "INT-004": ("REAL_BLOCKER", True, "Restore the referenced assembly or replace it with a supported dependency.", "Re-run the analyzer and verify the HintPath resolves."),
    "INT-005": ("REAL_BLOCKER", True, "Restore or remove the missing imported build file.", "Re-run the analyzer and verify the import resolves."),
    "INT-006": ("TECHNICAL_DEBT", False, "Add the source file to the classic project or remove the orphan file.", "Re-run the analyzer and confirm project inventory is complete."),
    "INT-007": ("MANUAL_REVIEW", False, "Analyze each project separately or confirm the selected project is the intended entry point.", "Re-run against the intended project."),
    "INT-008": ("REAL_BLOCKER", True, "Fix malformed configuration XML before migration analysis.", "Re-run and confirm configuration parses."),
    "INT-009": ("REAL_BLOCKER", True, "Rename case-colliding files so their names are unique across case-sensitive environments.", "Re-run and confirm no case collision remains."),
    "INT-010": ("TECHNICAL_DEBT", False, "Remove duplicate project item declarations.", "Re-run and confirm the duplicate declaration is gone."),
    "INT-011": ("MANUAL_REVIEW", True, "Restore access to the unreadable source file so it can be analyzed.", "Re-run and confirm the file is readable."),
    "INT-012": ("MANUAL_REVIEW", False, "Spot-check legacy encoded source and convert it to UTF-8 when practical.", "Re-run and confirm encoding is understood."),
    "INT-013": ("TECHNICAL_DEBT", False, "Remove or populate the empty declared file.", "Re-run and confirm the file is no longer empty."),
    "MIG-001": ("REAL_BLOCKER", True, "Assess COM/ActiveX compatibility and retain, isolate, or replace the dependency.", "Re-run after the dependency decision and compatibility test."),
    "MIG-002": ("WARNING", False, "Review Windows-specific APIs and isolate them where portability is required.", "Re-run and verify target-sensitive usage is understood."),
    "MIG-003": ("REAL_BLOCKER", True, "Review native/P/Invoke dependencies and provide a supported target-runtime strategy.", "Re-run and test the native integration on the target runtime."),
    "MIG-004": ("TECHNICAL_DEBT", False, "Review the database provider and migrate to a supported provider where required.", "Re-run and verify provider compatibility."),
    "MIG-005": ("TECHNICAL_DEBT", False, "Move environment-specific paths into configuration or platform-aware path APIs.", "Re-run and confirm path assumptions are documented."),
    "MIG-006": ("REAL_BLOCKER", True, "Replace or redesign legacy System.Web/Remoting dependencies for modern .NET.", "Re-run and validate the replacement architecture."),
    "MIG-007": ("REAL_BLOCKER", True, "Replace BinaryFormatter with a supported serialization mechanism.", "Re-run and test serialization compatibility."),
    "MIG-008": ("INTENTIONAL_DEPENDENCY", False, "Verify the third-party assembly is available and supported on the target runtime.", "Confirm package/assembly compatibility before retargeting."),
    "MIG-009": ("REAL_BLOCKER", True, "Replace Enterprise Services/COM+ dependencies with a supported design.", "Re-run and test the replacement behavior."),
    "MIG-010": ("REAL_BLOCKER", True, "Redesign multi-AppDomain usage for modern .NET process/component isolation.", "Re-run and validate the replacement isolation model."),
    "MIG-011": ("MANUAL_REVIEW", False, "Determine whether WCF usage is client-side or server-side and choose an appropriate migration path.", "Test the selected CoreWCF/HTTP/gRPC or other replacement."),
    "MIG-012": ("WARNING", False, "Move credentials into secure configuration or a secret-management mechanism.", "Re-run and confirm no credentials remain embedded in source."),
    "MIG-013": ("REAL_BLOCKER", True, "Plan a framework modernization from .NET Framework to modern .NET and validate every dependency against the selected target.", "Re-run after selecting the target framework and verify the project/dependencies build on it."),
    "BLD-002": ("REAL_BLOCKER", True, "Resolve the local build/toolchain failure before relying on build verification.", "Re-run with the required local SDK/targeting pack installed."),
    "BLD-003": ("REAL_BLOCKER", True, "Investigate the non-zero build result, including SDK, targeting pack, package, and build dependencies.", "Re-run the build and confirm a successful exit code."),
    "ROS-000": ("REAL_BLOCKER", True, "Build or install the local Roslyn sidecar when semantic analysis is required.", "Re-run with --roslyn on and confirm semantic analysis is available."),
}


def apply_guidance(finding: Finding) -> Finding:
    data = _GUIDANCE.get(finding.id)
    if data:
        classification, blocks_ir, recommendation, verification = data
        finding.classification = classification
        finding.blocks_ir = blocks_ir
        finding.recommendation = finding.recommendation or recommendation
        finding.verification = finding.verification or verification
        finding.classification_reason = finding.classification_reason or classification.replace("_", " ").title()
        if classification == "REAL_BLOCKER":
            finding.blocker_scope = "MIGRATION" if finding.category == "migration" else "IR_READINESS"
            finding.manual_review_required = False
        elif classification == "MANUAL_REVIEW":
            finding.manual_review_required = True
    else:
        finding.classification = finding.classification or "MANUAL_REVIEW"
        finding.manual_review_required = True
        finding.classification_reason = finding.classification_reason or "No specific guidance rule was available."
    return finding
