# 项目协作说明

本文档记录当前目录中项目的结构、运行方式和开发注意事项，供后续 agent 或开发者快速接手。

## 项目概览

这是一个 Python 股票研究辅助项目，当前重点围绕 `TSLA`，但主体架构应放在通用 `stock_agent` 包下，方便后续扩展到更多股票。项目采用三层架构：

1. 信息收集层：`stock_agent.collection`，负责数据采集、标准化、去重、冲突识别、来源可信度和质量报告。
2. 分析处理层：`stock_agent.analysis`，负责把事实转成事件信号、驱动因子权重、市场状态、情景预测和质量降级原因。
3. 建议生成/决策表达层：`stock_agent.decision`，在显式开启时根据投资者画像生成条件化投资/交易计划。

`tsla_agent` 是 TSLA 专用入口，负责把 TSLA 数据接入通用三层框架并生成报告。

重要边界：所有输出只作为研究辅助，不构成无条件投资建议。第一层不能生成 `buy_signal`、`sell_signal`、`trade_plan`、目标价推荐等交易决策字段；第二层只输出分析信号；第三层可以输出条件化计划，但必须包含触发条件、风险、反方观点、证伪条件和不交易条件。

## 主要目录

- `README.md`：项目说明和快速开始命令。
- `tsla_agent/`：TSLA 分析 agent。
  - `cli.py`：命令行入口逻辑。
  - `__main__.py`：支持 `python3 -m tsla_agent`。
  - `config.py`：默认 symbol、数据目录、报告目录、预测周期等配置。
  - `models.py`：分析层数据结构，如 `PricePoint`、`Event`、`MarketSummary`、`ForecastResult`。
  - `connectors/`：分析层数据连接器，包括本地 CSV/JSON、Alpha Vantage、SEC、RSS。
  - `scoring.py`：事件关键词情绪、类别推断、时间衰减和影响分计算。
  - `forecast.py`：价格摘要、动量/波动率预测、事件情绪加权。
  - `llm.py`：OpenAI-compatible Chat Completions 摘要调用。
  - `report.py`：中文 Markdown 报告生成。
- `stock_agent/`：通用股票工具包。
  - `cli.py`：通用命令入口，包含 `collect`、`inspect`、`decide`、`layer12-report`、`layer123-report`。
  - `collection/`：独立采集层。
    - `models.py`：采集请求、结果、来源、告警、冲突、质量报告等 dataclass。
    - `collector.py`：采集编排、缓存、来源合并、去重、冲突检测、质量评估。
    - `config.py`：数据需求枚举、来源别名、默认 CIK/FRED 指标、可信度表。
    - `quality.py`：质量门禁和告警逻辑。
    - `dedup.py`：新闻事件去重。
    - `inspection.py`：把采集结果 JSON 渲染为中文审计 Markdown。
    - `normalization.py`：symbol、日期、数值、账户号脱敏等标准化工具。
    - `sources/`：采集来源实现，包括 `local`、`alpha_vantage`、`sec_edgar`、`fred`、`rss`、`ibkr`。
  - `analysis/`：第二层分析处理，输出事件信号、驱动因子评分、市场状态、情景预测和置信度。
    - `chinese_titles.py`：把英文资讯标题转成“类型摘要 + 中文译题”，同时保留英文原题用于追溯。
    - `report.py`：一二层中文测试报告生成，包含事件影响分解释、质量校验和 PDF 自动输出。
  - `data_coverage/`：数据源路线图和质量门禁，说明缺失数据影响哪些驱动因子和投资者画像。
  - `decision/`：第三层建议生成/决策表达，按投资者画像输出条件化计划。
    - `cli.py`：独立第三层 CLI，支持 JSON 和 Markdown 输出。
    - `report.py`：单个投资者画像 Markdown 报告。
    - `layer123_report.py`：一二三层综合测试报告，批量生成六类画像计划。
    - `test_report.py`：第三层字段和合规边界测试报告。
  - `reporting/`：人读报告通用工具。
    - `text.py`：清洗 `。、`、`，、`、`、、` 等连续标点，用于人读摘要行。
    - `pdf.py`：把人读 Markdown 报告转成 PDF，支持彩色表格和中文字体。
- `tests/`：单元测试，使用标准库 `unittest`。
- `data/`：示例数据。
  - `sample_prices.csv`：示例价格数据。
  - `sample_events.json`：示例事件数据。
- `reports/`：生成的分析报告。
- `output/pdf/`：自动生成的 PDF 报告输出目录，通常不应把大批生成物纳入源码提交。
- `collection_result_tsla.json`：一次采集结果样例。
- `collection_audit_tsla.md`：一次采集审计报告样例。
- `tmp/`、`output/`：临时或生成文件目录。

## 运行命令

使用项目自带示例数据生成 TSLA 报告：

```bash
python3 -m tsla_agent --sample-data --offline
```

默认不输出第三层建议计划。显式开启第三层：

```bash
python3 -m tsla_agent --sample-data --offline \
  --include-decision-plan \
  --investor-type short_term_trader
```

可选 `--investor-type`：

- `long_term_fundamental`
- `growth_narrative`
- `event_driven`
- `swing_trader`
- `short_term_trader`
- `risk_control`

指定本地价格和事件文件：

```bash
python3 -m tsla_agent \
  --prices-csv data/sample_prices.csv \
  --events-json data/sample_events.json \
  --offline
```

运行独立采集层并输出 JSON：

```bash
python3 -m stock_agent.cli collect \
  --symbol TSLA \
  --market US \
  --requirements market_data,news_events \
  --prices-csv data/sample_prices.csv \
  --events-json data/sample_events.json \
  --output collection_result.json
```

把采集结果 JSON 转成审计 Markdown：

```bash
python3 -m stock_agent.cli inspect \
  --input collection_result.json \
  --output collection_audit.md
```

`inspect` 会为人读 Markdown 审计报告自动尝试生成同名 PDF，默认写入 `output/pdf/`。

运行一二层中文综合测试报告：

```bash
python3 -m stock_agent.cli layer12-report \
  --collection-input collection_result.json \
  --analysis-output analysis_result.json \
  --report-output layer12_report.md \
  --validation-output layer12_validation.json
```

运行一二三层综合测试报告，并批量生成六类画像计划：

```bash
python3 -m stock_agent.cli layer123-report \
  --collection-input collection_result.json \
  --analysis-input analysis_result.json \
  --output-dir output/layer123 \
  --report-output layer123_report.md \
  --validation-output layer123_validation.json
```

`layer123-report` 会输出综合 Markdown、校验 JSON、六类画像的 JSON/Markdown，并为所有人读 Markdown 自动尝试生成 PDF。PDF 路径会记录在 validation JSON 的 `output_files` 中。

运行独立第三层决策表达层：

```bash
python3 -m stock_agent.cli decide \
  --input analysis_result.json \
  --output decision_plan.md \
  --format markdown \
  --investor-type long_term_fundamental
```

`--format markdown` 会自动尝试生成 PDF；`--format json` 只输出机器可读 JSON，不生成 PDF。

运行测试：

```bash
python3 -m unittest discover
```

## 外部数据源和环境变量

项目使用标准库 `urllib` 访问外部接口，没有看到依赖管理文件。常用环境变量如下：

- `ALPHAVANTAGE_API_KEY`：Alpha Vantage 行情和新闻。采集层支持 `TIME_SERIES_DAILY_ADJUSTED`，如遇免费额度或 premium endpoint 限制，会尝试回退到 `TIME_SERIES_DAILY`。
- `SEC_USER_AGENT`：SEC EDGAR 必需的 User-Agent，建议包含姓名和邮箱。
- `NEWS_RSS_URLS`：`tsla_agent` RSS 源，逗号分隔。
- `FRED_API_KEY`：FRED 宏观数据。
- `OPENAI_API_KEY`：可选 LLM 摘要。
- `LLM_MODEL`：可选 LLM 模型名。
- `OPENAI_BASE_URL`：可选，默认 `https://api.openai.com/v1`，兼容 OpenAI Chat Completions。

`stock_agent.collection` 的 RSS URL、API key、CIK、FRED series、IBKR client 等也可以通过 `CollectionRequest.data_source_config` 传入。

PDF 生成依赖 `reportlab`，PDF 渲染检查依赖 Poppler 的 `pdftoppm`/`pdfinfo`。项目核心代码不强制要求这些依赖；本地 Python 没有 `reportlab` 时，`stock_agent.reporting.pdf` 会优先尝试 Codex bundled runtime。若仍不可用，Markdown/JSON 主输出不应被阻断，只是 PDF 不生成。

## 数据模型要点

### `tsla_agent` 分析层

- `PricePoint`：简化价格点，核心字段是 `date` 和 `close`。
- `Event`：事件数据，包含来源、标题、摘要、URL、发布时间、类别、情绪、影响分和 tags。
- `MarketSummary`：最新收盘、5/20 日涨跌幅、年化波动率、20/50 日均线、趋势标签。
- `ForecastResult`：总体信号、理由和多个周期的情景价格。

分析层数据结构较轻，适合直接生成报告。

### `stock_agent.collection` 采集层

采集层数据结构更细，覆盖：

- `PricePoint`
- `FilingEvent`
- `OfficialEvent`
- `FinancialMetric`
- `NewsEvent`
- `MacroPoint`
- `IndustryEvent`
- `OptionData`
- `BrokerAccountData`
- `ResearchReport`
- `SourceRecord`
- `ConflictRecord`
- `WarningRecord`
- `DataQualityReport`
- `CollectionSummary`
- `CollectionResult`

`CollectionResult.to_json()` 会用 `ensure_ascii=False` 输出中文友好的 JSON。

### `stock_agent.analysis` 分析层

- `MarketState`：最新收盘、交易日期、5/20 日涨跌幅、年化波动率、20/50 日均线、支撑、压力、ATR 和趋势标签。
- `EventSignal`：单条事件信号，包含 `title`、`source`、`category`、`driver`、`direction`、`impact_score`、`time_window`、`surprise_level`、`source_reliability`、`evidence`。
- `EventSignal` 还包含面向报告解释的字段：`impact_reason`、`counterpoint`、`quantitative_evidence`、`score_breakdown`。这些字段用于说明为什么判为正面/负面、有哪些量化证据、影响分如何得出，以及可能的反方论点。
- `ScenarioForecast`：Bear/Base/Bull 等情景区间、时间跨度、逻辑和触发条件。
- `AnalysisResult`：二层总输出，包含 `market_state`、`event_signals`、`driver_scores`、`scenario_forecasts`、`quality_downgrades`、`confidence_level` 和 `data_coverage`。

## 采集层行为

`collect_data(CollectionRequest)` 的主要流程：

1. 规范化 symbol、数据需求和来源别名。
2. 记录禁用来源和未知数据需求。
3. 按 `data_source_config` 中启用的来源依次采集。
4. 支持内存缓存，默认关闭；IBKR 账户数据不缓存。
5. 合并不同来源输出。
6. 对新闻事件去重。
7. 检测行情价格冲突和财务指标冲突。
8. 评估整体数据质量。
9. 填充 `collection_summary`，包括来源使用情况、失败来源、事件数量、数据新鲜度、质量等级和 IBKR 状态。

支持的数据需求在 `stock_agent/collection/config.py` 的 `DATA_REQUIREMENTS` 中定义：

- `market_data`
- `filings`
- `official_events`
- `financial_metrics`
- `news_events`
- `macro_data`
- `industry_data`
- `options_data`
- `broker_account_data`
- `research_reports`

## 分析层行为

`stock_agent.analysis` 是第二层，输入第一层 `CollectionResult` 或兼容的价格/事件对象，输出 `AnalysisResult`。它只做分析，不做投资者画像建议。

主要输出：

- `market_state`：最新收盘、5/20 日涨跌幅、年化波动率、20/50 日均线、支撑位、压力位、ATR 和趋势标签。
- `event_signals`：事件标题、来源、类别、驱动因子、影响方向、影响分、时间窗口、超预期状态、来源可信度、方向理由、量化证据、评分拆解和反方论点。
- `driver_scores`：Tesla/成长股通用驱动因子评分。
- `scenario_forecasts`：Bear/Base/Bull 情景区间和触发条件。
- `quality_downgrades`：样例数据、缺少宏观/财报/期权/成交量、事件数量不足等降级原因。
- `confidence_level`：`LOW`、`MEDIUM`、`HIGH`。
- `data_coverage`：结构化数据覆盖报告，包含缺口、路线图、影响画像和置信度上限。

分析层不得输出买入、卖出、止损、目标位、交易计划或画像化建议字段。

二层事件影响分口径：

- 影响分表示事件对对应驱动因子的“重要程度/影响强度”，不等于上涨概率、下跌概率或预期涨跌幅。
- `0.70 以上`：高影响事件，优先阅读和验证。
- `0.50-0.70`：中高影响事件，可能影响某个画像或因子。
- `0.30-0.50`：中等影响，更多是背景信息。
- `0.30 以下`：低影响或噪音，通常不应单独决策。
- 摘要表中应优先显示影响等级，不直接堆具体分数；具体分数和计算过程放在事件详情中。
- 影响分由驱动因子基础权重、关键词情绪、来源可信度、TSLA 相关度、事件类型上限和可选来源预置影响分共同决定。
- 事件方向和影响强度必须一起看：`正面 0.77` 是高影响正面证据，`负面 0.77` 是高影响风险证据。
- 当新闻没有结构化数字时，报告必须明确写“原始事件未提供可量化数值”，不得把标题判断伪装成已确认数据。
- `driver_scores` 会综合事件信号、市场技术状态，以及可用的结构化宏观数据和行业/交付数据；缺少相关结构化数据时，应显示为无可评分证据或降级理解。

当前主要驱动因子：

- `交付/库存/价格`
- `毛利率/EPS/现金流`
- `FSD/Robotaxi/AI`
- `利率/美元/纳指`
- `竞争格局`
- `监管/诉讼/政策`
- `能源/供应链`
- `技术面/期权/资金流`
- `估值/安全边际`

## 数据源路线图与质量门禁

`stock_agent.data_coverage` 把生产数据建议拆成结构化路线图，并把数据缺口映射到驱动因子和投资者画像。

路线图分级：

- P1：高质量行情、财报与预期、宏观变量、严格回测。
- P2：行业数据、期权与资金流。
- P3：实时低延迟行情、gamma exposure、机构级资金流、Bloomberg/FactSet 等高成本终端。

低成本优先默认来源：

- 行情：Alpha Vantage、本地 CSV、Nasdaq Data Link 免费/低价数据集。
- 财报与预期：SEC、公司 IR、earnings call transcripts、本地分析师预期 CSV。
- 宏观：FRED、公开 VIX/指数 CSV、美元指数/纳指本地导入。
- 行业：本地 CSV/JSON、公司交付公告、行业协会公开数据、监管/召回公开数据。
- 期权/资金流：IBKR 只读接口、本地期权链/put-call CSV、公开持仓 CSV。
- 回测：本地历史行情、本地事件快照、walk-forward validation 脚本。

门禁规则：

- 缺少价格数据或使用样例数据时，整体和所有画像置信度最高为 `LOW`。
- 缺少财报/预期会降低长期基本面、成长叙事、事件驱动、风险控制画像。
- 缺少宏观会降低成长叙事、波段、短线、风险控制画像。
- 缺少成交量/期权会降低短线和波段画像。
- 缺少回测会降低所有画像的生产级置信度。

## 决策表达层行为

`stock_agent.decision` 是第三层，输入 `AnalysisResult` 和投资者画像，输出 `DecisionPlan`。第三层默认不出现在 TSLA 报告里，必须通过 `--include-decision-plan` 显式开启。

内置投资者画像：

- 长期基本面投资者：`long_term_fundamental`
- 成长叙事投资者：`growth_narrative`
- 事件驱动投资者：`event_driven`
- 波段交易者：`swing_trader`
- 短线交易者：`short_term_trader`
- 风险控制型投资者：`risk_control`

第三层必须输出：

- 当前倾向和置信度。
- 当前画像数据覆盖等级、置信度上限和关键数据缺口。
- 支持因素和风险因素。
- 条件化参与方案。
- 卖出/减仓条件。
- 止损/失效条件。
- 不交易条件。
- 反方观点。
- 后续监控清单。

第三层评分展示规则：

- 每个投资者画像都要展示 `总得分`，口径为 `总得分 = Σ(因子权重 x 当前因子得分)`。
- 总得分解释需和 `_bias()` 阈值保持一致：`> 0.18` 为条件偏多，`-0.18 到 0.18` 为区间观察，`< -0.18` 为条件偏谨慎，`LOW` 置信度下为低置信度观察。
- 每个画像应展示“因子权重与贡献”表，列为 `因子`、`画像权重`、`当前得分`、`加权贡献`，并显示 `贡献合计`。
- 若某因子当前没有可评分证据，报告里应明确标注 `当前无可评分证据`，避免把 `0.000` 误解成中性事实。
- 支持因素/风险因素中，后续提到事件时使用短引用，例如 `事件#2 FSD 自动驾驶进展（Reuters，影响等级或影响分）`，不要重复完整英文标题。
- 完整英文原题、中文译题、具体影响分和评分拆解保留在“重要资讯/事件影响分解释”部分，保证可追溯但不污染摘要。

## 来源可信度规则

来源可信度集中定义在 `stock_agent/collection/config.py`：

- SEC、公司 IR、官方披露：最高，约 `1.00`。
- FRED、政府宏观数据：约 `0.95`。
- IBKR、Alpha Vantage、交易所/券商 API：约 `0.90`。
- Bloomberg/FactSet 等终端：约 `0.80`。
- Reuters、WSJ、CNBC 等主流财经媒体：约 `0.75`。
- RSS 或行业媒体：约 `0.60`。
- 研究报告：约 `0.50`。
- 社交媒体/论坛/传言：低可信。
- 未知来源即使传入较高显式可信度，也会被限制到 `0.30` 以内。
- 示例数据或 fictional/sample 数据会触发质量告警。

## 权限和隐私约束

IBKR 来源必须严格遵守权限开关：

- 未设置 `allow_broker_account_data=True` 时，不读取账户摘要。
- 未设置 `allow_positions_pnl=True` 时，不读取持仓和盈亏。
- 账户号必须脱敏，测试确保原始账户 ID 不会出现在 JSON 输出里。
- IBKR 账户数据不应进入缓存。

采集层应保持 read-only，不下单、不生成交易指令。

## 质量评估规则

`evaluate_quality` 会根据以下因素给出 `overall_quality`、`can_generate_analysis` 和 `confidence_cap`：

- 是否提供 `data_requirements`。
- 请求的数据是否缺失。
- 是否有行情、成交量、披露、宏观、新闻。
- 是否有冲突数据。
- 是否合并了重复新闻。
- 是否有低可信或未知来源。
- 是否检测到 sample/fictional/example 数据。
- 行情是否陈旧，最新市场数据超过 7 天会标记 stale。
- IBKR 是否启用、连接、被授权读取账户数据。

质量等级包括 `INSUFFICIENT`、`LOW`、`MEDIUM`、`HIGH`。

## 事件评分和预测逻辑

`stock_agent.analysis.events.py`：

- 把采集层新闻、披露、宏观和行业数据映射成 `EventSignal`。
- 根据事件文本和类别判断驱动因子，交付/库存/价格、监管、FSD、宏观、竞争、估值等关键词有明确优先级。
- 方向由关键词情绪决定，包含负面短语优先处理，例如 `raises concerns`、`misleading`、`support withdrawn`、`fires back`，避免被单个正面词误判。
- 影响分使用驱动基础权重、关键词情绪、来源可信度、TSLA 相关度、事件类型上限和预置影响分。
- 结构化宏观数据会补充 `利率/美元/纳指` 因子；结构化行业/交付数据会补充 `交付/库存/价格` 因子。
- 输出按影响分排序，但报告摘要应展示影响等级，具体分数放入详情。

`stock_agent.analysis.chinese_titles.py`：

- `chinese_event_title()` 输出稳定的事件类型摘要。
- `translated_event_title()` 尽量给出英文原题的中文译题。
- `event_title_with_translation()` 组合成 `类型摘要｜英文原题中文译题`，用于重要资讯表和事件详情标题。
- 完整英文原题必须保留在详情行，便于追溯来源。

`tsla_agent/scoring.py`：

- 用关键词识别正负面情绪。
- 根据文本推断类别，如 `delivery`、`earnings`、`filing`、`regulatory`、`macro`、`competition`。
- 影响分由类别权重、发布时间衰减、重大事件关键词和情绪强度组成。
- 输出按影响分和情绪绝对值排序。

`tsla_agent/forecast.py`：

- 清洗价格并按日期排序。
- 计算 5 日、20 日涨跌幅、日收益、年化波动率、20/50 日均线。
- 预测使用短期动量、中期动量和事件情绪修正。
- 默认周期是 1、5、20 天。
- 输出信号为 `偏多`、`偏空`、`震荡` 或数据不足。

## 报告输出

所有给人看的 Markdown 报告都应尽量同步生成 PDF；机器可读 JSON 不需要转 PDF。统一入口是 `stock_agent.reporting.write_pdf_for_markdown`，默认输出到 `output/pdf/{markdown_stem}.pdf`。如果 PDF 依赖不可用，不应阻断 Markdown/JSON 主输出。

`stock_agent.reporting.text` 用于人读摘要行的文本清洗，避免出现 `。、`、`，、`、`、、`、`。。` 等连续标点。不要对新闻标题、路径、URL、JSON 原文做这类清洗。

`stock_agent.reporting.pdf` 负责 Markdown 到 PDF 的转换，当前实现包含：

- 横向 A4 页面、中文字体、页眉页码。
- Markdown 标题、列表、表格和粗体的基础渲染。
- 表格颜色区分：正面浅绿、负面浅红、中性浅灰；影响等级、画像倾向、因子得分和加权贡献也有轻量颜色提示。
- PDF 输出是生成物，通常应放在 `output/pdf/`，不应把大量 PDF/PNG 渲染中间件纳入源码提交。

`tsla_agent/report.py` 生成中文 Markdown 报告，并自动尝试生成 PDF，包含：

- 生成时间和用途声明。
- 核心结论。
- 市场状态。
- 关键影响因素。
- 情景预测表。
- 需要继续监控的事项。
- 数据覆盖提醒。
- 方法说明。

默认输出到 `reports/{symbol_lower}_report.md`。

`stock_agent.collection.inspection` 生成采集审计 Markdown/PDF，强调质量、来源、告警、冲突、IBKR 状态和数据覆盖，不包含交易建议。

`stock_agent.analysis.report` 生成一二层中文综合测试报告，包含：

- 第一层采集结果和质量门禁。
- 第二层市场状态、Top 事件信号、事件影响分解释、SEC 披露摘要、驱动因子评分和情景预测。
- 重要资讯标题使用 `类型摘要｜英文原题中文译题` 格式；完整英文原题保留在事件详情。
- 摘要表显示影响等级，具体影响分和计算方式放在事件详情。
- 合规边界检查，确保一二层不输出交易建议字段。

`stock_agent.decision.layer123_report` 生成一二三层综合测试报告，包含：

- 六类画像结果对比。
- 得分含义说明、重要资讯摘要、事件影响分解释。
- 每个画像的总得分、因子权重与贡献表、支持/风险因素、条件化参与、不交易条件。
- 六类画像的独立 JSON、Markdown 和 PDF。
- validation JSON，记录 Markdown、PDF、计划文件路径和检查结果。

## 测试覆盖

当前测试重点：

- 本地 CSV 行情读取。
- 本地 JSON 新闻读取。
- 采集层不生成交易输出字段。
- 采集审计 Markdown 渲染和 CLI inspect。
- 预测周期和缺失价格处理。
- 正负面事件评分。
- 未知来源可信度封顶。
- 示例数据告警。
- 缺失行情和缺失需求降级。
- 单个来源失败不阻断其他来源。
- Alpha Vantage adjusted endpoint 回退。
- IBKR 账户、持仓、盈亏权限控制。
- 新闻去重。
- 行情冲突记录。
- 数据覆盖路线图和画像置信度上限。
- 二层事件分类、影响分解释、量化证据、反方论点和误判回归样本。
- 结构化宏观数据对 `利率/美元/纳指` 因子的评分。
- 结构化行业/交付数据对 `交付/库存/价格` 因子的评分。
- 一二层中文报告生成和合规边界检查。
- 一二三层综合报告、六类画像计划、因子权重贡献表和影响等级说明。
- Markdown 输出自动 PDF 的主流程回归。
- 人读报告连续标点清洗。

建议每次改动后至少运行：

```bash
python3 -m unittest discover
```

## 开发注意事项

- 保持 `stock_agent.collection` 独立于分析/交易判断，只做采集、清洗、审计和质量门禁。
- 新增数据源时，应实现 `SourceOutput`，填写 `source_inventory`，并把来源注册到 `SOURCE_FACTORIES`。
- 新增数据需求时，需要同步更新 `DATA_REQUIREMENTS`、`REQUIREMENT_TO_RESULT_FIELD`、模型字段、采集合并逻辑和质量评估。
- 外部接口失败应转成 `WarningRecord`，不要让整个采集流程崩溃。
- 所有外部来源都要记录 `source`、`source_reliability`、`collected_at` 和尽量完整的 `raw_metadata`。
- 本地文件解析应接受常见字段别名，但输出要归一化。
- 处理用户或券商账户数据时优先脱敏、权限显式化和避免缓存。
- 报告和审计文档用中文输出，保持“不构成投资建议”的边界。
- 给人看的 Markdown 报告应调用统一 PDF 生成 helper；不要为每个报告重新复制一套 PDF 渲染逻辑。
- 重要资讯摘要表应显示影响等级，不直接显示具体影响分；具体分数、评分拆解和反方论点放在事件详情中。
- 英文资讯标题在摘要中应使用 `类型摘要｜中文译题`，完整英文原题只放在详情行。
- 后续画像摘要引用事件时使用短引用，避免重复整条英文标题导致 PDF 横向挤压。
- 任何自动标题翻译都是确定性规则，不是权威翻译；新增新闻样本时应补充回归测试。
- 当前仓库没有 `requirements.txt` 或 `pyproject.toml`，核心代码主要依赖 Python 标准库；IBKR 真实连接需要额外安装 `ib_insync`，也可以在测试或集成中传入 `client_factory`。

## 当前仓库状态观察

当前目录是 Git 仓库，但 `git status --short` 显示大量文件处于未跟踪状态，包括源码、测试、README、示例数据和生成报告。后续做版本管理时，应先确认哪些生成文件需要纳入仓库，哪些应加入 `.gitignore`。
