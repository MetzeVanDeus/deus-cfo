import asyncio
import json
from datetime import datetime, timezone

import collector
import database
import main
import market_data
import pytest
import strategies
from strategies import (
    DivCardRecipe,
    DivCardRegistry,
    DivinationCardStrategyProvider,
    default_div_card_registry,
)

_RECENT_OBSERVED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def recipe(**changes):
    value = {
        "id": "test-card",
        "card": "Test Card",
        "set_size": 4,
        "card_market_key": "DivinationCard:test-card",
        "reward_type": "exact_currency",
        "reward_item": "Test Orb",
        "reward_quantity": 10,
        "reward_market_key": "Currency:test-orb",
        "variant": "",
        "corrupted": False,
        "item_level": None,
        "special_conditions": [],
        "deterministic": True,
        "verified_version": "3.0",
        "poe_patch": "3.28",
        "source": "test",
        "manual_actions": [],
        "expected_execution_time_hours": 1,
        "expected_sale_time_hours": 1,
    }
    value.update(changes)
    return value


def test_typed_recipe_contract_is_constructible():
    typed = DivCardRecipe(**recipe())
    assert typed.card_market_key == "DivinationCard:test-card"


def market_context(*, depth=True, bankroll=10):
    context = {
        "prices": {"DivinationCard:test-card": 5, "Currency:test-orb": 3},
        "price_records": {
            "DivinationCard:test-card": {"confidence_grade": "A"},
            "Currency:test-orb": {"confidence_grade": "A"},
        },
        "bankroll": bankroll,
        "chaos_per_divine": 10,
        "capacity_horizon_hours": 24,
    }
    if depth:
        context["execution_prices"] = {
            "DivinationCard:test-card": {
                "buy_levels": [{"price": 6, "quantity": 4}],
                "fee_rate": 0,
                "observed_at": _RECENT_OBSERVED_AT,
                "confidence": 0.9,
                "source": "test-depth",
            },
            "Currency:test-orb": {
                "sell_levels": [{"price": 3.5, "quantity": 10}],
                "fee_rate": 0.05,
                "observed_at": _RECENT_OBSERVED_AT,
                "confidence": 0.8,
                "source": "test-depth",
            },
        }
    return context


def test_registry_is_versioned_strict_and_unique():
    registry = DivCardRegistry([recipe()], version="3.0", source="test")
    assert registry.records()[0]["card_market_key"] == "DivinationCard:test-card"
    with pytest.raises(ValueError, match="unmodelled"):
        DivCardRegistry([recipe(extra="nope")], version="3.0", source="test")
    with pytest.raises(ValueError, match="duplicate"):
        DivCardRegistry([recipe(), recipe()], version="3.0", source="test")
    with pytest.raises(ValueError, match="canonical"):
        DivCardRegistry([recipe(card_market_key="DivinationCard")], version="3.0", source="test")
    with pytest.raises(ValueError, match="verified_version .* registry version"):
        DivCardRegistry([recipe(verified_version="2.9")], version="3.0", source="test")

def test_poe_patch_metadata_is_separate_and_active_patch_is_required_for_verification():
    registry = DivCardRegistry([recipe()], version="3.0", source="test", poe_patch="3.28")
    assert registry.version == "3.0"
    assert registry.poe_patch == "3.28"
    provider = DivinationCardStrategyProvider(registry)
    matching = provider.evaluate({**market_context(depth=False), "active_poe_patch": "3.28"})
    assert matching and matching[0].theoretical_roi is not None
    assert matching[0].poe_patch == "3.28"
    assert provider.evaluate({**market_context(depth=False), "active_poe_patch": "3.27"}) == []
    with pytest.raises(ValueError, match="poe_patch .* registry patch"):
        DivCardRegistry([recipe(poe_patch="3.27")], version="3.0", source="test", poe_patch="3.28")


def test_unknown_depth_is_unscalable_and_not_discoverable():
    provider = DivinationCardStrategyProvider(DivCardRegistry([recipe()], version="3.0", source="test"))
    route = provider.evaluate(market_context(depth=False))[0]
    assert route.market_capacity == 0
    assert route.recommended_capacity == 0
    assert route.executable_roi is None
    assert provider.discover(market_context(depth=False)) == []
    assert any("depth unavailable" in reason for reason in route.reasons)
    assert route.status == "theoretical"


def test_depth_pricing_exposes_theoretical_and_executable_roi_and_repeatability():
    provider = DivinationCardStrategyProvider(DivCardRegistry([recipe()], version="3.0", source="test"))
    route = provider.evaluate(market_context())[0]
    assert route.total_input_cost == pytest.approx(24)
    assert route.realistic_output_value == pytest.approx(33.25)
    assert route.profit_per_set == pytest.approx(9.25)
    assert route.theoretical_roi == pytest.approx((30 - 20) / 20)
    assert route.executable_roi == pytest.approx(9.25 / 24)
    assert route.capacity_units == "sets"
    assert route.market_capacity == 1
    assert route.budget_capacity == 1
    assert route.estimated_sets_per_lock_hour == pytest.approx(0.5)
    assert route.verification_metadata["card_market_key"] == "DivinationCard:test-card"
    assert provider.discover(market_context())[0].strategy_type == "divination_card"


def test_non_deterministic_cards_require_trusted_finite_distribution():
    with pytest.raises(ValueError, match="trusted finite"):
        DivCardRegistry([recipe(deterministic=False)], version="3.0", source="test")
    with pytest.raises(ValueError, match="not deterministic"):
        DivCardRegistry([recipe(corrupted=True)], version="3.0", source="test")
    registry = DivCardRegistry([recipe(
        deterministic=False,
        trusted_distribution=True,
        outcomes=[{
            "reward_item": "Test Orb", "reward_quantity": 10,
            "reward_market_key": "Currency:test-orb", "probability": 1.0,
        }],
    )], version="3.0", source="test")
    route = DivinationCardStrategyProvider(registry).evaluate(market_context())[0]
    assert "trusted finite-outcome" in route.reasons[1]


def test_exact_keys_do_not_fall_back_to_broad_names():
    provider = DivinationCardStrategyProvider(DivCardRegistry([recipe()], version="3.0", source="test"))
    context = market_context()
    context["prices"] = {"Test Card": 5, "Test Orb": 3}
    context["price_records"] = {}
    context["execution_prices"] = {}
    route = provider.evaluate(context)[0]
    assert route.theoretical_roi is None
    assert route.market_capacity == 0


def test_default_registry_loads_curated_version():
    registry = default_div_card_registry()
    assert registry.version == "3.0.0"
    assert registry.records()[0]["deterministic"] is True

def test_active_patch_resolves_from_verified_league_without_environment(monkeypatch):
    monkeypatch.delenv("DEUSCFO_ACTIVE_POE_PATCH", raising=False)
    assert asyncio.run(main.resolve_active_poe_patch("Allflame")) == "3.29.0"
    assert asyncio.run(main.resolve_active_poe_patch("Standard")) is None


def test_profit_routes_endpoint_exposes_card_routes(monkeypatch):
    rows = {
        "DivinationCard": [{
            "item_id": "test-card", "item_name": "Test Card", "price_chaos": 5,
            "source": "test", "confidence_grade": "A",
            "buy_levels": [{"price": 6, "quantity": 4}], "fee_rate": 0, "observed_at": _RECENT_OBSERVED_AT, "confidence": 0.9,
        }],
        "Currency": [{
            "item_id": "test-orb", "item_name": "Test Orb", "price_chaos": 3,
            "source": "test", "confidence_grade": "A",
            "sell_levels": [{"price": 3.5, "quantity": 10}], "fee_rate": 0.05, "observed_at": _RECENT_OBSERVED_AT, "confidence": 0.8,
        }],
    }
    async def latest(_league):
        return rows
    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.28"))
    monkeypatch.setattr(main.strategies, "default_div_card_registry", lambda: DivCardRegistry([recipe()], version="3.0", source="test"))
    result = asyncio.run(main.get_profit_routes("Test"))
    assert result["routes"]
    assert result["routes"][0]["strategy_family"] == "divination_card"
    assert result["routes"][0]["capacity_units"] == "sets"

def test_actual_recipe_snapshot_ids_produce_theoretical_route(monkeypatch):
    async def latest(_league):
        return {
            "DivinationCard": [{
                "league": "Test", "category": "DivinationCard",
                "item_id": "the-doctor", "item_name": "The Doctor",
                "variant": "", "price_chaos": 42, "volume": 12,
                "listing_count": 12, "source": "poe.ninja",
                "observation_type": "DIRECT_OBSERVATION",
                "observed_at": _RECENT_OBSERVED_AT,
                "confidence_grade": "B",
            }],
            "UniqueAccessory": [{
                "league": "Test", "category": "UniqueAccessory",
                "item_id": "headhunter-leather-belt", "item_name": "Headhunter",
                "variant": "", "price_chaos": 410, "volume": 4,
                "listing_count": 4, "source": "poe.ninja",
                "observation_type": "DIRECT_OBSERVATION",
                "observed_at": _RECENT_OBSERVED_AT,
                "confidence_grade": "B",
            }],
        }

    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.29.0"))
    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    result = asyncio.run(main.get_profit_routes("Test", category="DivinationCard"))
    route = result["routes"][0]
    assert route["transformation_id"] == "the-doctor-to-headhunter"
    assert route["status"] == "theoretical"
    assert route["theoretical_roi"] == pytest.approx((410 - 42 * 8) / (42 * 8))
    assert route["realistic_output_value"] == pytest.approx(410)
    assert route["expected_net_profit"] == 0
    assert route["executable_roi"] is None

def test_profit_routes_keeps_theoretical_route_when_reward_has_no_sell_depth(monkeypatch):
    card_recipe = recipe(
        reward_item="Headhunter",
        reward_market_key="UniqueAccessory:headhunter-leather-belt",
    )
    rows = {
        "DivinationCard": [{
            "item_id": "test-card", "item_name": "Test Card", "price_chaos": 5,
            "source": "poe.ninja", "confidence_grade": "B",
        }],
        "UniqueAccessory": [{
            "item_id": "headhunter-leather-belt", "item_name": "Headhunter", "price_chaos": 3,
            "source": "poe.ninja", "confidence_grade": "B",
        }],
    }

    async def latest(_league):
        return rows
    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.28"))

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(
        main.strategies,
        "default_div_card_registry",
        lambda: DivCardRegistry([card_recipe], version="3.0", source="test"),
    )
    result = asyncio.run(main.get_profit_routes("Test", category="DivinationCard"))
    route = result["routes"][0]
    assert route["status"] == "theoretical"
    assert route["theoretical_roi"] == pytest.approx(0.5)
    assert route["expected_net_profit"] == 0
    assert route["executable_roi"] is None
    assert route["market_capacity"] == 0

    assert any("missing buy depth" in reason for reason in route["reasons"])
def test_profit_routes_fail_closed_without_matching_active_patch(monkeypatch):
    async def latest(_league):
        return {
            "DivinationCard": [{
                "item_id": "the-doctor", "item_name": "The Doctor", "price_chaos": 42,
                "source": "poe.ninja", "confidence_grade": "B",
            }],
            "UniqueAccessory": [{
                "item_id": "headhunter-leather-belt", "item_name": "Headhunter", "price_chaos": 410,
                "source": "poe.ninja", "confidence_grade": "B",
            }],
        }

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result=None))
    unknown = asyncio.run(main.get_profit_routes("Allflame", category="DivinationCard"))
    assert unknown["patch_status"] == "unknown"
    assert unknown["routes"] == []
    assert any("unknown" in reason for reason in unknown["patch_reasons"])

    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.28"))
    stale = asyncio.run(main.get_profit_routes("Allflame", category="DivinationCard"))
    assert stale["routes"] == []
    assert stale["patch_status"] == "mismatch"


def test_capital_planning_receives_card_opportunity(monkeypatch, tmp_path):
    rows = {
        "DivinationCard": [{
            "item_id": "test-card", "item_name": "Test Card", "price_chaos": 5,
            "source": "test", "confidence_grade": "A",
            "buy_levels": [{"price": 6, "quantity": 4}], "fee_rate": 0, "observed_at": _RECENT_OBSERVED_AT, "confidence": 0.9,
        }],
        "Currency": [{
            "item_id": "test-orb", "item_name": "Test Orb", "price_chaos": 3,
            "source": "test", "confidence_grade": "A",
            "sell_levels": [{"price": 3.5, "quantity": 10}], "fee_rate": 0.05, "observed_at": _RECENT_OBSERVED_AT, "confidence": 0.8,
        }],
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
    monkeypatch.setattr(main.database, "DB_PATH", str(tmp_path / "cards.db"))
    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.opportunity, "get_all_opportunities", no_opportunities)
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda _league: asyncio.sleep(0, result=10))
    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.28"))
    monkeypatch.setattr(main.strategies, "default_div_card_registry", lambda: DivCardRegistry([recipe()], version="3.0", source="test"))
    monkeypatch.setattr(main.capital, "build_capital_plan", build)
    request = main.CapitalPlanRequest(
        league="Test", bankroll=main.capital.Bankroll(total_net_worth=10, liquid_currency=10),
        mode="PAPER", simulations=5,
    )
    asyncio.run(main.create_capital_plan(request))
    card = next(item for item in captured["candidates"] if item.strategy_type == "divination_card")
    assert card.metadata["capacity_units"] == "sets"

    for active_patch in (None, "3.29"):
        monkeypatch.setattr(
            main,
            "resolve_active_poe_patch",
            lambda _league, active_patch=active_patch: asyncio.sleep(0, result=active_patch),
        )
        captured["candidates"] = []
        asyncio.run(main.create_capital_plan(request))
        assert not any(item.strategy_type == "divination_card" for item in captured["candidates"])
    assert card.metadata["profit_route"]["recommended_capacity"] == 1

def test_collector_database_and_market_context_preserve_execution_quote(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        def json(self):
            return {"lines": [{
                "id": "test-card",
                "primaryValue": 5,
                "volumePrimaryValue": 4,
                "execution_quote": {
                    "buy_levels": [{"price": 6, "quantity": 4}],
                    "fee_rate": 0,
                    "observed_at": _RECENT_OBSERVED_AT,
                    "confidence": 0.9,
                    "source": "collector-depth",
                },
            }]}

    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_):
            return None
        async def get(self, *_args, **_kwargs):
            return Response()

    async def run():
        timestamp = "2026-08-15T00:00:00+00:00"
        await collector.collect_snapshot("Test", "DivinationCard", timestamp=timestamp)
        reward = collector._normalize({
            "detailsId": "test-orb",
            "name": "Test Orb",
            "chaosValue": 3,
            "listingCount": 10,
            "execution_quote": {
                "sell_levels": [{"price": 3.5, "quantity": 10}],
                "fee_rate": 0.05,
                "observed_at": _RECENT_OBSERVED_AT,
                "confidence": 0.8,
                "source": "collector-depth",
            },
        }, "Test", "Currency", False)
        await database.insert_snapshots([reward], timestamp=timestamp)
        latest = await market_data.get_all_latest("Test")
        context = main._latest_market_context(latest)
        route = DivinationCardStrategyProvider(
            DivCardRegistry([recipe()], version="3.0", source="test")
        ).evaluate({**context, "league": "Test", "chaos_per_divine": 10, "bankroll": 10})[0]
        return latest, route

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "depth.db"))
    monkeypatch.setattr(database, "_schema_path", None)
    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_kwargs: Client())
    latest, route = asyncio.run(run())
    assert json.loads(latest["DivinationCard"][0]["execution_quote"])["buy_levels"][0]["quantity"] == 4
    assert route.market_capacity == 1
    assert route.executable_roi == pytest.approx(9.25 / 24)


def test_trade_depth_adapter_only_normalizes_buy_payload(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "id": "search-card",
                "result": ["card-1", "card-2"],
            } if self.kind == "search" else {
                "result": [
                    {
                        "id": "card-1",
                        "listing": {
                            "indexed": "2026-08-15T01:00:00Z",
                            "price": {"amount": 5, "currency": "chaos"},
                        },
                        "item": {"typeLine": "Test Card", "stackSize": 4},
                    },
                    {
                        "id": "card-2",
                        "listing": {
                            "indexed": "2026-08-15T01:01:00Z",
                            "price": {"amount": 6, "currency": "chaos"},
                        },
                        "item": {"typeLine": "Test Card", "stackSize": 2},
                    },
                ]
            }

        def __init__(self, kind):
            self.kind = kind

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, _url, *, json):
            assert json["query"]["name"] == "Test Card"
            return Response("search")

        async def get(self, _url, *, params):
            return Response("fetch")

    monkeypatch.setattr(collector.httpx, "AsyncClient", lambda **_kwargs: Client())
    quotes = asyncio.run(collector.TradeDepthAdapter(limit=10).collect(
        "Test", [recipe()], chaos_per_divine=10
    ))
    assert quotes["DivinationCard:test-card"]["buy_levels"] == [
        {"price": 5.0, "quantity": 4.0},
        {"price": 6.0, "quantity": 2.0},
    ]
    assert "Currency:test-orb" not in quotes
    assert quotes["DivinationCard:test-card"]["source"] == "pathofexile_trade_api"

    async def unsupported_sell():
        return await collector.TradeDepthAdapter().quote(
            Client(), "Test", "Test Orb", side="sell", chaos_per_divine=10
        )

    assert asyncio.run(unsupported_sell()) is None


def test_trade_depth_uses_zero_when_divine_rate_unavailable(monkeypatch):
    seen = []

    class Adapter:
        async def collect(self, _league, _recipes, *, chaos_per_divine):
            seen.append(chaos_per_divine)
            return {}

    monkeypatch.setattr(
        collector.market_data,
        "resolve_chaos_per_divine",
        lambda _league: asyncio.sleep(0, result=None),
    )
    assert asyncio.run(collector.collect_trade_depth("Test", adapter=Adapter())) == {}
    assert seen == [0.0]


def test_trade_depth_collector_persists_adapter_quotes(monkeypatch, tmp_path):
    class Adapter:
        async def collect(self, _league, _recipes, *, chaos_per_divine):
            assert chaos_per_divine == 10
            return {
                "DivinationCard:test-card": {
                    "buy_levels": [{"price": 6, "quantity": 4}],
                    "fee_rate": 0,
                    "observed_at": _RECENT_OBSERVED_AT,
                    "confidence": 0.6,
                    "source": "pathofexile_trade_api",
                },
                "Currency:test-orb": {
                    "sell_levels": [{"price": 40, "quantity": 10}],
                    "fee_rate": 0,
                    "observed_at": _RECENT_OBSERVED_AT,
                    "confidence": 0.6,
                    "source": "pathofexile_trade_api",
                },
            }

    async def run():
        await database.insert_snapshots([{
            "league": "Test", "category": "Currency", "item_id": "divine",
            "item_name": "Divine Orb", "price_chaos": 10, "volume": 1,
            "listing_count": 1, "source": "test", "observation_type": "DIRECT_OBSERVATION",
            "observed_at": _RECENT_OBSERVED_AT, "confidence_grade": "A",
        }], timestamp=_RECENT_OBSERVED_AT)
        quotes = await collector.collect_trade_depth(
            "Test", timestamp=_RECENT_OBSERVED_AT, adapter=Adapter()
        )
        latest = await market_data.get_all_latest("Test")
        return quotes, latest

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "trade-depth.db"))
    monkeypatch.setattr(
        collector.market_data, "resolve_chaos_per_divine",
        lambda _league: asyncio.sleep(0, result=10),
    )
    monkeypatch.setattr(strategies, "default_div_card_registry", lambda: DivCardRegistry([recipe()], version="3.0", source="test"))
    quotes, latest = asyncio.run(run())
    assert set(quotes) == {"DivinationCard:test-card", "Currency:test-orb"}
    assert json.loads(latest["DivinationCard"][0]["execution_quote"])["source"] == "pathofexile_trade_api"
    orb = next(row for row in latest["Currency"] if row["item_id"] == "test-orb")
    assert json.loads(orb["execution_quote"])["sell_levels"][0]["quantity"] == 10

def test_finite_outcome_executable_value_is_probability_weighted():
    card_recipe = recipe(
        deterministic=False,
        trusted_distribution=True,
        outcomes=[
            {"reward_item": "Common", "reward_quantity": 10, "reward_market_key": "Currency:common", "probability": 0.25},
            {"reward_item": "Rare", "reward_quantity": 10, "reward_market_key": "Currency:rare", "probability": 0.75},
        ],
    )
    context = market_context()
    context["prices"] = {
        "DivinationCard:test-card": 5,
        "Currency:common": 10,
        "Currency:rare": 2,
    }
    context["execution_prices"] = {
        "DivinationCard:test-card": {"buy_levels": [{"price": 6, "quantity": 4}], "fee_rate": 0, "observed_at": _RECENT_OBSERVED_AT, "confidence": 1, "source": "test"},
        "Currency:common": {"sell_levels": [{"price": 10, "quantity": 10}], "fee_rate": 0, "observed_at": _RECENT_OBSERVED_AT, "confidence": 1, "source": "test"},
        "Currency:rare": {"sell_levels": [{"price": 2, "quantity": 10}], "fee_rate": 0, "observed_at": _RECENT_OBSERVED_AT, "confidence": 1, "source": "test"},
    }
    route = DivinationCardStrategyProvider(DivCardRegistry([card_recipe], version="3.0", source="test")).evaluate(context)[0]
    assert route.realistic_output_value == pytest.approx(40)
    assert route.executable_net_profit == pytest.approx(16)


def test_cumulative_depth_ladder_worsens_larger_batch_economics():
    card_recipe = recipe(max_batch=2)
    context = market_context()
    context["execution_prices"]["DivinationCard:test-card"]["buy_levels"] = [
        {"price": 6, "quantity": 4}, {"price": 7, "quantity": 4},
    ]
    context["execution_prices"]["Currency:test-orb"]["sell_levels"] = [
        {"price": 4, "quantity": 10}, {"price": 3, "quantity": 10},
    ]
    route = DivinationCardStrategyProvider(DivCardRegistry([card_recipe], version="3.0", source="test")).evaluate(context)[0]
    ladder = route.verification_metadata["batch_ladder"]
    assert len(ladder) == 2
    assert ladder[1]["roi"] < ladder[0]["roi"]
    assert route.market_capacity == 2
    assert route.recommended_capacity == 2

def test_flat_market_context_preserves_stale_execution_marker():
    context = main._latest_market_context({
        "DivinationCard": [{
            "item_id": "test-card", "item_name": "Test Card", "price_chaos": 5,
            "stale": True,
            "buy_levels": [{"price": 6, "quantity": 4}],
            "observed_at": _RECENT_OBSERVED_AT, "confidence": 0.9,
            "source": "test",
        }],
    })
    assert context["execution_prices"]["DivinationCard:test-card"]["stale"] is True
    route = DivinationCardStrategyProvider(DivCardRegistry([recipe()], version="3.0", source="test")).evaluate({
        **market_context(depth=False), "execution_prices": context["execution_prices"],
    })[0]
    assert route.market_capacity == 0
    assert route.recommended_capacity == 0

def test_batch_ladder_stops_before_negative_marginal_batch():
    ladder = strategies.evaluate_batch_ladder(
        set_size=1,
        outcomes=[{"reward_quantity": 1, "probability": 1.0}],
        buy_quote={"levels": [{"price": 1, "quantity": 1}, {"price": 100, "quantity": 1}], "fee": 0},
        sell_quotes=[{"levels": [{"price": 100, "quantity": 1}, {"price": 90, "quantity": 1}], "fee": 0}],
        max_batch=2,
        budget_chaos=0,
        time_horizon_hours=24,
        capital_lock_time=1,
    )
    assert [entry["batch_size"] for entry in ladder] == [1]

def test_quote_outside_one_day_window_is_not_executable():
    now = datetime.now(timezone.utc)
    for observed_at in (
        (now - strategies._EXECUTION_QUOTE_MAX_AGE - strategies.timedelta(seconds=1)).isoformat(),
        (now + strategies.timedelta(seconds=1)).isoformat(),
    ):
        assert strategies._quote_info({"item": {
            "buy_levels": [{"price": 1, "quantity": 1}], "observed_at": observed_at,
            "confidence": 1, "source": "test",
        }}, "item", side="buy") is None
