import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import opportunity
import validation


def row(timestamp, price, volume=100, item_id="item", category="Currency"):
    return {
        "timestamp": timestamp.isoformat(),
        "league": "Test",
        "category": category,
        "item_id": item_id,
        "item_name": item_id,
        "price_chaos": price,
        "volume": volume,
    }


def test_historical_detector_ignores_rows_after_event():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [row(start, 100), row(start + timedelta(hours=1), 101)]
    rows.append(row(start + timedelta(hours=2), 160, 400))
    still_at_event = validation.detect_historical_signals(rows, rows[1]["timestamp"], 24)
    later = validation.detect_historical_signals(rows, rows[-1]["timestamp"], 24)

    assert not any(signal.get("regime") == "Demand Shock" for signal in still_at_event)
    assert any(signal.get("regime") == "Demand Shock" for signal in later)


def test_wilson_confidence_and_return_percentiles_are_standard():
    summary = validation.summarize_returns([10.0, -5.0, 10.0])

    assert summary["sample_size"] == 3
    assert summary["win_probability"] == pytest.approx(2 / 3)
    assert summary["median_return"] == 10.0
    assert summary["p10_return"] == pytest.approx(-2.0)
    assert summary["p90_return"] == pytest.approx(10.0)
    low, high = validation.wilson_interval(2, 3)
    assert summary["confidence_interval"] == [round(low, 6), round(high, 6)]
    assert summary["historical_confidence"] == round(low, 6)

def test_backtest_uses_forward_endpoint_only(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        row(start, 100),
        row(start + timedelta(hours=1), 80, 300),
        row(start + timedelta(hours=2), 88),
        row(start + timedelta(hours=3), 96),
    ]

    async def fake_load_rows(league, category=None):
        return rows

    monkeypatch.setattr(validation, "_load_rows", fake_load_rows)

    async def run():
        return await validation.backtest("Test", horizons="1")

    result = asyncio.run(run())
    assert result["horizons"] == [1.0]
    # The 1h outcome at the crashing event is measured at the next snapshot,
    # not from a present-time/latest price.
    crashing = next(group for group in result["groups"] if group["signal_type"] == "Crashing")
    assert crashing["horizons"]["1"]["sample_size"] == 1
    assert crashing["horizons"]["1"]["median_return"] == pytest.approx(10.0)


def test_sparse_endpoint_path_includes_observation_after_target():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        row(start, 100),
        row(start + timedelta(minutes=30), 110),
        row(start + timedelta(hours=2), 80),
        row(start + timedelta(hours=3), 140),
    ]
    outcome = validation._event_outcome(rows, rows[0], start + timedelta(hours=1))
    assert outcome["return"] == pytest.approx(-20)
    assert outcome["adverse"] == pytest.approx(-20)
    assert outcome["favorable"] == pytest.approx(10)
    assert outcome["end_timestamp"] == rows[2]["timestamp"]



def test_opportunity_filter_rejects_thin_market_and_requires_empirical_fields():
    from opportunity import Opportunity, filter_opportunities

    base = dict(
        type="anomaly", detector_id="price_drop", item_id="item",
        item_name="item", category="Currency", league="Test",
        what_happened="", why_it_matters="", possible_action="",
        confidence=0.9, signals={}, historical_context={"data_points": 2},
        timestamp="2026-01-01T00:00:00+00:00", expected_return=2,
        win_probability=.7, median_return=2, downside_percentile=-1,
        sample_size=20, historical_confidence=.6,
        theoretical_price=100, realistic_entry=103, realistic_exit=104,
        capital_required=103, realistic_profit=1, roi=1,
        estimated_time=6, profit_per_hour=.1,
        liquidity={"tier": "medium", "volume": 100, "slippage_pct": 3},
        risk="medium",
    )
    accepted, rejected = filter_opportunities([Opportunity(**base)])
    assert len(accepted) == 1
    assert rejected == {}
    thin = Opportunity(**{**base, "liquidity": {"tier": "low", "volume": 1}})
    accepted, rejected = filter_opportunities([thin])
    assert not accepted
    assert rejected["liquidity_below_threshold"] == 1
    thin.historical_context.update(
        return_samples=[2] * 20,
        duration_samples=[24] * 20,
    )
    normalized = thin.to_investable(chaos_per_divine=200)
    assert normalized.tier == "REJECTED"
    assert normalized.rejection_reason == "liquidity_below_threshold"


def test_opportunity_factories_use_requested_analysis_window(monkeypatch):
    latest = {
        "Currency": [
            {"category": "Currency", "item_id": item, "item_name": item,
             "price_chaos": 100, "volume": 100}
            for item in ("regime-item", "anomaly-item")
        ]
    }
    calls = []

    async def get_all_latest(_league):
        return latest

    async def get_rolling_stats(_league, _category, _item_id, hours):
        calls.append(hours)
        return {
            "median": 100, "min": 90, "max": 110, "percentile_rank": .5,
            "volume_median": 100, "count": 14 if hours == 168 else 1,
        }

    async def detect_regimes(_league, _category, _hours):
        return [{
            "regime": "Trending Up", "category": "Currency", "item_id": "regime-item",
            "confidence": .8, "signals": {}, "explanation": "",
        }]

    async def detect_anomalies(_league, _category, _hours):
        return [{
            "anomaly_type": "price_spike", "category": "Currency", "item_id": "anomaly-item",
            "item_name": "anomaly-item", "severity": .8, "z_score": 3,
            "percentile": 1, "volume_multiplier": 1, "price_current": 100,
            "price_median": 90, "explanation": "",
        }]

    async def attach_outcomes(opportunities, *, include_feedback=True):
        for item in opportunities:
            item.expected_return = 10
            item.win_probability = .8
            item.downside_percentile = -2
            item.sample_size = 5
            item.historical_confidence = .5
            item.historical_context["return_samples"] = [10] * 5
            item.historical_context["duration_samples"] = [24] * 5

    monkeypatch.setattr(opportunity.market_data, "get_all_latest", get_all_latest)
    monkeypatch.setattr(opportunity.market_data, "get_rolling_stats", get_rolling_stats)
    monkeypatch.setattr(opportunity.regime_mod, "detect_all_regimes", detect_regimes)
    monkeypatch.setattr(opportunity.anomaly_mod, "detect_anomalies", detect_anomalies)
    monkeypatch.setattr(opportunity, "_attach_historical_outcomes", attach_outcomes)

    async def run():
        detected = await opportunity.get_all_opportunities("Test", 168, include_feedback=False)
        signal = await opportunity.signal_to_opportunity({
            "source": "regime", "type": "Trending Up", "item": "signal-item",
            "category": "Currency", "confidence": .8,
        }, "Test", 168)
        return detected, signal

    detected, signal = asyncio.run(run())
    eligible, rejected = opportunity.filter_opportunities(detected)

    assert calls == [168, 168, 168]
    assert len(eligible) == 2
    assert rejected == {}
    assert all(item.historical_context["data_points"] == 14 for item in detected)
    assert signal.historical_context["data_points"] == 14


def test_execution_fields_apply_slippage_and_keep_heuristic_separate():
    from opportunity import Opportunity, _attach_execution_fields

    opp = Opportunity(
        type="anomaly", detector_id="price_drop", item_id="item",
        item_name="item", category="Currency", league="Test",
        what_happened="", why_it_matters="", possible_action="",
        confidence=.4, signals={}, historical_context={"data_points": 3},
        timestamp="2026-01-01T00:00:00+00:00", expected_return=10,
        downside_percentile=-2, sample_size=20, historical_confidence=.7,
    )
    _attach_execution_fields([opp], {("Currency", "item"): {"price_chaos": 100, "volume": 100}})
    assert opp.theoretical_price == 100
    assert opp.realistic_entry > opp.theoretical_price
    assert opp.realistic_profit > 0
    assert opp.confidence == .4


def test_strategy_conditions_are_declarative_and_reject_unknown_operators():
    with pytest.raises(ValueError):
        validation._match_condition(0.5, {"eval": "price > 0"}, "price_percentile")


def test_strategy_backtest_returns_category_and_period_stats(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        row(start, 100),
        row(start + timedelta(hours=1), 80, 300),
        row(start + timedelta(hours=2), 88),
        row(start + timedelta(hours=3), 96),
    ]

    async def fake_load_rows(league, category=None):
        return rows

    monkeypatch.setattr(validation, "_load_rows", fake_load_rows)

    async def run():
        return await validation.strategy_backtest(
            "Test", {"price_percentile": {"gte": 0}}, horizons="1"
        )

    result = asyncio.run(run())
    assert result["occurrences"] == 4
    horizon = result["horizon_results"]["1"]
    assert horizon["sample_size"] == 3
    assert horizon["best_period"]["return"] == pytest.approx(10.0)
    assert horizon["worst_period"]["return"] == pytest.approx(-20.0)
    assert result["category_performance"]["Currency"]["1"]["sample_size"] == 3


def test_positive_price_returns_never_breach_negative_100():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [row(start, 1), row(start + timedelta(hours=1), 29911), row(start + timedelta(hours=2), 2)]
    outcome = validation._event_outcome(rows, rows[1], start + timedelta(hours=2))
    assert outcome["return"] >= -100
    assert outcome["adverse"] >= -100
 
def test_historical_return_estimator_uses_median_for_reconstructed_only(monkeypatch):
    opp = opportunity.Opportunity(
        type="regime", detector_id="Trending Up", item_id="item", item_name="Item",
        category="Currency", league="Test", what_happened="", why_it_matters="",
        possible_action="", confidence=.8, signals={}, historical_context={},
        timestamp="2026-01-01T00:00:00+00:00",
    )
    result = {"groups": [{
        "category": "Currency", "source": "regime", "signal_type": "Trending Up",
        "horizons": {"24": {
            "sample_size": 3, "median_return": 2, "mean_return": 1000,
            "win_probability": .7, "p10_return": -1, "historical_confidence": .6,
            "return_samples": [2, 2, 1000], "evidence_sources": {"poe.ninja_sparkline_reconstructed": 3},
            "reconstructed_sample_size": 3,
        }},
    }]}
    async def fake_backtest(*args, **kwargs):
        return result
    monkeypatch.setattr(opportunity.validation, "backtest", fake_backtest)
    asyncio.run(opportunity._attach_historical_outcomes([opp]))
    assert opp.expected_return == 2
    assert opp.historical_context["return_estimator"] == "median"
    normalized = opp.to_investable(chaos_per_divine=100, paper_only=True)
    assert normalized.expected_return == 2
    assert normalized.metadata["return_estimator"] == "median"

def test_historical_outcome_does_not_let_empty_liquidity_bucket_win(monkeypatch):
    opp = opportunity.Opportunity(
        type="regime", detector_id="Trending Up", item_id="item", item_name="Item",
        category="Currency", league="Test", what_happened="", why_it_matters="",
        possible_action="", confidence=.8, signals={}, historical_context={},
        timestamp="2026-01-01T00:00:00+00:00",
    )
    summary = {
        "sample_size": 3, "median_return": 2, "mean_return": 2,
        "win_probability": 1, "p10_return": 2, "historical_confidence": .4,
        "return_samples": [1, 2, 3], "evidence_sources": {"observed": 3},
        "reconstructed_sample_size": 0,
    }
    result = {"groups": [
        {"category": "Currency", "source": "regime", "signal_type": "Trending Up",
         "horizons": {"24": summary}},
        {"category": "Currency", "source": "regime", "signal_type": "Trending Up",
         "horizons": {"24": {"sample_size": 0}}},
    ]}
    async def fake_backtest(*args, **kwargs):
        return result
    monkeypatch.setattr(opportunity.validation, "backtest", fake_backtest)
    asyncio.run(opportunity._attach_historical_outcomes([opp]))
    assert opp.expected_return == 2

def test_historical_return_estimator_keeps_mean_for_direct_observed(monkeypatch):
    opp = opportunity.Opportunity(
        type="regime", detector_id="Trending Up", item_id="item", item_name="Item",
        category="Currency", league="Test", what_happened="", why_it_matters="",
        possible_action="", confidence=.8, signals={}, historical_context={},
        timestamp="2026-01-01T00:00:00+00:00",
    )
    result = {"groups": [{
        "category": "Currency", "source": "regime", "signal_type": "Trending Up",
        "horizons": {"24": {
            "sample_size": 3, "median_return": 2, "mean_return": 1000,
            "win_probability": .7, "p10_return": -1, "historical_confidence": .6,
            "return_samples": [2, 2, 1000], "evidence_sources": {"observed": 3},
            "reconstructed_sample_size": 0,
        }},
    }]}
    async def fake_backtest(*args, **kwargs):
        return result
    monkeypatch.setattr(opportunity.validation, "backtest", fake_backtest)
    asyncio.run(opportunity._attach_historical_outcomes([opp]))
    assert opp.expected_return == 1000
    assert opp.historical_context["return_estimator"] == "mean"
 
def test_historical_return_estimator_uses_median_for_mixed_reconstruction(monkeypatch):
    opp = opportunity.Opportunity(
        type="regime", detector_id="Trending Up", item_id="item", item_name="Item",
        category="Currency", league="Test", what_happened="", why_it_matters="",
        possible_action="", confidence=.8, signals={}, historical_context={},
        timestamp="2026-01-01T00:00:00+00:00",
    )
    result = {"groups": [{
        "category": "Currency", "source": "regime", "signal_type": "Trending Up",
        "horizons": {"24": {
            "sample_size": 3, "median_return": 2, "mean_return": 1000,
            "win_probability": .7, "p10_return": -1, "historical_confidence": .6,
            "return_samples": [2, 2, 1000],
            "evidence_sources": {"observed": 1, "poe.ninja_sparkline_reconstructed": 2},
            "reconstructed_sample_size": 2,
        }},
    }]}
    async def fake_backtest(*args, **kwargs):
        return result
    monkeypatch.setattr(opportunity.validation, "backtest", fake_backtest)
    asyncio.run(opportunity._attach_historical_outcomes([opp]))
    assert opp.expected_return == 2
    assert opp.historical_context["return_estimator"] == "median"
    normalized = opp.to_investable(chaos_per_divine=100)
    assert normalized.metadata["direct_observation"] is True
    assert normalized.metadata["reconstruction_dependent"] is True
