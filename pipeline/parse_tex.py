#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 1 — parse the DxAThing LaTeX corpus into a structured JSONL problem bank.

Source layout:
  content/<year>/<paper>.tex
    \chapter{2006年北京卷（理）}
      \section{单选题}
        \begin{problem} ... \end{problem}
          \begin{answer} ... \end{answer}     (or \answer{...})
          \begin{solution} ... \end{solution} (or \solution{...})
        \choices{A}{B}{C}{D}                   (or \choicesfive{A}..{E})

Output: data/problems.jsonl — one JSON object per problem.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "vendor_dxathing" / "content"
DATA = ROOT / "data"

# ---------------------------------------------------------------- brace utils

BRACE_RE = re.compile(r"[{}]")


def find_matching(s: str, open_idx: int) -> int:
    """s[open_idx] == '{'. Return index of matching '}' or -1.

    Scans with a compiled regex (C speed) rather than a Python char loop;
    the char loop made the full corpus take tens of minutes.
    """
    depth = 0
    pos = open_idx
    n = len(s)
    while pos < n:
        b = BRACE_RE.search(s, pos)
        if b is None:
            return -1
        i = b.start()
        # a brace is escaped only when preceded by an ODD number of
        # backslashes; the 2nd backslash of `\\{` is not itself an escape
        nb = 0
        j = i - 1
        while j >= 0 and s[j] == "\\":
            nb += 1
            j -= 1
        pos = i + 1
        if nb % 2:
            continue
        if b.group() == "{":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return i
    return -1


def split_top_level_args(s: str) -> list[str]:
    """Split a brace-body into top-level {...} groups (returns inner text)."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == "{":
            j = find_matching(s, i)
            if j == -1:
                out.append(s[i + 1:])
                return out
            out.append(s[i + 1:j])
            i = j + 1
        else:
            i += 1
    return out


def extract_env(s: str, start: int, name: str) -> tuple[str, int] | tuple[None, int]:
    """From index of '\\begin{name}', return (inner, index after '\\end{name}')."""
    bt = s.find("{", start)
    if bt == -1:
        return None, start
    name_close = find_matching(s, bt)
    if name_close == -1:
        return None, start
    body_start = name_close + 1
    # find matching \end{name} accounting for nesting
    n = len(s)
    scan = body_start
    level = 0
    pat_begin = "\\begin{" + name + "}"
    pat_end = "\\end{" + name + "}"
    while scan < n:
        b = s.find(pat_begin, scan)
        e = s.find(pat_end, scan)
        if e == -1:
            return s[body_start:], len(s)
        if b != -1 and b < e:
            level += 1
            scan = b + len(pat_begin)
            continue
        if level == 0:
            # slice to the matching \end, not to the next \begin
            return s[body_start:e], e + len(pat_end)
        level -= 1
        scan = e + len(pat_end)
    return s[body_start:], len(s)


def grab_cmd_args(s: str, pos: int, name: str, maxn: int) -> tuple[list[str], int]:
    """pos points at '\\name'. Collect up to maxn brace groups. Return (args, end)."""
    i = pos + len("\\" + name)
    args = []
    n = len(s)
    while i < n and len(args) < maxn:
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i < n and s[i] == "[":
            j = s.find("]", i)
            i = (j + 1) if j != -1 else i + 1
            continue
        if i < n and s[i] == "{":
            j = find_matching(s, i)
            if j == -1:
                break
            args.append(s[i + 1:j])
            i = j + 1
        else:
            break
    return args, i


# ---------------------------------------------------------------- chapter meta

REGION_CANON = {
    "全国": "national", "地区不明": "unknown",
    "北京": "beijing", "天津": "tianjin", "上海": "shanghai", "重庆": "chongqing",
    "河北": "hebei", "山西": "shanxi", "内蒙古": "neimenggu", "辽宁": "liaoning",
    "吉林": "jilin", "黑龙江": "heilongjiang", "江苏": "jiangsu", "浙江": "zhejiang",
    "安徽": "anhui", "福建": "fujian", "江西": "jiangxi", "山东": "shandong",
    "河南": "henan", "湖北": "hubei", "湖南": "hunan", "广东": "guangdong",
    "广西": "guangxi", "海南": "hainan", "四川": "sichuan", "贵州": "guizhou",
    "云南": "yunnan", "西藏": "xizang", "陕西": "shaanxi", "甘肃": "gansu",
    "青海": "qinghai", "宁夏": "ningxia", "新疆": "xinjiang", "台湾": "taiwan",
    "香港": "xianggang", "澳门": "aomen",
    "山东青岛": "qingdao", "上海春": "shanghai", "浙江嘉兴": "jiaxing",
}
# multi-region joint papers
MULTI = re.compile(r"^(?P<r1>[一-龥]{2,4})、(?P<r2>[一-龥、]+?)新课标卷$")

# National unified-paper names that carry no province: 大纲 / 新课标 / 新高考
NATIONAL_PAPER_TYPES = {
    "大纲", "新课标", "新高考", "全国", "新课标Ⅰ", "新课标Ⅱ",
    "新高考Ⅰ", "新高考Ⅱ", "大纲Ⅰ", "大纲Ⅱ",
}

# A joint paper is named by concatenating province abbreviations, e.g.
# 京蒙皖卷 / 三南卷 / 苏豫粤桂卷. 三南 is a historical name, so allow a
# small set of non-abbreviation forms too.
_JOINT_ABBR = "京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼"
JOINT_PAPER_RE = re.compile(
    r"^(?:[" + _JOINT_ABBR + r"]{2,}|三南|四省|联考)" + r"\s*(?:卷)?$"
)

CHAPTER_RE = re.compile(r"^(\d{4})年(.+?卷)(（(.+?)）)?$")


def parse_chapter(title: str) -> dict:
    """Turn '2006年北京卷（理）' into structured metadata."""
    m = re.match(r"^(\d{4})年(.+)$", title.strip())
    if not m:
        return {"year": None, "region_raw": title, "region": "unknown", "region_cn": "未知",
                "track": "unspecified", "track_cn": "未分类", "paper": title}
    year = int(m.group(1))
    rest = m.group(2)
    track = "unspecified"
    track_cn = "未分类"
    season = ""
    tm = re.search(r"（\s*(春|秋|夏)?\s*(理|文|理科|文科|史)\s*）\s*$", rest)
    if tm:
        season = tm.group(1) or ""
        t = tm.group(2)            # group(1) is the optional season
        if t in ("理", "理科"):
            track, track_cn = "science", "理科"
        elif t in ("文", "文科"):
            track, track_cn = "liberal", "文科"
        else:
            track, track_cn = "history", "史科"
        rest = rest[:tm.start()]

    # spring / autumn / exam classes.
    # NOTE: the season may have been consumed by the （春文）track suffix above,
    # so test the captured group too, not just the remaining text.
    variant = "regular"
    if season == "春" or "春" in rest:
        variant = "spring"
    elif season == "秋" or "秋" in rest:
        variant = "autumn"
    elif season == "夏" or "夏" in rest:
        variant = "summer"
    if "选考" in rest or "自主招生" in rest or "保送" in rest:
        variant = "special"

    region_raw = rest
    region = "unknown"
    region_cn = "未知"

    mm = MULTI.match(rest)
    if mm:
        region_raw = mm.group(0)
        region_cn = mm.group(0).replace("新课标卷", "")
        # r1 is the FIRST province; using only r2 dropped it (e.g. 辽宁、宁夏、海南
        # -> ningxia,hainan). Include both so region agrees with region_cn.
        region = "multi:" + ",".join(
            REGION_CANON.get(x, x)
            for x in (mm.group(1) + "、" + mm.group(2)).split("、"))
    else:
        core = rest
        # strip known paper-type tokens from the middle
        core = re.sub(r"新课标卷?$", "", core)
        core = re.sub(r"大纲[ⅠⅡI]+卷?$", "", core)
        core = re.sub(r"课改卷$", "", core)
        core = re.sub(r"卷$", "", core)
        core = core.strip(" ")
        if not core or core in NATIONAL_PAPER_TYPES or re.fullmatch(
                r"(?:大纲|新课标|新高考|全国)[ⅠⅡI1-9]*", core):
            # "新课标卷" / "大纲I卷" / "新高考II卷" carry no province name but
            # ARE the national unified paper. region_raw keeps the exact name.
            region, region_cn = "national", "全国"
        elif JOINT_PAPER_RE.match(core):
            # 京蒙皖卷 / 三南卷 / 苏豫粤桂卷 … multi-province joint papers
            region, region_cn = "joint", "多省联考"
        elif core.startswith("全国"):
            region, region_cn = "national", "全国"
            if core != "全国":
                paper_kind = core  # 全国I / 全国II / 全国1 ...
        elif core in REGION_CANON:
            region, region_cn = REGION_CANON[core], core
        else:
            # try longest known region prefix, e.g. 广西百色 / 黑龙江大兴安岭
            hit = None
            for k in sorted(REGION_CANON, key=len, reverse=True):
                if core.startswith(k):
                    hit = k
                    break
            if hit:
                region, region_cn = REGION_CANON[hit], hit
                region_raw = core
            else:
                region, region_cn = "other:" + core, core

    paper_kind = region_raw
    return {
        "year": year,
        "region_raw": region_raw,
        "region": region,
        "region_cn": region_cn,
        "track": track,
        "track_cn": track_cn,
        "variant": variant,
        "paper": paper_kind,
        "chapter": title,
    }


SECTION_TYPE = {
    "单选题": ("choice_single", "单项选择题"),
    "多选题": ("choice_multi", "多项选择题"),
    "选择题": ("choice_single", "单项选择题"),
    "填空题": ("fill_blank", "填空题"),
    "解答题": ("solve", "解答题"),
    "作图题": ("solve", "解答题"),
    "补充题": ("solve", "解答题"),
}


def classify_section(title: str) -> tuple[str, str, str]:
    """Return (type, type_cn, group). group in base|optional|extra|reference"""
    base = title.replace("选考题：", "").replace("选做题：", "").replace("选作题：", "")
    base = base.replace("附加题：", "").replace("附加题", "")
    group = "base"
    if "选考" in title or "选做" in title or "选作" in title:
        group = "optional"
    if "附加题" in title:
        group = "extra"
    if "参考题" in title:
        group = "reference"
    t, tcn = SECTION_TYPE.get(base.strip(), ("solve", base.strip() or "解答题"))
    return t, tcn, group


def infer_section_type(body: str) -> tuple[str, str, str]:
    """Papers before ~1980 sometimes carry no \\section. Infer the question
    type from the constructs actually used inside the problems."""
    if re.search(r"\\choices(five)?\s*[{A-Za-z]", body):
        return ("choice_single", "单项选择题", "base")
    if re.search(r"\\(?:fillinblank|\\underline\{\\hspace)", body):
        return ("fill_blank", "填空题", "base")
    return ("solve", "解答题", "base")


# ---------------------------------------------------------------- main parse

FIGURE_CMD = re.compile(
    r"\\(?:bitmapfigure|texfigure|sourcefigure|choicebitmap|choicetexfigure|bitmapinclude)"
    r"(?:\[[^\]]*\])?\{([^}]*)\}")


def clean_tex(t: str) -> str:
    """Drop layout-only commands so the text is readable."""
    # An escaped percent is common in the corpus (增长率 5\%). Without the
    # lookbehind, `\%` starts a "comment" and silently truncates the rest of
    # the line -- 33 stems / 27 solutions in the corpus end mid-sentence.
    t = re.sub(r"(?<!\\)%.*", "", t)
    t = re.sub(r"\\(?:begingroup|endgroup|relax|centering|noindent|hfil|hfill|par|vskip|medskip)\b", "", t)
    t = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", "", t)
    t = re.sub(r"\\setcounter\{[^}]*\}\{[^}]*\}", "", t)
    t = re.sub(r"\\(?:problemresetlayout|allowbreak|examavoidshortpage|problembodyindent)\b", "", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def pull_blocks(text: str) -> tuple[str, str, str, list[str]]:
    """Remove any \\begin{answer}/\\begin{solution} (or \\answer{}/\\solution{})
    blocks nested inside a problem body, returning the cleaned body plus the
    first answer, first solution and the solution's figure list."""
    answer = sol = ""
    figs: list[str] = []

    out = text
    guard = 0
    while "\\begin{answer}" in out and not answer and guard < 10:
        a = out.find("\\begin{answer}")
        inner, end = extract_env(out, a, "answer")
        if inner is None or end <= a:
            break
        answer = inner
        out = out[:a] + out[end:]
        guard += 1

    guard = 0
    while "\\begin{solution}" in out and not sol and guard < 10:
        a = out.find("\\begin{solution}")
        inner, end = extract_env(out, a, "solution")
        if inner is None or end <= a:
            break
        sol = inner
        figs = FIGURE_CMD.findall(inner)
        out = out[:a] + out[end:]
        guard += 1

    if not answer:
        m = re.search(r"\\answer\{", out)
        if m:
            ob = out.find("{", m.start())
            ce = find_matching(out, ob)
            if ce != -1:
                answer = out[ob + 1:ce]
                out = out[:m.start()] + out[ce + 1:]
    if not sol:
        m = re.search(r"\\solution\{", out)
        if m:
            ob = out.find("{", m.start())
            ce = find_matching(out, ob)
            if ce != -1:
                sol = out[ob + 1:ce]
                figs = FIGURE_CMD.findall(sol)
                out = out[:m.start()] + out[ce + 1:]

    return out, answer, sol, figs


def parse_file(path: Path) -> list[dict]:
    src = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(CONTENT).as_posix()
    parts = rel.split("/")
    year = int(parts[0]) if parts[0].isdigit() else None
    fname = parts[1] if len(parts) > 1 else path.stem

    chapters = list(re.finditer(r"\\chapter\{", src))
    results: list[dict] = []
    if not chapters:
        return results

    # `idx` restarts at every \section, so a file whose sections share a
    # section_type (解答题 / 补充题 / 选作题 all -> "solve") would emit
    # colliding ids. gseq is monotonic per file and is what the id uses.
    gseq = 0

    for ci, cm in enumerate(chapters):
        bt = src.find("{", cm.start())
        ce = find_matching(src, bt)
        title = src[bt + 1:ce]
        seg_start = ce + 1
        seg_end = chapters[ci + 1].start() if ci + 1 < len(chapters) else len(src)
        segment = src[seg_start:seg_end]

        meta = parse_chapter(title)
        if meta["year"] is None:
            meta["year"] = year

        sections = list(re.finditer(r"\\section\{", segment))
        # A chapter may contain problems before its first \section (early
        # papers put everything under \chapter), so always emit an implicit
        # section for that preamble when it actually holds problems.
        blocks: list[tuple[str, str]] = []   # (section_title, body)
        if sections:
            head_body = segment[:sections[0].start()]
            if "\\begin{problem}" in head_body:
                blocks.append(("", head_body))
        else:
            blocks.append(("", segment))

        for si, sm in enumerate(sections):
            sbt = segment.find("{", sm.start())
            sce = find_matching(segment, sbt)
            stitle = segment[sbt + 1:sce]
            s_start = sce + 1
            s_end = sections[si + 1].start() if si + 1 < len(sections) else len(segment)
            blocks.append((stitle, segment[s_start:s_end]))

        for stitle, body in blocks:
            if stitle:
                stype, stype_cn, sgroup = classify_section(stitle)
            else:
                stype, stype_cn, sgroup = infer_section_type(body)

            # iterate problems in this section
            pos = 0
            idx = 0
            while True:
                pm = re.search(r"\\begin\{problem\}", body[pos:])
                if not pm:
                    break
                p_abs = pos + pm.start()
                pbody, after_p = extract_env(body, p_abs, "problem")
                if pbody is None:
                    break
                if after_p <= p_abs:          # no forward progress -> bail out
                    break
                pos = after_p
                idx += 1
                gseq += 1

                # Two authoring layouts exist in the corpus:
                #   A) \end{problem} then answer/solution as siblings
                #   B) answer/solution nested INSIDE the problem environment
                # Pull (B) out of the body first, then look for (A) after it.
                pbody, inner_ans, inner_sol, inner_figs = pull_blocks(pbody)
                answer_txt, sol_txt, sol_figs = inner_ans, inner_sol, inner_figs

                # find answer / solution that belong to this problem:
                # scan forward until the next \begin{problem} or \section
                nxt = body.find("\\begin{problem}", after_p)
                nxt = nxt if nxt != -1 else len(body)
                tail = body[after_p:nxt]

                tail_pos = 0
                for envname, setter in (("answer", 0), ("solution", 1)):
                    while True:
                        if envname == "answer":
                            hit = re.search(r"\\begin\{answer\}", tail[tail_pos:])
                            if not hit:
                                am = re.search(r"\\answer\{", tail[tail_pos:])
                                if am:
                                    ob = tail.find("{", tail_pos + am.start())
                                    ce2 = find_matching(tail, ob)
                                    if ce2 != -1:
                                        if setter == 0 and not answer_txt:
                                            answer_txt = tail[ob + 1:ce2]
                                        tail_pos = tail_pos + am.start() + 1
                                        continue
                                break
                            a = tail_pos + hit.start()
                            inner, nxt_pos = extract_env(tail, a, "answer")
                            if setter == 0 and not answer_txt and inner is not None:
                                answer_txt = inner
                            tail_pos = nxt_pos
                        else:
                            hit = re.search(r"\\begin\{solution\}", tail[tail_pos:])
                            if not hit:
                                sm2 = re.search(r"\\solution\{", tail[tail_pos:])
                                if sm2:
                                    ob = tail.find("{", tail_pos + sm2.start())
                                    ce2 = find_matching(tail, ob)
                                    if ce2 != -1:
                                        if not sol_txt:
                                            sol_txt = tail[ob + 1:ce2]
                                        tail_pos = tail_pos + sm2.start() + 1
                                        continue
                                break
                            a = tail_pos + hit.start()
                            inner, nxt_pos = extract_env(tail, a, "solution")
                            if not sol_txt and inner is not None:
                                sol_txt = inner
                                sol_figs = FIGURE_CMD.findall(inner)
                            tail_pos = nxt_pos

                # Choices. NOTE: `\choices` is a literal prefix of
                # `\choicesfive`, so a plain str.find for "\choices" always
                # lands on the "five" variant and the ordering test below can
                # never be true. Use regexes that assert the word boundary.
                choices = []
                seg = body[p_abs:after_p] if after_p > p_abs else body[p_abs:]
                m5 = re.search(r"\\choicesfive\b", seg)
                m4 = re.search(r"\\choices(?!five)\b", seg)
                if m5 and (not m4 or m5.start() < m4.start()):
                    cm5, nm, want = p_abs + m5.start(), "choicesfive", 5
                elif m4:
                    cm5, nm, want = p_abs + m4.start(), "choices", 4
                else:
                    cm5 = None
                if cm5 is not None:
                    args, c_end = grab_cmd_args(body, cm5, nm, want)
                    choices = [a.strip() for a in args]
                    span = body[cm5:c_end]
                    if span in pbody:
                        pbody = pbody.replace(span, "")
                pbody = re.sub(r"\\choices(?:five)?\s*\{[^{}]*\}(\s*\{[^{}]*\}){1,4}", "", pbody)
                pbody = re.sub(r"\\choices(?:five)?\b", "", pbody)

                figs = FIGURE_CMD.findall(pbody)
                rec = {
                    "id": f"{meta['year']}|{fname}|{gseq}",
                    "index_in_section": idx,
                    "year": meta["year"],
                    "region": meta["region"],
                    "region_cn": meta["region_cn"],
                    "region_raw": meta["region_raw"],
                    "track": meta["track"],
                    "track_cn": meta["track_cn"],
                    "variant": meta["variant"],
                    "paper": meta["paper"],
                    "paper_file": fname,
                    "chapter": meta["chapter"],
                    "section": stitle,
                    "section_type": stype,
                    "section_type_cn": stype_cn,
                    "section_group": sgroup,
                    "number": idx,
                    "problem_tex": clean_tex(pbody),
                    "choices": choices,
                    "answer_tex": clean_tex(answer_txt),
                    "solution_tex": clean_tex(sol_txt),
                    "figures": figs,
                    "figures_solution": sol_figs,
                }
                rec["has_figure"] = bool(figs)
                rec["has_solution"] = bool(sol_txt.strip())
                rec["has_answer"] = bool(answer_txt.strip())
                results.append(rec)
    return results


def main() -> int:
    DATA.mkdir(exist_ok=True)
    files = sorted(CONTENT.rglob("*.tex"))
    total = 0
    per_year: dict[int, int] = {}
    out_path = DATA / "problems.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for i, f in enumerate(files, 1):
            try:
                recs = parse_file(f)
            except Exception as e:  # keep going, report at the end
                print(f"!! {f.relative_to(CONTENT)}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                total += 1
                per_year[r["year"]] = per_year.get(r["year"], 0) + 1
            if i % 150 == 0:
                print(f"  ...{i}/{len(files)} files, {total} problems", file=sys.stderr)
    print(f"parsed {total} problems from {len(files)} tex files -> {out_path}")
    yrs = sorted(k for k in per_year if k)
    print(f"years: {yrs[0]}-{yrs[-1]} ({len(yrs)} distinct)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
