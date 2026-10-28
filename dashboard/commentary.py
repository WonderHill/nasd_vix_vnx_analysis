"""用固定规则把指标翻译成中文分析。

所有阈值都集中在这里，方便以后自己调整。规则只描述当前状态，不预测涨跌。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Signal:
    level: str  # "info" | "warn" | "alert"
    text: str


@dataclass
class Section:
    title: str
    paragraphs: list[str] = field(default_factory=list)
    signals: list[Signal] = field(default_factory=list)


@dataclass
class Commentary:
    headline: str
    trend_tag: str
    vol_tag: str
    sections: list[Section]


def _p(x: float | None, digits: int = 2, sign: bool = True) -> str:
    """格式化百分比。"""
    if x is None:
        return "—"
    return f"{x:+.{digits}f}%" if sign else f"{x:.{digits}f}%"


def _n(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{x:,.{digits}f}"


# ---------- 纳指走势 ----------

def _trend(m: dict) -> tuple[str, str]:
    """返回 (简短标签, 描述)。"""
    c, a20, a50, a200 = m["close"], m["ma20"], m["ma50"], m["ma200"]
    if None in (a20, a50, a200):
        return "数据不足", "历史数据不足 200 个交易日，无法判断长期趋势。"
    if c > a20 > a50 > a200:
        return "强势上涨", "收盘价位于 20、50、200 日均线之上，且均线呈多头排列，短中长期趋势一致向上。"
    if c < a20 < a50 < a200:
        return "弱势下跌", "收盘价位于 20、50、200 日均线之下，且均线呈空头排列，短中长期趋势一致向下。"
    if c > a200 and a50 > a200:
        if c < a50:
            return "上升中回调", "长期趋势仍然向上（50 日均线在 200 日均线之上），但价格已跌破 50 日均线，处于回调阶段。"
        return "上升趋势", "价格位于 50 日和 200 日均线之上，中长期趋势向上，短期有所波动。"
    if c < a200 and a50 < a200:
        if c > a50:
            return "下跌中反弹", "长期趋势偏弱（50 日均线在 200 日均线之下），价格反弹到 50 日均线之上，但仍低于 200 日均线。"
        return "下降趋势", "价格位于 50 日和 200 日均线之下，中长期趋势向下。"
    if c > a200:
        return "震荡偏强", "价格在 200 日均线之上，但均线方向不一致，处于震荡阶段。"
    return "震荡偏弱", "价格跌破 200 日均线，均线方向不一致，趋势转弱。"


def _move_word(pct: float) -> str:
    a = abs(pct)
    up = pct >= 0
    if a >= 3:
        return "大涨" if up else "大跌"
    if a >= 1.5:
        return "明显上涨" if up else "明显下跌"
    if a >= 0.5:
        return "上涨" if up else "下跌"
    return "小幅上涨" if up else "小幅下跌"


def _nasdaq_section(m: dict) -> tuple[Section, str]:
    ix, ndx = m["ixic"], m["ndx"]
    sec = Section("纳斯达克指数走势")
    tag, trend_text = _trend(ix)

    sec.paragraphs.append(
        f"纳斯达克综合指数收于 {_n(ix['close'])}，{_move_word(ix['chg_pct'])} {_p(ix['chg_pct'])}"
        f"（{ix['chg']:+,.2f} 点）；纳斯达克 100 收于 {_n(ndx['close'])}，{_p(ndx['chg_pct'])}。"
        f"近 5 日 {_p(ix['ret_5d'])}，近 20 日 {_p(ix['ret_20d'])}，年初至今 {_p(ix['ret_ytd'])}。"
    )
    sec.paragraphs.append(
        f"{trend_text}当前距 20 日均线 {_p(ix['dist_ma20'])}，距 50 日均线 {_p(ix['dist_ma50'])}，"
        f"距 200 日均线 {_p(ix['dist_ma200'])}。"
    )

    dd = ix["drawdown"]
    if dd > -2:
        dd_text = "接近 52 周高点"
    elif dd > -10:
        dd_text = "处于正常回撤范围"
    elif dd > -20:
        dd_text = "已进入调整区间（回撤超过 10%）"
    else:
        dd_text = "回撤超过 20%，按常用定义已进入熊市区间"
    sec.paragraphs.append(
        f"距 52 周高点 {_n(ix['high_52w'])} 回撤 {_p(-dd, sign=False)}，{dd_text}。"
        f"RSI(14) 为 {_n(ix['rsi14'], 1)}，20 日已实现波动率（年化）为 {_n(ix['rv20'], 1)}%。"
    )

    r = ix["rsi14"]
    if r is not None and r >= 70:
        sec.signals.append(Signal("warn", f"RSI {r:.1f}，进入超买区（≥70），短期涨幅较大。"))
    elif r is not None and r <= 30:
        sec.signals.append(Signal("warn", f"RSI {r:.1f}，进入超卖区（≤30），短期跌幅较大。"))
    if abs(ix["chg_pct"]) >= 3:
        sec.signals.append(Signal("alert", f"单日波动 {_p(ix['chg_pct'])}，幅度超过 3%。"))
    if ix["dist_ma200"] is not None and abs(ix["dist_ma200"]) < 1:
        sec.signals.append(Signal("warn", "价格贴近 200 日均线（±1% 以内），长期趋势处于关键位置。"))
    if dd <= -10:
        sec.signals.append(Signal("alert" if dd <= -20 else "warn", f"距 52 周高点回撤 {_p(-dd, sign=False)}。"))
    return sec, tag


# ---------- 波动率 ----------

def _vix_level(v: float) -> tuple[str, str]:
    """VIX 绝对水平的粗略分档（VIX 长期中位数大约在 17-18）。"""
    if v < 12:
        return "极低", "市场非常平静，对冲成本便宜，但也容易出现过度乐观"
    if v < 15:
        return "偏低", "市场情绪平稳"
    if v < 20:
        return "正常", "处于历史常见区间"
    if v < 30:
        return "偏高", "市场有一定紧张情绪"
    return "恐慌", "市场处于明显的恐慌状态"


def _pct_word(p: float | None) -> str:
    if p is None:
        return ""
    if p >= 90:
        return "处于过去一年的最高区域"
    if p >= 70:
        return "高于过去一年的大多数时间"
    if p <= 10:
        return "处于过去一年的最低区域"
    if p <= 30:
        return "低于过去一年的大多数时间"
    return "处于过去一年的中间水平"


def _vol_section(m: dict) -> tuple[Section, str]:
    vix, vxn, sp, vrp, term = m["vix"], m["vxn"], m["spread"], m["vrp"], m["term"]
    sec = Section("VIX 与 VXN 波动率")
    level, level_text = _vix_level(vix["value"])

    sec.paragraphs.append(
        f"VIX 收于 {_n(vix['value'])}，较前一日 {vix['chg']:+.2f}（{_p(vix['chg_pct'], 1)}），"
        f"水平{level}，{level_text}。过去一年百分位 {_n(vix['pct_1y'], 0)}%，{_pct_word(vix['pct_1y'])}"
        f"（一年区间 {_n(vix['low_1y'])} – {_n(vix['high_1y'])}，中位数 {_n(vix['median_1y'])}）。"
    )
    sec.paragraphs.append(
        f"VXN 收于 {_n(vxn['value'])}，较前一日 {vxn['chg']:+.2f}（{_p(vxn['chg_pct'], 1)}），"
        f"过去一年百分位 {_n(vxn['pct_1y'], 0)}%，{_pct_word(vxn['pct_1y'])}。"
        f"VXN 比 VIX 高 {_n(sp['value'])} 个点（一年中位数 {_n(sp['median_1y'])}），"
        + (
            "科技股相对大盘的风险溢价偏高。"
            if (sp["pct_1y"] or 50) >= 80
            else "科技股相对大盘的风险溢价偏低。"
            if (sp["pct_1y"] or 50) <= 20
            else "科技股相对大盘的风险溢价处于正常水平。"
        )
    )
    sec.paragraphs.append(
        f"纳指 100 的 20 日已实现波动率为 {_n(vrp['ndx_rv20'], 1)}%，VXN 比它高 {_n(vrp['value'], 1)} 个点"
        f"（一年中位数 {_n(vrp['median_1y'], 1)}）。隐含波动率通常高于已实现波动率，差值代表期权市场为不确定性支付的溢价。"
    )

    if term:
        r = term["ratio"]
        if r >= 1:
            t_text = "期限结构倒挂（短期波动率高于 3 个月波动率），说明短期恐慌程度高于中期预期，通常出现在市场紧张时。"
        elif r >= 0.95:
            t_text = "期限结构接近持平，短期避险需求在上升。"
        elif r >= 0.85:
            t_text = "期限结构为正常的升水状态，短期没有明显的恐慌。"
        else:
            t_text = "期限结构升水幅度较大，短期情绪非常平静。"
        sec.paragraphs.append(
            f"VIX / VIX3M = {r:.3f}（VIX3M 为 {_n(term['vix3m'])}，5 个交易日前为 {_n(term['ratio_5d_ago'], 3)}）。{t_text}"
        )
        if r >= 1:
            sec.signals.append(Signal("alert", f"VIX 期限结构倒挂（比值 {r:.3f}）。"))
        elif r >= 0.95:
            sec.signals.append(Signal("warn", f"VIX 期限结构接近倒挂（比值 {r:.3f}）。"))

    if vix["chg_pct"] >= 15:
        sec.signals.append(Signal("alert", f"VIX 单日上升 {_p(vix['chg_pct'], 1)}，恐慌情绪快速升温。"))
    elif vix["chg_pct"] >= 8:
        sec.signals.append(Signal("warn", f"VIX 单日上升 {_p(vix['chg_pct'], 1)}。"))
    elif vix["chg_pct"] <= -10:
        sec.signals.append(Signal("info", f"VIX 单日下降 {_p(vix['chg_pct'], 1)}，紧张情绪明显缓解。"))
    if vix["value"] >= 30:
        sec.signals.append(Signal("alert", f"VIX 高于 30（{vix['value']:.2f}）。"))
    elif vix["value"] < 12:
        sec.signals.append(Signal("warn", f"VIX 低于 12（{vix['value']:.2f}），市场可能过于自满。"))
    if vrp["value"] is not None and vrp["value"] < 0:
        sec.signals.append(Signal("warn", "VXN 低于纳指 100 的实际波动率，这种情况不常见，说明实际波动超出了期权市场的预期。"))
    return sec, level


# ---------- 两者关系 ----------

def _relation_section(m: dict) -> Section:
    ix, vix, c = m["ixic"], m["vix"], m["corr"]
    sec = Section("纳指与 VIX 的关系")
    c20, c1y = c["ixic_vix_20d"], c["ixic_vix_1y"]

    if c20 is None:
        strength = "无法计算"
    elif c20 <= -0.6:
        strength = "强负相关，符合常态"
    elif c20 <= -0.3:
        strength = "中等负相关，基本符合常态"
    elif c20 < 0:
        strength = "弱负相关，反向关系有所减弱"
    else:
        strength = "正相关，反向关系暂时失效"
    sec.paragraphs.append(
        f"过去 20 个交易日，纳指日涨跌幅与 VIX 日变化的相关系数为 {_n(c20)}，{strength}；"
        f"过去一年为 {_n(c1y)}。纳指 100 与 VXN 的 20 日相关系数为 {_n(c['ndx_vxn_20d'])}。"
    )

    same_dir = (ix["chg_pct"] > 0.3 and vix["chg_pct"] > 3) or (ix["chg_pct"] < -0.3 and vix["chg_pct"] < -3)
    if same_dir:
        word = "上涨" if ix["chg_pct"] > 0 else "下跌"
        sec.paragraphs.append(
            f"今天纳指和 VIX 同时{word}（纳指 {_p(ix['chg_pct'])}，VIX {_p(vix['chg_pct'], 1)}）。"
            + (
                "指数上涨但避险需求同时上升，常见于重大事件前的对冲，或看涨期权投机推高了隐含波动率。"
                if ix["chg_pct"] > 0
                else "指数下跌但恐慌没有加剧，可能说明下跌已被市场预期，或之前的避险头寸在平仓。"
            )
        )
        sec.signals.append(Signal("warn", f"纳指与 VIX 同向{word}，偏离通常的反向关系。"))
    else:
        sec.paragraphs.append("今天两者的变化方向符合通常的反向关系，或变化幅度太小，不足以判断。")

    if c20 is not None and c20 >= 0:
        sec.signals.append(Signal("warn", f"20 日相关系数为 {c20:+.2f}，纳指与 VIX 的负相关暂时失效。"))
    return sec


def build(m: dict) -> Commentary:
    nas, trend_tag = _nasdaq_section(m)
    vol, vol_tag = _vol_section(m)
    rel = _relation_section(m)

    ix, vix = m["ixic"], m["vix"]
    headline = (
        f"纳指{_move_word(ix['chg_pct'])} {_p(ix['chg_pct'])}，趋势：{trend_tag}；"
        f"VIX {vix['value']:.2f}（{_p(vix['chg_pct'], 1)}），波动率水平{vol_tag}。"
    )
    n_alert = sum(s.level == "alert" for sec in (nas, vol, rel) for s in sec.signals)
    n_warn = sum(s.level == "warn" for sec in (nas, vol, rel) for s in sec.signals)
    if n_alert:
        headline += f"今日有 {n_alert} 项需要重点关注的信号。"
    elif n_warn:
        headline += f"今日有 {n_warn} 项提示信号。"
    else:
        headline += "今日没有异常信号。"

    return Commentary(headline=headline, trend_tag=trend_tag, vol_tag=vol_tag, sections=[nas, vol, rel])
