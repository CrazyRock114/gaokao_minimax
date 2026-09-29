#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 2 — convert problem/answer/solution LaTeX into browser-ready HTML.

Strategy: the corpus LaTeX is ~95% standard math, so we keep it as LaTeX and
hand math spans to MathJax, while normalising the project's custom macros and
dropping layout-only constructs. We split the text into math / non-math spans
so that Chinese prose stays as HTML and formulas get rendered.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------- macro mapping

# LaTeX -> MathJax/KaTeX compatible replacements
MACRO_SIMPLE = {
    r"\i": r"\mathrm{i}",
    r"\e": r"\mathrm{e}",
    r"\d": r"\mathrm{d}",
    r"\R": r"\mathbb{R}",
    r"\Z": r"\mathbb{Z}",
    r"\N": r"\mathbb{N}",
    r"\degree": r"^{\circ}",
    r"\Pr": r"P",
    r"\myarc": r"\overset{\frown}",          # takes 1 arg, handled as fn
    r"\Pr": r"\mathrm{P}",
}

# commands that take a single braced argument and expand to a wrapper
MACRO_WRAP1 = {
    r"\bs": r"\mathbf",        # bold symbol
    r"\widehat": r"\widehat",
    r"\widetilde": r"\widetilde",
    r"\boxed": r"\boxed",
}

DROP_CMD = [
    r"\begingroup", r"\endgroup", r"\relax", r"\centering", r"\noindent",
    r"\hfil", r"\hfill", r"\par", r"\vskip", r"\medskip", r"\parbox",
    r"\allowbreak", r"\problemresetlayout", r"\examavoidshortpage",
    r"\problembodyindent", r"\reuseproblemnumber", r"\tallpagetrue",
    r"\nobreak", r"\linebreak", r"\pagebreak", r"\newpage",
    r"\small", r"\footnotesize", r"\scriptsize", r"\large", r"\normalsize",
    r"\hbox", r"\mbox", r"\textsuperscript", r"\textsubscript",
    r"\hbox{}",
]

FIGURE_MACROS = (
    "bitmapfigure", "texfigure", "sourcefigure", "choicebitmap",
    "choicetexfigure", "bitmapinclude",
)
FIGURE_RE = re.compile(
    r"\\(?:" + "|".join(FIGURE_MACROS) + r")(?:\[[^\]]*\])?\{([^}]*)\}")


def _find_matching(s: str, i: int) -> int:
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _brace(s: str, pos: int):
    """pos at '{' -> (inner, end_after_closing) or (None, pos)"""
    j = _find_matching(s, pos)
    if j == -1:
        return None, pos
    return s[pos + 1:j], j + 1


def _brace_opt(s: str, pos: int):
    """Read '[opt]{arg1}{arg2}...' for a command with optional arg."""
    i = pos
    n = len(s)
    while i < n and s[i] in " \t\r\n":
        i += 1
    if i < n and s[i] == "[":
        j = s.find("]", i)
        if j == -1:
            return [], i
        i = j + 1
    args = []
    while True:
        while i < n and s[i] in " \t\r\n":
            i += 1
        if i < n and s[i] == "{":
            inner, i = _brace(s, i)
            if inner is None:
                break
            args.append(inner)
        else:
            break
    return args, i


def expand_special(tex: str) -> str:
    """Expand the repo's bespoke display/markup commands into plain LaTeX."""
    tex = re.sub(r"\\FigureLayoutDeclare(?:\[[^\]]*\])?\{[^}]*\}\{[^}]*\}\{[^}]*\}", "", tex)
    tex = re.sub(r"\\FigureTrimDeclare(?:\[[^\]]*\])?\{[^}]*\}\{[^}]*\}", "", tex)
    tex = re.sub(r"\\setlength\{[^}]*\}\{[^}]*\}", "", tex)
    tex = re.sub(r"\\setcounter\{[^}]*\}\{[^}]*\}", "", tex)
    tex = re.sub(r"\\(?:examtablefractionpad|examfiguregroup|examstatxlabel|examstatylabel|airqualityheader)\b", "", tex)

    # \examdisplaycases{open}{body}
    def _cases(m):
        ob = m.start()
        args, end = _brace_opt(tex, ob + len("\\examdisplaycases"))
        if len(args) >= 2:
            return r"\[" + args[0] + r"\begin{cases}" + args[1] + r"\end{cases}\]"
        return ""
    while True:
        m = re.search(r"\\examdisplaycases", tex)
        if not m:
            break
        args, end = _brace_opt(tex, m.end())
        rep = (r"\[" + args[0] + r"\begin{cases}" + args[1] + r"\end{cases}\]") if len(args) >= 2 else ""
        tex = tex[:m.start()] + rep + tex[end:]

    while True:
        m = re.search(r"\\examdisplayaligned", tex)
        if not m:
            break
        args, end = _brace_opt(tex, m.end())
        rep = r"\[\begin{aligned}" + (args[-1] if args else "") + r"\end{aligned}\]" if args else ""
        tex = tex[:m.start()] + rep + tex[end:]

    while True:
        m = re.search(r"\\examdisplayarray", tex)
        if not m:
            break
        args, end = _brace_opt(tex, m.end())
        rep = ""
        if len(args) >= 4:
            rep = r"\[" + args[0] + r"\begin{array}{" + args[1] + "}" + args[2] + r"\end{array}" + args[3] + r"\]"
        tex = tex[:m.start()] + rep + tex[end:]

    while True:
        m = re.search(r"\\examdisplaychain", tex)
        if not m:
            break
        args, end = _brace_opt(tex, m.end())
        rep = r"\begin{align*}" + (args[0] if args else "") + r"\end{align*}" if args else ""
        tex = tex[:m.start()] + rep + tex[end:]

    return tex


def strip_figures(tex: str) -> tuple[str, list[str]]:
    figs = FIGURE_RE.findall(tex)
    tex = FIGURE_RE.sub("", tex)
    tex = re.sub(r"\\(?:solutionfigure|examfiguregroup)\s*", "", tex)
    return tex, figs


# ------------------------------------------------------------------ text prep

ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def normalise(tex: str) -> str:
    tex = expand_special(tex)
    tex, _ = strip_figures(tex)
    # Strip prose environments HERE, before the math/text split: when a problem
    # has unbalanced \( \) delimiters these tags can end up inside a math
    # segment, where _render_text would never see them.
    tex = re.sub(r"\\(?:begin|end)\{(enumerate|itemize|description|list|circlelist"
                 r"|quote|quotation|center|flushleft|flushright|small|footnotesize"
                 r"|large|bfseries|itshape|ttfamily|raggedright|array)\}", " ", tex)
    tex = re.sub(r"\\begin\{tabular\}(?:\{[^}]*\})?(?:\[[^\]]*\])?", " ", tex)
    tex = re.sub(r"\\begin\{minipage\}(?:\[[^\]]*\])?\{[^}]*\}", " ", tex)
    tex = re.sub(r"(?<!\\)%.*", "", tex)
    for c in DROP_CMD:
        tex = re.sub(re.escape(c) + r"\b", "", tex)
    # \linewidth / \paperwidth / \textwidth dimension reads
    tex = re.sub(r"\\(?:linewidth|paperwidth|textwidth|tabcolsep|arraystretch|baselineskip|leftskip|rightskip|dimexpr)\b", "", tex)
    tex = re.sub(r"\\makebox(?:\[[^\]]*\])?\{[^}]*\}", "", tex)
    tex = re.sub(r"\\cline\{[^}]*\}", r"\\hline", tex)
    # myarc: \myarc{x}
    tex = re.sub(r"\\myarc\{([^{}]*)\}", r"\\overset{\\frown}{\1}", tex)
    # single-arg wrappers
    for name, wrapper in MACRO_WRAP1.items():
        def _w(m, w=wrapper, nm=name):
            return w + m.group(1) + "}"
        tex = re.sub(re.escape(name) + r"\{([^{}]*)\}", _w, tex)
    # simple replacements (longest first, word-boundary safe)
    for src in (r"\i", r"\e", r"\d", r"\R", r"\Z", r"\N", r"\degree", r"\Pr"):
        tex = re.sub(re.escape(src) + r"(?![a-zA-Z])",
                     MACRO_SIMPLE[src].replace("\\", "\\\\"), tex)
    # \circled{n} -> unicode circled numeral where possible
    def _circ(m):
        n = m.group(1)
        if n.isdigit() and 1 <= int(n) <= 20:
            return "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"[int(n) - 1]
        return "(" + n + ")"
    tex = re.sub(r"\\circled\{([^{}]*)\}", _circ, tex)
    tex = re.sub(r"\\fillinblank", r"\\underline{\\hspace{2.2em}}", tex)
    tex = re.sub(r"\\examspecialsection\{([^{}]*)\}", r"\\textbf{\1}", tex)
    # environments MathJax does not know, degrade gracefully
    tex = re.sub(r"\\(?:smallmatrix|minipage|subarray)\b", "matrix", tex)
    # Option bodies may be images (\choicebitmap / \choicetexfigure). Turn them
    # into <img> markup; a bare \choicebitmap{...} would otherwise print raw.
    tex = re.sub(r"\\(?:choicebitmap|choicetexfigure)(?:\[[^\]]*\])?\{([^}]*)\}",
                 lambda m: f'\\(\\includegraphics{{{m.group(1)}}}\\)', tex)
    tex = re.sub(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}",
                 lambda m: f'\\(\\includegraphics{{{m.group(1)}}}\\)', tex)
    return tex


# ------------------------------------------------------------ math/text split

INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)|\\\[\s*(.+?)\s*\\\]|\$([^$]+?)\$", re.S)


def split_math(tex: str) -> list[tuple[str, bool, bool]]:
    """Split LaTeX into [(text, is_math, is_display)] segments.

    `is_math` marks a math span; `is_display` records whether the source used
    \\[...\\] or an align/cases-style body that genuinely needs its own line.
    """
    out: list[tuple[str, bool, bool]] = []
    pos = 0
    for m in INLINE_MATH_RE.finditer(tex):
        if m.start() > pos:
            out.append((tex[pos:m.start()], False, False))
        body = (m.group(1) or m.group(2) or m.group(3) or "")
        if body.strip():
            display = (m.group(2) is not None) or bool(
                re.search(r"\\begin\{(aligned|gathered|array|split|align\*?|multline)\}"
                          r"|\\\\", body))
            out.append((body, True, display))
        pos = m.end()
    if pos < len(tex):
        out.append((tex[pos:], False, False))
    return out


BARE_MATH_RE = re.compile(r"\\(hspace|underline|overline|vec|overrightarrow|mathbf|mathrm|mathbb)")


def _wrap_bare_math(s: str) -> str:
    """Wrap standalone math macros that landed in a *text* segment.

    The corpus sometimes writes \\fillinblank or \\vec{a} outside \\(..\\), so
    MathJax never sees them and the raw macro is printed. A single balanced
    pass wraps the outermost macro once — layering separate regexes for
    \\hspace and \\underline double-wraps \\underline{\\hspace{..}}.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        m = BARE_MATH_RE.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        name = m.group(1)
        j = m.end()
        while j < n and s[j] == " ":      # \vec {a}
            j += 1
        if j >= n or s[j] != "{":
            out.append(m.group(0))
            i = m.end()
            continue
        depth = 0
        k = j
        while k < n:
            if s[k] == "\\":
                k += 2
                continue
            if s[k] == "{":
                depth += 1
            elif s[k] == "}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        if k >= n:
            out.append(s[m.start():])
            break
        arg = s[j:k + 1]
        if name == "hspace":
            out.append("\\(\\underline{\\hspace{2.2em}}\\)")
        else:
            out.append("\\(" + m.group(0) + arg + "\\)")
        i = k + 1
    return "".join(out)


def _render_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    # environments that are really prose -> readable text
    s = re.sub(r"\\begin\{(?:tabular)\}(?:\{[^}]*\})?(?:\[[^\]]*\])?", " ", s)
    s = re.sub(r"\\(?:begin|end)\{(?:enumerate|itemize|description|list|circlelist|quote|quotation|center|flushleft|flushright|small|footnotesize|large|bfseries|itshape|ttfamily|raggedright|centering|noindent|par|noindent)\}", " ", s)
    s = re.sub(r"\\begin\{minipage\}(?:\[[^\]]*\])?\{[^}]*\}", " ", s)
    s = re.sub(r"\\end\{tabular\}", " ", s)
    s = re.sub(r"\\begin\{center\}", " ", s)
    s = re.sub(r"\\end\{center\}", " ", s)
    s = re.sub(r"\\begin\{minipage\}(?:\[[^\]]*\])?\{[^}]*\}", " ", s)
    s = re.sub(r"\\end\{minipage\}", " ", s)
    s = re.sub(r"\\item\b", "\u2022 ", s)
    s = re.sub(r"\\hline\b", " ", s)
    s = re.sub(r"\\(?:quad|qquad|enspace)\b", " ", s)
    s = re.sub(r"\\[\[\]()]", "", s)        # stray delimiters outside math
    s = _wrap_bare_math(s)
    s = re.sub(r"\\(?:par|noindent|centering)\b", "\n", s)
    s = re.sub(r"\\\\", " ", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()
    return "".join(ESCAPE.get(c, c) for c in s)


def tex_to_html(tex: str, figure_prefix: str = "") -> tuple[str, list[str]]:
    """Return (html, figure_paths). MathJax renders the \\( \\) / \\[ \\] spans."""
    if not tex or not tex.strip():
        return "", []
    _, figs = strip_figures(tex)
    t = normalise(tex)
    html_parts: list[str] = []
    for seg, is_math, display in split_math(t):
        if is_math:
            body = seg.strip()
            if body:
                # The HTML parser runs BEFORE MathJax, so a bare '<' followed by
                # a letter inside a math span is eaten as a tag start and the
                # formula silently never renders. Escaping to entities makes
                # the DOM text identical to the intended LaTeX, so MathJax
                # (and \text{...} inside it) behaves exactly as before.
                # \<len> is LaTeX row spacing ("\\[0.5ex]"). The inner "["
                # reads as a display-math opener to MathJax's delimiter
                # scanner, so drop the optional length (web rendering has no
                # use for the extra leading anyway).
                body = re.sub(r"\\\\\[[^\]]*\]", r"\\\\", body)
                body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_parts.append(("\\[" + body + "\\]") if display
                                  else ("\\(" + body + "\\)"))
        else:
            html_parts.append(_render_text(seg))
    html = "".join(html_parts)

    imgs = []
    for f in figs:
        imgs.append(f)
        if f.lower().endswith(".tex"):
            # TikZ vector source cannot render as an <img>; offer the source
            # instead of shipping a broken image tag.
            html += ('\n<figure class="fig texfig">'
                     f'<a href="{figure_prefix}{f}" target="_blank" rel="noopener">'
                     '\u77e2\u91cf\u9898\u56fe\uff08TikZ \u6e90\u7801 .tex\uff09'
                     '\u00b7 \u70b9\u51fb\u67e5\u770b</a></figure>')
        else:
            html += (f'\n<figure class="fig"><img loading="lazy" src="{figure_prefix}{f}"'
                     f' alt="\u9898\u56fe"></figure>')
    return html.strip(), imgs


# Symbol names a student would search in Chinese but which live as LaTeX
# macros in the source. Applied only to the plain-text/search projection.
SYMBOL_CN = {
    r"\perp": "垂直", r"\parallel": "平行", r"\angle": "角", r"\triangle": "三角形",
    r"\degree": "度", r"\sim": "相似", r"\cong": "全等", r"\approx": "约等于",
    r"\neq": "不等于", r"\ne": "不等于", r"\leq": "小于等于", r"\le": "小于等于",
    r"\geq": "大于等于", r"\ge": "大于等于", r"\times": "乘", r"\cdot": "点乘",
    r"\in": "属于", r"\cap": "交集", r"\cup": "并集",
    r"\subseteq": "子集", r"\supseteq": "包含",
    r"\subset": "子集", r"\supset": "包含",
    r"\complement": "补集", r"\odot": "⊙",
    r"\to\infty": "趋于无穷", r"\to+\infty": "趋于无穷",
    r"\infty": "无穷大", r"\to": "趋于", r"\rightarrow": "指向", r"\Rightarrow": "推出",
    r"\lim": "极限", r"\sin": "正弦", r"\cos": "余弦", r"\tan": "正切",
    r"\cot": "余切", r"\log": "对数", r"\ln": "自然对数", r"\lg": "常用对数",
    r"\exp": "指数", r"\pi": "π", r"\alpha": "阿尔法", r"\beta": "贝塔",
    r"\theta": "theta", r"\lambda": "lambda", r"\varphi": "phi", r"\omega": "omega",
    r"\arcsin": "反正弦", r"\arccos": "反余弦", r"\arctan": "反正切",
    r"\leqslant": "小于等于", r"\geqslant": "大于等于",
    r"\lim_{n\to\infty}": "n趋于无穷", r"\lim_{x\to\infty}": "x趋于无穷",
    r"\displaystyle": "", r"\mathrm": "", r"\mathbf": "", r"\cdot": "·",
    r"\ldots": "…", r"\cdots": "…", r"\sqrt": "根号", r"\left": " ", r"\right": " ",
    r"\lim": "极限", r"\sin": "正弦", r"\cos": "余弦", r"\tan": "正切",
}


def _build_symbol_re() -> re.Pattern:
    """Longest-first alternation, each alternative boundary-guarded.

    Without the guard `\\le` matches inside `\\left` and `\\lim` inside
    `\\limits`, leaving the fragments '小于等于ft' / '极限its_' behind.
    """
    bs = chr(92)
    alts = []
    for k in sorted(SYMBOL_CN, key=len, reverse=True):
        # only append a boundary to bare control words
        if len(k) >= 2 and k[0] == bs and k[1:].isalpha():
            alts.append(re.escape(k) + r"(?![a-zA-Z])")
        else:
            alts.append(re.escape(k))
    return re.compile("|".join(alts))


_SYMBOL_RE = _build_symbol_re()


def tex_to_plain(tex: str) -> str:
    """Plain text for full-text search and keyword matching."""
    if not tex:
        return ""
    _, _f = strip_figures(tex)
    t = normalise(tex)
    parts = []
    for seg, is_math, _d in split_math(t):
        if is_math:
            body = _SYMBOL_RE.sub(lambda m: SYMBOL_CN[m.group(0)], seg)
            parts.append(" " + body + " ")
        else:
            parts.append(_render_text(seg))
    s = "".join(parts)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Consolidated cleanup so the snippet on a card reads like prose, not source.
    s = re.sub(r"\\underline\{\\hspace\{[^{}]*\}\}(?:\{\})?", "____", s)
    s = re.sub(r"\\hspace\{[^{}]*\}", "____", s)
    s = re.sub(r"\\(?:begin|end)\{[a-zA-Z*]+\}", " ", s)
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"\\[^a-zA-Z0-9\s]", " ", s)     # escaped specials: \{ \} \% …
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"([\^_])\s+", r"\1", s)      # "y^ 2" -> "y^2"
    s = re.sub(r"\s+([，。；：、）】])", r"\1", s)
    s = re.sub(r"\s{2,}", " ", s)
    s = s.strip(" .,")
    return s
