#!/usr/bin/env python3
"""Scan all content LaTeX for macro usage so we can build a correct
LaTeX -> MathJax conversion map. Writes a report to data/macro_report.json."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "vendor_dxathing" / "content"

MACRO_RE = re.compile(r"\\([a-zA-Z]+)")
CMD_RE = re.compile(r"\\([a-zA-Z]+)\s*(?:\[[^\]]*\])?\s*\{", re.S)

macros = Counter()
cmds = Counter()
envs = Counter()
files = sorted(CONTENT.rglob("*.tex"))
for f in files:
    s = f.read_text(encoding="utf-8", errors="replace")
    for m in MACRO_RE.finditer(s):
        macros[m.group(1)] += 1
    for m in CMD_RE.finditer(s):
        cmds[m.group(1)] += 1
    for m in re.finditer(r"\\begin\{([a-zA-Z*]+)\}", s):
        envs[m.group(1)] += 1

out = {
    "n_files": len(files),
    "macros": macros.most_common(),
    "commands_with_arg": cmds.most_common(),
    "environments": envs.most_common(),
}
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "macro_report.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("files:", len(files))
print("distinct macros:", len(macros))
print()
print("--- top macros ---")
for k, v in macros.most_common(60):
    print(f"{v:7d}  \\{k}")
