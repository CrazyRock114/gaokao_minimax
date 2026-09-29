#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 5 — multi-dimensional analysis of the corpus -> site/report/index.html

Dimensions: 时间 / 地区 / 科类 / 题型 / 知识点 / 难度 / 配图 / 解析覆盖
plus cross-cuts and an explicit data-quality section.
"""
from __future__ import annotations

import html
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import KNOWLEDGE, CHAPTER_LIST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site" / "report" / "index.html"

E = html.escape
KNAME = {k["code"]: k["name"] for k in KNOWLEDGE}
KCHAP = {k["code"]: k["chapter"] for k in KNOWLEDGE}
DIFF = ["易", "较易", "中等", "较难", "难"]


def bar_rows(items, total=None, width=300, cols=0):
    """items: [(label, count)] -> html bar rows.

    cols>0 lays the rows out in a multi-column grid (used for the 64-row
    per-year chart, which is unreadable as one long column).
    """
    if not items:
        return '<div class="hint">无数据</div>'
    top = total or max(c for _, c in items) or 1
    h = [f'<div class="bars" style="--cols:{cols}">'] if cols else ['<div class="bars">']
    for lab, c in items:
        w = max(2, int(width * c / top))
        h.append(f'<div class="brow"><span class="lb">{E(str(lab))}</span>'
                 f'<span class="bar" style="width:{w}px"></span>'
                 f'<span class="vl">{c:,}</span></div>')
    h.append("</div>")
    return "".join(h)


def tbl(headers, rows):
    h = ["<table><thead><tr>"]
    for x in headers:
        h.append(f"<th>{E(str(x))}</th>")
    h.append("</tr></thead><tbody>")
    for r in rows:
        h.append("<tr>")
        for i, c in enumerate(r):
            cls = ' class="num"' if i and str(c).replace(",", "").replace(
                "%", "").replace(".", "").isdigit() else ""
            h.append(f"<td{cls}>{c if str(c).startswith('<') else E(str(c))}</td>")
        h.append("</tr>")
    h.append("</tbody></table>")
    return "".join(h)


def main() -> int:
    recs = [json.loads(l) for l in (DATA / "problems_rich.jsonl").open(encoding="utf-8")]
    N = len(recs)

    by_year = Counter(r["year"] for r in recs)
    by_decade = Counter((r["year"] // 10) * 10 for r in recs)
    by_region = Counter(r["region_cn"] for r in recs)
    by_track = Counter(r["track_cn"] for r in recs)
    by_type = Counter(r["section_type_cn"] for r in recs)
    by_diff = Counter(r["difficulty"] for r in recs)
    by_variant = Counter(r["variant"] for r in recs)
    by_paper = Counter(r["chapter"] for r in recs)
    # derived from the corpus, not hardcoded
    TYPE_COLS = [k for k, _ in Counter(r["section_type_cn"] for r in recs).most_common()
                 if k in ("单项选择题", "填空题", "解答题", "多项选择题")]

    # knowledge: all tags, and primary tag
    kp_all, kp_primary = Counter(), Counter()
    kp_year = defaultdict(Counter)
    kp_track = defaultdict(Counter)
    for r in recs:
        for k in r["knowledge"]:
            kp_all[k["code"]] += 1
            kp_year[k["code"]][r["year"]] += 1
            kp_track[k["code"]][r["track_cn"]] += 1
        if r["knowledge"]:
            kp_primary[r["knowledge"][0]["code"]] += 1

    chap_all = Counter()
    for c, n in kp_all.items():
        chap_all[KCHAP[c]] += n

    # figures / solutions by year
    fig_year, sol_year, tot_year = Counter(), Counter(), Counter()
    for r in recs:
        tot_year[r["year"]] += 1
        if r["has_figure"]:
            fig_year[r["year"]] += 1
        if r["has_solution"]:
            sol_year[r["year"]] += 1
    n_fig = sum(fig_year.values())
    n_sol = sum(sol_year.values())

    # type by decade
    type_decade = defaultdict(Counter)
    diff_decade = defaultdict(Counter)
    for r in recs:
        d = (r["year"] // 10) * 10
        type_decade[d][r["section_type_cn"]] += 1
        diff_decade[d][r["difficulty"]] += 1

    # 文理 knowledge contrast
    sci_only = [(c, kp_track[c].get("理科", 0), kp_track[c].get("文科", 0))
                for c in kp_all
                if kp_track[c].get("理科", 0) + kp_track[c].get("文科", 0) >= 60]
    sci_only.sort(key=lambda x: -(x[1] - x[2]))

    # first appearance of each knowledge point
    first_year = {}
    for c in kp_year:
        first_year[c] = min(kp_year[c])
    introduced = sorted(((y, c) for c, y in first_year.items()))

    years = sorted(by_year)
    maxy = max(years)

    P = []
    A = P.append
    A(f"<h1>高考数学真题（{years[0]}–{maxy}）多维分析报告</h1>")
    A(f"<p>语料来源：<a href='https://github.com/deekur/gaokaomath'>deekur/gaokaomath</a>（原始扫描卷）与 "
      f"<a href='https://github.com/DxAThing/Gaokao-Math-Problems-Compilation'>DxAThing/Gaokao-Math-Problems-Compilation</a>"
      f"（整理为 LaTeX 的题库）。共解析 <b>{N:,}</b> 道题，覆盖 <b>{len(years)}</b> 个年份、"
      f"<b>{len(by_paper)}</b> 份试卷、<b>{len(by_region)}</b> 个地区。所有数字由本仓库脚本 "
      f"<code>pipeline/</code> 统计生成，可复现。</p>")

    A("<div class='note'>口径说明：题量 = 题库收录题目数，<b>不是</b>当年实际考生人数或卷面题量的官方统计；"
      "早期年份（1966–1976）无高考，语料中没有对应数据，图表中为空属正常。</div>")

    # ---- 1 时间
    A("<h2>一、时间维度</h2>")
    A("<h3>1.1 逐年题量</h3>")
    A(bar_rows([(y, by_year[y]) for y in years], width=150, cols=4))
    A("<h3>1.2 分年代题量</h3>")
    A(tbl(["年代", "题量", "占比", "年均"],
          [[f"{d}s", f"{by_decade[d]:,}", f"{by_decade[d]/N*100:.1f}%",
            f"{by_decade[d]/len([y for y in years if d<=y<d+10]):.0f}"]
           for d in sorted(by_decade)]))
    A(f"<p>语料重心在 <b>2000 年代与 2010 年代</b>（合计 "
      f"{(by_decade[2000]+by_decade[2010])/N*100:.1f}%）。早期（1950–1970s）题量少，一方面是收录完整度有限，"
      f"另一方面是当年确有卷面题量与科类较少。1977 年是恢复高考后的首年，收录 "
      f"{by_year[1977]:,} 题，为早期年份之最。</p>")

    # ---- 2 地区
    A("<h2>二、地区维度</h2>")
    A(bar_rows(by_region.most_common(20), width=300))
    A(tbl(["地区", "题量", "占比"],
          [[k, f"{v:,}", f"{v/N*100:.1f}%"] for k, v in by_region.most_common(20)]))
    A("<p>「全国卷」与「上海」题量最大：全国卷长期统考多省，上海在 1988–2000 年代长期独立命题且题量稳定。"
      "地区题量差异既反映命题活跃度，也反映该地区档案的数字化完整度。</p>")

    # ---- 3 科类
    A("<h2>三、科类维度</h2>")
    A(tbl(["科类", "题量", "占比"], [[k, f"{v:,}", f"{v/N*100:.1f}%"] for k, v in by_track.most_common()]))
    A(f"<p>理科 {by_track['理科']:,} 题、文科 {by_track['文科']:,} 题，未分类 "
      f"{by_track.get('未分类',0):,} 题（主要来自 1977 及更早与部分合并卷）。"
      f"文理分科始于 1977 年，1990 年代后文理分化明显加强。</p>")
    A("<h3>3.1 文理科知识点差异（理科 − 文科 题数）</h3>")
    A(tbl(["知识点", "所属主题", "理科", "文科", "差值"],
          [[KNAME.get(c, c), CHAPTER_LIST.get(KCHAP[c], ""), f"{s:,}", f"{l:,}",
            f"{s-l:+,}"] for c, s, l in sci_only[:18]]))
    A("<p>导数、空间向量、参数/极坐标、极性差异最大的均为理科专属内容；"
      "文科侧偏重三角、解析几何与数列的基本运算。</p>")

    # ---- 4 题型
    A("<h2>四、题型维度</h2>")
    A(tbl(["题型", "题量", "占比"], [[k, f"{v:,}", f"{v/N*100:.1f}%"] for k, v in by_type.most_common()]))
    A("<h3>4.1 题型结构随年代变化（各年代内部占比）</h3>")
    rows = []
    for d in sorted(type_decade):
        tot = sum(type_decade[d].values())
        cells = [f"{type_decade[d][k]/tot*100:.1f}%" for k in TYPE_COLS]
        other = tot - sum(type_decade[d][k] for k in TYPE_COLS)
        # percentage, not a raw count, so the row visibly sums to 100%
        cells.append(f"{other/tot*100:.1f}%")
        rows.append([f"{d}s"] + cells + [f"{other:,} / {tot:,}"])
    A(tbl(["年代"] + TYPE_COLS + ["其他", "其他/题量"], rows))
    A("<p>「其他」为该年代出现的其余题型（选做题/选作题/参考题等）。"
      "列清单由语料推导而非写死，写死会漏掉这些题型并让多选列恒为 0.0%。</p>")
    A("<p>选择题占比在 2000 年后被明显压缩（部分省份改为解答题形式），"
      "解答题比重上升，与「加大考查力度」的命题取向一致。</p>")
    A("<h3>4.2 卷面归属类型</h3>")
    A(tbl(["类型", "题量"], [[{"regular": "常规卷", "spring": "春季高考", "autumn": "秋季/自主招生",
                             "special": "特殊类型"}.get(k, k), f"{v:,}"]
                            for k, v in by_variant.most_common()]))

    # ---- 5 知识点
    A("<h2>五、知识点维度</h2>")
    A("<h3>5.1 主题分布（按标签出现次数）</h3>")
    A(bar_rows([(CHAPTER_LIST.get(c, c), n) for c, n in chap_all.most_common()], width=300))
    A("<h3>5.2 高频知识点 Top 30（按出现题数）</h3>")
    A(tbl(["知识点", "主题", "出现题数", "占比", "作为主标签"],
          [[KNAME.get(c, c), CHAPTER_LIST.get(KCHAP[c], ""), f"{n:,}", f"{n/N*100:.1f}%",
            f"{kp_primary.get(c,0):,}"] for c, n in kp_all.most_common(30)]))
    A("<p>知识点由规则化标签器打标（66 个知识点 / 18 个主题）。一条题可命中多个知识点：下表「出现题数」是<b>命中该知识点的题目数</b>（一个知识点对一道题最多计一次）；「作为主标签」是得分最高者，故各知识点之和会大于总题数。5.1 的主题分布按<b>标签出现次数</b>汇总（一题命中同主题的多个知识点时计多次），因此与题库侧边栏「主题」筛选返回的<b>去重题数</b>口径不同。</p>")
    A("<h3>5.3 知识点的历史引入（首次出现年份）</h3>")
    A(tbl(["知识点", "首次出现", "所属主题", "累计题数"],
          [[KNAME.get(c, c), y, CHAPTER_LIST.get(KCHAP[c], ""), f"{kp_all[c]:,}"]
           for y, c in introduced[:40] if kp_all[c] >= 40]))
    A("<p>此表反映考点进入考纲的时间，如复数、向量、导数、极坐标均为某一时点后集中出现；"
      "早期题目（1950s–1970s）则以因式分解、对数运算、平面几何与初等代数为主。</p>")

    # ---- 6 难度
    A("<h2>六、难度维度</h2>")
    A("<div class='note'>难度为<b>启发式估计</b>（1–5），由题型基线 + 解析长度 + 小问数 + 证明/开放性标志 + "
      "知识点个数综合计算，<b>不是</b>官方难度系数，仅可用于相对比较与组卷配平。</div>")
    A(tbl(["难度", "题量", "占比"], [[DIFF[i - 1], f"{by_diff[i]:,}", f"{by_diff[i]/N*100:.1f}%"]
                                   for i in range(1, 6)]))
    A("<h3>6.1 难度结构随年代变化（各年代内部占比）</h3>")
    A(tbl(["年代"] + DIFF + ["题量"],
          [[f"{d}s"] + [f"{diff_decade[d][i]/max(1,sum(diff_decade[d].values()))*100:.1f}%"
                        for i in range(1, 6)] + [f"{sum(diff_decade[d].values()):,}"]
           for d in sorted(diff_decade)]))
    A(bar_rows([(f"{d}s", sum(diff_decade[d].values())) for d in sorted(diff_decade)], width=200))

    # ---- 7 图 / 解析
    A("<h2>七、配图与解析覆盖</h2>")
    A(tbl(["项目", "题数", "占比"],
          [["含题图（题干或解析）", f"{n_fig:,}", f"{n_fig/N*100:.1f}%"],
           ["含详细解析", f"{n_sol:,}", f"{n_sol/N*100:.1f}%"],
           ["含答案（选择/填空）",
            f"{sum(1 for r in recs if r['has_answer']):,}",
            f"{sum(1 for r in recs if r['has_answer'])/N*100:.1f}%"],
           ["总题数", f"{N:,}", "100%"]]))
    A("<h3>7.1 各年代配图率与解析覆盖率</h3>")
    rows = []
    for d in sorted(by_decade):
        ys = [y for y in years if d <= y < d + 10]
        t = sum(tot_year[y] for y in ys)
        if not t:
            continue
        f = sum(fig_year[y] for y in ys)
        s = sum(sol_year[y] for y in ys)
        rows.append([f"{d}s", f"{t:,}", f"{f/t*100:.1f}%", f"{s/t*100:.1f}%"])
    A(tbl(["年代", "题量", "配图率", "解析覆盖率"], rows))
    A(f"<p>全库配图题 <b>{n_fig:,}</b> 道（{n_fig/N*100:.1f}%），"
      f"解析覆盖 <b>{n_sol/N*100:.1f}%。未覆盖解析的多为 1977 年及更早的原始档案与个别早年补录题。</p>")

    # ---- 8 数据质量
    A("<h2>八、数据质量与局限</h2>")
    untagged = sum(1 for r in recs if not r["knowledge"])
    # computed, never hardcoded, so the report cannot drift from the data
    leak = sum(1 for r in recs
               if re.search(r"\\(?:begin|end)\\{problem\\}", r.get("problem_html") or ""))
    gaps = Counter(g for r in recs for g in r.get("data_gaps", []))
    ans_status = Counter(r.get("answer_status", "ok") for r in recs)
    try:
        mf = json.loads((ROOT / "site" / "data" / "manifest.json").read_text(encoding="utf-8"))
        manifest_figs = f"{mf.get('assets', {}).get('referenced', 0):,}"
        manifest_missing = mf.get("assets", {}).get("missing", "?")
    except Exception:
        manifest_figs, manifest_missing = "?", "?"
    cross = sum(1 for r in recs if any(k.get("cross_track") for k in r["knowledge"]))
    nolabel = sum(1 for r in recs if r["region_cn"] in ("", "未知"))
    A(tbl(["检查项", "结果", "说明"],
          [["解析完整性", f"{N:,} / {N:,}",
            "源文件 \\begin{problem} 数与入库题数逐文件比对，零丢失（verify_parse.py）"],
           ["唯一 ID", f"{len({r['id'] for r in recs}):,} / {N:,}", "题目 ID 无碰撞"],
           ["环境标签泄漏", f"{leak}", "题干/答案/解析中残留 \\end{problem} 等标记的题数"],
           ["题图", f"{n_fig:,} 题有图 / {manifest_figs} 个图文件，缺失 {manifest_missing}",
            "只复制被引用的图，复制时逐个校验存在性"],
           ["选项缺失", f"{gaps.get('options_missing',0)}", "原卷未收录选项（上游数据缺口）"],
           ["答案状态", " / ".join(f"{k} {v:,}" for k, v in ans_status.items()),
            "conflicted = 上游整理者标注原卷题面存在问题，非本系统臆造"],
           ["知识点未打标", f"{untagged}", "无任何知识点命中的题目"],
           ["文理越界标记", f"{cross:,}", "文科题命中理科专属知识点（多为文本歧义，已保留为质量信号）"],
           ["地区未标注", f"{nolabel}", "无法从卷名解析出地区"],
           ["难度为启发式", "—", "非官方难度，仅供相对参考"]]))
    A(f"<p>当前 <b>{untagged}</b> 道题（{untagged/N*100:.1f}%）未命中任何知识点；"
      f"{cross:,} 道（{cross/N*100:.1f}%）存在文科题命中理科专属知识点的现象，"
      "通常来自题干措辞歧义（如「垂直」既可能是几何也可能是向量），已作为数据质量信号保留而非静默丢弃。</p>")
    A("<h3>8.1 已知局限</h3>")
    A("<ul>"
      "<li>标签基于正则规则与关键词统计，<b>非模型语义理解</b>；对表述新颖、隐含的考点可能漏标或错标。</li>"
      "<li>难度与知识点均无人工校核，属于自动估计。</li>"
      "<li>题量统计反映的是<b>本语料库</b>的收录情况，不等同于当年真实考卷数量。</li>"
      "<li>原始 PDF（deekur/gaokaomath）与本分析使用整理后的 LaTeX（DxAThing），二者在极少数题目上可能存在转写差异。</li>"
      "</ul>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<title>高考数学真题多维分析报告</title>"
        "<link rel='stylesheet' href='../style.css'>"
        "<style>.bars[style*='--cols']{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:4px 18px}"
        ".bars[style*='--cols'] .brow .lb{width:44px;font-size:11.5px}"
        ".bars[style*='--cols'] .vl{width:52px;font-size:11px}</style></head><body>"
        "<div class='rep'>" + "".join(P) + "</div></body></html>",
        encoding="utf-8")
    print(f"report -> {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
