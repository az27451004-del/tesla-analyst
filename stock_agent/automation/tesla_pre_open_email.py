from __future__ import annotations

import json
import os
import smtplib
import ssl
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_agent.analysis.pipeline import analyze_collection
from stock_agent.collection import CollectionRequest, collect_data
from stock_agent.decision.layer123_report import write_layer123_test_outputs


AUTOMATION_ID = "tesla-pre-open-analysis-email"
NEW_YORK_TZ = ZoneInfo("America/New_York")
REQUIRED_SMTP_VARS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "SMTP_USE_TLS",
)
DEFAULT_REQUIREMENTS = ("market_data", "filings", "news_events", "macro_data")
DEFAULT_WINDOW_START = "07:20"
DEFAULT_WINDOW_END = "07:35"
DEFAULT_MARKET_TOPIC_QUERIES = (
    "Federal Reserve OR Jerome Powell OR rate cut OR inflation OR Treasury yield",
    "\"Strait of Hormuz\" OR Hormuz OR Iran talks OR Middle East oil supply",
    "tariff OR sanctions OR export controls OR trade war",
    "\"America First\" economic policy OR \"Trump economic policy\" OR \"economic security\"",
    "\"capital flows\" OR \"capital inflows\" OR \"capital return\" OR \"U.S. assets\"",
    "\"tariff policy\" OR \"China trade talks\" OR \"export controls\"",
    "\"Middle East oil risk\" OR \"oil supply risk\" OR \"shipping lane risk\"",
    "\"White House speech\" OR \"president speech\" OR \"Trump speech\"",
    "\"White House\" policy speech OR U.S. president speech OR election policy",
    "\"U.S.-China\" OR \"US-China\" OR \"China-US\" OR China trade talks OR U.S. China trade",
    "\"U.S.-China relations\" OR \"China relations\" OR diplomatic talks OR summit meeting",
    "\"Xi Jinping\" meeting OR \"Donald Trump\" meeting OR leader summit OR bilateral talks",
)


@dataclass(frozen=True)
class TradingDayStatus:
    trading_day: bool
    reason: str
    source: str


@dataclass(frozen=True)
class DeliveryWindowStatus:
    should_run: bool
    reason: str
    source: str
    window_start: str
    window_end: str
    current_time_ny: str
    enforced: bool


def main() -> int:
    load_local_env_file()
    run_started = datetime.now(tz=NEW_YORK_TZ)
    summary = run_pre_open_automation(run_started=run_started)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def run_pre_open_automation(*, run_started: datetime | None = None) -> dict[str, Any]:
    started = run_started or datetime.now(tz=NEW_YORK_TZ)
    if started.tzinfo is None:
        started = started.replace(tzinfo=NEW_YORK_TZ)
    else:
        started = started.astimezone(NEW_YORK_TZ)

    run_date = started.date()
    run_stamp = started.strftime("%Y%m%d-%H%M%S")
    automation_root = _automation_root()
    output_dir = automation_root / "output" / f"{run_date.isoformat()}_{run_stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "automation_id": AUTOMATION_ID,
        "run_started_at_ny": started.isoformat(),
        "run_date_ny": run_date.isoformat(),
        "output_dir": str(output_dir),
        "status": "started",
        "trading_day": None,
        "skip_reason": "",
        "email_status": "not_attempted",
        "email_error": "",
        "report_status": "",
        "confidence_level": "",
        "key_data_gaps": [],
        "quality_downgrades": [],
        "generated_files": {},
        "trading_day_check": {},
        "delivery_window_check": {},
    }

    delivery_window = determine_delivery_window(started)
    summary["delivery_window_check"] = asdict(delivery_window)
    if delivery_window.enforced and not delivery_window.should_run:
        summary["status"] = "skipped"
        summary["skip_reason"] = delivery_window.reason
        _write_json(output_dir / "run_summary.json", summary)
        return summary

    trading_day = determine_trading_day(run_date)
    summary["trading_day"] = trading_day.trading_day
    summary["trading_day_check"] = asdict(trading_day)
    if not trading_day.trading_day:
        summary["status"] = "skipped"
        summary["skip_reason"] = trading_day.reason
        _write_json(output_dir / "run_summary.json", summary)
        return summary

    collection_path = output_dir / "collection_result_tsla.json"
    analysis_path = output_dir / "analysis_result_tsla.json"
    report_path = output_dir / "layer123_report_tsla_zh.md"
    validation_path = output_dir / "layer123_validation_tsla.json"
    plans_dir = output_dir / "plans"

    collection_result = collect_data(_build_collection_request())
    _write_json(collection_path, collection_result.to_dict())

    analysis_result = analyze_collection(collection_result)
    _write_json(analysis_path, analysis_result.to_dict())

    validation = write_layer123_test_outputs(
        collection_input=collection_path,
        analysis_input=analysis_path,
        output_dir=plans_dir,
        report_output=report_path,
        validation_output=validation_path,
    )

    output_files = _normalize_output_files(
        {
            "collection_json": str(collection_path),
            "analysis_json": str(analysis_path),
            "report_markdown": str(report_path),
            "validation_json": str(validation_path),
            **validation.get("output_files", {}),
        }
    )
    output_files = {key: value for key, value in output_files.items() if value}

    summary["status"] = "completed"
    summary["report_status"] = validation.get("status", "")
    summary["confidence_level"] = analysis_result.confidence_level
    summary["key_data_gaps"] = [_stringify_gap(item) for item in analysis_result.data_coverage.gaps[:8]]
    summary["quality_downgrades"] = list(analysis_result.quality_downgrades[:8])
    summary["generated_files"] = output_files

    email_body = build_email_body(summary)
    email_body_path = output_dir / "email_body.txt"
    email_body_path.write_text(email_body, encoding="utf-8")
    summary["generated_files"]["email_body"] = str(email_body_path)

    attachments = [report_path]
    report_pdf = output_files.get("report_pdf")
    if report_pdf:
        attachments.append(Path(report_pdf))

    email_result = send_report_email(
        subject=f"TSLA 盘前研究报告 {run_date.isoformat()} (America/New_York)",
        body=email_body,
        attachments=attachments,
    )
    summary["email_status"] = email_result["status"]
    summary["email_error"] = email_result.get("error", "")
    _write_json(output_dir / "run_summary.json", summary)
    return summary


def determine_delivery_window(run_started: datetime) -> DeliveryWindowStatus:
    if run_started.tzinfo is None:
        run_started = run_started.replace(tzinfo=NEW_YORK_TZ)
    else:
        run_started = run_started.astimezone(NEW_YORK_TZ)

    enforced = _truthy_env("ENFORCE_DELIVERY_WINDOW")
    if _truthy_env("FORCE_RUN"):
        return DeliveryWindowStatus(
            should_run=True,
            reason="FORCE_RUN 已启用，跳过发送窗口检查。",
            source="environment_override",
            window_start=_window_start_raw(),
            window_end=_window_end_raw(),
            current_time_ny=run_started.strftime("%H:%M"),
            enforced=enforced,
        )

    start_raw = _window_start_raw()
    end_raw = _window_end_raw()
    start_time = _parse_clock_time(start_raw)
    end_time = _parse_clock_time(end_raw)
    current_time = run_started.time().replace(second=0, microsecond=0)
    in_window = start_time <= current_time <= end_time
    if in_window:
        return DeliveryWindowStatus(
            should_run=True,
            reason=f"当前纽约时间在发送窗口 {start_raw}-{end_raw} 内。",
            source="window_rule",
            window_start=start_raw,
            window_end=end_raw,
            current_time_ny=run_started.strftime("%H:%M"),
            enforced=enforced,
        )
    return DeliveryWindowStatus(
        should_run=False,
        reason=f"当前纽约时间 {run_started.strftime('%H:%M')} 不在发送窗口 {start_raw}-{end_raw} 内。",
        source="window_rule",
        window_start=start_raw,
        window_end=end_raw,
        current_time_ny=run_started.strftime("%H:%M"),
        enforced=enforced,
    )


def determine_trading_day(run_date: date) -> TradingDayStatus:
    manual_reason = os.getenv("US_MARKET_CLOSED_REASON", "").strip()
    if manual_reason:
        return TradingDayStatus(False, manual_reason, "environment_override")
    if run_date.weekday() >= 5:
        return TradingDayStatus(False, "美国股市周末休市。", "calendar_rule")
    holiday_name = us_market_holiday_name(run_date)
    if holiday_name:
        return TradingDayStatus(False, f"NYSE/Nasdaq 因 {holiday_name} 休市。", "calendar_rule")
    return TradingDayStatus(True, "纽约交易所与纳斯达克正常交易。", "calendar_rule")


def us_market_holiday_name(run_date: date) -> str:
    holidays = {
        _observed_date(date(run_date.year, 1, 1)): "New Year's Day",
        _nth_weekday(run_date.year, 1, 0, 3): "Martin Luther King Jr. Day",
        _nth_weekday(run_date.year, 2, 0, 3): "Washington's Birthday",
        _good_friday(run_date.year): "Good Friday",
        _last_weekday(run_date.year, 5, 0): "Memorial Day",
        _observed_date(date(run_date.year, 6, 19)): "Juneteenth National Independence Day",
        _observed_date(date(run_date.year, 7, 4)): "Independence Day",
        _nth_weekday(run_date.year, 9, 0, 1): "Labor Day",
        _nth_weekday(run_date.year, 11, 3, 4): "Thanksgiving Day",
        _observed_date(date(run_date.year, 12, 25)): "Christmas Day",
    }
    return holidays.get(run_date, "")


def _observed_date(value: date) -> date:
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    current += timedelta(days=7 * (occurrence - 1))
    return current


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _good_friday(year: int) -> date:
    easter = _easter_sunday(year)
    return easter - timedelta(days=2)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _build_collection_request() -> CollectionRequest:
    data_source_config: dict[str, Any] = {}
    if os.getenv("ALPHAVANTAGE_API_KEY"):
        data_source_config["alpha_vantage"] = {
            "enabled": True,
            "limit": 50,
            "company_aliases": ["Tesla", "Tesla Inc", "Tesla Motors"],
        }
    if os.getenv("SEC_USER_AGENT"):
        data_source_config["sec_edgar"] = {"enabled": True}
    if os.getenv("FRED_API_KEY"):
        data_source_config["fred"] = {"enabled": True}
    rss_urls = [item.strip() for item in os.getenv("NEWS_RSS_URLS", "").split(",") if item.strip()]
    market_topic_queries = _market_topic_queries()
    if rss_urls:
        data_source_config["rss"] = {
            "enabled": True,
            "urls": rss_urls,
            "symbols": ["TSLA"],
            "company_aliases": {"TSLA": ["Tesla", "Tesla Inc", "Tesla Motors"]},
            "topic_queries": market_topic_queries,
            "limit": 30,
        }
    return CollectionRequest(
        symbol="TSLA",
        market="US",
        company_name="Tesla, Inc.",
        data_requirements=list(DEFAULT_REQUIREMENTS),
        allow_realtime=True,
        data_source_config=data_source_config,
    )


def _market_topic_queries() -> list[str]:
    raw = os.getenv("MARKET_EVENT_RSS_QUERIES", "").strip()
    if not raw:
        return list(DEFAULT_MARKET_TOPIC_QUERIES)
    return [item.strip() for item in raw.split(",") if item.strip()]


def build_email_body(summary: dict[str, Any]) -> str:
    lines = [
        "TSLA 盘前研究报告自动化结果",
        f"运行日期（纽约）：{summary.get('run_date_ny', '')}",
        f"交易日判断：{'是' if summary.get('trading_day') else '否'}",
    ]
    if summary.get("skip_reason"):
        lines.append(f"跳过原因：{summary['skip_reason']}")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"报告状态：{summary.get('report_status') or '未生成'}",
            f"分析置信度：{summary.get('confidence_level') or '未生成'}",
            f"邮件状态：{summary.get('email_status')}",
            f"关键数据缺口：{_join_items(summary.get('key_data_gaps'))}",
            f"质量降级：{_join_items(summary.get('quality_downgrades'))}",
            "生成文件：",
        ]
    )
    for key, value in sorted((summary.get("generated_files") or {}).items()):
        lines.append(f"- {key}: {value}")
    if summary.get("email_error"):
        lines.append(f"发送失败说明：{summary['email_error']}")
    lines.append("声明：本报告仅供研究辅助，不构成无条件投资建议。")
    return "\n".join(lines) + "\n"


def send_report_email(*, subject: str, body: str, attachments: list[Path]) -> dict[str, str]:
    missing = [key for key in REQUIRED_SMTP_VARS if not os.getenv(key)]
    if missing:
        return {"status": "failed_missing_env", "error": f"缺少 SMTP 环境变量：{', '.join(missing)}"}

    host = str(os.getenv("SMTP_HOST"))
    port = int(str(os.getenv("SMTP_PORT")))
    username = str(os.getenv("SMTP_USER"))
    password = str(os.getenv("SMTP_PASSWORD"))
    sender = str(os.getenv("SMTP_FROM"))
    use_tls = str(os.getenv("SMTP_USE_TLS")).strip().lower() in {"1", "true", "yes", "on"}

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = username
    message.set_content(body)

    for attachment in attachments:
        if not attachment.exists():
            continue
        data = attachment.read_bytes()
        if attachment.suffix.lower() == ".pdf":
            maintype, subtype = "application", "pdf"
        else:
            maintype, subtype = "text", "markdown"
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=attachment.name)

    try:
        with smtplib.SMTP(host, port, timeout=60) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(username, password)
            server.send_message(message)
        return {"status": "sent"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed_send", "error": str(exc)}


def _automation_root() -> Path:
    explicit_root = os.getenv("AUTOMATION_OUTPUT_ROOT", "").strip()
    if explicit_root:
        return Path(explicit_root).expanduser().resolve() / AUTOMATION_ID
    if _truthy_env("GITHUB_ACTIONS"):
        return Path.cwd() / "automation_output" / AUTOMATION_ID
    codex_home = Path(os.getenv("CODEX_HOME", Path.home() / ".codex"))
    return codex_home / "automations" / AUTOMATION_ID


def load_local_env_file(env_path: Path | None = None) -> None:
    path = env_path or Path.cwd() / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        name = key.strip()
        if not name:
            continue
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[name] = value


def _join_items(values: Any) -> str:
    items = [str(item).strip() for item in values or [] if str(item).strip()]
    return "；".join(items[:5]) if items else "无"


def _normalize_output_files(files: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in files.items():
        if not value:
            continue
        path = Path(str(value))
        normalized[key] = str(path.resolve()) if not path.is_absolute() else str(path)
    return normalized


def _stringify_gap(value: Any) -> str:
    if isinstance(value, str):
        return value
    if is_dataclass(value):
        message = getattr(value, "message", "")
        label = getattr(value, "label", "")
        severity = getattr(value, "severity", "")
        parts = [part for part in (severity, label, message) if part]
        return " | ".join(parts) if parts else str(value)
    if isinstance(value, dict):
        parts = [str(value.get(key, "")).strip() for key in ("severity", "label", "message")]
        parts = [part for part in parts if part]
        return " | ".join(parts) if parts else json.dumps(value, ensure_ascii=False)
    return str(value)


def _window_start_raw() -> str:
    return os.getenv("DELIVERY_WINDOW_START_NY", DEFAULT_WINDOW_START).strip() or DEFAULT_WINDOW_START


def _window_end_raw() -> str:
    return os.getenv("DELIVERY_WINDOW_END_NY", DEFAULT_WINDOW_END).strip() or DEFAULT_WINDOW_END


def _parse_clock_time(value: str) -> time:
    parsed = datetime.strptime(value, "%H:%M")
    return parsed.time()


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
