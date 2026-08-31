import asyncio
from datetime import datetime, timezone

import pytest

import main
from strategies import TransformationRegistry, TransformationStrategyProvider


def _record(item, price, *, source="test-market", grade="A"):
    return {
        "item_id": item.lower(),
        "item_name": item,
        "price_chaos": price,
        "volume": 20,
        "source": source,
        "observation_type": "DIRECT_OBSERVATION",
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "confidence_grade": grade,
    }


def _registry():
    return TransformationRegistry([{
        "id": "test-route",
        "name": "Test conversion",
        "strategy_family": "test",
        "category": "Currency",
        "status": "Validated",
        "inputs": [{"item": "A", "quantity": 2, "category": "Currency"}],
        "deterministic_costs": [{"item": "Chaos", "quantity": 1, "category": "Currency"}],
        "probabilistic_costs": [],
        "outputs": [{"item": "B", "quantity": 1, "probability": 0.75, "category": "Currency"},
                    {"item": "C", "quantity": 1, "probability": 0.25, "category": "Currency"}],
        "expected_execution_time_hours": 2,
        "expected_sale_time_hours": 1,
        "requirements": {},
        "manual_actions": [],
        "risk_model": {"kind": "finite_outcome", "execution_risk": 0.1},
        "source": "test-definition",
        "verified_version": "v1",
        "max_batch": 3,
        "sale_fee_rate": 0.1,
        "output_discount_rate": 0.2,
        "strategy_confidence": 0.9,
    }])


def test_profit_route_calculation_preserves_price_provenance():
    rows = {item: _record(item, price) for item, price in (("A", 10), ("Chaos", 1), ("B", 40), ("C", 4))}
    prices = {f"Currency:{item}": row for item, row in rows.items()}
    routes = TransformationStrategyProvider(_registry()).evaluate({
        "league": "Test",
        "prices": prices,
        "price_records": prices,
        "chaos_per_divine": 100,
    })
    route = routes[0]
    assert route.total_input_cost == 21
    assert route.realistic_output_value == 24.8
    assert route.gross_profit == pytest.approx(3.8)
    assert route.expected_net_profit == pytest.approx(1.32)
    assert route.roi == pytest.approx(1.32 / 21)
    assert route.profit_per_active_hour == pytest.approx(1.32 / 2)
    assert route.roi_per_lock_hour == pytest.approx((1.32 / 21) / 3)
    assert route.elapsed_cycle_time == pytest.approx(3)
    assert route.capacity == 0
    assert route.source == "test-market"
    assert route.verification_metadata["definition_source"] == "test-definition"
    assert route.verification_metadata["verified_version"] == "v1"
    assert route.verified_version == "v1"
    assert route.execution_steps == []
    assert route.pricing_confidence == 1
    assert route.execution_risk == 0.1
    assert route.liquidity == {
        "tier": "low",
        "volume": 20,
        "components": {
            "Currency:A": 20,
            "Currency:Chaos": 20,
            "Currency:B": 20,
            "Currency:C": 20,
        },
    }

def test_profit_routes_api_uses_latest_market_rows(monkeypatch):
    rows = {
        "Currency": [_record("Divine", 100), _record("Chaos", 1), _record("A", 10),
                     _record("B", 40), _record("C", 4)],
    }

    async def latest(_league):
        return rows

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.strategies, "default_transformation_registry", _registry)
    response = asyncio.run(main.get_profit_routes("Test", category="Currency"))
    assert set(response) == {"league", "category", "poe_patch", "patch_status", "patch_reasons", "deterministic_readiness", "routes"}
    assert response["league"] == "Test"
    assert response["category"] == "Currency"
    assert response["routes"][0]["transformation_id"] == "test-route"
    assert response["routes"][0]["source"] == "test-market"
    assert response["routes"][0]["verified_version"] == "v1"
    assert response["deterministic_readiness"]["families"]["assembly"]["state"] == "unsupported_empty"
    assert response["deterministic_readiness"]["families"]["vendor"]["accepted_count"] == 0
    assert response["routes"][0]["execution_steps"] == []


def test_capital_plan_keeps_theoretical_candidate_without_exact_execution_depth(monkeypatch, tmp_path):
    rows = {
        "Currency": [_record("Divine", 100), _record("Chaos", 1), _record("A", 10),
                     _record("B", 40), _record("C", 4)],
    }
    captured = {}

    async def latest(_league):
        return rows

    async def no_opportunities(*_args, **_kwargs):
        return []

    original = main.capital.build_capital_plan

    def build(*args, **kwargs):
        captured["candidates"] = args[2]
        captured["plan"] = original(*args, **kwargs)
        return captured["plan"]

    monkeypatch.setattr(main.database, "DB_PATH", str(tmp_path / "capital.db"))
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda _league: asyncio.sleep(0, result=100))
    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.opportunity, "get_all_opportunities", no_opportunities)
    monkeypatch.setattr(main.strategies, "default_transformation_registry", _registry)
    monkeypatch.setattr(main.capital, "build_capital_plan", build)
    request = main.CapitalPlanRequest(
        league="Test",
        bankroll=main.capital.Bankroll(total_net_worth=50, liquid_currency=50),
        mode="PAPER",
        simulations=5,
    )
    asyncio.run(main.create_capital_plan(request))
    candidate = next(item for item in captured["candidates"] if item.id == "test-route")
    assert candidate.opportunity_capacity == 0
    assert captured["plan"].positions == []


def test_profit_route_requires_every_market_component():
    prices = {
        "Currency:A": _record("A", 10),
        "Currency:Chaos": _record("Chaos", 1),
        "Currency:B": _record("B", 40),
    }
    assert not TransformationStrategyProvider(_registry()).evaluate({
        "prices": prices,
        "price_records": prices,
    })


def test_discover_keeps_theoretical_candidate_without_execution_depth():
    rows = {item: _record(item, price) for item, price in (("A", 10), ("Chaos", 1), ("B", 40), ("C", 4))}
    prices = {f"Currency:{item}": row for item, row in rows.items()}
    candidates = TransformationStrategyProvider(_registry()).discover({
        "prices": prices, "price_records": prices, "chaos_per_divine": 100, "bankroll": 50,
    })
    assert len(candidates) == 1
    assert candidates[0].expected_profit_per_unit > 0
    assert candidates[0].opportunity_capacity == 0


def test_scalar_prices_are_unverified():
    prices = {"Currency:A": 10, "Currency:Chaos": 1, "Currency:B": 40, "Currency:C": 4}
    route = TransformationStrategyProvider(_registry()).evaluate({
        "prices": prices,
        "price_records": {},
    })[0]
    assert route.pricing_confidence == 0
    assert route.source == "request"
    assert route.liquidity["volume"] == 0


def test_invalid_strategy_confidence_is_rejected():
    record = _registry().records()[0]
    with pytest.raises(ValueError, match="strategy_confidence"):
        TransformationRegistry([{**record, "strategy_confidence": 1.1}])
    with pytest.raises(ValueError, match="strategy_confidence"):
        TransformationRegistry([{**record, "strategy_confidence": "high"}])


def test_loss_making_routes_remain_read_only_but_are_not_public_or_allocatable(monkeypatch):
    rows = {item: _record(item, price) for item, price in (("A", 10), ("Chaos", 1), ("B", 1), ("C", 1))}
    prices = {f"Currency:{item}": row for item, row in rows.items()}
    provider = TransformationStrategyProvider(_registry())
    context = {"prices": prices, "price_records": prices, "chaos_per_divine": 100}
    routes = provider.evaluate(context)
    assert routes and routes[0].expected_net_profit < 0
    assert provider.discover(context) == []

    async def latest(_league):
        return {"Currency": [_record("Divine", 100), *rows.values()]}

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.strategies, "default_transformation_registry", _registry)
    response = asyncio.run(main.get_profit_routes("Test", category="Currency"))
    assert response["routes"][0]["status"] == "theoretical"
    assert response["routes"][0]["expected_net_profit"] < 0


def test_placeholder_fixture_is_rejected():
    record = next(iter(main.strategies.default_transformation_registry().records()))
    assert record["status"] == "Rejected"
