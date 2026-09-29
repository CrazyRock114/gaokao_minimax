#!/usr/bin/env python3
"""Profile parse_file on a sample of files to find the hotspot."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_tex as P  # noqa: E402

CONTENT = P.CONTENT
files = sorted(CONTENT.rglob("*.tex"))
idxs = [int(x) for x in sys.argv[1:]] or [0, 1, 2, 3, 4, 5, 100, 300, 500, 700]
for i in idxs:
    f = files[i]
    t0 = time.time()
    r = P.parse_file(f)
    dt = time.time() - t0
    size = f.stat().st_size
    print(f"{dt:8.3f}s  {len(r):4d} probs  {size/1024:7.0f}KB  {f.relative_to(CONTENT).as_posix()}")
