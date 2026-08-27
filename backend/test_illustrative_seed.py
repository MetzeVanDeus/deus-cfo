import os

from capital import Bankroll, InvestmentPreferences, build_capital_plan
import illustrative_seed


DEMO_BANKROLL = Bankroll(
    total_net_worth=25,
    liquid_currency=20,
    currently_invested=0,
    reserved_capital=3,
)
DEMO_PREFS = InvestmentPreferences()


def test_seed_is_inert_without_env(monkeypatch):
    monkeypatch.delenv(illustrative_seed.ENV_FLAG, raising=False)
    original = []
    assert illustrative_seed.seed_enabled() is False
    assert illustrative_seed.apply_illustrative_seed(original, 100) is original
    assert illustrative_seed.label_plan_reason("WAIT") == "WAIT"


def test_seed_is_opt_in_and_labeled(monkeypatch):
    monkeypatch.setenv(illustrative_seed.ENV_FLAG, "1")
    seeded = illustrative_seed.apply_illustrative_seed([], 250.5)
    assert len(seeded) == 1
    item = seeded[0]
    assert item.id == "illustrative-seed-doctor"
    assert "illustrative / non-observed" in item.entry_item
    assert item.tier == "A"
    assert item.historical_sample_size == 100
    assert item.confidence >= 0.60
    assert item.historical_returns and item.duration_distribution
    assert item.realistic_entry_price == 250.5
    labeled = illustrative_seed.label_plan_reason("Deploy only the listed capacity-bounded positions.")
    assert labeled.startswith("ILLUSTRATIVE / NON-OBSERVED INPUTS.")


def test_seed_clears_real_allocator_gates_as_deploy(monkeypatch):
    monkeypatch.setenv(illustrative_seed.ENV_FLAG, "1")
    chaos_per_divine = 868.2
    opportunities = illustrative_seed.apply_illustrative_seed([], chaos_per_divine)
    plan = build_capital_plan(
        DEMO_BANKROLL,
        DEMO_PREFS,
        opportunities,
        mode="PAPER",
        seed=0,
        simulations=50,
        chaos_per_divine=chaos_per_divine,
    )
    assert plan.recommendation == "DEPLOY"
    assert plan.mode == "PAPER"
    assert len(plan.positions) == 1
    position = plan.positions[0]
    assert position.entry_item == "The Doctor · illustrative / non-observed"
    assert position.estimated_quantity == 6
    assert position.capital == 6.0
    assert position.target_entry_chaos == chaos_per_divine
    assert abs(position.estimated_quantity * position.target_entry_chaos / chaos_per_divine - position.capital) < 1e-9
    assert abs(plan.deployed + plan.reserve + plan.unallocated - DEMO_BANKROLL.liquid_currency) < 1e-9
    assert plan.deployed == 6.0
    assert plan.reserve == 5.0
    assert plan.unallocated == 9.0
    assert plan.reason.startswith("Deploy")


def test_seed_does_not_bypass_observe_mode(monkeypatch):
    monkeypatch.setenv(illustrative_seed.ENV_FLAG, "1")
    plan = build_capital_plan(
        DEMO_BANKROLL,
        DEMO_PREFS,
        illustrative_seed.apply_illustrative_seed([], 100),
        mode="OBSERVE",
        simulations=10,
        chaos_per_divine=100,
    )
    assert plan.recommendation == "WAIT"
    assert plan.positions == []
    assert plan.mode == "OBSERVE"
