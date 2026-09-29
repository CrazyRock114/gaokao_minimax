#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full-corpus acceptance check. Exits non-zero if any invariant fails.

Covers: parse completeness, unique ids, env-tag leakage, escaped-% truncation,
choice/answer integrity, rendering, figure coverage, manifest consistency,
knowledge-tag coverage. Run after every pipeline change.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
CONTENT = ROOT / "vendor_dxathing" / "content"
BS = chr(92)

fails, warns = [], []


def ck(label, cond, detail=""):
    if cond:
        print(f"  PASS  {label}" + (f"  ({detail})" if detail else ""))
    else:
        fails.append(f"{label} {detail}")
        print(f"  FAIL  {label}  {detail}")


print("== 1. 解析完整性 ==")
recs = [json.loads(l) for l in (ROOT / "data" / "problems.jsonl").open(encoding="utf-8")]
N = len(recs)
src = 0
for f in CONTENT.rglob("*.tex"):
    src += len(re.findall(r"\\begin\{problem\}", f.read_text(encoding="utf-8", errors="replace")))
ck("题数 = 源 \\begin{problem} 数", N == src == 16273, f"parsed={N} src={src}")
ids = [r["id"] for r in recs]
ck("ID 唯一", len(set(ids)) == N, f"{N - len(set(ids))} duplicates")

print("== 2. 文本完整性 ==")
ck("无环境标签残留", not [r for r in recs
                    if re.search(r"\\(?:begin|end)\{problem\}", r["problem_tex"])])
trunc = sum(1 for r in recs for f in ("problem_tex", "solution_tex", "answer_tex")
            if r[f].rstrip().endswith(BS))
ck("无 \\% 截断（字段不以裸反斜杠结尾）", trunc == 0, f"{trunc} truncated fields")
ck("题干非空", all(r["problem_tex"].strip() for r in recs))

rich = [json.loads(l) for l in (ROOT / "data" / "problems_rich.jsonl").open(encoding="utf-8")]

print("== 3. 选项与答案 ==")
ch = [r for r in recs if r["choices"]]
missing_ch = [r for r in recs if r["section_type"].startswith("choice") and not r["choices"]]
rich_by_id = {r["id"]: r for r in rich}
ck("未带选项的选择题均已标记为上游缺口",
   all("options_missing" in rich_by_id[r["id"]]["data_gaps"] for r in missing_ch),
   f"{len(missing_ch)} upstream gaps (not a pipeline bug)")
ck("选项数均为 4 或 5", all(len(r["choices"]) in (4, 5) for r in ch),
   str(Counter(len(r["choices"]) for r in ch)))

print("== 4. 站点数据 ==")
ck("rich 记录数一致", len(rich) == N)
mf = json.loads((SITE / "data" / "manifest.json").read_text(encoding="utf-8"))
ck("manifest.total 一致", mf["total"] == N)
bad = [1 for c in mf["chapters"] for p in c["points"]
       if p["count"] != mf["facets"]["point"].get(p["code"])]
ck("章节→知识点计数 = 知识点 facet", not bad, f"{len(bad)} mismatched cells")
for g in ("region", "track", "type", "diff"):
    truth = sum(mf["facets"][g].values())
    ck(f"单值 facet {g} 合计 = {N}", truth == N, f"{truth}")
# chapter/point are MULTI-LABEL: a problem contributes once per chapter it
# touches and once per knowledge point, so their totals legitimately exceed N.
for g in ("chapter", "point"):
    truth = sum(mf["facets"][g].values())
    ck(f"多值 facet {g} 合计在 [N, 8N] 内", N <= truth <= 8 * N, f"{truth}")
ck("多值 facet 不超过 8N（标签上限生效）",
   max(len(r["k"]) for r in
       json.loads((SITE / "data" / "index.json").read_text(encoding="utf-8"))) <= 8)

print("== 5. 渲染 ==")
sys.path.insert(0, str(ROOT / "pipeline"))
import latex_render as LR  # noqa: E402
outside = 0
for r in rich:
    for f in ("problem_html", "solution_html", "answer_html"):
        for seg, is_math, _d in LR.split_math(r.get(f) or ""):
            if not is_math and re.search(r"\\(hspace|underline|overrightarrow|mathbb|mathbf|mathrm)\b", seg):
                outside += 1
ck("无落在数学定界符外的裸宏", outside == 0, f"{outside}")

print("== 6. 题图 ==")
refs = set()
for r in rich:
    refs |= set(r.get("figures", [])) | set(r.get("figures_solution", []))
    for c in r.get("choices_html", []):
        refs |= set(re.findall(r'<img[^>]+src="([^"]+)"', c))
on_disk = {p.relative_to(SITE).as_posix() for root in ("img", "img_repaint")
           for p in (SITE / root).rglob("*") if p.is_file()}
ck("被引用的图全部存在", refs <= on_disk, f"missing {len(refs - on_disk)}")
ck("站点无冗余图", on_disk <= refs, f"extra {len(on_disk - refs)}")
ck("图来源全部可追溯", all((ROOT / "vendor_dxathing" / f).exists() for f in refs))
ck("manifest.assets 与实际一致",
   mf["assets"]["referenced"] == len(refs) and mf["assets"]["missing"] == 0,
   str(mf["assets"]))

print("== 6.5 数学段内危险字符（P1 疫苗）==")
# The HTML parser runs before MathJax, so a bare '<' + letter inside a math
# span is eaten as a tag start and the formula silently never renders.
# This was a blind spot: the older check only looked the OTHER way (macros
# leaking OUTSIDE math).
danger = 0
for r in rich:
    for f in ("problem_html", "solution_html", "answer_html"):
        for seg, is_math, _d in LR.split_math(r.get(f) or ""):
            if is_math and ("<" in seg or ">" in seg):
                danger += 1
ck("数学段内无裸 < 或 >（HTML 吞标签）", danger == 0, f"{danger} 段")

print("== 7. 知识点 ==")
un = sum(1 for r in rich if not r["knowledge"])
ck("标签覆盖率 ≥ 95%", un / N <= 0.05, f"untagged {un} ({un/N*100:.1f}%)")
ck("每题至多 8 个标签", all(r["n_knowledge"] <= 8 for r in rich))
ck("难度均在 1..5", all(1 <= r["difficulty"] <= 5 for r in rich))
ck("derived 答案已刷新 has_answer",
   all(r["has_answer"] == bool(r["answer_tex"].strip())
       for r in rich if r["answer_status"] == "derived"))

print("== 7.5 搜索字段完整性 ==")
idxj = json.loads((SITE / "data" / "index.json").read_text(encoding="utf-8"))
ck("index 记录含全文检索字段 pl", all("pl" in r for r in idxj))
ck("pl 覆盖 pl/stem 两种来源", sum(1 for r in idxj if r.get("pl")) == N)
ck("地区 facet 全部 33 个可筛（不再截断 16）",
   len(idxj and {r["r"] for r in idxj}) == 33)

print("== 8. 元数据 ==")
ck("无空地区", all(r["region_cn"] for r in recs))
ck("无 other: 地区", not [r for r in recs if r["region"].startswith("other:")])
ck("年份范围合理", min(r["year"] for r in recs) == 1952
   and max(r["year"] for r in recs) == 2026)

print()
if fails:
    print(f"*** {len(fails)} FAILURE(S) ***")
    for f in fails:
        print("   -", f)
    raise SystemExit(1)
print("ALL ACCEPTANCE CHECKS PASSED")
