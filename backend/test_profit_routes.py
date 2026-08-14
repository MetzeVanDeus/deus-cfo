import asyncio

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
        "observed_at": "2026-08-14T21:00:00+00:00",
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
    assert route.realistic_output_value == 31
    assert route.gross_profit == 10
    assert route.expected_net_profit == 10
    assert route.roi == 10 / 21
    assert route.profit_per_hour == 10 / 3
    assert route.profit_per_divine_hour == (10 / 100) / 3
    assert route.capacity == 3
    assert route.source == "test-market"
    assert route.verification_metadata["definition_source"] == "test-definition"
    assert route.verification_metadata["verified_version"] == "v1"
    assert route.verified_version == "v1"
    assert route.execution_steps == []
    assert route.pricing_confidence == 1
    assert route.execution_risk == 0.1

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
    assert set(response) == {"league", "category", "routes"}
    assert response["league"] == "Test"
    assert response["category"] == "Currency"
    assert response["routes"][0]["transformation_id"] == "test-route"
    assert response["routes"][0]["source"] == "test-market"
    assert response["routes"][0]["verified_version"] == "v1"
    assert response["routes"][0]["execution_steps"] == []


def test_capital_plan_receives_transformation_as_allocator_candidate(monkeypatch, tmp_path):
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
        return original(*args, **kwargs)

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
    route = next(item for item in captured["candidates"] if item.id == "test-route")
    assert route.strategy_type == "transformation"
    assert route.metadata["profit_route"]["verified_version"] == "v1"
    assert route.minimum_capital == 21 / 100


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
