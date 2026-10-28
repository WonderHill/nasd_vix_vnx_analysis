"""根据收盘价计算技术指标和波动率指标。所有数值都可以用公开数据复现。"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

YEAR = 252  # 一年的交易日数


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = gain / loss
    return 100 - 100 / (1 + rs)


def realized_vol(close: pd.Series, n: int = 20) -> pd.Series:
    """n 日已实现波动率，年化，单位 %。可以直接和 VIX/VXN 比较。"""
    logret = np.log(close).diff()
    return logret.rolling(n).std() * math.sqrt(YEAR) * 100


def pct_rank(series: pd.Series, window: int = YEAR) -> float | None:
    """最新值在过去 window 个交易日中的百分位（0-100）。"""
    s = series.dropna().iloc[-window:]
    if len(s) < 20:
        return None
    return float((s <= s.iloc[-1]).mean() * 100)


def _f(x) -> float | None:
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def _ret(close: pd.Series, n: int) -> float | None:
    if len(close) <= n:
        return None
    return _f((close.iloc[-1] / close.iloc[-1 - n] - 1) * 100)


def _index_metrics(close: pd.Series) -> dict:
    last, prev = close.iloc[-1], close.iloc[-2]
    ma = {n: close.rolling(n).mean() for n in (20, 50, 200)}
    high_52w = close.iloc[-YEAR:].max()

    this_year = close.index[-1].year
    prior = close[close.index.year < this_year]
    ytd = _f((last / prior.iloc[-1] - 1) * 100) if len(prior) else None

    m = {
        "close": _f(last),
        "chg": _f(last - prev),
        "chg_pct": _f((last / prev - 1) * 100),
        "ret_5d": _ret(close, 5),
        "ret_20d": _ret(close, 20),
        "ret_ytd": ytd,
        "rsi14": _f(rsi(close).iloc[-1]),
        "high_52w": _f(high_52w),
        "drawdown": _f((last / high_52w - 1) * 100),
        "rv20": _f(realized_vol(close).iloc[-1]),
    }
    for n, s in ma.items():
        m[f"ma{n}"] = _f(s.iloc[-1])
        m[f"dist_ma{n}"] = _f((last / s.iloc[-1] - 1) * 100) if _f(s.iloc[-1]) else None
    # 50 日均线的 10 日斜率，用来判断中期趋势方向
    m["ma50_slope"] = _f((ma[50].iloc[-1] / ma[50].iloc[-11] - 1) * 100) if len(close) > 60 else None
    return m


def _vol_metrics(s: pd.Series) -> dict:
    last, prev = s.iloc[-1], s.iloc[-2]
    window = s.iloc[-YEAR:]
    return {
        "value": _f(last),
        "chg": _f(last - prev),
        "chg_pct": _f((last / prev - 1) * 100),
        "chg_5d": _f(last - s.iloc[-6]) if len(s) > 5 else None,
        "ma20": _f(s.rolling(20).mean().iloc[-1]),
        "pct_1y": pct_rank(s),
        "high_1y": _f(window.max()),
        "low_1y": _f(window.min()),
        "median_1y": _f(window.median()),
    }


def compute(close: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """返回 (最新指标字典, 用于画图的时间序列)。"""
    ixic, ndx, vix, vxn = close["IXIC"], close["NDX"], close["VIX"], close["VXN"]

    ixic_ret = ixic.pct_change()
    vix_chg = vix.pct_change()
    corr20 = ixic_ret.rolling(20).corr(vix_chg)
    corr_ndx_vxn20 = ndx.pct_change().rolling(20).corr(vxn.pct_change())
    corr_1y = ixic_ret.iloc[-YEAR:].corr(vix_chg.iloc[-YEAR:])

    spread = vxn - vix
    ndx_rv20 = realized_vol(ndx)
    vrp = vxn - ndx_rv20  # 隐含波动率减已实现波动率

    m = {
        "ixic": _index_metrics(ixic),
        "ndx": _index_metrics(ndx),
        "vix": _vol_metrics(vix),
        "vxn": _vol_metrics(vxn),
        "spread": {
            "value": _f(spread.iloc[-1]),
            "pct_1y": pct_rank(spread),
            "median_1y": _f(spread.iloc[-YEAR:].median()),
        },
        "vrp": {
            "value": _f(vrp.iloc[-1]),
            "ndx_rv20": _f(ndx_rv20.iloc[-1]),
            "median_1y": _f(vrp.iloc[-YEAR:].median()),
        },
        "corr": {
            "ixic_vix_20d": _f(corr20.iloc[-1]),
            "ndx_vxn_20d": _f(corr_ndx_vxn20.iloc[-1]),
            "ixic_vix_1y": _f(corr_1y),
        },
        "term": None,
    }

    ts = pd.DataFrame(
        {
            "IXIC": ixic,
            "MA20": ixic.rolling(20).mean(),
            "MA50": ixic.rolling(50).mean(),
            "MA200": ixic.rolling(200).mean(),
            "VIX": vix,
            "VXN": vxn,
            "CORR20": corr20,
        }
    )

    if "VIX3M" in close and close["VIX3M"].notna().iloc[-1]:
        ratio = vix / close["VIX3M"]
        m["term"] = {
            "vix3m": _f(close["VIX3M"].iloc[-1]),
            "ratio": _f(ratio.iloc[-1]),
            "ratio_5d_ago": _f(ratio.iloc[-6]) if len(ratio) > 5 else None,
            "pct_1y": pct_rank(ratio),
        }
        ts["VIX3M"] = close["VIX3M"]
        ts["TERM"] = ratio

    return m, ts
