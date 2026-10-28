"""生成纳指与波动率日报。

用法：
    python build.py            # 有新的交易日数据时才重新生成
    python build.py --force    # 无论数据是否更新都重新生成
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dashboard import commentary, data, indicators, render

OUT = Path(__file__).resolve().parent / "docs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="数据日期没变也重新生成")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    md = data.load()
    logging.info("数据日期 %s，数据源 %s", md.asof, md.sources)
    for n in md.notes:
        logging.info("说明：%s", n)

    snap = args.out / "data.json"
    if not args.force and snap.exists():
        prev = json.loads(snap.read_text(encoding="utf-8")).get("asof")
        # ISO 日期字符串可以直接比较大小。备用源可能比上次的数据还旧，这时也不覆盖
        if prev and md.asof.isoformat() <= prev:
            logging.info("没有新的交易日数据（本次 %s，上次已生成 %s），跳过。", md.asof, prev)
            return 0

    metrics, ts = indicators.compute(md.close)
    text = commentary.build(metrics)
    out = render.render(md, metrics, text, ts, args.out)
    logging.info("已生成 %s", out)
    logging.info("摘要：%s", text.headline)
    return 0


if __name__ == "__main__":
    sys.exit(main())
