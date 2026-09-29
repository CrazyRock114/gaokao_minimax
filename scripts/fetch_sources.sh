#!/usr/bin/env bash
# 拉取上游真题语料。
#
# 两个上游仓库体积很大（711 MB + 306 MB），因此不入本仓库，改由本脚本按需拉取。
# 拉取后执行 pipeline/ 下的脚本即可完整重建题库与站点。
#
#   bash scripts/fetch_sources.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 原始扫描卷（PDF，711 MB，CC BY 4.0）
if [ ! -d vendor_deekur/.git ]; then
  echo "==> 拉取 deekur/gaokaomath（原始扫描卷，~711 MB）"
  git clone --depth 1 https://github.com/deekur/gaokaomath.git vendor_deekur
else
  echo "==> vendor_deekur 已存在，跳过"
fi

# 整理后的 LaTeX 题库（306 MB，CC BY-SA 4.0）
# 管线实际读取的是这个仓库的 content/ 与 img/
if [ ! -d vendor_dxathing/.git ]; then
  echo "==> 拉取 DxAThing/Gaokao-Math-Problems-Compilation（LaTeX 题库，~306 MB）"
  git clone --depth 1 https://github.com/DxAThing/Gaokao-Math-Problems-Compilation.git vendor_dxathing
else
  echo "==> vendor_dxathing 已存在，跳过"
fi

cat <<'EOF'

上游已就绪。接下来重建题库与站点：

    python3 pipeline/parse_tex.py     # LaTeX -> data/problems.jsonl        (~2s)
    python3 pipeline/enrich.py       # 渲染 + 打标签 + 难度               (~90s)
    python3 pipeline/build_site.py   # 生成 site/data + 拷贝题图          (~5s)
    python3 pipeline/make_report.py  # 生成 site/report/index.html

校验（应当全部通过）：

    python3 pipeline/selftest_parse.py   # 30 项解析单测
    python3 pipeline/verify_parse.py     # 逐文件核对解析完整性
    python3 pipeline/acceptance.py       # 26 项全库验收

本地预览：

    cd site && python3 -m http.server 8817   # http://localhost:8817
EOF
