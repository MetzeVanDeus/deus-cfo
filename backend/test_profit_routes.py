import asyncio
from datetime import datetime, timezone

import pytest

import main
import capital
import database
import portfolio
import strategies
from strategies import BatchPlan, ProfitRoute, TransformationRegistry, TransformationStrategyProvider


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

def test_primary_transformation_provider_applies_route_calibration_and_lifecycle():
    rows = {
        item: _record(item, price)
        for item, price in (("A", 10), ("Chaos", 1), ("B", 40), ("C", 4))
    }
    prices = {f"Currency:{item}": row for item, row in rows.items()}
    records = [
        _calibration_record(
            route_id="test-route", family="test", entry=1.2, exit=.8,
            duration=1.5, patch=None,
        )
        for _ in range(3)
    ]
    route = TransformationStrategyProvider(_registry()).evaluate({
        "league": "Test", "prices": prices, "price_records": prices,
        "route_execution_records": records,
    })[0]
    assert route.calibration["scope"] == "exact_route"
    assert route.calibration["baseline"]["batch_count"] == 1
    assert route.total_input_cost > route.calibration["baseline"]["cost_chaos"]
    assert route.realistic_output_value < 30
    assert route.capital_lock_time > 3
    assert route.active_execution_time == 2
    assert route.verification_metadata["strategy_lifecycle"] == "Validated"


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
    assert set(response) == {
        "league", "category", "poe_patch", "patch_status", "patch_reasons",
        "planning", "deterministic_readiness", "sections", "routes",
    }
    assert response["league"] == "Test"
    assert response["category"] == "Currency"
    assert response["routes"][0]["transformation_id"] == "test-route"
    assert response["routes"][0]["source"] == "test-market"
    assert response["routes"][0]["verified_version"] == "v1"
    assert response["deterministic_readiness"]["families"]["assembly"]["state"] == "unsupported_empty"
    assert response["deterministic_readiness"]["families"]["vendor"]["accepted_count"] == 0
    assert response["routes"][0]["execution_steps"] == []


def test_profit_routes_normalizes_divine_budget_and_fails_closed_without_rate(monkeypatch):
    rows = {"Currency": [_record("Divine", 100)]}

    async def latest(_league):
        return rows

    async def no_records(*_args, **_kwargs):
        return []

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.portfolio, "route_execution_records", no_records)
    converted = asyncio.run(main.get_profit_routes(
        "Test", category="Currency", budget_amount=2, budget_currency="Divine",
    ))
    assert converted["planning"]["budget_chaos"] == 200
    assert converted["planning"]["rate_provenance"]["source"] == "test-market"
    assert converted["planning"]["rate_provenance"]["max_age_hours"] == 24

    rows["Currency"][0]["observed_at"] = "2000-01-01T00:00:00+00:00"
    blocked = asyncio.run(main.get_profit_routes(
        "Test", category="Currency", budget_amount=2, budget_currency="Divine",
    ))
    assert blocked["planning"]["budget_chaos"] is None
    assert "older than 24 hours" in blocked["planning"]["normalization_blocker"]
    best = next(section for section in blocked["sections"] if section["key"] == "best_actionable")
    assert best["reason"].startswith("WAIT:")


def test_profit_routes_backend_filters_ranks_and_sections(monkeypatch):
    async def latest(_league):
        return {"Currency": [_record("Divine", 100)]}

    async def no_records(*_args, **_kwargs):
        return []

    first = _phase4_route()
    first.confidence = .8
    second_plan = first.batch_plan.model_copy(update={
        "executable_revenue_chaos": 23,
        "executable_net_chaos": 1,
    })
    second = first.model_copy(update={
        "transformation_id": "route-b", "name": "Route B",
        "safe_edge_chaos": 1, "safe_edge_ratio": .1,
        "roi_per_lock_hour": .05, "confidence": .5,
        "batch_plan": second_plan,
    })

    class EmptyDeferred:
        def evaluate(self, _context):
            return []

        def readiness(self, _context, *, routes):
            return {"families": {}}

    monkeypatch.setattr(main.market_data, "get_all_latest", latest)
    monkeypatch.setattr(main.portfolio, "route_execution_records", no_records)
    monkeypatch.setattr(
        main.strategies.TransformationStrategyProvider,
        "evaluate",
        lambda _self, _context: [second, first],
    )
    monkeypatch.setattr(main.strategies, "default_deferred_strategy_provider", EmptyDeferred)
    response = asyncio.run(main.get_profit_routes(
        "Test", category="Currency", minimum_roi_percent=15,
        family="deterministic", lifecycle="Experimental",
        deterministic_only=True, sort="safe_profit_per_active_hour",
    ))
    assert [route["transformation_id"] for route in response["routes"]] == ["route-a"]
    route = response["routes"][0]
    assert route["section"] == "best_actionable"
    assert route["ranking"]["safe_profit_per_active_hour"] == pytest.approx(4.8)
    assert route["ranking"]["divine_per_hour"] == pytest.approx(.06)
    assert response["planning"]["applied_filters"]["minimum_roi_percent"] == 15


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

def _phase4_route() -> ProfitRoute:
    return ProfitRoute(
        transformation_id="route-a",
        name="Route A",
        strategy_family="deterministic_test",
        status="executable",
        league="Test",
        total_input_cost=10,
        realistic_output_value=12,
        gross_profit=2,
        expected_net_profit=2,
        executable_net_profit=2,
        roi=.2,
        executable_roi=.2,
        capital_required=10,
        capacity=2,
        capacity_units="batches",
        active_execution_time=1,
        capital_lock_time=2,
        elapsed_cycle_time=2,
        profit_per_active_hour=2,
        roi_per_lock_hour=.1,
        budget_capacity=2,
        recommended_capacity=2,
        market_capacity=2,
        safe_edge_chaos=2,
        safe_edge_ratio=.2,
        liquidity={"tier": "medium", "volume": 100},
        verified_version="v1",
        certainty=strategies.RouteCertainty.DETERMINISTIC,
        poe_patch="3.29",
        inputs=[{"item": "A"}],
        outputs=[{"item": "B"}],
        batch_plan=BatchPlan(
            budget_chaos=25,
            set_count=2,
            exact_cards_to_buy=0,
            expected_outcomes=[],
            executable_cost_chaos=22,
            executable_revenue_chaos=28,
            executable_net_chaos=6,
            minimum_target_sale_chaos=22,
            active_effort_hours=1,
            lock_time_min_hours=1,
            lock_time_max_hours=2,
            maximum_recommended_batch=2,
            binding_constraint="market_depth",
        ),
    )


def _completed_route_record(*, profit=2, version="v1", league="Test", invalid=False):
    return {
        "status": "invalidated" if invalid else "completed",
        "opportunity_id": "route-a",
        "league": league,
        "route_version": version,
        "poe_patch": "3.29",
        "actual_cost_chaos": 10,
        "actual_revenue_chaos": 10 + profit,
        "actual_duration_hours": 3,
        "batch_count": 1,
    }


def _calibration_record(
    route_id="route-a", family="deterministic_test", *, entry=1.2, exit=.8,
    duration=1.5, league="Test", version="v1", patch="3.29",
):
    return {
        "status": "completed", "opportunity_id": route_id, "league": league,
        "route_version": version, "poe_patch": patch,
        "actual_cost_chaos": 10 * entry, "actual_revenue_chaos": 20 * exit,
        "actual_duration_hours": 2 * duration,
        "predicted_cost_chaos": 11, "predicted_revenue_chaos": 18,
        "predicted_duration_hours": 3,
        "route_snapshot": {"route": {
            "transformation_id": route_id,
            "strategy_family": family,
            "calibration": {
                "applied": True,
                "factors": {"entry": 1.1, "exit": .9, "duration": 1.5},
                "baseline": {
                    "batch_count": 1, "cost_chaos": 10,
                    "revenue_chaos": 20, "lock_time_hours": 2,
                },
            },
        }},
    }


def test_route_execution_calibration_is_robust_bounded_and_non_compounding():
    records = [
        _calibration_record(entry=1.2, exit=.8, duration=1.5),
        _calibration_record(entry=1.2, exit=.8, duration=1.5),
        _calibration_record(entry=10, exit=.1, duration=20),
        _calibration_record(league="Other"),
        _calibration_record(version="v2"),
        _calibration_record(patch="3.30"),
    ]
    calibration = strategies.route_execution_calibration(
        route_id="route-a", strategy_family="deterministic_test",
        league="Test", route_version_value="v1", poe_patch="3.29",
        records=records,
    )
    assert calibration["scope"] == "exact_route"
    assert calibration["sample_size"] == 3
    assert calibration["observed_medians"] == pytest.approx(
        {"entry": 1.2, "exit": .8, "duration": 1.5}
    )
    assert calibration["factors"] == pytest.approx(
        {"entry": 1.1, "exit": .9, "duration": 1.25}
    )


def test_route_execution_calibration_uses_independent_family_strength_and_exact_tie():
    exact = [_calibration_record() for _ in range(2)]
    peers = [_calibration_record(route_id=f"peer-{index}", entry=1.4) for index in range(5)]
    family = strategies.route_execution_calibration(
        route_id="route-a", strategy_family="deterministic_test",
        league="Test", route_version_value="v1", poe_patch="3.29",
        records=[*exact, *peers],
    )
    assert family["scope"] == "strategy_family"
    assert family["family_sample_size"] == 5
    tied = strategies.route_execution_calibration(
        route_id="route-a", strategy_family="deterministic_test",
        league="Test", route_version_value="v1", poe_patch="3.29",
        records=[*[_calibration_record() for _ in range(5)], *peers],
    )
    assert tied["scope"] == "exact_route"
    sparse = strategies.route_execution_calibration(
        route_id="route-a", strategy_family="deterministic_test",
        league="Test", route_version_value="v1", poe_patch="3.29",
        records=[_calibration_record()],
    )
    assert sparse["applied"] is False
    assert "needs 2 completed" in sparse["fallback_reason"]


def test_calibration_factors_reduce_batch_economics_before_budget_and_horizon():
    ladder = strategies.evaluate_deterministic_batch_ladder(
        inputs=[{"quantity": 1}], conversion_costs=[], outputs=[{"quantity": 1}],
        input_quotes=[{"levels": [{"price": 10, "quantity": 2}], "fee": 0}],
        cost_quotes=[],
        output_quotes=[{"levels": [{"price": 20, "quantity": 2}], "fee": 0}],
        max_batch=2, budget_chaos=22, time_horizon_hours=3,
        capital_lock_time=2.5, entry_calibration_factor=1.1,
        exit_calibration_factor=.8,
    )
    assert len(ladder) == 1
    assert ladder[0]["baseline_cost_chaos"] == 10
    assert ladder[0]["baseline_revenue_chaos"] == 20
    assert ladder[0]["input_cost_chaos"] == pytest.approx(11)
    assert ladder[0]["executable_output_chaos"] == pytest.approx(16)
    assert ladder[0]["safe_net_chaos"] == pytest.approx(5)

    reconciled = strategies.evaluate_deterministic_batch_ladder(
        inputs=[{"quantity": 1}], conversion_costs=[], outputs=[{"quantity": 1}],
        input_quotes=[{"levels": [{"price": 10, "quantity": 1}], "fee": .1}],
        cost_quotes=[],
        output_quotes=[{"levels": [{"price": 30, "quantity": 1}], "fee": .1}],
        max_batch=1, budget_chaos=0, time_horizon_hours=3,
        capital_lock_time=1, sale_fee_rate=.1, output_discount_rate=.1,
        friction_chaos=1, execution_bias_rate=.05,
        entry_calibration_factor=1.1, exit_calibration_factor=.9,
    )[0]
    adjustments = reconciled["adjustments"]
    rebuilt_net = (
        adjustments["raw_output_fill_chaos"]
        - adjustments["raw_input_fill_chaos"]
        - adjustments["explicit_fees_chaos"]
        - adjustments["execution_bias_chaos"]
        - adjustments["friction_chaos"]
        - adjustments["output_discount_chaos"]
        - adjustments["calibration_entry_chaos"]
        - adjustments["calibration_exit_chaos"]
    )
    assert rebuilt_net == pytest.approx(reconciled["safe_net_chaos"])


def test_route_evidence_uses_exact_completed_identity_and_preserves_observed_zero():
    route = _phase4_route()
    evidence = strategies.route_allocator_evidence(route, [
        _completed_route_record(profit=0),
        _completed_route_record(version="other"),
        _completed_route_record(league="Other"),
        _completed_route_record(invalid=True),
    ])
    assert evidence["sample_size"] == 1
    assert evidence["mean_return_percent"] == 0
    assert evidence["tier"] == "REJECTED"
    candidate = route.to_investable(chaos_per_divine=100, evidence=evidence)
    assert candidate.expected_return == 0
    assert candidate.downside_percentile == 0
    short = _completed_route_record()
    short["actual_duration_hours"] = 1
    long = _completed_route_record()
    long["actual_duration_hours"] = 23
    assert strategies.route_allocator_evidence(
        route, [short, long]
    )["median_duration_hours"] == 12
    assert candidate.upside_percentile == 0


def test_route_shared_gate_and_exact_cumulative_capital_units():
    route = _phase4_route()
    fresh = strategies.route_allocator_evidence(route, [])
    assert fresh["tier"] == "WATCH"
    fresh_candidate = route.to_investable(
        status="Validated", chaos_per_divine=100, evidence=fresh
    )
    fresh_plan = capital.build_capital_plan(
        capital.Bankroll(total_net_worth=10, liquid_currency=10),
        capital.InvestmentPreferences(),
        [fresh_candidate],
        mode="PAPER",
        chaos_per_divine=100,
        simulations=5,
    )
    assert fresh_candidate.metadata["certainty"] == "DETERMINISTIC"
    assert fresh_plan.positions == []
    assert fresh["rejection_reasons"] == ["missing_empirical_distribution"]
    observed = strategies.route_allocator_evidence(
        route, [_completed_route_record() for _ in range(20)]
    )
    assert observed["tier"] == "A"
    assert observed["eligible"] is True
    candidate = route.to_investable(
        status="Validated", chaos_per_divine=100, evidence=observed
    )
    assert candidate.minimum_capital == pytest.approx(.22)
    assert candidate.opportunity_capacity == pytest.approx(.22)
    assert candidate.maximum_reasonable_capital == pytest.approx(.22)
    assert candidate.expected_roi_per_lock_hour == pytest.approx(.2 / 3)
    assert candidate.rejection_reason is None
    plan = capital.build_capital_plan(
        capital.Bankroll(total_net_worth=10, liquid_currency=10),
        capital.InvestmentPreferences(),
        [candidate],
        mode="PAPER",
        chaos_per_divine=100,
        simulations=5,
    )
    assert plan.positions[0].estimated_quantity == 1
    assert plan.positions[0].capital == pytest.approx(.22)
    assert plan.positions[0].capital <= candidate.opportunity_capacity


def test_route_capture_completion_correction_and_invalidation_preserve_totals(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "route-journal.db"))
    database._schema_path = None
    route = _phase4_route()
    snapshot = {"route": route.model_dump(mode="json"), "planner": {"league": "Test"}}

    async def run():
        captured = await portfolio.capture_route_execution(
            opportunity_id=route.transformation_id,
            league="Test",
            route_version="v1",
            poe_patch="3.29",
            quantity_unit="batches",
            route_snapshot=snapshot,
            route_snapshot_id="a" * 64,
            execution_kind="paper",
            batch_count=2,
            predicted_cost_chaos=22,
            predicted_revenue_chaos=28,
            predicted_duration_hours=2,
        )
        assert captured["status"] == "pending"
        assert captured["predicted_cost_chaos"] == 22
        assert strategies.route_allocator_evidence(route, [captured])["sample_size"] == 0
        assert await portfolio.manual_trade_records() == []
        with pytest.raises(ValueError, match="positive"):
            await portfolio.complete_route_execution(
                captured["id"],
                actual_cost_chaos=float("nan"),
                actual_revenue_chaos=0,
                actual_duration_hours=4,
            )
        with pytest.raises(ValueError, match="before"):
            await portfolio.complete_route_execution(
                captured["id"],
                actual_cost_chaos=24,
                actual_revenue_chaos=0,
                actual_duration_hours=4,
                completed_at="2000-01-01T00:00:00+00:00",
            )
        with pytest.raises(ValueError, match="future"):
            await portfolio.complete_route_execution(
                captured["id"],
                actual_cost_chaos=24,
                actual_revenue_chaos=0,
                actual_duration_hours=4,
                completed_at="2999-01-01T00:00:00+00:00",
            )
        completed = await portfolio.complete_route_execution(
            captured["id"],
            actual_cost_chaos=24,
            actual_revenue_chaos=0,
            actual_duration_hours=4,
        )
        assert completed["status"] == "completed"
        assert completed["realized_profit"] == -24
        assert completed["actual_revenue_chaos"] == 0
        corrected = await portfolio.correct_route_execution(
            captured["id"],
            actual_cost_chaos=20,
            actual_revenue_chaos=30,
            actual_duration_hours=3,
        )
        assert corrected["realized_profit"] == 10
        invalidated = await portfolio.invalidate_route_execution(captured["id"], "entry was test data")
        assert invalidated["status"] == "invalidated"
        assert strategies.route_allocator_evidence(route, [invalidated])["sample_size"] == 0
        assert invalidated["completed_at"] is not None
        pending = await portfolio.capture_route_execution(
            opportunity_id=route.transformation_id,
            league="Test",
            route_version="v1",
            poe_patch="3.29",
            quantity_unit="batches",
            route_snapshot=snapshot,
            route_snapshot_id="b" * 64,
            execution_kind="paper",
            batch_count=2,
            predicted_cost_chaos=22,
            predicted_revenue_chaos=28,
            predicted_duration_hours=2,
        )
        invalid_pending = await portfolio.invalidate_route_execution(pending["id"], "cancelled")
        assert invalid_pending["completed_at"] is None

    asyncio.run(run())


def test_route_snapshot_hash_excludes_journal_state():
    route = _phase4_route()
    planner = main._route_planner_capture(
        league="Test",
        category=None,
        budget_amount=25,
        budget_currency="Chaos",
        horizon_hours=24,
        minimum_safe_profit_chaos=1,
        execution_bias_percent=2,
        minimum_roi_percent=None,
        maximum_active_effort_hours=None,
        maximum_lock_time_hours=None,
        family=None,
        lifecycle=None,
        deterministic_only=False,
        sort="safe_profit_per_active_hour",
    )
    before = main._route_snapshot_id(main._route_capture(route, planner))
    assert main._route_snapshot_id(main._route_capture(route, planner)) == before
    assert "allocator_evidence" not in main._route_capture(route, planner)["route"]
    enriched = route.model_dump(mode="json")
    enriched["actual_net_profit"] = 7
    reconstructed = main._route_from_payload(enriched)
    assert main._route_snapshot_id(main._route_capture(reconstructed, planner)) == before
