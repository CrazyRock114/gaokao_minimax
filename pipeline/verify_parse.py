#!/usr/bin/env python3
"""Verify parse completeness: compare \\begin{problem} occurrences in source
against records emitted per file, and report exact discrepancies."""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "vendor_dxathing" / "content"

src_count = Counter()
for f in sorted(CONTENT.rglob("*.tex")):
    s = f.read_text(encoding="utf-8", errors="replace")
    src_count[f.relative_to(CONTENT).as_posix()] = len(re.findall(r"\\begin\{problem\}", s))

got = Counter()
sol = Counter()
ans = Counter()
fig = Counter()
with (ROOT / "data" / "problems.jsonl").open(encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        y, fname = r["id"].split("|")[0], r["id"].split("|")[1]
        key = f"{y}/{fname}"
        got[key] += 1
        sol[key] += 1 if r["has_solution"] else 0
        ans[key] += 1 if r["has_answer"] else 0
        fig[key] += 1 if r["has_figure"] else 0

print(f"{'file':46s} {'src':>5s} {'got':>5s} {'diff':>5s}")
diffs = []
for k, v in src_count.items():
    g = got.get(k, 0)
    if g != v:
        diffs.append((k, v, g))
diffs.sort(key=lambda x: -(x[1] - x[2]))
for k, v, g in diffs[:25]:
    print(f"{k:46s} {v:5d} {g:5d} {g - v:+5d}")
print(f"\nfiles with mismatch: {len(diffs)} / {len(src_count)}")
print(f"total src={sum(src_count.values())} got={sum(got.values())} "
      f"missing={sum(src_count.values()) - sum(got.values())}")
