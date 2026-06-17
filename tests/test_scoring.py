import unittest

from tsla_agent.models import Event
from tsla_agent.scoring import score_event


class ScoringTest(unittest.TestCase):
    def test_positive_delivery_event_scores_positive(self):
        event = score_event(Event(source="test", title="Tesla deliveries beat consensus with record growth"))

        self.assertGreater(event.sentiment, 0)
        self.assertEqual(event.category, "delivery")
        self.assertGreater(event.impact_score, 0.5)

    def test_negative_regulatory_event_scores_negative(self):
        event = score_event(Event(source="test", title="Tesla faces regulatory investigation and recall"))

        self.assertLess(event.sentiment, 0)
        self.assertEqual(event.category, "regulatory")
        self.assertGreater(event.impact_score, 0.5)


if __name__ == "__main__":
    unittest.main()
