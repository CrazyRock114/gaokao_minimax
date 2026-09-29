#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manual-audit helper: print a random sample with primary tag so the tagging
can be eyeballed, and report the objective coverage figures."""
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42

recs = [json.loads(l) for l in (ROOT / "data" / "problems_rich.jsonl").open(encoding="utf-8")]
random.seed(seed)
un = [r for r in recs if not r["knowledge"]]
print(f"total={len(recs)}  untagged={len(un)} ({len(un)/len(recs)*100:.1f}%)")
print(f"tags/problem: mean={sum(r['n_knowledge'] for r in recs)/len(recs):.2f}\n")
for r in random.sample(recs, n):
    pk = r["knowledge"][0] if r["knowledge"] else None
    print(f"{r['year']} {r['region_cn']:5s} {r['track_cn']:3s} {r['section_type_cn']:6s} "
          f"d{r['difficulty']} -> {pk['name'][:18] if pk else '** NONE **':20s} | {r['plain'][:72]}")
