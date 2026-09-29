#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit checks for the brace matcher and chapter parser.

Run: python3 pipeline/selftest_parse.py
Exits non-zero on any failure, so it can gate the pipeline.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_tex as P  # noqa: E402

FAILS = []


def check(label, got, want):
    if got != want:
        FAILS.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")
    else:
        print(f"  ok   {label}")


print("find_matching")
check("plain", P.find_matching("{a{b}}d", 0), 5)
check("empty group", P.find_matching("{}", 0), 1)
check("no match", P.find_matching("{a", 0), -1)
check("2 backslashes => brace NOT escaped", P.find_matching("\\\\{x}", 0), 4)
check("1 backslash => brace IS escaped", P.find_matching("\\{x}", 0), -1)
check("doubled backslash line break", P.find_matching("a\\\\{b}", 2), 5)
check("nested deep", P.find_matching("{{{}}}", 0), 5)
check("matched pair in longer string", P.find_matching("{a}b", 0), 2)
check("truly unbalanced", P.find_matching("{ab", 0), -1)

print("clean_tex (escaped percent must not truncate)")
check("keeps \\%", P.clean_tex(r"增长率为 5\%，产值 100 万元。"),
      r"增长率为 5\%，产值 100 万元。")
check("strips real comment", P.clean_tex("abc % comment\ndef"), "abc \ndef")

print("parse_chapter")
check("track 理", P.parse_chapter("2006年北京卷（理）")["track_cn"], "理科")
check("track 文", P.parse_chapter("2006年北京卷（文）")["track_cn"], "文科")
check("track 春文", P.parse_chapter("1985年京蒙皖卷（春文）")["track_cn"], "文科")
check("variant spring", P.parse_chapter("1985年京蒙皖卷（春文）")["variant"], "spring")
check("全国", P.parse_chapter("1952年全国卷")["region_cn"], "全国")
check("新课标->全国", P.parse_chapter("2007年新课标卷（理）")["region_cn"], "全国")
check("新高考I->全国", P.parse_chapter("2021年新高考I卷")["region_cn"], "全国")
check("大纲->全国", P.parse_chapter("2009年大纲I卷（理）")["region_cn"], "全国")
check("上海", P.parse_chapter("2004年上海卷（春）")["region_cn"], "上海")
check("joint 三南", P.parse_chapter("2003年三南卷")["region_cn"], "多省联考")
check("multi keeps all provinces",
      P.parse_chapter("2021年辽宁、宁夏、海南新课标卷（理）")["region"],
      "multi:liaoning,ningxia,hainan")
check("empty region_cn", P.parse_chapter("2007年新课标卷（理）")["region_cn"], "全国")

print("classify_section")
check("单选题", P.classify_section("单选题")[0], "choice_single")
check("多选题", P.classify_section("多选题")[0], "choice_multi")
check("选考题：解答题", P.classify_section("选考题：解答题")[0], "solve")
check("选考题 group", P.classify_section("选考题：解答题")[2], "optional")
check("参考题 group", P.classify_section("参考题")[2], "reference")

print("grab_cmd_args")
check("choices 4", P.grab_cmd_args("\\choices{a}{b}{c}{d} rest", 0, "choices", 4)[0],
      ["a", "b", "c", "d"])
check("choicesfive 5",
      P.grab_cmd_args("\\choicesfive{a}{b}{c}{d}{e} x", 0, "choicesfive", 5)[0],
      ["a", "b", "c", "d", "e"])
check("optional bracket",
      P.grab_cmd_args("\\choices[x]{a}{b}{c}{d}", 0, "choices", 4)[0], ["a", "b", "c", "d"])

print()
if FAILS:
    print(f"{len(FAILS)} FAILURE(S)")
    raise SystemExit(1)
print("all parse self-tests passed")
