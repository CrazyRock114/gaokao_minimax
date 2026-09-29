#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 3 — enrich parsed problems: render HTML, tag knowledge points,
estimate difficulty. Writes data/problems_rich.jsonl + data/stats.json.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import latex_render as LR  # noqa: E402
from taxonomy import KNOWLEDGE, CHAPTER_LIST, _guard  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# --------------------------------------------------------------- compile rules

COMPILED = []
for k in KNOWLEDGE:
    pat = "|".join(f"(?:{_guard(p)})" for p in k["kw"])
    try:
        rx = re.compile(pat)
    except re.error as e:
        print(f"!! bad regex in {k['code']}: {e}", file=sys.stderr)
        continue
    COMPILED.append((k, rx, k["kw"]))

PROOF_RE = re.compile(r"求证|证明|试证|说明.{0,4}成立|论证")
OPEN_RE = re.compile(r"是否存在|能否|讨论.{0,4}的个数|所有|任意|至少存在|恰有")

# The upstream editor deliberately leaves the answer blank / marks it invalid for
# exam items that are themselves defective (the printed options contradict the
# computation). Those blanks must NOT be "fixed" by inventing an answer.
#
# Deliberately narrow: ordinary solution prose says things like
# "其余选项均不成立" / "选项 C、D 均不符合题设" when eliminating distractors,
# so those phrases must NOT be treated as a paper defect. We only trust:
#   (a) the editor's explicit disclaimer, and
#   (b) the answer field itself saying there is no valid option.
CONFLICT_DISCLAIMER_RE = re.compile(
    r"不臆造|现保留这一客观题面|保留这一客观题面冲突|原题题面存在冲突"
    r"|按原题面不能|按原始试卷题面不能|严格按原题面不能|严格按原始试卷题面"
    r"|题面存在冲突|原题存在冲突|题面本身存在")
ANSWER_NO_VALID_RE = re.compile(
    r"无正确选项|无唯一值|无唯一解|条件不足|无法确定|无法唯一确定|不能唯一确定"
    r"|题面冲突|题面无|无解|按原题面|严格按原题面|原 PDF 四个选项均无此值"
    r"|题面不成立|题面与选项矛盾|题面缺少|按原题面无对应选项|原题无正确选项")
# The answer IS given, but the editor notes it is not unique. Not a defect.
ANSWER_NONUNIQUE_RE = re.compile(r"不唯一|也可填|均可填")
# Solutions that do state the answer, so it can be recovered transparently.
ANS_IN_SOL_RE = re.compile(
    r"(?:故|因此|所以)?\s*(?:正确答案?|答案为|答案为：|故选|对应选项|正确选项(?:为|是)?)"
    r"\s*[:：]?\s*([A-F]{1,4})(?![A-Za-z])")


def answer_status(rec: dict) -> tuple[str, str]:
    """Return (status, note).

    ok        - an answer is present
    derived   - answer recovered from the solution text (flagged as such)
    conflicted- upstream documents the printed exam item as self-inconsistent
    missing   - genuinely absent
    """
    ans = (rec.get("answer_tex") or "").strip()
    sol = rec.get("solution_tex") or ""
    disclaimer = bool(CONFLICT_DISCLAIMER_RE.search(sol))
    if ans:
        if ANSWER_NO_VALID_RE.search(ans) or (disclaimer and not re.fullmatch(
                r"\(?[A-F]{1,4}\)?[.．]?", ans)):
            return "conflicted", "原卷题面存在问题，整理者标注无有效答案"
        if re.fullmatch(r"\(?[A-F]{1,4}\)?[.．]?", ans) and rec.get("choices"):
            letters = [c for c in ans if c in "ABCDEF"]
            if letters and max(ord(c) - 65 for c in letters) >= len(rec["choices"]):
                return "conflicted", "整理者标注：原卷选项中无此答案"
        if ANSWER_NONUNIQUE_RE.search(ans):
            return "ok", "整理者提示该题答案可能不唯一"
        return "ok", ""
    if rec.get("choices"):
        m = None
        for m in ANS_IN_SOL_RE.finditer(sol):
            pass                      # keep the LAST statement
        if m and max(ord(c) - 65 for c in m.group(1)) < len(rec["choices"]) and not disclaimer:
            rec["answer_tex"] = m.group(1)
            rec["answer_derived"] = True
            return "derived", "答案取自解析原文"
        if disclaimer or ANSWER_NO_VALID_RE.search(sol):
            return "conflicted", "原卷题面存在问题，整理者标注无有效答案"
    return "missing", ""


def match_points(text: str, year: int | None = None) -> dict[str, dict]:
    """Score every knowledge point against `text`.

    Weighting rationale: a bare keyword like 动点 (2 chars) is far weaker
    evidence than 单调递增区间 (6 chars), and counts a lot more. Scoring by
    keyword length stops generic one-word concepts from outranking the
    specific method actually being tested.
    """
    out: dict[str, dict] = {}
    for k, rx, _kws in COMPILED:
        # If the year is unknown the era restriction cannot be checked, so
        # skip the rule rather than silently applying it to every year.
        if k.get("era_max_year") and (year is None or year > k["era_max_year"]):
            continue
        found: set[str] = set()
        for m in rx.finditer(text):
            if not m.group(0):
                # a zero-length match means an unescaped alternation slipped
                # into a keyword; it would "hit" on literally every problem
                continue
            found.add(m.group(0))
        if not found:
            continue
        score = sum(1.0 + 0.6 * min(len(f), 8) for f in found)
        out[k["code"]] = {
            "code": k["code"],
            "name": k["name"],
            "chapter": k["chapter"],
            "hits": len(found),
            "raw": score,
            "evidence": sorted(found, key=lambda s: -len(s))[:6],
            "scope": k["scope"],
        }
    return out


def merge_scores(stem: dict, sol: dict, choices: dict, track: str,
                 joined: str = "") -> list[dict]:
    """Combine the three evidence channels into a ranked tag list.

    Choices are weak evidence: distractor options routinely mention topics
    the question is not about (a 轨迹 question offering 椭圆/双曲线 options).
    """
    codes = set(stem) | set(sol) | set(choices)
    merged = []
    for c in codes:
        s = stem.get(c)
        o = sol.get(c)
        q = choices.get(c)
        score = (1.0 * (s["raw"] if s else 0.0)
                 + 0.55 * (o["raw"] if o else 0.0)
                 + 0.20 * (q["raw"] if q else 0.0))
        base = s or o or q
        if s and o:
            source = "stem+solution"
        elif s:
            source = "stem" + ("+choice" if q else "")
        elif o:
            source = "solution"
        else:
            source = "choice-only"
        merged.append({
            "code": c, "name": base["name"], "chapter": base["chapter"],
            "score": round(score, 2), "hits": max(
                (s or {}).get("hits", 0), (o or {}).get("hits", 0),
                (q or {}).get("hits", 0)),
            "in_stem": bool(s), "in_solution": bool(o), "in_choices": bool(q),
            "source": source, "evidence": base["evidence"],
            "scope": base["scope"],
        })
    merged.sort(key=lambda x: (-x["score"], x["code"]))

    # Conics are mutually exclusive families. Without this, a 双曲线 problem
    # (whose solution also says 焦点/焦距/准线) wins 椭圆 on raw keyword count.
    conics = {"椭圆": ("ANAL2", {"ANAL3", "ANAL4"}),
              "双曲线": ("ANAL3", {"ANAL2", "ANAL4"}),
              "抛物线": ("ANAL4", {"ANAL2", "ANAL3"})}
    for word, (_keep, _drop) in conics.items():
        if word in joined:
            merged = [m for m in merged if m["code"] not in _drop] or merged
            break
    merged.sort(key=lambda x: (-x["score"], x["code"]))

    if merged:
        # Keep tags competitive with the leader. The floor must stay RELATIVE:
        # a choice-only or short-keyword match scores far below an absolute
        # 1.6, which used to discard every tag including the leader and made
        # `knowledge == []` mean "a rule matched but we threw it away".
        top = merged[0]["score"]
        keep = [m for m in merged if m["score"] >= 0.28 * top]
        if merged[0] not in keep:
            keep.insert(0, merged[0])
        merged = keep[:8]
    if track == "liberal":
        for m in merged:
            if m["scope"] == "S":
                m["cross_track"] = True
    return merged


def difficulty(rec: dict, pts: list[dict], sol_len: int, stem_text: str) -> int:
    """Heuristic 1-5. Documented in reports/methodology.md."""
    base = {"choice_single": 1, "fill_blank": 2, "solve": 3, "choice_multi": 3}
    s = base.get(rec["section_type"], 2)

    # solution length (chars of Chinese prose)
    if sol_len > 900:
        s += 2
    elif sol_len > 400:
        s += 1.5
    elif sol_len > 150:
        s += 0.5
    elif sol_len < 40 and rec["section_type"] == "solve":
        s -= 0.5

    n_sub = len(re.findall(r"\\item", rec["problem_tex"]))
    if n_sub >= 3:
        s += 1
    elif n_sub == 2:
        s += 0.5

    if PROOF_RE.search(rec["problem_tex"]):
        s += 0.5
    if OPEN_RE.search(rec["problem_tex"]):
        s += 0.5
    if rec["has_figure"]:
        s += 0.25
    if len(pts) >= 4:
        s += 0.5
    if len(pts) <= 1 and rec["section_type"] == "solve":
        s -= 0.5
    # very short stems are usually easy lookups
    if len(stem_text) < 25 and rec["section_type"] != "solve":
        s -= 0.5

    return max(1, min(5, int(round(s))))


def main() -> int:
    src = DATA / "problems.jsonl"
    out = DATA / "problems_rich.jsonl"
    n = 0
    stats = {
        "by_year": Counter(), "by_region": Counter(), "by_track": Counter(),
        "by_type": Counter(), "by_variant": Counter(), "by_difficulty": Counter(),
        "by_point": Counter(), "by_chapter": Counter(), "by_decade": Counter(),
        "figures_by_year": Counter(), "solution_coverage_by_year": Counter(),
        "cross_track": Counter(),
        "answer_status": Counter(),
        "data_gaps": Counter(),
    }
    with src.open(encoding="utf-8") as fh, out.open("w", encoding="utf-8") as oh:
        for line in fh:
            r = json.loads(line)
            # --- render
            ph, figs = LR.tex_to_html(r["problem_tex"])
            ch = [LR.tex_to_html(c)[0] for c in r["choices"]]
            ah, _ = LR.tex_to_html(r["answer_tex"])
            sh, sfigs = LR.tex_to_html(r["solution_tex"])
            # stem text only -- `plain` includes the solution, so using it
            # made the "very short stem" difficulty term dead code
            stem_text = LR.tex_to_plain(r["problem_tex"] + " " +
                                        " ".join(r["choices"]))
            plain = LR.tex_to_plain(r["problem_tex"] + " " +
                                    " ".join(r["choices"]) + " " + r["solution_tex"])

            r["problem_html"] = ph
            r["choices_html"] = ch
            r["answer_html"] = ah
            r["solution_html"] = sh
            r["figures"] = sorted(set(figs) | set(r.get("figures", [])))
            r["figures_solution"] = sorted(set(sfigs) | set(r.get("figures_solution", [])))
            # option images count too: 155 questions carry their choices only
            # as bitmaps, so a stem/solution-only test missed them entirely
            r["has_figure"] = bool(r["figures"] or r["figures_solution"]
                                   or any('src="' in c for c in r["choices_html"]))
            r["plain"] = plain

            # --- knowledge tagging: stem = what is asked, solution = how it is
            # solved, choices = weak/distractor-prone evidence.
            y = r["year"]
            ask_text = LR.tex_to_plain(r["problem_tex"])
            ch_text = LR.tex_to_plain(" ".join(r["choices"]))
            method_text = LR.tex_to_plain(r["solution_tex"])
            m_stem = match_points(ask_text, y)
            m_sol = match_points(method_text, y)
            m_ch = match_points(ch_text, y)
            pts = merge_scores(m_stem, m_sol, m_ch, r["track"],
                                stem_text + " " + method_text + " " + ch_text)
            r["knowledge"] = [
                {"code": p["code"], "name": p["name"], "chapter": p["chapter"],
                 "chapter_cn": CHAPTER_LIST[p["chapter"]], "score": p["score"],
                 "hits": p["hits"], "source": p["source"],
                 "in_stem": p["in_stem"], "in_solution": p["in_solution"],
                 "evidence": p["evidence"],
                 **({"cross_track": True} if p.get("cross_track") else {})}
                for p in pts
            ]
            r["primary_knowledge"] = r["knowledge"][0] if r["knowledge"] else None
            r["n_knowledge"] = len(r["knowledge"])

            # --- answer integrity: the upstream repo leaves some answers blank
            # on purpose because the printed exam item is self-inconsistent.
            a_status, a_note = answer_status(r)
            r["answer_status"] = a_status
            # answer_status() may fill a blank answer from the solution, so
            # has_answer has to be recomputed or the record self-contradicts.
            r["has_answer"] = bool((r.get("answer_tex") or "").strip())
            r["answer_note"] = a_note
            r.setdefault("answer_derived", False)
            if a_status == "derived":
                # answer_tex was just filled in from the solution, so the HTML
                # rendered earlier (from an empty answer) must be redone --
                # otherwise answer_tex says "BC" while answer_html is empty.
                ah, _ = LR.tex_to_html(r["answer_tex"])
                r["answer_html"] = ah

            r["data_gaps"] = []
            if r["section_type"].startswith("choice") and not r["choices"]:
                r["data_gaps"].append("options_missing")   # upstream has no options
            if a_status == "conflicted":
                r["data_gaps"].append("answer_conflicted")
            elif a_status == "missing" and r["section_type"].startswith("choice"):
                r["data_gaps"].append("answer_missing")
            if a_status == "derived":
                r["data_gaps"].append("answer_derived")

            r["difficulty"] = difficulty(r, pts, len(method_text), stem_text)
            r["difficulty_label"] = ["", "易", "较易", "中等", "较难", "难"][r["difficulty"]]

            oh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1

            stats["by_year"][y] += 1
            stats["by_region"][r["region_cn"]] += 1
            stats["by_track"][r["track_cn"]] += 1
            stats["by_type"][r["section_type_cn"]] += 1
            stats["by_variant"][r["variant"]] += 1
            stats["by_difficulty"][r["difficulty"]] += 1
            stats["by_decade"][(y // 10) * 10] += 1
            if r["has_figure"]:
                stats["figures_by_year"][y] += 1
            if r["has_solution"]:
                stats["solution_coverage_by_year"][y] += 1
            stats["answer_status"][a_status] += 1
            for g in r["data_gaps"]:
                stats["data_gaps"][g] += 1
            for p in r["knowledge"]:
                stats["by_point"][p["code"]] += 1
                stats["by_chapter"][p["chapter"]] += 1
                if p.get("cross_track"):
                    stats["cross_track"][p["code"]] += 1

    (DATA / "stats.json").write_text(
        json.dumps({k: dict(v) for k, v in stats.items()}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"enriched {n} problems -> {out}")
    print("top knowledge points:")
    for code, c in stats["by_point"].most_common(15):
        print(f"  {c:6d}  {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
