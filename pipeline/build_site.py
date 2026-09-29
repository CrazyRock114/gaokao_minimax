#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 4 — build the static question-bank site.

Outputs:
  site/data/manifest.json   facet counts + taxonomy + year list
  site/data/index.json      light record per problem (filtering + search)
  site/data/p/<year>.json   full records (HTML, answers, solutions) per year
  site/img/...              ONLY the figures actually referenced
  site/report/...           analysis report assets
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy import CHAPTER_LIST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
SRC_IMG = ROOT / "vendor_dxathing"

# option images live inside choices_html rather than the figures[] array
IMG_SRC_RE = re.compile(r'<img[^>]+src="([^"]+)"')


def main() -> int:
    rich = DATA / "problems_rich.jsonl"
    out_dir = SITE / "data" / "p"
    out_dir.mkdir(parents=True, exist_ok=True)

    by_year: dict[int, list[dict]] = defaultdict(list)
    light: list[dict] = []
    needed_figs: set[str] = set()
    facet = {
        "year": Counter(), "region": Counter(), "track": Counter(),
        "type": Counter(), "diff": Counter(), "point": Counter(),
        "chapter": Counter(), "variant": Counter(), "paper": Counter(),
    }
    kp_point: dict[str, dict] = {}
    kp_chapter: dict[str, Counter] = defaultdict(Counter)
    year_by_kp: dict[str, Counter] = defaultdict(Counter)
    n_sol = n_fig = 0
    answer_status = Counter()
    data_gaps = Counter()

    with rich.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            for f in r.get("figures", []) + r.get("figures_solution", []):
                needed_figs.add(f)
            # 5-option questions keep their option images inside choices_html
            for c in r.get("choices_html", []):
                for m in IMG_SRC_RE.findall(c):
                    needed_figs.add(m)
            n_sol += bool(r["has_solution"])
            n_fig += bool(r["has_figure"])
            answer_status[r.get("answer_status", "ok")] += 1
            for g in r.get("data_gaps", []):
                data_gaps[g] += 1
            y = r["year"]
            by_year[y].append(r)
            facet["year"][y] += 1
            facet["region"][r["region_cn"]] += 1
            facet["track"][r["track_cn"]] += 1
            facet["type"][r["section_type_cn"]] += 1
            facet["diff"][r["difficulty"]] += 1
            facet["variant"][r["variant"]] += 1
            facet["paper"][r["chapter"]] += 1
            seen_ch = set()
            for k in r["knowledge"]:
                facet["point"][k["code"]] += 1
                seen_ch.add(k["chapter"])
                # these three must use THIS point, not a leaked loop variable
                kp_chapter[k["chapter"]][k["code"]] += 1
                year_by_kp[k["code"]][y] += 1
                kp_point[k["code"]] = {"code": k["code"], "name": k["name"],
                                      "chapter": k["chapter"],
                                      "chapter_cn": k["chapter_cn"]}
            # chapter facet counts DISTINCT problems, matching what the UI
            # filter returns; summing per-point would count a problem once
            # per knowledge point it carries in that chapter.
            for ch in seen_ch:
                facet["chapter"][ch] += 1
            snippet = (r["plain"] or "")[:110]
            light.append({
                "id": r["id"], "y": y, "r": r["region_cn"], "rt": r["region"],
                "t": r["track_cn"], "ty": r["section_type"], "tyc": r["section_type_cn"],
                "d": r["difficulty"], "k": [x["code"] for x in r["knowledge"]],
                "kn": [x["name"] for x in r["knowledge"][:4]],
                "f": 1 if r["has_figure"] else 0,
                "s": 1 if r["has_solution"] else 0,
                "g": r["section_group"],
                "as": r.get("answer_status", "ok"),
                "dg": r.get("data_gaps", []),
                "p": r["chapter"],
                "sec": r["section"],
                "n": r["number"],
                "tx": snippet,
                # full plain-text projection: makes search actually cover
                # stem + options + solution, as the README claims
                "pl": r["plain"] or "",
            })

    # ---- full records, sharded by year
    for y, recs in by_year.items():
        slim = []
        for r in recs:
            slim.append({
                "id": r["id"], "y": r["year"], "r": r["region_cn"], "rt": r["region"],
                # ty/tyc must carry the SAME value space in both files:
                # ty = English code, tyc = Chinese label
                "t": r["track_cn"], "ty": r["section_type"],
                "tyc": r["section_type_cn"], "g": r["section_group"],
                "n": r["number"], "p": r["chapter"], "sec": r["section"],
                "ph": r["problem_html"],
                "ch": r["choices_html"],
                "ah": r["answer_html"],
                "sh": r["solution_html"],
                "af": r["answer_tex"],
                "sf": r["solution_tex"],
                "pt": r["problem_tex"],
                "fi": r["figures"], "fs": r["figures_solution"],
                "d": r["difficulty"], "dl": r["difficulty_label"],
                "k": r["knowledge"],
                "ks": r["has_solution"], "ans": r["has_answer"],
                "as": r.get("answer_status", "ok"), "anote": r.get("answer_note", ""),
                "dg": r.get("data_gaps", []),
            })
        (out_dir / f"{y}.json").write_text(
            json.dumps(slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    (SITE / "data" / "index.json").write_text(
        json.dumps(light, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    manifest = {
        "total": len(light),
        "years": sorted(by_year),
        "shards": {str(y): f"data/p/{y}.json" for y in sorted(by_year)},
        "facets": {k: dict(v) for k, v in facet.items()},
        "points": {c: dict(v) for c, v in kp_point.items()},
        "chapters": [
            {"chapter": ch, "chapter_cn": CHAPTER_LIST[ch],
             "points": [{"code": c, "name": kp_point[c]["name"],
                         "count": n} for c, n in
                        sorted(kp_chapter[ch].items(), key=lambda x: -x[1])]}
            for ch in CHAPTER_LIST
            if kp_chapter.get(ch)
        ],
        "point_years": {c: dict(v) for c, v in year_by_kp.items()},
        "coverage": {"solution": n_sol, "figure": n_fig},
        "assets": {},          # filled in after the figure copy below
        "quality": {
            "answer_status": dict(answer_status),
            "data_gaps": dict(data_gaps),
        },
        "generated_from": ["deekur/gaokaomath", "DxAThing/Gaokao-Math-Problems-Compilation"],
    }

    # Prune first: a figure that stopped being referenced (or was renamed
    # upstream) would otherwise stay in the repo forever and silently bloat
    # the deployed site.
    pruned = 0
    for root in ("img", "img_repaint"):
        d = SITE / root
        if not d.exists():
            continue
        for fp in d.rglob("*"):
            if fp.is_file():
                if fp.relative_to(SITE).as_posix() not in needed_figs:
                    fp.unlink()
                    pruned += 1
    if pruned:
        print(f"pruned {pruned} unreferenced figure(s)")
    copied = missing = 0
    for f in sorted(needed_figs):
        src = SRC_IMG / f
        dst = SITE / f
        if src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        else:
            missing += 1
    print(f"figures referenced={len(needed_figs)} copied={copied} missing={missing}")
    manifest["assets"] = {"referenced": len(needed_figs),
                          "copied": copied, "missing": missing}

    (SITE / "data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # Invariant: every cell of chapters[].points[].count must equal the
    # point facet, which is counted independently. This catches the class of
    # bug where a leaked loop variable corrupts the chapter->point rollup.
    bad = []
    for ch in manifest["chapters"]:
        for p in ch["points"]:
            if p["count"] != manifest["facets"]["point"].get(p["code"]):
                bad.append(f'{ch["chapter"]}/{p["code"]}: '
                           f'{p["count"]} != {manifest["facets"]["point"].get(p["code"])}')
    if bad:
        print(f"!! chapter/point count mismatch in {len(bad)} cells:")
        for b in bad[:10]:
            print("   ", b)
        return 1
    print("chapter/point counts consistent: OK")
    if missing:
        miss = sorted(needed_figs)[:5]
        print("  sample missing:", miss)
    print(f"index.json  {len(light)} records")
    print(f"shards      {len(by_year)} year files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
