from __future__ import annotations

from typing import Any

from ..config import reliability_for_source
from ..models import (
    BrokerAccountData,
    BrokerPosition,
    CollectionRequest,
    OptionData,
    PricePoint,
    SourceRecord,
    WarningRecord,
    now_iso,
)
from ..normalization import mask_account_id, normalize_symbol, parse_datetime_to_iso, to_float_or_none
from .base import SourceOutput


class IBKRSource:
    name = "ibkr"
    source_type = "broker_api_read_only"

    def collect(self, request: CollectionRequest) -> SourceOutput:
        output = SourceOutput()
        collected_at = now_iso()
        config = request.data_source_config.get(self.name, {})
        client = None

        try:
            client = self._build_client(request, config)
        except Exception as exc:  # noqa: BLE001
            output.warnings.append(_warning("ibkr_connection_failed", f"IBKR connection failed: {exc}", self.name))

        if client is None:
            output.warnings.append(_warning("ibkr_not_connected", "IBKR client is not connected.", self.name))
            output.source_inventory.append(self._source_record(output, collected_at, connected=False))
            return output

        if "market_data" in request.normalized_requirements:
            try:
                output.market_data.extend(self._collect_market_data(client, request.normalized_symbol, collected_at))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("ibkr_market_data_failed", f"IBKR market data failed: {exc}", self.name))

        if "options_data" in request.normalized_requirements:
            try:
                output.options_data.extend(self._collect_options(client, request.normalized_symbol, collected_at))
            except Exception as exc:  # noqa: BLE001
                output.warnings.append(_warning("ibkr_options_failed", f"IBKR options data failed: {exc}", self.name))

        if "broker_account_data" in request.normalized_requirements:
            if not request.allow_broker_account_data:
                output.warnings.append(
                    _warning(
                        "broker_account_data_not_allowed",
                        "broker_account_data was requested but allow_broker_account_data is false.",
                        self.name,
                    )
                )
            else:
                try:
                    output.broker_account_data.append(
                        self._collect_account_data(client, request.allow_positions_pnl, collected_at)
                    )
                except Exception as exc:  # noqa: BLE001
                    output.warnings.append(_warning("ibkr_account_data_failed", f"IBKR account data failed: {exc}", self.name))

        output.source_inventory.append(self._source_record(output, collected_at, connected=True))
        return output

    def _build_client(self, request: CollectionRequest, config: dict[str, Any]) -> Any:
        factory = config.get("client_factory") or request.broker_config.get("client_factory")
        if factory:
            return factory()
        client = config.get("client") or request.broker_config.get("client")
        if client:
            return client

        try:
            from ib_insync import IB  # type: ignore
        except ImportError as exc:
            raise RuntimeError("ib_insync is not installed; provide an IBKR client_factory for this source") from exc

        ib = IB()
        host = request.broker_config.get("host", config.get("host", "127.0.0.1"))
        port = int(request.broker_config.get("port", config.get("port", 7497)))
        client_id = int(request.broker_config.get("client_id", config.get("client_id", 19)))
        ib.connect(host, port, clientId=client_id, readonly=True)
        return ib

    def _collect_market_data(self, client: Any, symbol: str, collected_at: str) -> list[PricePoint]:
        rows = _call_first(client, ["historical_bars", "get_historical_bars", "market_data", "get_market_data"], symbol)
        if rows is None:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        prices: list[PricePoint] = []
        for row in rows:
            row_dict = _object_to_dict(row)
            close = to_float_or_none(_first(row_dict, "close", "last", "market_price", "price"))
            if close is None:
                continue
            prices.append(
                PricePoint(
                    date_time=parse_datetime_to_iso(_first(row_dict, "date_time", "datetime", "date", "time")),
                    open=to_float_or_none(_first(row_dict, "open")),
                    high=to_float_or_none(_first(row_dict, "high")),
                    low=to_float_or_none(_first(row_dict, "low")),
                    close=close,
                    adjusted_close=to_float_or_none(_first(row_dict, "adjusted_close", "adj_close")),
                    volume=to_float_or_none(_first(row_dict, "volume")),
                    source="IBKR",
                    source_reliability=reliability_for_source("IBKR"),
                    is_realtime=bool(row_dict.get("is_realtime", False)),
                    is_adjusted=bool(row_dict.get("is_adjusted", False)),
                    collected_at=collected_at,
                    raw_metadata={"row": row_dict, "symbol": normalize_symbol(symbol)},
                )
            )
        return prices

    def _collect_options(self, client: Any, symbol: str, collected_at: str) -> list[OptionData]:
        rows = _call_first(client, ["option_chain", "get_option_chain", "options_data"], symbol)
        if rows is None:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        options: list[OptionData] = []
        for row in rows:
            row_dict = _object_to_dict(row)
            options.append(
                OptionData(
                    metric_name=str(_first(row_dict, "metric_name", "field", "name") or "option_quote"),
                    value=to_float_or_none(_first(row_dict, "value", "price", "mid", "last")),
                    date_time=parse_datetime_to_iso(_first(row_dict, "date_time", "datetime", "date")),
                    expiration=parse_datetime_to_iso(_first(row_dict, "expiration", "expiry")),
                    strike=to_float_or_none(_first(row_dict, "strike")),
                    option_type=str(_first(row_dict, "option_type", "right", "type")),
                    source="IBKR",
                    source_reliability=reliability_for_source("IBKR"),
                    collected_at=collected_at,
                    raw_metadata={"row": row_dict, "symbol": normalize_symbol(symbol)},
                )
            )
        return options

    def _collect_account_data(self, client: Any, allow_positions_pnl: bool, collected_at: str) -> BrokerAccountData:
        summary = _call_first(client, ["account_summary", "get_account_summary"])
        summary_dict = _object_to_dict(summary or {})
        positions: list[BrokerPosition] = []
        pnl = {}

        if allow_positions_pnl:
            raw_positions = _call_first(client, ["positions", "get_positions"])
            if isinstance(raw_positions, dict):
                raw_positions = [raw_positions]
            for row in raw_positions or []:
                row_dict = _object_to_dict(row)
                positions.append(
                    BrokerPosition(
                        symbol=normalize_symbol(str(_first(row_dict, "symbol", "contract_symbol", "localSymbol"))),
                        quantity=to_float_or_none(_first(row_dict, "quantity", "position")),
                        average_cost=to_float_or_none(_first(row_dict, "average_cost", "avgCost")),
                        market_price=to_float_or_none(_first(row_dict, "market_price", "price")),
                        market_value=to_float_or_none(_first(row_dict, "market_value", "value")),
                        unrealized_pnl=to_float_or_none(_first(row_dict, "unrealized_pnl", "unrealizedPNL")),
                        currency=str(_first(row_dict, "currency") or summary_dict.get("currency", "")),
                        source="IBKR",
                    )
                )
            pnl = _object_to_dict(_call_first(client, ["pnl", "get_pnl"]) or {})

        return BrokerAccountData(
            account_id_masked=mask_account_id(_first(summary_dict, "account_id", "account", "accountId")),
            currency=str(_first(summary_dict, "currency") or "USD"),
            net_liquidation=to_float_or_none(_first(summary_dict, "net_liquidation", "NetLiquidation")),
            cash_balance=to_float_or_none(_first(summary_dict, "cash_balance", "TotalCashValue")),
            margin_requirement=to_float_or_none(_first(summary_dict, "margin_requirement", "FullMaintMarginReq")),
            positions=positions,
            unrealized_pnl=to_float_or_none(_first(pnl, "unrealized_pnl", "unrealizedPnL")) if allow_positions_pnl else None,
            realized_pnl=to_float_or_none(_first(pnl, "realized_pnl", "realizedPnL")) if allow_positions_pnl else None,
            source="IBKR",
            source_reliability=reliability_for_source("IBKR"),
            collected_at=collected_at,
            raw_metadata={"summary_keys": sorted(summary_dict.keys()), "positions_included": allow_positions_pnl},
        )

    def _source_record(self, output: SourceOutput, collected_at: str, connected: bool) -> SourceRecord:
        return SourceRecord(
            name=self.name,
            source_type=self.source_type,
            enabled=True,
            used=output.records_collected > 0,
            reliability=reliability_for_source("IBKR"),
            records_collected=output.records_collected,
            failed=bool(output.warnings) and output.records_collected == 0,
            failure_reason="; ".join(w.message for w in output.warnings),
            collected_at=collected_at,
            raw_metadata={"connected": connected, "read_only": True},
        )


def _call_first(client: Any, method_names: list[str], *args: Any) -> Any:
    for name in method_names:
        method = getattr(client, name, None)
        if callable(method):
            return method(*args)
    return None


def _object_to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _first(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return ""


def _warning(code: str, message: str, source: str) -> WarningRecord:
    return WarningRecord(code=code, message=message, source=source, severity="WARNING", collected_at=now_iso())

