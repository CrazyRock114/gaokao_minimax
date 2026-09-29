#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复刻外部审查报告 §7.3 audit_l3.py 的渲染不变量，独立实现、不 import 仓库代码。
用于确认 P1 修复没有破坏其他渲染/选项/图引用不变量。"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
man = json.load(open(SITE / "data" / "manifest.json"))
fails = []


def ck(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        fails.append(f"{label} {detail}")


def math_spans(h):
    return (re.findall(r"\\\((.+?)\\\)", h, re.S) + re.findall(r"\\\[(.+?)\\\]", h, re.S))


shards = {y: json.load(open(SITE / "data" / "p" / f"{y}.json")) for y in man["years"]}

print("== L3.1 数学定界符平衡 ==")
unbal = []
for y, arr in shards.items():
    for r in arr:
        for fld in ("ph", "ah", "sh"):
            h = r.get(fld) or ""
            # \<len> is LaTeX row spacing, not a display-math delimiter
            h = re.sub(r"\\\\\[[^\]]*\]", "", h)
            if h.count("\\(") != h.count("\\)") or h.count("\\[") != h.count("\\]"):
                unbal.append((r["id"], fld))
ck("题干/答案/解析 \\( \\) \\[ \\] 全部成对", not unbal, f"{len(unbal)} 例 {unbal[:3]}")

print("== L3.2 '<' 是否破坏 HTML（P1 疫苗）==")
danger = lt_any = 0
for y, arr in shards.items():
    for r in arr:
        for fld in ("ph", "ah", "sh"):
            for body in math_spans(r.get(fld) or ""):
                if "<" in body or ">" in body:
                    lt_any += 1
                if re.search(r"[<>]\s*[a-zA-Z]", body):
                    danger += 1
ck("数学段内无裸 < 或 >", danger == 0, f"危险 {danger} / 含裸符号 {lt_any}")

print("== L3.3 正文(非数学非标签)无裸 < ==")
bare = 0
for y, arr in shards.items():
    for r in arr:
        h = r.get("ph") or ""
        s = re.sub(r"\\\(.+?\\\)|\\\[.+?\\\]", "", h, flags=re.S)
        s = re.sub(r"<[^>]+>", "", s)
        if "<" in s:
            bare += 1
ck("正文无裸 <", bare == 0, str(bare))

print("== L3.4 选项与答案完整性 ==")
ch_lens = Counter()
no_opts = flagged = 0
oob = []
for y, arr in shards.items():
    for r in arr:
        ch = r.get("ch") or []
        if ch:
            ch_lens[len(ch)] += 1
        if str(r.get("ty", "")).startswith("choice") and not ch:
            no_opts += 1
            if "options_missing" in (r.get("dg") or []):
                flagged += 1
        a = (r.get("af") or "").strip()
        m = re.fullmatch(r"\(?([A-F]{1,4})\)?[.．]?", a)
        if m and ch and any(ord(c) - 65 >= len(ch) for c in m.group(1)):
            oob.append((r["id"], a, len(ch)))
ck("选项数 ∈ {4,5}", set(ch_lens) <= {4, 5}, str(dict(ch_lens)))
ck("无选项选择题全部带 options_missing", no_opts == flagged, f"{no_opts}/{flagged}")
ck("答案字母不越选项界", not oob, str(oob[:3]))

print("== L3.5 图引用闭合 ==")
bad_link = bad_img = 0
for y, arr in shards.items():
    for r in arr:
        for fld in ("ph", "sh"):
            h = r.get(fld) or ""
            for m in re.finditer(r'<a href="([^"]+)"', h):
                if not (SITE / m.group(1)).exists():
                    bad_link += 1
            for m in re.finditer(r'<img[^>]+src="([^"]+)"', h):
                if not (SITE / m.group(1)).exists():
                    bad_img += 1
        for c in r.get("ch") or []:
            for m in re.finditer(r'<img[^>]+src="([^"]+)"', c):
                if not (SITE / m.group(1)).exists():
                    bad_img += 1
ck("ph/sh <a href> 目标全部存在", bad_link == 0, str(bad_link))
ck("全部 <img src> 目标存在", bad_img == 0, str(bad_img))

print()
print(f"*** L3: {len(fails)} FAILURE(S) ***")
for f in fails:
    print("   -", f)
sys.exit(1 if fails else 0)
