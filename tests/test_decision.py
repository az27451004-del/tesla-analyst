import unittest

from stock_agent.analysis import analyze_market_events
from stock_agent.decision import (
    GROWTH_NARRATIVE,
    LONG_TERM_FUNDAMENTAL,
    RISK_CONTROL,
    SHORT_TERM_TRADER,
    build_decision_plan,
)
from tsla_agent.models import Event, PricePoint


def _analysis():
    prices = [
        PricePoint(date=f"2026-06-{day:02d}", close=100 + day, high=102 + day, low=98 + day, volume=1000 + day)
        for day in range(1, 31)
    ]
    events = [
        Event(source="Reuters", title="Tesla deliveries beat consensus with record growth"),
        Event(source="SEC", title="Tesla faces regulatory investigation and recall"),
        Event(source="manual", title="Robotaxi milestone improves AI narrative"),
    ]
    return analyze_market_events(symbol="TSLA", prices=prices, events=events)


def _analysis_with_missing_data():
    prices = [
        PricePoint(date=f"2026-06-{day:02d}", close=100 + day, high=102 + day, low=98 + day)
        for day in range(1, 31)
    ]
    return analyze_market_events(
        symbol="TSLA",
        prices=prices,
        events=[Event(source="Reuters", title="Tesla deliveries beat consensus with record growth")],
        missing_requirements=["macro_data", "financial_metrics", "options_data"],
    )


class DecisionLayerTest(unittest.TestCase):
    def test_profiles_weight_same_analysis_differently(self):
        analysis = _analysis()

        long_plan = build_decision_plan(analysis, LONG_TERM_FUNDAMENTAL)
        short_plan = build_decision_plan(analysis, SHORT_TERM_TRADER)

        self.assertNotEqual(long_plan.profile.focus_factors, short_plan.profile.focus_factors)
        self.assertNotEqual(long_plan.profile.weights, short_plan.profile.weights)

    def test_short_term_trader_includes_trade_controls(self):
        plan = build_decision_plan(_analysis(), SHORT_TERM_TRADER)
        combined = "\n".join(
            list(plan.conditional_entry_plan)
            + list(plan.stop_or_invalidation_conditions)
            + list(plan.no_trade_conditions)
        )

        self.assertIn("支撑", combined)
        self.assertIn("压力", combined)
        self.assertIn("不", combined)

    def test_long_term_plan_includes_margin_of_safety_and_invalidation(self):
        plan = build_decision_plan(_analysis(), LONG_TERM_FUNDAMENTAL)
        combined = "\n".join(list(plan.conditional_entry_plan) + list(plan.stop_or_invalidation_conditions))

        self.assertIn("安全边际", combined)
        self.assertIn("证伪", "\n".join(plan.contrarian_view) + combined)

    def test_every_plan_includes_contrarian_view_and_invalidation(self):
        plan = build_decision_plan(_analysis(), SHORT_TERM_TRADER)

        self.assertTrue(plan.contrarian_view)
        self.assertTrue(plan.stop_or_invalidation_conditions)

    def test_profile_gate_caps_decision_confidence(self):
        plan = build_decision_plan(_analysis_with_missing_data(), LONG_TERM_FUNDAMENTAL)

        self.assertEqual(plan.confidence_level, "LOW")
        self.assertTrue(plan.profile_coverage.critical_gaps)

    def test_macro_gap_affects_growth_short_and_risk_profiles(self):
        analysis = _analysis_with_missing_data()

        for investor_type in (GROWTH_NARRATIVE, SHORT_TERM_TRADER, RISK_CONTROL):
            plan = build_decision_plan(analysis, investor_type)
            messages = "\n".join(plan.profile_coverage.warnings)
            self.assertIn("宏观", messages)

    def test_missing_volume_and_options_lower_short_term_confidence(self):
        plan = build_decision_plan(_analysis_with_missing_data(), SHORT_TERM_TRADER)
        messages = "\n".join(plan.profile_coverage.warnings)

        self.assertEqual(plan.confidence_level, "LOW")
        self.assertIn("成交量", messages)
        self.assertIn("期权", messages)

    def test_event_factors_use_short_references_without_original_titles(self):
        plan = build_decision_plan(_analysis(), LONG_TERM_FUNDAMENTAL)
        combined = "\n".join(list(plan.supporting_factors) + list(plan.risk_factors))

        self.assertIn("事件#", combined)
        self.assertIn("监管调查或召回风险", combined)
        self.assertNotIn("英文原题：Tesla faces regulatory investigation and recall", combined)


if __name__ == "__main__":
    unittest.main()
