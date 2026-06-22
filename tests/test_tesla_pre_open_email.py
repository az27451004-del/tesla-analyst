import os
import unittest
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from stock_agent.automation.tesla_pre_open_email import (
    build_email_body,
    determine_delivery_window,
    determine_trading_day,
    us_market_holiday_name,
)


NEW_YORK_TZ = ZoneInfo("America/New_York")


class TeslaPreOpenEmailTest(unittest.TestCase):
    def test_regular_trading_day(self):
        status = determine_trading_day(date(2026, 6, 18))
        self.assertTrue(status.trading_day)
        self.assertIn("正常交易", status.reason)

    def test_juneteenth_is_holiday(self):
        self.assertEqual(us_market_holiday_name(date(2026, 6, 19)), "Juneteenth National Independence Day")
        status = determine_trading_day(date(2026, 6, 19))
        self.assertFalse(status.trading_day)
        self.assertIn("Juneteenth", status.reason)

    def test_email_body_includes_failure_and_paths(self):
        body = build_email_body(
            {
                "run_date_ny": "2026-06-18",
                "trading_day": True,
                "report_status": "通过，带降级观察",
                "confidence_level": "LOW",
                "email_status": "failed_missing_env",
                "email_error": "缺少 SMTP 环境变量",
                "key_data_gaps": ["缺少期权数据"],
                "quality_downgrades": ["新闻事件不足"],
                "generated_files": {"report_markdown": "/tmp/report.md"},
            }
        )
        self.assertIn("分析置信度：LOW", body)
        self.assertIn("缺少期权数据", body)
        self.assertIn("/tmp/report.md", body)
        self.assertIn("发送失败说明", body)

    def test_delivery_window_allows_target_time(self):
        with patch.dict(os.environ, {"ENFORCE_DELIVERY_WINDOW": "true"}, clear=False):
            status = determine_delivery_window(datetime(2026, 6, 18, 7, 27, tzinfo=NEW_YORK_TZ))
        self.assertTrue(status.should_run)
        self.assertTrue(status.enforced)

    def test_delivery_window_force_run_bypasses_window(self):
        with patch.dict(os.environ, {"ENFORCE_DELIVERY_WINDOW": "true", "FORCE_RUN": "true"}, clear=False):
            status = determine_delivery_window(datetime(2026, 6, 18, 3, 18, tzinfo=NEW_YORK_TZ))
        self.assertTrue(status.should_run)
        self.assertIn("FORCE_RUN 已启用", status.reason)
        self.assertTrue(status.enforced)

    def test_delivery_window_skips_outside_window(self):
        with patch.dict(os.environ, {"ENFORCE_DELIVERY_WINDOW": "true"}, clear=False):
            status = determine_delivery_window(datetime(2026, 6, 18, 8, 27, tzinfo=NEW_YORK_TZ))
        self.assertFalse(status.should_run)
        self.assertIn("不在发送窗口", status.reason)


if __name__ == "__main__":
    unittest.main()
