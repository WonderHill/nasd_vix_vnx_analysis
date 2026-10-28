# 纳斯达克指数与波动率日报

每天美股收盘后自动生成一个静态网页，内容包括：

- 纳斯达克综合指数和纳斯达克 100 的走势：涨跌幅、均线位置、RSI、回撤、已实现波动率
- VIX 和 VXN：数值、一年百分位、VXN 与 VIX 的差值、隐含波动率与已实现波动率的差值
- VIX / VIX3M 期限结构
- 纳指与 VIX 的 20 日滚动相关系数，以及两者同涨同跌时的提示
- 交互图表（K 线和均线、波动率走势、期限结构、相关系数），可以切换 3 个月、6 个月、1 年或全部区间

分析文字由固定规则生成，只描述当前状态，不预测走势。

## 目录结构

```
build.py                    入口脚本
dashboard/data.py           拉取数据（主源 Yahoo，备用源 FRED）
dashboard/indicators.py     计算指标
dashboard/commentary.py     生成分析文字，所有阈值都在这个文件里
dashboard/render.py         渲染 HTML
templates/index.html.j2     页面模板
docs/                       生成结果（index.html、data.json、本地 ECharts）
.github/workflows/daily.yml 每日定时任务
```

## 本地运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build.py --force
```

运行后直接用浏览器打开 `docs/index.html`。ECharts 已经放在 `docs/assets/` 里，不依赖外部 CDN，国内网络也能正常显示。

不加 `--force` 时，只有出现新交易日的数据才会重新生成。

## 部署到 GitHub，每天自动更新

1. 在 GitHub 新建一个仓库，把这个目录推送上去。
2. 打开仓库的 Settings → Pages，Source 选择 “Deploy from a branch”，分支选 `main`，目录选 `/docs`。
3. 打开 Settings → Actions → General，在 Workflow permissions 中选择 “Read and write permissions”。
4. 在 Actions 页面手动运行一次 “每日更新”，确认能成功运行。

之后每个美股交易日的北京时间早上 6 点左右会自动更新页面。遇到美股休市日时，因为没有新数据，任务不会提交任何更改。

注意事项：

- 免费账户的 GitHub Pages 要求仓库是公开的，生成的网址任何人都可以访问。页面已经设置了 `noindex`，不会被搜索引擎收录。如果不希望公开，可以把仓库设为私有，不开启 Pages，在本地运行或从仓库下载 `docs/` 查看。
- GitHub 的定时任务可能延迟几分钟到几十分钟。仓库连续 60 天没有活动时，定时任务会被自动停用，需要到 Actions 页面重新启用。

## 数据源

| 指数 | Yahoo 代码 | FRED 序列 |
| --- | --- | --- |
| 纳斯达克综合指数 | ^IXIC | NASDAQCOM |
| 纳斯达克 100 | ^NDX | NASDAQ100 |
| VIX | ^VIX | VIXCLS |
| VXN | ^VXN | VXNCLS |
| VIX3M | ^VIX3M | VXVCLS |

Yahoo 是非官方接口，偶尔会限流或失效，这时程序会自动改用 FRED。FRED 只有收盘价，所以图表会从 K 线变成折线，数据通常也会晚一天。如果两个数据源都失败，程序会报错退出，页面保留上一次的内容。

## 调整规则

所有判断阈值都在 `dashboard/commentary.py` 里，例如 VIX 水平分档、RSI 超买超卖线、期限结构倒挂的判断标准。修改后运行 `python build.py --force` 就能看到效果。
