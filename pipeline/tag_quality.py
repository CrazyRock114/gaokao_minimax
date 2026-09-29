#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tagging-quality report.

Deliberately does NOT try to auto-grade correctness: a keyword-presence test
over the full text (which includes the solution) flags almost every problem
as "competing" and produces a meaningless number. Instead it reports the
hard, checkable facts and prints a fixed sample for human adjudication.

    python3 pipeline/tag_quality.py 40
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 20260930

recs = [json.loads(l) for l in (ROOT / "data" / "problems_rich.jsonl").open(encoding="utf-8")]
N_all = len(recs)

print("=== 硬指标 ===")
un = [r for r in recs if not r["knowledge"]]
print(f"题数                      {N_all:,}")
print(f"无任何知识点标签          {len(un):,} ({len(un)/N_all*100:.2f}%)")
print(f"平均标签数/题             {sum(r['n_knowledge'] for r in recs)/N_all:.2f}")
print(f"仅 1 个标签的题           {sum(1 for r in recs if r['n_knowledge']==1):,}")
print(f"标签数达上限 8 的题       {sum(1 for r in recs if r['n_knowledge']>=8):,}")
cross = sum(1 for r in recs for k in r["knowledge"] if k.get("cross_track"))
print(f"文理越界标签(理科词入文科) {cross:,} ({cross/N_all*100:.2f}%)")

print()
print("=== 主标签分布 Top 15 ===")
prim = Counter(r["knowledge"][0]["code"] if r["knowledge"] else "NONE" for r in recs)
KNAME = {k["code"]: k["name"] for k in __import__("taxonomy").KNOWLEDGE}
for c, n in prim.most_common(15):
    print(f"  {n:6,} ({n/N_all*100:4.1f}%)  {KNAME.get(c,c)}")
tail = prim.most_common()[-6:]
print("  ... 最少命中的 6 个:")
for c, n in tail:
    print(f"  {n:6,} ({n/N_all*100:4.2f}%)  {KNAME.get(c,c)}")

print()
print("=== 66 个知识点中从未成为主标签的数量 ===")
never = [c for c in KNAME if c not in prim]
print(f"  {len(never)} 个: {[KNAME[c] for c in never]}")

print()
print(f"=== 人工裁决样本 (n={N}, seed={SEED}) ===")
print("只打印题干（不含解析），请人工判断主标签是否合理：")
random.seed(SEED)
for i, r in enumerate(random.sample(recs, min(N, N_all)), 1):
    pk = r["knowledge"][0]["name"] if r["knowledge"] else "** 未打标 **"
    stem = (r["plain"] or "").split("。")[0][:72]
    print(f"{i:3d}. {r['year']} {r['track_cn']:3s} | {pk:22s} | {stem}")
