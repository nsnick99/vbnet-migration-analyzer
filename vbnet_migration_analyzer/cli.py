from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .analyzer import analyze, verify_resolution
from .report import text_report, json_report
from .critical_report import critical_json_report
import json


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Analyze a VB.NET application for project health, integrity, and migration blockers."
    )
    parser.add_argument("path", help="VB.NET application directory or .vbproj path")
    parser.add_argument("--no-build", action="store_true", help="Skip local MSBuild/dotnet build verification")
    parser.add_argument("--roslyn", choices=("auto", "on", "off"), default="auto",
                        help="Roslyn semantic analysis mode: auto (use when locally compiled), on (required), or off")
    args = parser.parse_args()

    try:
        result = analyze(Path(args.path), run_build=not args.no_build, roslyn_mode=args.roslyn)
    except Exception as exc:
        print(f"Analyzer failed: {exc}")
        return 2

    report_path = Path("migration-report.txt")
    json_path = Path("project-health.json")
    critical_path = Path("critical_updates.json")
    previous = None
    try:
        if json_path.exists():
            previous = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        previous = None
    result = verify_resolution(result, previous)

    report = text_report(result)
    report_path.write_text(report, encoding="utf-8")
    json_path.write_text(json_report(result), encoding="utf-8")
    critical_path.write_text(critical_json_report(result), encoding="utf-8")

    print("Analysis completed.")
    print(f"Health status: {result.status}")
    print(f"Report: {report_path.resolve()}")
    print(f"Health JSON: {json_path.resolve()}")
    print(f"Critical JSON: {critical_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
