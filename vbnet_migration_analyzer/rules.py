from __future__ import annotations
import re
from pathlib import Path
from .models import Finding

# (id, title, severity, is_blocker, pattern)
# `id` is internal routing only (picks the right guidance text and keeps test
# assertions precise) -- it is never shown in the report or the JSON output.
RULES = [
    ("MIG-001", "COM dependency", "HIGH", True,
     re.compile(r"\bCOMReference\b|\bCreateObject\s*\(|(?<![.\w])GetObject\s*\(|\bGetTypeFromProgID\b", re.I)),
    ("MIG-002", "Windows-specific API", "HIGH", False,
     re.compile(r"\bMicrosoft\.Win32\b|\bRegistryKey\b|\bMy\.Computer\.Registry\b"
                r"|\bSendKeys\b|\bSystem\.Management\b|\bSystem\.ServiceProcess\b", re.I)),
    ("MIG-003", "P/Invoke or native dependency", "HIGH", True,
     re.compile(r"\bDllImport\b|\bDeclare\s+(Auto|Unicode|Ansi)?\s*(Sub|Function)\b", re.I)),
    ("MIG-004", "Legacy database provider", "MEDIUM", False,
     re.compile(r"System\.Data\.SqlClient|OleDb|Odbc|\bADODB\b|OracleClient|Microsoft\.Jet", re.I)),
    ("MIG-005", "Hard-coded Windows path", "MEDIUM", False,
     re.compile(r'(?<![A-Za-z0-9_])[A-Za-z]:[\\/]{1,2}[^"\r\n]*|(?<=")\\\\[\w.\-]+\\[\w$.\-]+')),
    ("MIG-006", "Legacy Web/Remoting dependency", "HIGH", True,
     re.compile(r"System\.Web|System\.Runtime\.Remoting|WebClient", re.I)),
    ("MIG-007", "Binary serialization (BinaryFormatter)", "HIGH", True,
     re.compile(r"\bBinaryFormatter\b", re.I)),
    ("MIG-009", "Enterprise Services / COM+ dependency", "HIGH", True,
     re.compile(r"\bSystem\.EnterpriseServices\b|\bServicedComponent\b", re.I)),
    ("MIG-010", "Multi-AppDomain usage", "HIGH", True,
     re.compile(r"\bAppDomain\.CreateDomain\b", re.I)),
    ("MIG-011", "WCF (System.ServiceModel) dependency", "HIGH", False,
     re.compile(r"\bSystem\.ServiceModel\b", re.I)),
    ("MIG-012", "Hard-coded credential", "HIGH", False,
     re.compile(r'(?<=[";])\s*(?:password|pwd)(?![A-Za-z])\s*=\s*[^;"\s][^;"]*(?=[;"])', re.I)),
]


def strip_vb_comments(text: str) -> str:
    """Blank out VB comments while keeping offsets and line numbers identical."""
    def blank(s: str) -> str:
        return re.sub(r"[^\r]", " ", s)

    out = []
    for line in text.split("\n"):
        if re.match(r"\s*rem(\s|$)", line, re.I):
            out.append(blank(line))
            continue
        in_string = False
        for i, ch in enumerate(line):
            if ch == '"':
                in_string = not in_string
            elif ch == "'" and not in_string:
                line = line[:i] + blank(line[i:])
                break
        out.append(line)
    return "\n".join(out)


def analyze_vb_file(path: Path, text: str, display_path: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    code = strip_vb_comments(text)
    lines = text.split("\n")
    shown = display_path or path.as_posix()
    for rid, title, severity, blocker, pattern in RULES:
        matches = list(pattern.finditer(code))
        if not matches:
            continue
        line_no = text.count("\n", 0, matches[0].start()) + 1
        evidence = lines[line_no - 1].strip()[:300]
        findings.append(Finding(rid, "migration", severity, title,
                                f"Migration-impacting construct detected in {path.name}.",
                                shown, evidence, blocker, line_no, len(matches)))
    return findings
