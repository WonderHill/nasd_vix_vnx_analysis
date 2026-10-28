"""拉取纳指、VIX、VXN 等日线数据。

主数据源：Yahoo Finance（yfinance），有开高低收。
备用数据源：FRED，只有收盘价，通常比 Yahoo 晚一天更新。
"""

from __future__ import annotations

import io
import logging
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

log = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")

# key -> (Yahoo 代码, FRED 序列, 中文名)
SERIES = {
    "IXIC": ("^IXIC", "NASDAQCOM", "纳斯达克综合指数"),
    "NDX": ("^NDX", "NASDAQ100", "纳斯达克 100"),
    "VIX": ("^VIX", "VIXCLS", "VIX（标普 500 波动率）"),
    "VXN": ("^VXN", "VXNCLS", "VXN（纳指 100 波动率）"),
    "VIX3M": ("^VIX3M", "VXVCLS", "VIX3M（3 个月波动率）"),
}
REQUIRED = ("IXIC", "NDX", "VIX", "VXN")  # VIX3M 缺失时只跳过期限结构分析

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


@dataclass
class MarketData:
    close: pd.DataFrame  # 每列一个指数的收盘价，按日期对齐
    ixic_ohlc: pd.DataFrame | None  # 纳指开高低收，FRED 兜底时为 None
    asof: date  # 分析所用的最新交易日
    sources: dict[str, str] = field(default_factory=dict)  # key -> "Yahoo" / "FRED"
    notes: list[str] = field(default_factory=list)


def _drop_unfinished_today(df: pd.DataFrame) -> pd.DataFrame:
    """盘中运行时，Yahoo 会返回当天未收盘的数据，需要去掉。"""
    if df.empty:
        return df
    now = datetime.now(NY)
    if df.index[-1].date() == now.date() and (now.hour, now.minute) < (16, 30):
        return df.iloc[:-1]
    return df


def _fetch_yahoo(start: date) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    symbols = [v[0] for v in SERIES.values()]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(
            symbols,
            start=start.isoformat(),
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=False,
        )
    out: dict[str, pd.DataFrame] = {}
    for key, (sym, _, _) in SERIES.items():
        if raw is None or raw.empty or sym not in raw.columns.get_level_values(0):
            continue
        df = raw[sym][["Open", "High", "Low", "Close"]].dropna(subset=["Close"])
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        df = _drop_unfinished_today(df)
        if len(df) > 0:
            out[key] = df
    return out


def _session() -> requests.Session:
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = requests.Session()
    retry = Retry(total=3, backoff_factor=3, status_forcelist=(429, 500, 502, 503, 504))
    s.mount("https://", HTTPAdapter(max_retries=retry))
    # 注意：不要设置自定义 User-Agent，FRED 会直接丢弃这类请求
    return s


_http = _session()


def _fetch_fred(series_id: str, start: date) -> pd.Series:
    # FRED 有时响应很慢，读超时设长一些，并自动重试
    resp = _http.get(
        FRED_URL,
        params={"id": series_id, "cosd": start.isoformat()},
        timeout=(10, 60),
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = ["date", "value"]
    s = pd.to_numeric(df["value"], errors="coerce")  # FRED 用 "." 表示缺失
    s.index = pd.to_datetime(df["date"])
    return s.dropna()


def load(years: int = 3) -> MarketData:
    start = date.today() - timedelta(days=365 * years + 10)
    closes: dict[str, pd.Series] = {}
    sources: dict[str, str] = {}
    notes: list[str] = []
    ixic_ohlc = None

    try:
        yahoo = _fetch_yahoo(start)
    except Exception as exc:  # 网络错误、限流、接口变化
        log.warning("Yahoo 拉取失败：%s", exc)
        yahoo = {}

    for key, (_, fred_id, name) in SERIES.items():
        if key in yahoo:
            closes[key] = yahoo[key]["Close"]
            sources[key] = "Yahoo"
            if key == "IXIC":
                ixic_ohlc = yahoo[key]
            continue
        try:
            closes[key] = _fetch_fred(fred_id, start)
            sources[key] = "FRED"
            notes.append(f"{name} 使用 FRED 备用数据（只有收盘价，可能晚一天）。")
        except Exception as exc:
            log.warning("FRED 拉取 %s 失败：%s", fred_id, exc)
            if key in REQUIRED:
                raise RuntimeError(f"{name} 两个数据源都失败，无法生成分析。") from exc
            notes.append(f"{name} 数据获取失败，已跳过相关分析。")

    close = pd.DataFrame(closes).sort_index()

    # 不同数据源更新时间不同，用所有必需序列都有数据的最新日期作为分析日
    asof_ts = min(close[k].last_valid_index() for k in REQUIRED)
    latest = max(close[k].last_valid_index() for k in REQUIRED)
    if latest > asof_ts:
        notes.append(
            f"部分数据只更新到 {asof_ts.date()}，为保证各指标在同一天对齐，分析日期取 {asof_ts.date()}。"
        )
    close = close.loc[:asof_ts]
    close = close.dropna(subset=list(REQUIRED), how="any")
    if ixic_ohlc is not None:
        ixic_ohlc = ixic_ohlc.loc[ixic_ohlc.index.isin(close.index)]

    return MarketData(
        close=close,
        ixic_ohlc=ixic_ohlc,
        asof=asof_ts.date(),
        sources=sources,
        notes=notes,
    )
