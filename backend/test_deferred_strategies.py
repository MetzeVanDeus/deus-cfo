import asyncio

import pytest

import main
from strategies import (
    ArbitrageGraphStrategyProvider,
    AssemblyStrategyProvider,
    AssemblyTransformationRegistry,
    DeterministicSixLinkStrategyProvider,
    SixLinkRegistry,
    VendorTransformationRegistry,
)


def row(item, price, *, volume=100, grade="A"):
    return {
        "item_id": item,
        "item_name": item,
        "price_chaos": price,
        "volume": volume,
        "source": "verified-market",
        "confidence_grade": grade,
        "observed_at": "2026-08-16T00:00:00Z",
    }


def context(*pairs, category=None):
    records = {key: row(key, price, grade=grade) for key, price, grade in pairs}
    return {
        "prices": records,
        "price_records": records,
        "category": category,
        "league": "Test",
        "chaos_per_divine": 100,
        "active_poe_patch": "3.29.0",
    }


def assembly_record(direction="both"):
    return {
        "id": "parts-to-whole",
        "name": "Parts to whole",
        "category": "Assembly",
        "parts": [
            {"item": "Part", "market_key": "Fragment:Part", "quantity": 3},
        ],
        "whole": [{"item": "Whole", "market_key": "Fragment:Whole", "quantity": 1}],
        "direction": direction,
        "friction_chaos": 0.5,
        "source": "verified-registry",
        "verified_version": "3.29.0-1",
        "max_batch": 4,
    }


def vendor_record(identifier, source_item, target_item, *, cost=0):
    return {
        "id": identifier,
        "name": identifier,
        "category": "VendorTransformation",
        "inputs": [{"item": source_item, "market_key": f"Currency:{source_item}", "quantity": 1}],
        "outputs": [{"item": target_item, "market_key": f"Currency:{target_item}", "quantity": 1}],
        "conversion_costs": ([{"item": "Fee", "market_key": "Currency:Fee", "quantity": cost}] if cost else []),
        "source": "verified-vendor-registry",
        "verified_version": "3.29.0-1",
    }


def test_assembly_checks_both_directions_and_full_friction_cost():
    registry = AssemblyTransformationRegistry([assembly_record()])
    routes = AssemblyStrategyProvider(registry).evaluate(context(
        ("Fragment:Part", 2, "A"), ("Fragment:Whole", 20, "A"),
    ))
    assert {route.transformation_id for route in routes} == {"parts-to-whole", "parts-to-whole:disassemble"}
    assembly = next(route for route in routes if route.transformation_id == "parts-to-whole")
    assert assembly.total_input_cost == pytest.approx(6.5)
    assert assembly.expected_net_profit == pytest.approx(13.5)
    assert assembly.verification_metadata["market_keys"] == ["Fragment:Part", "Fragment:Whole"]


def test_vendor_graph_is_bounded_and_loop_free_with_all_edge_costs():
    vendor = VendorTransformationRegistry([
        vendor_record("a-to-b", "A", "B", cost=1),
        vendor_record("b-to-c", "B", "C", cost=2),
        vendor_record("c-to-a", "C", "A"),
        vendor_record("c-to-d", "C", "D"),
    ])
    prices = context(
        ("Currency:A", 5, "A"), ("Currency:B", 8, "A"), ("Currency:C", 20, "A"),
        ("Currency:D", 30, "A"), ("Currency:Fee", 1, "A"),
    )
    routes = ArbitrageGraphStrategyProvider(vendor, max_edges=3, min_edges=2).evaluate(prices)
    paths = {tuple(route.verification_metadata["graph_edges"]) for route in routes}
    assert ("a-to-b", "b-to-c") in paths
    assert ("a-to-b", "b-to-c", "c-to-d") in paths
    assert ("a-to-b", "b-to-c", "c-to-a") not in paths
    assert not any(len(path) > 3 for path in paths)
    two = next(route for route in routes if route.verification_metadata["graph_edges"] == ["a-to-b", "b-to-c"])
    assert two.total_input_cost == pytest.approx(8)
    assert two.expected_net_profit == pytest.approx(12)


def test_graph_scales_fixed_ratios_for_a_short_chain():
    first = vendor_record("three-a-to-b", "A", "B")
    first["inputs"][0]["quantity"] = 3
    second = vendor_record("three-b-to-c", "B", "C")
    second["inputs"][0]["quantity"] = 3
    vendor = VendorTransformationRegistry([first, second])
    routes = ArbitrageGraphStrategyProvider(vendor, min_edges=2).evaluate(
        context(("Currency:A", 2, "A"), ("Currency:C", 30, "A"))
    )
    route = next(route for route in routes if len(route.verification_metadata["graph_edges"]) == 2)
    assert route.inputs[0]["quantity"] == 9
    assert route.outputs[0]["quantity"] == 1
    assert route.total_input_cost == pytest.approx(18)


def six_link_record():
    return {
        "id": "known-unique-six-link",
        "name": "Known unique six-link",
        "category": "SixLink",
        "item_id": "known-unique",
        "base": {"item": "Known Unique", "item_id": "known-unique", "market_key": "UniqueArmour:base", "quantity": 1},
        "linked": {"item": "Known Unique", "item_id": "known-unique", "market_key": "UniqueArmour:linked", "quantity": 1},
        "linking_costs": [{"item": "Orb", "market_key": "Currency:Orb", "quantity": 2}],
        "linking_method": "verified-fixed-link-method",
        "source": "verified-six-link-registry",
        "verified_version": "3.29.0-1",
        "manual_actions": ["apply_linking_method"],
    }


def test_six_link_requires_same_known_item_and_remains_manual_only():
    registry = SixLinkRegistry([six_link_record()])
    route = DeterministicSixLinkStrategyProvider(registry).evaluate(context(
        ("UniqueArmour:base", 10, "A"), ("UniqueArmour:linked", 30, "A"), ("Currency:Orb", 3, "A"),
        category="SixLink",
    ))[0]
    assert route.total_input_cost == pytest.approx(16)
    assert route.expected_net_profit == pytest.approx(14)
    assert route.status == "manual_only"
    assert DeterministicSixLinkStrategyProvider(registry).discover({**context(
        ("UniqueArmour:base", 10, "A"), ("UniqueArmour:linked", 30, "A"), ("Currency:Orb", 3, "A"),
    ), "bankroll": 100}) == []
    low = context(
        ("UniqueArmour:base", 10, "C"), ("UniqueArmour:linked", 30, "A"), ("Currency:Orb", 3, "A"),
    )
    assert DeterministicSixLinkStrategyProvider(registry).evaluate(low) == []
    with pytest.raises(ValueError, match="same item"):
        SixLinkRegistry([{**six_link_record(), "linked": {**six_link_record()["linked"], "item_id": "other"}}])


def test_six_link_is_manual_only_even_without_declared_manual_actions():
    registry = SixLinkRegistry([{**six_link_record(), "manual_actions": []}])
    provider = DeterministicSixLinkStrategyProvider(registry)
    route = provider.evaluate(context(
        ("UniqueArmour:base", 10, "A"), ("UniqueArmour:linked", 30, "A"), ("Currency:Orb", 3, "A"),
    ))[0]
    assert route.status == "manual_only"
    assert provider.discover({**context(
        ("UniqueArmour:base", 10, "A"), ("UniqueArmour:linked", 30, "A"), ("Currency:Orb", 3, "A"),
    ), "bankroll": 100}) == []


@pytest.mark.parametrize(("field", "first_value", "second_value"), [
    ("source", "verified-vendor-registry", "other-vendor-registry"),
    ("verified_version", "3.29.0-1", "3.29.0-2"),
    ("poe_patch", "3.29.0", "3.30.0"),
])
def test_graph_rejects_incompatible_edge_metadata(field, first_value, second_value):
    first = vendor_record("a-to-b", "A", "B")
    second = vendor_record("b-to-c", "B", "C")
    first[field] = first_value
    second[field] = second_value
    registry = VendorTransformationRegistry([first, second])
    assert ArbitrageGraphStrategyProvider(registry, min_edges=2).evaluate(
        context(("Currency:A", 5, "A"), ("Currency:C", 20, "A"))
    ) == []


def test_default_deferred_registries_fail_closed():
    provider = main.strategies.default_deferred_strategy_provider()
    assert provider.evaluate({"prices": {}, "price_records": {}}) == []
    assert provider.discover({"prices": {}, "price_records": {}, "bankroll": 100}) == []


def test_deferred_routes_are_wired_into_profit_routes_without_touching_div_cards(monkeypatch):
    async def latest(_league):
        return {"Currency": [row("Currency:A", 5), row("Currency:B", 20), row("Currency:Fee", 1)]}

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main, "resolve_active_poe_patch", lambda _league: asyncio.sleep(0, result="3.29.0"))
    provider = main.strategies.DeferredDeterministicStrategyProvider(
        vendor=VendorTransformationRegistry([vendor_record("a-to-b", "Currency:A", "Currency:B", cost=1)])
    )
    monkeypatch.setattr(main.strategies, "default_deferred_strategy_provider", lambda: provider)
    result = asyncio.run(main.get_profit_routes("Test", category="VendorTransformation"))
    assert any(route["transformation_id"] == "a-to-b" for route in result["routes"])
