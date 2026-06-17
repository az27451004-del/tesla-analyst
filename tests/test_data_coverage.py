import unittest

from stock_agent.data_coverage import (
    DOMAIN_BACKTEST,
    DOMAIN_FUNDAMENTALS,
    DOMAIN_MACRO,
    DOMAIN_MARKET_DATA,
    PRIORITY_P1,
    build_data_source_roadmap,
    evaluate_data_coverage,
    evaluate_profile_coverage,
)


class DataCoverageTest(unittest.TestCase):
    def test_roadmap_contains_six_domains(self):
        roadmap = build_data_source_roadmap()

        self.assertEqual(len(roadmap), 6)
        self.assertEqual(
            {item.domain for item in roadmap},
            {
                DOMAIN_MARKET_DATA,
                DOMAIN_FUNDAMENTALS,
                DOMAIN_MACRO,
                "industry_data",
                "options_and_flow",
                DOMAIN_BACKTEST,
            },
        )

    def test_p1_contains_market_fundamentals_macro_and_backtest(self):
        p1_domains = {item.domain for item in build_data_source_roadmap() if item.priority == PRIORITY_P1}

        self.assertIn(DOMAIN_MARKET_DATA, p1_domains)
        self.assertIn(DOMAIN_FUNDAMENTALS, p1_domains)
        self.assertIn(DOMAIN_MACRO, p1_domains)
        self.assertIn(DOMAIN_BACKTEST, p1_domains)

    def test_high_cost_terminals_are_late_enhancements(self):
        roadmap = build_data_source_roadmap()
        terminal_items = [
            item for item in roadmap if any("Bloomberg/FactSet" in source for source in item.paid_enhancement_sources)
        ]

        self.assertTrue(terminal_items)
        self.assertTrue(all("Bloomberg/FactSet" not in " ".join(item.low_cost_sources) for item in terminal_items))

    def test_missing_fundamentals_caps_long_term_profile(self):
        coverage = evaluate_data_coverage(
            has_market_data=True,
            has_volume=True,
            has_filings=False,
            has_financial_metrics=False,
            has_research_reports=False,
            has_macro_data=True,
            has_industry_data=True,
            has_official_events=True,
            has_options_data=True,
            has_broker_account_data=False,
            has_backtest=True,
        )

        profile = evaluate_profile_coverage(coverage, "long_term_fundamental")

        self.assertEqual(profile.confidence_cap, "MEDIUM")
        self.assertTrue(any(gap.domain == DOMAIN_FUNDAMENTALS for gap in profile.critical_gaps))

    def test_sample_data_caps_all_profiles_low(self):
        coverage = evaluate_data_coverage(
            has_market_data=True,
            has_volume=True,
            has_filings=True,
            has_financial_metrics=True,
            has_research_reports=True,
            has_macro_data=True,
            has_industry_data=True,
            has_official_events=True,
            has_options_data=True,
            has_broker_account_data=False,
            has_backtest=True,
            sample_data_detected=True,
        )

        for investor_type in ("long_term_fundamental", "growth_narrative", "short_term_trader", "risk_control"):
            self.assertEqual(evaluate_profile_coverage(coverage, investor_type).confidence_cap, "LOW")


if __name__ == "__main__":
    unittest.main()

