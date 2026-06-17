# Tesla 股价分析 Agent

这是一个面向 `TSLA` 起步、可扩展到更多股票的研究型投资 agent MVP。系统采用三层架构：信息收集层、分析处理层、建议生成/决策表达层。`stock_agent` 是通用主体，`tsla_agent` 是 TSLA 专用入口。

> 重要：预测结果只能作为研究辅助，不构成投资建议。股票价格会受突发新闻、流动性、宏观政策和市场情绪影响，任何模型都不能稳定预测未来价格。

## 能力范围

- 第一层收集可能影响股价的信息：行情、SEC 披露、新闻/RSS、示例本地事件。
- 第二层把事实转为分析信号：事件评分、驱动因子权重、市场状态和情景预测。
- 第三层在显式开启时，根据投资者画像生成条件化投资/交易计划。
- 基于价格动量、均线、波动率和事件情绪生成 1/5/20 日预测区间。
- 可选调用 OpenAI-compatible Chat Completions 接口做高层综合摘要。
- 输出可追踪来源的中文 Markdown 报告。

## 快速开始

在当前目录运行示例数据报告：

```bash
python3 -m tsla_agent --sample-data --offline
```

生成的报告会写入 `reports/`。

默认报告只包含研究分析，不输出第三层建议计划。显式开启第三层：

```bash
python3 -m tsla_agent --sample-data --offline \
  --include-decision-plan \
  --investor-type short_term_trader
```

可选投资者画像：

- `long_term_fundamental`
- `growth_narrative`
- `event_driven`
- `swing_trader`
- `short_term_trader`
- `risk_control`

## 独立信息收集层

第一层信息收集模块位于 `stock_agent.collection`，只负责数据采集、标准化、去重、冲突识别、来源可信度标注和数据质量报告，不生成买卖判断、预测、目标价或交易计划。

统一入口：

```python
from stock_agent.collection import CollectionRequest, collect_data

result = collect_data(CollectionRequest(
    symbol="TSLA",
    market="US",
    data_requirements=["market_data", "news_events"],
    data_source_config={
        "local": {
            "enabled": True,
            "prices_csv": "data/sample_prices.csv",
            "events_json": "data/sample_events.json",
        }
    },
))
```

## 分析处理层

第二层位于 `stock_agent.analysis`。它输入第一层采集结果或兼容的价格/事件对象，输出：

- 市场状态：最新价格、涨跌幅、波动率、均线、支撑/压力、ATR。
- 事件信号：类别、驱动因子、方向、影响分、时间窗口、来源可信度。
- 驱动因子权重分析：交付/库存/价格、基本面、长期叙事、宏观、竞争、监管、技术面/期权/资金流、估值/安全边际等。
- Bear/Base/Bull 情景区间。
- 数据质量降级原因和分析置信度。

第二层只生成分析信号，不生成投资者专属建议。

## 建议生成/决策表达层

第三层位于 `stock_agent.decision`。它输入第二层 `AnalysisResult` 和投资者画像，输出条件化计划：

- 当前倾向和置信度。
- 支持因素和风险因素。
- 条件化参与方案。
- 卖出/减仓条件。
- 止损/失效条件。
- 不交易条件。
- 反方观点和后续监控清单。

第三层必须显式开启。它允许输出条件化计划，但禁止无条件买入/卖出结论。

第三层也可以独立运行。输入必须是第二层 `AnalysisResult.to_dict()` 生成的 JSON，因此不会触发采集层，也不会改变分析层输出：

```bash
python3 -m stock_agent.decision \
  --input analysis_result.json \
  --output decision_plan.md \
  --format markdown \
  --investor-type short_term_trader
```

也可以通过统一工具入口运行：

```bash
python3 -m stock_agent.cli decide \
  --input analysis_result.json \
  --output decision_plan.json \
  --format json \
  --investor-type long_term_fundamental
```

生成第三层测试中文报告：

```bash
python3 -m stock_agent.decision.test_report
```

默认报告写入 `reports/decision_layer_test_report.md`。也可以指定输出路径和测试详细度：

```bash
python3 -m stock_agent.decision.test_report \
  --output reports/decision_layer_test_report_custom.md \
  --verbosity 2
```

CLI 验证：

```bash
python3 -m stock_agent.cli collect \
  --symbol TSLA \
  --market US \
  --requirements market_data,news_events \
  --prices-csv data/sample_prices.csv \
  --events-json data/sample_events.json \
  --output collection_result.json
```

## 使用真实数据

### 1. Alpha Vantage 行情和新闻

```bash
export ALPHAVANTAGE_API_KEY="你的 key"
python3 -m tsla_agent --symbol TSLA
```

### 2. SEC 披露

SEC 要求请求带有可联系的 User-Agent：

```bash
export SEC_USER_AGENT="Your Name your.email@example.com"
python3 -m tsla_agent --symbol TSLA
```

### 3. RSS 新闻源

把你信任的财经新闻 RSS 源放进环境变量：

```bash
export NEWS_RSS_URLS="https://example.com/rss,https://another.example.com/feed"
python3 -m tsla_agent --symbol TSLA
```

### 4. LLM 总结

如果你有 OpenAI 或兼容 Chat Completions 的服务：

```bash
export OPENAI_API_KEY="你的 key"
export LLM_MODEL="你的模型名"
python3 -m tsla_agent --symbol TSLA
```

可选：

```bash
export OPENAI_BASE_URL="https://api.openai.com/v1"
```

如果不设置 `OPENAI_API_KEY` 和 `LLM_MODEL`，agent 会使用本地规则生成摘要。

## 本地数据格式

价格 CSV 至少需要：

```csv
date,close
2026-01-02,248.5
```

事件 JSON 示例：

```json
[
  {
    "source": "manual",
    "title": "Quarterly deliveries beat consensus",
    "summary": "Sample event only.",
    "category": "delivery",
    "published_at": "2026-01-05",
    "url": "https://example.com"
  }
]
```

运行：

```bash
python3 -m tsla_agent --prices-csv path/to/prices.csv --events-json path/to/events.json --offline
```

## 数据源路线图与质量门禁

生产版本按低成本优先拆成 P1/P2/P3 路线图。当前阶段不直接接入新外部 API，而是先让系统明确知道缺少哪些数据，以及这些缺口如何降低分析层和投资者画像的置信度。

### P1：优先补齐

- 高质量行情：先用 Alpha Vantage、本地 CSV、Nasdaq Data Link 免费/低价数据集等；Polygon/IEX 可作为付费增强；Bloomberg/FactSet 暂列为后期增强。
- 财报与预期：SEC、公司 IR、earnings call transcripts、本地分析师预期 CSV。
- 宏观变量：FRED、公开 VIX/指数 CSV、美元指数/纳指本地导入。
- 严格回测：walk-forward validation、特征泄漏检查、交易成本和滑点。

### P2：增强覆盖

- 行业数据：中国/欧洲/美国 EV 销量、库存、补贴、关税、召回、监管、竞争对手动态。
- 期权与资金流：IBKR 只读接口、本地期权链/put-call CSV、公开持仓 CSV。

### P3：后期高成本增强

- 实时低延迟行情、gamma exposure、机构级资金流。
- Bloomberg/FactSet 或同类终端数据。

`stock_agent.data_coverage` 会输出结构化覆盖报告。缺少财报会降低长期基本面画像置信度；缺少宏观会影响成长叙事、短线和风险控制画像；缺少成交量/期权会降低短线交易者画像置信度；样例数据参与时所有画像置信度最高为 `LOW`。
