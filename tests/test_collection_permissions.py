import unittest

from stock_agent.collection import CollectionRequest, collect_data


class FakeIBKRClient:
    def __init__(self):
        self.account_summary_called = False
        self.positions_called = False
        self.pnl_called = False

    def account_summary(self):
        self.account_summary_called = True
        return {
            "account_id": "DU12345678",
            "currency": "USD",
            "net_liquidation": 100000,
            "cash_balance": 25000,
            "margin_requirement": 5000,
        }

    def positions(self):
        self.positions_called = True
        return [{"symbol": "TSLA", "quantity": 5, "average_cost": 200, "unrealized_pnl": 100}]

    def pnl(self):
        self.pnl_called = True
        return {"unrealized_pnl": 100, "realized_pnl": 50}


class CollectionPermissionsTest(unittest.TestCase):
    def test_broker_account_data_denied_when_not_allowed(self):
        client = FakeIBKRClient()
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["broker_account_data"],
            allow_broker_account_data=False,
            data_source_config={"ibkr": {"enabled": True, "client_factory": lambda: client}},
        )

        result = collect_data(request)

        self.assertEqual(result.broker_account_data, [])
        self.assertFalse(client.account_summary_called)
        self.assertFalse(client.positions_called)
        self.assertIn("broker_account_data_not_allowed", {warning.code for warning in result.warnings})

    def test_positions_and_pnl_denied_when_not_allowed(self):
        client = FakeIBKRClient()
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["broker_account_data"],
            allow_broker_account_data=True,
            allow_positions_pnl=False,
            data_source_config={"ibkr": {"enabled": True, "client_factory": lambda: client}},
        )

        result = collect_data(request)

        self.assertEqual(len(result.broker_account_data), 1)
        account = result.broker_account_data[0]
        self.assertTrue(client.account_summary_called)
        self.assertFalse(client.positions_called)
        self.assertFalse(client.pnl_called)
        self.assertEqual(account.positions, [])
        self.assertIsNone(account.unrealized_pnl)
        self.assertNotIn("DU12345678", result.to_json())

    def test_positions_and_pnl_read_when_explicitly_allowed(self):
        client = FakeIBKRClient()
        request = CollectionRequest(
            symbol="TSLA",
            data_requirements=["broker_account_data"],
            allow_broker_account_data=True,
            allow_positions_pnl=True,
            data_source_config={"ibkr": {"enabled": True, "client_factory": lambda: client}},
        )

        result = collect_data(request)

        self.assertTrue(client.positions_called)
        self.assertTrue(client.pnl_called)
        self.assertEqual(len(result.broker_account_data[0].positions), 1)
        self.assertEqual(result.broker_account_data[0].unrealized_pnl, 100.0)


if __name__ == "__main__":
    unittest.main()

