"""把指标、分析文字和图表数据渲染成静态 HTML。"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .commentary import Commentary
from .data import SERIES, MarketData

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


def _clean(values) -> list:
    out = []
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(round(float(v), 4))
    return out


def chart_payload(md: MarketData, ts: pd.DataFrame) -> dict:
    payload = {
        "dates": [d.strftime("%Y-%m-%d") for d in ts.index],
        "ixic": _clean(ts["IXIC"]),
        "ma20": _clean(ts["MA20"]),
        "ma50": _clean(ts["MA50"]),
        "ma200": _clean(ts["MA200"]),
        "vix": _clean(ts["VIX"]),
        "vxn": _clean(ts["VXN"]),
        "corr20": _clean(ts["CORR20"]),
        "vix3m": _clean(ts["VIX3M"]) if "VIX3M" in ts else None,
        "term": _clean(ts["TERM"]) if "TERM" in ts else None,
        "ohlc": None,
    }
    if md.ixic_ohlc is not None:
        o = md.ixic_ohlc.reindex(ts.index)
        # ECharts K 线的顺序是 [开, 收, 低, 高]
        payload["ohlc"] = [
            _clean([r.Open, r.Close, r.Low, r.High]) for r in o.itertuples()
        ]
    return payload


def render(md: MarketData, metrics: dict, commentary: Commentary, ts: pd.DataFrame, out_dir: Path) -> Path:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
    )
    tpl = env.get_template("index.html.j2")
    now_bj = datetime.now(ZoneInfo("Asia/Shanghai"))

    html = tpl.render(
        asof=md.asof.isoformat(),
        weekday="一二三四五六日"[md.asof.weekday()],
        generated=now_bj.strftime("%Y-%m-%d %H:%M"),
        m=metrics,
        c=commentary,
        notes=md.notes,
        sources=[(SERIES[k][2], v) for k, v in md.sources.items()],
        chart_json=json.dumps(chart_payload(md, ts), ensure_ascii=False, separators=(",", ":")),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "index.html"
    out.write_text(html, encoding="utf-8")

    snapshot = {
        "asof": md.asof.isoformat(),
        "generated": now_bj.isoformat(timespec="seconds"),
        "sources": md.sources,
        "metrics": metrics,
        "commentary": asdict(commentary),
    }
    (out_dir / "data.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out
