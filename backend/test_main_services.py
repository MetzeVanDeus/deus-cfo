import asyncio
from datetime import datetime, timezone

import database
import main
import pytest


def run(coro):
    return asyncio.run(coro)


def request_for_plan():
    return main.CapitalPlanRequest(
        league="Allflame",
        bankroll=main.capital.Bankroll(total_net_worth=50, liquid_currency=50),
        mode="PAPER",
        simulations=5,
    )


def test_wait_plan_is_appended_and_listed(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "journal.db"))

    async def no_opportunities(*args):
        return []
    async def paper_ideas(*args, **kwargs):
        return [{"item_id": "divine", "confidence": "low", "snapshot_timestamp": "2026-08-13T20:00:00+00:00", "data_age_hours": 234.0}]
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda league: asyncio.sleep(0, result=None))

    monkeypatch.setattr(main.opportunity, "get_all_opportunities", no_opportunities)
    monkeypatch.setattr(main.cx_queries, "cx_paper_ideas", paper_ideas)
    monkeypatch.setattr(main.cx_metadata, "ensure_currency_mapping", lambda: asyncio.sleep(0, result={}))
    monkeypatch.setattr(main.cx_metadata, "resolve_name", lambda mapping, item_id: "Divine Orb")
    result = run(main.create_capital_plan(request_for_plan()))
    second = run(main.create_capital_plan(request_for_plan()))
    assert result["recommendation"] == "WAIT"
    assert isinstance(result["recommendation_id"], int)
    assert second["recommendation_id"] != result["recommendation_id"]
    assert result["paper_ideas"] == [{"item_id": "divine", "item_name": "Divine Orb", "confidence": "low", "snapshot_timestamp": "2026-08-13T20:00:00+00:00", "data_age_hours": 234.0}]
    assert "not validated EV" in result["evidence_warning"]
    rows = run(main.journal_recommendations())
    assert len(rows) == 2
    assert {row["id"] for row in rows} == {result["recommendation_id"], second["recommendation_id"]}
    assert all(
        row["league"] == "Allflame"
        and row["mode"] == "OBSERVE"
        and row["recommendation"] == "WAIT"
        and row["capital_currency"] == "Divine"
        and row["chaos_per_divine"] is None
        for row in rows
    )


def test_capital_endpoint_passes_resolved_rate_to_builder(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "resolved-rate.db"))
    raw = main.opportunity.Opportunity(
        type="anomaly", detector_id="test", item_id="item", item_name="Item",
        category="Currency", league="Allflame", what_happened="", why_it_matters="",
        possible_action="", confidence=.9, signals={}, historical_context={
            "data_points": 2, "return_samples": [5, 10], "duration_samples": [3, 6],
        },
        timestamp=datetime.now(timezone.utc).isoformat(), expected_return=10,
        win_probability=.8, sample_size=20, historical_confidence=.8,
        realistic_entry=100, realistic_exit=120, realistic_profit=10,
        estimated_time=6, liquidity={"tier": "medium", "volume": 1000},
    )

    async def opportunities(*args, **kwargs):
        return [raw]

    captured = {}
    original = main.capital.build_capital_plan

    def wrapped(*args, **kwargs):
        captured["chaos_per_divine"] = kwargs["chaos_per_divine"]
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda league: asyncio.sleep(0, result=100))
    monkeypatch.setattr(main.opportunity, "get_all_opportunities", opportunities)
    monkeypatch.setattr(main.capital, "build_capital_plan", wrapped)

    result = run(main.create_capital_plan(request_for_plan()))
    assert captured["chaos_per_divine"] == 100
    assert result["requested_mode"] == "PAPER"
    assert result["mode_downgraded"] is False
    assert result["recommendation"] == "DEPLOY"
    assert result["chaos_per_divine"] == 100
    assert result["positions"]
def test_capital_endpoint_sources_bankroll_from_paper_portfolio(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "paper-source.db"))
    portfolio_id = run(main.create_paper_portfolio(
        main.PaperPortfolioRequest(initial_bankroll=117.24, chaos_per_divine=100),
    ))["portfolio_id"]
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda league: asyncio.sleep(0, result=110))
    monkeypatch.setattr(main.opportunity, "get_all_opportunities", lambda *args, **kwargs: asyncio.sleep(0, result=[]))

    request = main.CapitalPlanRequest(
        league="Allflame",
        portfolio_id=portfolio_id,
        bankroll=main.capital.Bankroll(total_net_worth=999, liquid_currency=999),
        mode="PAPER",
        simulations=5,
    )
    result = run(main.create_capital_plan(request))

    assert result["bankroll"]["total_net_worth"] == 106.58181818181818
    assert result["bankroll"]["liquid_currency"] == 106.58181818181818
    assert result["bankroll"]["reserved_capital"] == 0
    assert result["chaos_per_divine"] == 110


def test_capital_endpoint_rejects_auto_source_without_rate(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "paper-source-unavailable.db"))
    portfolio_id = run(main.create_paper_portfolio(
        main.PaperPortfolioRequest(initial_bankroll=20, chaos_per_divine=100),
    ))["portfolio_id"]
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda league: asyncio.sleep(0, result=None))

    request = main.CapitalPlanRequest(
        league="Allflame",
        portfolio_id=portfolio_id,
        bankroll=main.capital.Bankroll(total_net_worth=999, liquid_currency=999),
    )
    try:
        run(main.create_capital_plan(request))
    except main.HTTPException as exc:
        assert exc.status_code == 400
        assert "cannot source bankroll" in str(exc.detail)
    else:
        raise AssertionError("auto-sourced plan must fail when rate is unavailable")

def test_capital_endpoint_passes_global_completed_calibration(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "calibration.db"))
    completed = {"confidence": .8, "profitable": True, "realized_profit": 1, "portfolio_id": 42}
    open_record = {"confidence": .8, "profitable": None, "realized_profit": None, "portfolio_id": 42}
    async def records():
        return [completed, open_record]
    monkeypatch.setattr(main.portfolio, "trade_records", records)
    captured = {}
    original = main.capital.build_capital_plan
    def wrapped(*args, **kwargs):
        captured["records"] = kwargs["calibration_records"]
        return original(*args, **kwargs)
    monkeypatch.setattr(main.capital, "build_capital_plan", wrapped)
    monkeypatch.setattr(main, "_resolve_chaos_per_divine", lambda league: asyncio.sleep(0, result=None))

    result = run(main.create_capital_plan(request_for_plan()))
    assert result["recommendation"] == "WAIT"
    assert captured["records"] == [completed]


def test_paper_and_reallocation_service_endpoints(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "paper.db"))
    portfolio_id = run(main.create_paper_portfolio(main.PaperPortfolioRequest(initial_bankroll=20, chaos_per_divine=1)))["portfolio_id"]
    status = run(main.paper_status(portfolio_id))
    assert status["liquid"] == 20
    position_id = run(main.open_paper_position(
        portfolio_id,
        main.PaperPositionRequest(
            opportunity_id="synthetic", quantity=1, entry_price=5,
            predicted_exit_price=6, predicted_profit=1,
        ),
    ))["position_id"]
    assert run(main.paper_positions(portfolio_id, "open"))[0]["id"] == position_id
    realized = run(main.realize_paper_position(position_id, main.PaperRealizeRequest(exit_price=6)))
    assert realized["realized_profit"] == 1
    assert not run(main.paper_positions(portfolio_id, "open"))
    assert run(main.paper_positions(portfolio_id, "realized"))[0]["id"] == position_id
    assert run(main.paper_performance(portfolio_id))["total_return"] == 1
    assert len(run(main.paper_equity(portfolio_id))) == 2
    assert len(run(main.paper_trades(portfolio_id))) == 1
    manual = run(main.record_real_trade(main.RealTradeRequest(
        opportunity_id="manual", quantity=2, predicted_entry_price=100,
        actual_entry_price=100, predicted_exit_price=200, actual_exit_price=200,
        predicted_duration_hours=1, actual_duration_hours=1, confidence=.5, chaos_per_divine=200,
    )))
    assert manual["portfolio_id"] is None
    assert manual["quantity"] == 2
    assert manual["chaos_per_divine"] == 200
    assert manual["realized_profit"] == 200
    decision = run(main.check_reallocation(main.ReallocationCheckRequest(
        current_remaining_return=.02, new_return=.05, exit_cost=.01, entry_cost=.01,
    )))
    assert decision["should_reallocate"] is True


def test_transformation_routes_are_explicitly_observe_only():
    listed = run(main.list_transformations())
    assert listed["transformations"]
    evaluated = run(main.evaluate_transformations(main.TransformationEvaluateRequest(
        prices={"Divine": 100, "Chaos": 110}, bankroll=50,
    )))
    assert evaluated["auto_execution"] is False
    assert all(item["tier"] == "WATCH" or item["strategy_status"] == "Experimental"
               for item in evaluated["opportunities"])

@pytest.mark.parametrize("amount", [0, -1, float("nan"), float("inf")])
def test_flip_request_rejects_nonpositive_or_nonfinite_budget(amount):
    with pytest.raises(ValueError):
        main.FlipRequest(
            budgetCurrency="chaos", budgetAmount=amount, leagueId="Allflame", category="Currency"
        )
    with pytest.raises(ValueError):
        main.FlipRequest(
            budgetCurrency="chaos", budgetAmount=1, leagueId="", category="Currency"
        )


def test_flip_request_reuses_one_http_client(monkeypatch):
    clients = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    def make_client(**_kwargs):
        client = Client()
        clients.append(client)
        return client

    async def fetch_stash(_client, _league, _category):
        return [{
            "detailsId": "test-item", "name": "Test Item", "chaosValue": 5,
            "listingCount": 100, "sparkLine": {"totalChange": 2, "data": [0, 2, 0]},
        }]

    async def fetch_exchange(_client, _league, _category):
        return [{"id": "chaos", "primaryValue": 1}]

    monkeypatch.setattr(main.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(main, "_fetch_stash", fetch_stash)
    monkeypatch.setattr(main, "_fetch_exchange", fetch_exchange)
    result = run(main.find_flips(main.FlipRequest(
        budgetCurrency="chaos", budgetAmount=10, leagueId="Allflame", category="SkillGem"
    )))
    assert result and result[0]["itemId"] == "test-item"
    assert len(clients) == 1
