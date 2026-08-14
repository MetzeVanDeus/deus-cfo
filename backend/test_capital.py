from datetime import datetime, timedelta, timezone
from capital import Bankroll, InvestmentPreferences, build_capital_plan, simulate_portfolio

from opportunity import InvestableOpportunity, Opportunity, normalize_opportunity
from portfolio import calibrate_probability


def make_opp(name, *, category="scarab", group=None, capacity=100, expires=None, downside=-5, effort=0):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return InvestableOpportunity(
        id=name,
        strategy_type="anomaly",
        entry_item=name,
        category=category,
        current_price=1,
        realistic_entry_price=1,
        realistic_exit_price=1.2,
        expected_return=20,
        expected_profit_per_unit=.2,
        win_probability=.8,
        expected_duration=3,
        duration_distribution=[2, 3, 5],
        downside_percentile=downside,
        historical_sample_size=100,
        confidence=.9,
        liquidity={"tier": "high", "volume": 1000},
        execution_effort=effort,
        minimum_capital=1,
        maximum_reasonable_capital=capacity,
        opportunity_capacity=capacity,
        correlation_group=group or name,
        created_at=now.isoformat(),
        last_validated_at=now.isoformat(),
        expected_half_life=24,
        expires_at=(expires or now + timedelta(hours=24)).isoformat(),
        historical_returns=[-5, 10, 20, 30],
        tier="A",
    )


def test_reserve_and_single_position_are_hard_limits():
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=.2, max_single_position_percent=.1),
        [make_opp("a")], mode="PAPER", now=datetime(2026, 1, 1, tzinfo=timezone.utc), simulations=25, chaos_per_divine=200,
    )
    assert plan.reserve >= 20
    assert plan.deployed <= 10
    assert plan.reserve + plan.deployed + plan.unallocated == 100


def test_category_and_correlated_exposure_limits():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prefs = InvestmentPreferences(
        minimum_reserve_percent=0, max_single_position_percent=.5,
        max_category_exposure_percent=.2, max_correlated_exposure_percent=.25,
    )
    same_category = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100), prefs,
        [make_opp("a", category="scarab"), make_opp("b", category="scarab")],
        mode="PAPER", now=now, simulations=25, chaos_per_divine=200,
    )
    assert sum(p.capital for p in same_category.positions) <= 20
    same_group = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100), prefs,
        [make_opp("a", category="scarab", group="event"), make_opp("b", category="essence", group="event")],
        mode="PAPER", now=now, simulations=25, chaos_per_divine=200,
    )
    assert sum(p.capital for p in same_group.positions) <= 25


def test_bootstrap_is_deterministic_and_expiration_waits():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = make_opp("a", expires=now - timedelta(seconds=1))
    plan = build_capital_plan(
        Bankroll(total_net_worth=50, liquid_currency=50), InvestmentPreferences(), [item],
        mode="PAPER", now=now, seed=7, simulations=100, chaos_per_divine=200,
    )
    assert plan.recommendation == "WAIT"
    assert plan.rejected["a"] == "expired_or_stale"

    live = make_opp("live")
    positions = build_capital_plan(
        Bankroll(total_net_worth=50, liquid_currency=50), InvestmentPreferences(), [live],
        mode="PAPER", now=now, seed=7, simulations=100, chaos_per_divine=200,
    ).positions
    first = simulate_portfolio(positions, [live], seed=123, trials=100)
    second = simulate_portfolio(positions, [live], seed=123, trials=100)
    assert first == second


def test_empty_or_observe_mode_never_fabricates_positions():
    plan = build_capital_plan(
        Bankroll(total_net_worth=50, liquid_currency=50), InvestmentPreferences(), [], mode="OBSERVE", simulations=10,
    )
    assert plan.recommendation == "WAIT"
    assert plan.positions == []
    assert plan.deployed == 0


def test_each_position_uses_its_own_downside_cap():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(
            minimum_reserve_percent=0, max_single_position_percent=1,
            max_category_exposure_percent=1, max_correlated_exposure_percent=1,
        ),
        [make_opp("low-risk", category="a", downside=-2),
         make_opp("high-risk", category="b", downside=-20)],
        mode="PAPER", now=now, simulations=10, chaos_per_divine=200,
    )
    amounts = {position.opportunity_id: position.capital for position in plan.positions}
    assert amounts["low-risk"] > amounts["high-risk"]
    assert amounts["high-risk"] <= 100 * .10 / .20


def test_observe_mode_keeps_setups_as_watchlist_without_allocating():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [make_opp("setup")], mode="OBSERVE", now=now, simulations=10, chaos_per_divine=200,
    )
    assert plan.recommendation == "WAIT"
    assert plan.positions == []
    assert plan.deployed == 0
    assert plan.simulation.capital_locked == 0
    assert [watch.opportunity_id for watch in plan.watchlist] == ["setup"]


def test_zero_advanced_caps_are_not_treated_as_unset():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bankroll = Bankroll(total_net_worth=100, liquid_currency=100)
    assert not build_capital_plan(
        bankroll,
        InvestmentPreferences(minimum_reserve_percent=0, max_category_exposure_amount=0),
        [make_opp("category-zero")], mode="PAPER", now=now, simulations=10, chaos_per_divine=200,
    ).positions
    assert not build_capital_plan(
        bankroll,
        InvestmentPreferences(minimum_reserve_percent=0, max_correlated_exposure_amount=0),
        [make_opp("group-zero")], mode="PAPER", now=now, simulations=10, chaos_per_divine=200,
    ).positions
    assert not build_capital_plan(
        bankroll,
        InvestmentPreferences(minimum_reserve_percent=0, max_execution_effort=0),
        [make_opp("effort-zero", effort=1)], mode="PAPER", now=now, simulations=10, chaos_per_divine=200,
    ).positions


def test_missing_empirical_distribution_cannot_deploy_or_claim_certainty():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = make_opp("missing-distribution")
    item.historical_returns = []
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [item], mode="PAPER", now=now, simulations=25, chaos_per_divine=200,
    )
    assert plan.recommendation == "WAIT"
    assert plan.positions == []
    assert plan.deployed == 0
    assert plan.simulation.probability_profitable == 0
    assert plan.rejected[item.id] == "missing_empirical_distribution"


def test_experimental_lifecycle_is_paper_only_and_capped():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    experimental = make_opp("experimental")
    experimental.strategy_status = "Experimental"
    paper = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [experimental], mode="PAPER", now=now, simulations=10, chaos_per_divine=200,
    )
    assert paper.recommendation == "DEPLOY"
    assert paper.deployed <= 2
    live = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [experimental], mode="LIVE-CANDIDATE", now=now, simulations=10, chaos_per_divine=200,
    )
    assert live.positions == []
    assert live.recommendation == "WAIT"


def test_normalization_converts_chaos_capacity_to_divines():
    raw = Opportunity(
        type="anomaly", detector_id="test", item_id="item", item_name="Item",
        category="Currency", league="Allflame", what_happened="", why_it_matters="",
        possible_action="", confidence=.9, signals={},
        historical_context={"return_samples": [10], "duration_samples": [6]},
        timestamp="2026-01-01T00:00:00+00:00", expected_return=10,
        win_probability=.7, downside_percentile=-5, sample_size=20,
        historical_confidence=1.0, theoretical_price=1, realistic_entry=1,
        realistic_exit=1.2, realistic_profit=0.1, estimated_time=6,
        liquidity={"tier": "high", "volume": 40000},
    )
    normalized = normalize_opportunity(raw, chaos_per_divine=200)
    assert normalized.opportunity_capacity == 10
    assert normalized.minimum_capital == .005
    assert normalized.expected_profit_per_unit == .0005
    assert normalized.expected_profit_per_divine_hour == .01666667


def test_calibration_is_sample_gated_and_shrunk_toward_raw_probability():
    overconfident = [{"confidence": .8, "profitable": i < 2} for i in range(20)]
    result = calibrate_probability(.8, overconfident)
    assert result["bucket"] == "80–90%"
    assert result["applied"] is True
    assert result["calibrated"] == .45
    assert .1 < result["calibrated"] < .8
    assert calibrate_probability(.8, overconfident[:19])["calibrated"] == .8

    underconfident = [{"confidence": .4, "profitable": i < 18} for i in range(20)]
    assert calibrate_probability(.4, underconfident)["calibrated"] == .65


def test_allocation_exposes_and_consumes_calibrated_probability():
    item = make_opp("calibrated")
    records = [{"confidence": .8, "profitable": i < 2} for i in range(20)]
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [item],
        mode="PAPER",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        simulations=5,
        chaos_per_divine=200,
        calibration_records=records,
    )
    position = plan.positions[0]
    assert position.probability_profitable == .45
    assert position.raw_probability_profitable == .8
    assert position.calibration["applied"] is True
    assert plan.calibration_summary["applied_positions"] == 1

def test_calibrated_probability_changes_allocation_ranking():
    poor = make_opp("poor", category="scarab")
    good = make_opp("good", category="essence")
    good.win_probability = .7
    records = (
        [{"confidence": .8, "profitable": i < 2} for i in range(20)]
        + [{"confidence": .7, "profitable": i < 18} for i in range(20)]
    )
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [poor, good],
        mode="PAPER",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        simulations=5,
        chaos_per_divine=200,
        calibration_records=records,
    )
    assert [position.opportunity_id for position in plan.positions] == ["good", "poor"]
    assert plan.positions[0].probability_profitable == .8
    assert plan.positions[1].probability_profitable == .45

def test_sparse_calibration_preserves_score_ordering():
    low_score = make_opp("low-score", category="scarab")
    low_score.expected_return = 5
    higher_score = make_opp("higher-score", category="essence")
    plan = build_capital_plan(
        Bankroll(total_net_worth=100, liquid_currency=100),
        InvestmentPreferences(minimum_reserve_percent=0),
        [low_score, higher_score],
        mode="PAPER",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        simulations=5,
        chaos_per_divine=200,
        calibration_records=[],
    )
    assert [position.opportunity_id for position in plan.positions] == ["higher-score", "low-score"]
def test_reconstructed_evidence_is_paper_only_and_capped():
    raw = Opportunity(
        type="regime", detector_id="Trending Down", item_id="reconstructed",
        item_name="Reconstructed", category="Scarab", league="Test",
        what_happened="", why_it_matters="", possible_action="", confidence=.7,
        signals={}, historical_context={
            "data_points": 16,
            "return_samples": [3] * 20,
            "evidence_sources": {"observed": 1, "poe.ninja_sparkline_reconstructed": 20},
            "reconstructed_sample_size": 20,
            "return_estimator": "median",
        },
        timestamp="2026-01-01T00:00:00+00:00", expected_return=3,
        win_probability=.55, median_return=3, downside_percentile=-1,
        sample_size=20, historical_confidence=.4, theoretical_price=1,
        realistic_entry=1, realistic_exit=1.03, realistic_profit=.02,
        liquidity={"tier": "high", "volume": 1000},
    )
    paper = normalize_opportunity(raw, chaos_per_divine=200, paper_only=True)
    live = normalize_opportunity(raw, chaos_per_divine=200)
    assert paper.tier == "B"
    assert paper.metadata["paper_only_reconstructed"] is True
    assert paper.metadata["direct_observation"] is True
    assert paper.metadata["reconstruction_dependent"] is True
    assert live.tier == "REJECTED"
    paper_plan = build_capital_plan(
        Bankroll(total_net_worth=60, liquid_currency=55),
        InvestmentPreferences.preset("high"), [paper], mode="PAPER",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc), simulations=5,
        chaos_per_divine=200,
    )
    assert paper_plan.recommendation == "WAIT"
    assert not paper_plan.positions
    expensive = paper.model_copy(update={"id": "expensive", "minimum_capital": 2})
    expensive_plan = build_capital_plan(
        Bankroll(total_net_worth=60, liquid_currency=55),
        InvestmentPreferences.preset("high"), [expensive], mode="PAPER",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc), simulations=5,
        chaos_per_divine=200,
    )
    assert expensive_plan.recommendation == "WAIT"
    assert not expensive_plan.positions
    assert expensive_plan.rejected["expensive"] == "missing_empirical_distribution"
    live_plan = build_capital_plan(
        Bankroll(total_net_worth=60, liquid_currency=55),
        InvestmentPreferences.preset("high"), [live], mode="LIVE-CANDIDATE",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc), simulations=5,
        chaos_per_divine=200,
    )
    assert live_plan.recommendation == "WAIT"
    assert not live_plan.positions
def test_aggressive_paper_increases_reconstructed_size_and_uses_units():
    item = make_opp("aggressive")
    item.tier = "B"
    item.confidence = .45
    item.metadata = {
        "reconstruction_dependent": True,
        "paper_only_reconstructed": True,
        "reconstructed_sample_size": 31,
    }
    bankroll = Bankroll(total_net_worth=60, liquid_currency=55)
    prefs = InvestmentPreferences(
        risk_tolerance="high", desired_horizon_hours=24, minimum_liquidity="low",
        maximum_effort="high", minimum_reserve_percent=0,
        max_single_position_percent=.40, max_category_exposure_percent=.60,
        max_correlated_exposure_percent=.50,
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    paper = build_capital_plan(
        bankroll, prefs, [item], mode="PAPER", now=now, simulations=5, chaos_per_divine=200,
    )
    aggressive = build_capital_plan(
        bankroll, prefs, [item], mode="AGGRESSIVE-PAPER", now=now, simulations=5, chaos_per_divine=200,
    )
    assert paper.recommendation == "DEPLOY"
    assert aggressive.mode == "AGGRESSIVE-PAPER"
    assert aggressive.deployed > paper.deployed
    assert isinstance(aggressive.positions[0].estimated_quantity, int)