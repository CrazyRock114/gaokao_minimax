#!/usr/bin/env python3
"""List macros used in content/ that are NOT known-standard, so we can
build an explicit conversion map. Anything unknown is a rendering risk."""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
report = json.loads((ROOT / "data" / "macro_report.json").read_text(encoding="utf-8"))

# Macros MathJax/KaTeX handles out of the box.
KNOWN = set("""
frac dfrac tfrac sqrt sin cos tan cot sec csc arcsin arccos arctan sinh cosh tanh
ln log lg exp lim max min sup inf det gcd deg dim ker hom arg
left right begin end text textrm textbf textit textsf mathrm mathbf mathit mathbb mathcal mathfrak mathscr boldsymbol bm
quad qquad hspace vspace space nobreak linebreak newline par
alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega
Gamma Delta Theta Lambda Xi Pi Sigma Upsilon Phi Psi Omega
leq le leqslant geq ge geqslant ne neq equiv approx sim simeq cong propto asymp ll gg subset subseteq supset supseteq in ni notin cup cap setminus emptyset varnothing forall exists neg lnot land lor
times div cdot pm mp ast star circ bullet oplus ominus otimes odot perp parallel mid vert lvert rvert Vert lVert rVert lvert rvert
angle triangle triangle* square diamond
circ dfrac cdots ldots vdots ddots dots dotsb dotso
to rightarrow leftarrow leftrightarrow Rightarrow Leftarrow Leftrightarrow Longrightarrow mapsto implies iff
cup cap prod sum int iint iiint oint bigcup bigcap bigoplus bigodot bigvee bigwedge
binom dbinom tbinom matrix pmatrix bmatrix Bmatrix vmatrix Vmatrix cases array aligned alignedat gathered split subarray
overline underline overbrace underbrace vec hat tilde bar check breve acute grave dot ddot
mathbb R N Z Q C F E
prime deg ddotsC
arc ddot overline
bf it rm cal bb fr sf tt
array col multicolumn row
nonumber label ref
max min gcd
left. right.
mathchoice
Bigl Bigr Bigm Bigr Bigl Bigr Bign Bigl Biggr Biggm Bigl
bigl bigr bigm
left\{ right\} lbrace rbrace lbrack rbrack
ulcorner urcorner llcorner lrcorner
diagup diagdown
setminus
lhd rhd unrhd
Vvdash vdash models
colon
nolinebreak
hspace
raisebox
scalebox
resizebox
def eqno substack
underset overset xrightarrow xleftarrow
mathchoice
%$
""".split())

used = Counter(dict(report["macros"]))
unknown = [(k, v) for k, v in used.items() if k not in KNOWN]
unknown.sort(key=lambda x: -x[1])
print("total distinct macros:", len(used))
print("non-standard (need mapping):", len(unknown))
print()
for k, v in unknown:
    print(f"{v:7d}  \\{k}")
