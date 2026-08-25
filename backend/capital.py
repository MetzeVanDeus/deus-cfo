"""Conservative, explainable capital allocation over validated opportunities."""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

import portfolio
from opportunity import InvestableOpportunity


Mode = Literal["OBSERVE", "PAPER", "AGGRESSIVE-PAPER", "LIVE-CANDIDATE"]
RiskTolerance = Literal["low", "medium", "high"]
Liquidity = Literal["low", "medium", "high"]
Effort = Literal["low", "medium", "high"]
_LIQUIDITY_RANK = {"low": 0, "medium": 1, "high": 2}
_EFFORT_LIMIT = {"low": 25.0, "medium": 100.0, "high": math.inf}
_PAPER_RECONSTRUCTED_CAP = 0.02
_AGGRESSIVE_PAPER_RECONSTRUCTED_CAP = 0.10


def _paper_reconstructed(item: InvestableOpportunity) -> bool:
    metadata = item.metadata or {}
    return (
        bool(metadata.get("reconstruction_dependent"))
        and bool(metadata.get("paper_only_reconstructed"))
        and int(metadata.get("reconstructed_sample_size") or 0) >= 20
    )

class Bankroll(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_net_worth: float = Field(ge=0)
    currency: Literal["Divine"] = "Divine"
    liquid_currency: float = Field(ge=0)
    currently_invested: float = Field(default=0, ge=0)
    reserved_capital: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def consistent(self) -> "Bankroll":
        if self.liquid_currency + self.currently_invested > self.total_net_worth + 1e-9:
            raise ValueError("liquid_currency + currently_invested cannot exceed total_net_worth")
        if self.reserved_capital > self.liquid_currency + 1e-9:
            raise ValueError("reserved_capital cannot exceed liquid_currency")
        return self

    @property
    def available_currency(self) -> float:
        return max(0.0, self.liquid_currency - self.reserved_capital)


class InvestmentPreferences(BaseModel):
    """Preset-friendly defaults with exact advanced constraints in the same model."""

    model_config = ConfigDict(extra="forbid")

    risk_tolerance: RiskTolerance = "medium"
    desired_horizon_hours: float = Field(default=12, gt=0)
    minimum_liquidity: Liquidity = "medium"
    maximum_effort: Effort = "medium"
    minimum_reserve_percent: float = Field(default=0.20, ge=0, le=1)
    minimum_reserve_amount: float = Field(default=0, ge=0)
    max_single_position_percent: float = Field(default=0.30, ge=0, le=1)
    max_category_exposure_percent: float = Field(default=0.50, ge=0, le=1)
    max_correlated_exposure_percent: float = Field(default=0.50, ge=0, le=1)
    max_risk_percent: float | None = Field(default=None, ge=0, le=1)
    max_single_position_amount: float | None = Field(default=None, ge=0)
    max_category_exposure_amount: float | None = Field(default=None, ge=0)
    max_correlated_exposure_amount: float | None = Field(default=None, ge=0)
    max_execution_effort: float | None = Field(default=None, ge=0)

    @property
    def risk_fraction(self) -> float:
        if self.max_risk_percent is not None:
            return self.max_risk_percent
        return {"low": 0.05, "medium": 0.10, "high": 0.20}[self.risk_tolerance]

    @classmethod
    def preset(cls, name: RiskTolerance = "medium", **overrides) -> "InvestmentPreferences":
        defaults = {
            "low": {"desired_horizon_hours": 6, "minimum_liquidity": "high", "maximum_effort": "low",
                    "minimum_reserve_percent": 0.30, "max_single_position_percent": 0.15,
                    "max_category_exposure_percent": 0.35, "max_correlated_exposure_percent": 0.25},
            "medium": {},
            "high": {"desired_horizon_hours": 24, "minimum_liquidity": "low", "maximum_effort": "high",
                     "minimum_reserve_percent": 0.10, "max_single_position_percent": 0.40,
                     "max_category_exposure_percent": 0.60, "max_correlated_exposure_percent": 0.50},
        }[name]
        return cls(risk_tolerance=name, **defaults, **overrides)

    @classmethod
    def advanced(cls, **constraints) -> "InvestmentPreferences":
        return cls(**constraints)


class WatchOpportunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    item: str
    category: str
    state: Literal["WATCHING"] = "WATCHING"
    trigger: str
    reason: str
    suggested_capital_range: list[float]
    trigger_probability: float | None = Field(default=None, ge=0, le=1)
    capital_currency: Literal["Divine"] = "Divine"


class AllocationPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    category: str
    correlation_group: str
    capital: float = Field(ge=0)
    expected_profit: float
    expected_return: float
    probability_profitable: float = Field(ge=0, le=1)
    expected_duration: float = Field(gt=0)
    duration_interval: list[float]
    downside_estimate: float
    tier: str
    reason: str
    capital_currency: Literal["Divine"] = "Divine"
    entry_item: str = ""
    action: Literal["BUY"] = "BUY"
    target_entry_chaos: float = Field(default=0, ge=0)
    maximum_entry_chaos: float = Field(default=0, ge=0)
    estimated_quantity: int = Field(default=0, ge=0)
    target_exit_chaos: float | list[float] | None = None
    historical_sample_size: int = Field(default=0, ge=0)
    time_exit_hours: float = Field(default=1, gt=0)
    invalidation_conditions: list[str] = Field(default_factory=list)
    raw_probability_profitable: float | None = Field(default=None, ge=0, le=1)
    calibration: dict[str, Any] = Field(default_factory=dict)


class PortfolioSimulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    trials: int
    expected_profit: float
    median_profit: float
    probability_profitable: float
    p10_profit: float
    p25_profit: float
    p75_profit: float
    p90_profit: float
    median_completion_hours: float
    completion_interval: list[float]
    capital_locked: float


class CapitalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode
    recommendation: Literal["DEPLOY", "WAIT"]
    bankroll: Bankroll
    positions: list[AllocationPosition]
    reserve: float = Field(ge=0)
    unallocated: float = Field(ge=0)
    deployed: float = Field(ge=0)
    simulation: PortfolioSimulation
    objective: str
    objective_components: dict[str, float]
    opportunity_tiers: dict[str, int]
    rejected: dict[str, str]
    reason: str
    capital_currency: Literal["Divine"] = "Divine"
    watchlist: list[WatchOpportunity]
    chaos_per_divine: float | None = Field(default=None, gt=0)
    calibration_summary: dict[str, Any] = Field(default_factory=dict)


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result if result.tzinfo else result.replace(tzinfo=timezone.utc)


def _quantile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def simulate_portfolio(
    positions: list[AllocationPosition],
    opportunities: dict[str, InvestableOpportunity] | list[InvestableOpportunity],
    *,
    seed: int = 0,
    trials: int = 2000,
) -> PortfolioSimulation:
    """Bootstrap empirical returns; positions in a group share a draw index."""
    lookup = opportunities if isinstance(opportunities, dict) else {item.id: item for item in opportunities}
    rng = random.Random(seed)
    profits: list[float] = []
    completion: list[float] = []
    groups: dict[str, list[tuple[AllocationPosition, InvestableOpportunity]]] = {}
    for position in positions:
        item = lookup[position.opportunity_id]
        if not item.historical_returns:
            raise ValueError(f"empirical return samples required for {item.id}")
        if not item.duration_distribution:
            raise ValueError(f"empirical duration samples required for {item.id}")
        groups.setdefault(position.correlation_group, []).append((position, item))
    for _ in range(max(1, trials)):
        profit = 0.0
        durations = []
        for group_positions in groups.values():
            # Draw one shared percentile for the correlation group, rather than
            # one integer index based on its longest history.  Applying an
            # index modulo a shorter history over-samples its early entries
            # whenever sample counts are not exact multiples of one another.
            draw_percentile = rng.random()
            for position, item in group_positions:
                returns = item.historical_returns
                return_index = min(int(draw_percentile * len(returns)), len(returns) - 1)
                value = returns[return_index]
                profit += position.capital * float(value) / 100
                samples = item.duration_distribution
                duration_index = min(int(draw_percentile * len(samples)), len(samples) - 1)
                durations.append(float(samples[duration_index]))
        profits.append(profit)
        completion.append(max(durations, default=0.0))
    return PortfolioSimulation(
        seed=seed,
        trials=max(1, trials),
        expected_profit=round(sum(profits) / len(profits), 6),
        median_profit=round(_quantile(profits, .5), 6),
        probability_profitable=round(sum(value > 0 for value in profits) / len(profits), 6),
        p10_profit=round(_quantile(profits, .1), 6),
        p25_profit=round(_quantile(profits, .25), 6),
        p75_profit=round(_quantile(profits, .75), 6),
        p90_profit=round(_quantile(profits, .9), 6),
        median_completion_hours=round(_quantile(completion, .5), 6),
        completion_interval=[round(_quantile(completion, .1), 6), round(_quantile(completion, .9), 6)],
        capital_locked=round(sum(position.capital for position in positions), 6),
    )

def _effective_mode(requested: Mode, candidates: list[InvestableOpportunity]) -> Mode:
    if requested == "OBSERVE":
        return "OBSERVE"
    required_sample = 100 if requested == "LIVE-CANDIDATE" else 20
    required_confidence = (
        .80 if requested == "LIVE-CANDIDATE"
        else .30 if requested == "AGGRESSIVE-PAPER"
        else .60
    )
    if not any(
        (
            (
                item.tier in ("S", "A")
                and not _paper_reconstructed(item)
                and item.historical_sample_size >= required_sample
                and item.confidence >= required_confidence
                and (
                    item.strategy_status.casefold() == "validated"
                    if requested == "LIVE-CANDIDATE"
                    else item.strategy_status.casefold() in {"validated", "experimental"}
                )
            )
            or (
                requested in {"PAPER", "AGGRESSIVE-PAPER"}
                and item.tier == "B"
                and _paper_reconstructed(item)
                and item.historical_sample_size >= 20
                and item.confidence >= .30
            )
        )
        and item.historical_returns
        and item.duration_distribution
        for item in candidates
    ):
        return "OBSERVE"
    return requested




def _watch_opportunity(
    item: InvestableOpportunity,
    bankroll: Bankroll,
    preferences: InvestmentPreferences,
    *,
    trigger: str,
    reason: str,
    probability: float | None = None,
) -> WatchOpportunity:
    maximum = min(
        item.opportunity_capacity,
        item.maximum_reasonable_capital,
        bankroll.total_net_worth * preferences.max_single_position_percent,
    )
    minimum = min(item.minimum_capital, maximum)
    if probability is None and item.historical_sample_size > 0 and item.historical_returns:
        probability = item.win_probability
    return WatchOpportunity(
        opportunity_id=item.id,
        item=item.entry_item,
        category=item.category,
        trigger=trigger,
        reason=reason,
        suggested_capital_range=[round(max(0.0, minimum), 6), round(max(0.0, maximum), 6)],
        trigger_probability=probability,
    )


def build_capital_plan(
    bankroll: Bankroll,
    preferences: InvestmentPreferences,
    opportunities: list[InvestableOpportunity],
    *,
    mode: Mode = "OBSERVE",
    now: datetime | None = None,
    seed: int = 0,
    simulations: int = 2000,
    chaos_per_divine: float | None = None,
    calibration_records: Sequence[Mapping[str, Any]] = (),
    calibration_minimum_samples: int = 20,
    calibration_prior_strength: float = 20.0,
) -> CapitalPlan:
    """Construct a constrained Divine-denominated plan."""
    if chaos_per_divine is not None and chaos_per_divine <= 0:
        raise ValueError("chaos_per_divine must be positive when supplied")
    if opportunities and chaos_per_divine is None:
        raise ValueError("positive chaos_per_divine is required when opportunities are present")
    if mode not in ("OBSERVE", "PAPER", "AGGRESSIVE-PAPER", "LIVE-CANDIDATE"):
        raise ValueError("mode must be OBSERVE, PAPER, AGGRESSIVE-PAPER, or LIVE-CANDIDATE")
    calibration_records = tuple(calibration_records)
    calibrations = {
        item.id: portfolio.calibrate_probability(
            item.win_probability,
            calibration_records,
            minimum_samples=calibration_minimum_samples,
            prior_strength=calibration_prior_strength,
        )
        for item in opportunities
    }
    calibration_summary = {
        "record_count": len(calibration_records),
        "minimum_samples": calibration_minimum_samples,
        "prior_strength": calibration_prior_strength,
        "applied_positions": 0,
        "buckets": portfolio.calibration_buckets(calibration_records),
    }
    current = now or datetime.now(timezone.utc)
    tiers = {tier: sum(item.tier == tier for item in opportunities) for tier in ("S", "A", "B", "WATCH", "REJECTED")}
    rejected: dict[str, str] = {}
    watchlist: list[WatchOpportunity] = []
    for item in opportunities:
        if item.tier == "WATCH":
            calibration = calibrations[item.id]
            watchlist.append(_watch_opportunity(
                item, bankroll, preferences,
                trigger="empirical evidence reaches an allocatable tier",
                reason=item.rejection_reason or "watch-only evidence",
                probability=calibration["calibrated"] if calibration["applied"] else item.win_probability,
            ))
    effective_mode = _effective_mode(mode, opportunities)
    reserve = max(
        bankroll.reserved_capital,
        bankroll.total_net_worth * preferences.minimum_reserve_percent,
        preferences.minimum_reserve_amount,
    )
    reserve = min(bankroll.liquid_currency, reserve)
    available = max(0.0, bankroll.liquid_currency - reserve)
    category_totals: dict[str, float] = {}
    group_totals: dict[str, float] = {}
    positions: list[AllocationPosition] = []
    scored: list[tuple[float, InvestableOpportunity]] = []
    for item in opportunities:
        if item.status == "INVALIDATED" or item.is_expired(current):
            item.status = "STALE" if item.status != "INVALIDATED" else item.status
            rejected[item.id] = "invalidated" if item.status == "INVALIDATED" else "expired_or_stale"
            continue
        lifecycle = item.strategy_status.casefold()
        if lifecycle in {"rejected", "deprecated"}:
            rejected[item.id] = f"strategy_lifecycle_{lifecycle}"
            continue
        if lifecycle == "experimental" and mode == "LIVE-CANDIDATE":
            rejected[item.id] = "experimental_not_allowed_live_candidate"
            continue
        if not item.historical_returns or not item.duration_distribution:
            watchlist.append(_watch_opportunity(
                item, bankroll, preferences,
                trigger="empirical return and duration samples become available",
                reason="missing_empirical_distribution",
            ))
            rejected[item.id] = "missing_empirical_distribution"
            continue
        if item.tier not in ("S", "A") and not (
            mode in {"PAPER", "AGGRESSIVE-PAPER"} and item.tier == "B" and _paper_reconstructed(item)
        ):
            rejected[item.id] = item.rejection_reason or "tier_not_allocatable"
            continue

        if item.expected_duration > preferences.desired_horizon_hours:
            rejected[item.id] = "horizon_exceeds_preference"
            continue
        liquidity = str(item.liquidity.get("tier", "low")).lower()
        if _LIQUIDITY_RANK.get(liquidity, 0) < _LIQUIDITY_RANK[preferences.minimum_liquidity]:
            rejected[item.id] = "liquidity_below_preference"
            continue
        effort_cap = preferences.max_execution_effort if preferences.max_execution_effort is not None else math.inf
        if item.execution_effort > min(_EFFORT_LIMIT[preferences.maximum_effort], effort_cap):
            rejected[item.id] = "execution_effort_exceeds_preference"
            continue
        calibration = calibrations[item.id]
        probability = calibration["calibrated"] if calibration["applied"] else item.win_probability
        confidence_factor = probability if calibration["applied"] else item.confidence
        uncertainty_shrink = min(1.0, math.sqrt(max(0, item.historical_sample_size) / 100)) * confidence_factor
        downside = max(0.0, -item.downside_percentile / 100)
        risk_scale = {"low": .50, "medium": .75, "high": 1.0}[preferences.risk_tolerance]
        score = max(0.0, item.expected_return / 100) * uncertainty_shrink * risk_scale / max(.25, item.expected_duration)
        scored.append((score, item))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    if effective_mode == "OBSERVE":
        watchlist.extend(
            _watch_opportunity(
                item, bankroll, preferences,
                trigger="explicit PAPER mode with validated evidence",
                reason="OBSERVE mode preserves this eligible setup without allocation",
                probability=(
                    calibrations[item.id]["calibrated"]
                    if calibrations[item.id]["applied"] else item.win_probability
                ),
            )
            for _, item in scored
            if item.id not in {watch.opportunity_id for watch in watchlist}
        )
        scored = []
    for _, item in scored:
        calibration = calibrations[item.id]
        probability = calibration["calibrated"] if calibration["applied"] else item.win_probability
        confidence_factor = probability if calibration["applied"] else item.confidence
        if available < item.minimum_capital:
            rejected[item.id] = "minimum_capital_unavailable"
            continue
        cap = min(item.opportunity_capacity, item.maximum_reasonable_capital, available,
                  bankroll.total_net_worth * preferences.max_single_position_percent)
        if item.strategy_status.casefold() == "experimental":
            cap = min(cap, bankroll.total_net_worth * item.experimental_allocation_cap)
        if preferences.max_single_position_amount is not None:
            cap = min(cap, preferences.max_single_position_amount)
        downside = max(0.0, -item.downside_percentile / 100)
        if downside:
            cap = min(cap, bankroll.total_net_worth * preferences.risk_fraction / downside)
        category_cap = (
            preferences.max_category_exposure_amount
            if preferences.max_category_exposure_amount is not None
            else bankroll.total_net_worth * preferences.max_category_exposure_percent
        )
        group_cap = (
            preferences.max_correlated_exposure_amount
            if preferences.max_correlated_exposure_amount is not None
            else bankroll.total_net_worth * preferences.max_correlated_exposure_percent
        )
        cap = min(cap, category_cap - category_totals.get(item.category, 0), group_cap - group_totals.get(item.correlation_group, 0))
        if _paper_reconstructed(item):
            reconstructed_cap = (
                _AGGRESSIVE_PAPER_RECONSTRUCTED_CAP
                if mode == "AGGRESSIVE-PAPER" else _PAPER_RECONSTRUCTED_CAP
            )
            cap = min(cap, bankroll.total_net_worth * reconstructed_cap)
        constrained_cap = cap
        size_factor = (
            1.0
            if mode == "AGGRESSIVE-PAPER" and _paper_reconstructed(item)
            else min(1.0, max(0.0, item.expected_return / 20) * confidence_factor)
        )
        cap *= size_factor
        if _paper_reconstructed(item) and constrained_cap >= item.minimum_capital:
            cap = max(cap, item.minimum_capital)
        if cap < item.minimum_capital:
            rejected[item.id] = "risk_adjusted_size_below_minimum"
            continue
        entry_chaos = max(0.0, item.realistic_entry_price)
        estimated_quantity = (
            math.floor(cap * chaos_per_divine / entry_chaos + 1e-9)
            if entry_chaos else 0
        )
        if estimated_quantity < 1:
            rejected[item.id] = "minimum_unit_unavailable"
            continue
        amount = round(estimated_quantity * entry_chaos / chaos_per_divine, 6)
        expected_profit = amount * item.expected_return / 100
        invalidation_conditions = [
            "status_not_active",
            "liquidity_below_required_tier",
            "duration_exceeds_horizon",
        ]
        if item.expires_at:
            invalidation_conditions.append(f"expires_at:{item.expires_at}")
        positions.append(AllocationPosition(
            opportunity_id=item.id,
            category=item.category,
            correlation_group=item.correlation_group,
            capital=amount,
            expected_profit=round(expected_profit, 6),
            expected_return=item.expected_return,
            probability_profitable=probability,
            expected_duration=item.expected_duration,
            duration_interval=[min(item.duration_distribution), max(item.duration_distribution)],
            downside_estimate=round(amount * item.downside_percentile / 100, 6),
            tier=item.tier,
            reason="Manual BUY plan based on empirical samples and current capacity constraints.",
            capital_currency=bankroll.currency,
            entry_item=item.entry_item,
            target_entry_chaos=entry_chaos,
            maximum_entry_chaos=entry_chaos,
            estimated_quantity=estimated_quantity,
            target_exit_chaos=item.realistic_exit_price,
            historical_sample_size=item.historical_sample_size,
            time_exit_hours=min(item.expected_duration, preferences.desired_horizon_hours),
            invalidation_conditions=invalidation_conditions,
            raw_probability_profitable=item.win_probability,
            calibration=calibration,
        ))
        available -= amount
        category_totals[item.category] = category_totals.get(item.category, 0) + amount
        group_totals[item.correlation_group] = group_totals.get(item.correlation_group, 0) + amount
    calibration_summary["applied_positions"] = sum(
        bool(position.calibration.get("applied")) for position in positions
    )
    deployed = bankroll.liquid_currency - reserve - available
    simulation = simulate_portfolio(positions, opportunities, seed=seed, trials=simulations)
    recommendation = "DEPLOY" if positions and effective_mode != "OBSERVE" else "WAIT"
    if recommendation == "WAIT":
        reason = ("Insufficient validated evidence for capital deployment; observing candidates and preserving reserve."
                  if effective_mode == "OBSERVE" else "No opportunity met constrained risk-adjusted sizing requirements.")
    else:
        reason = "Deploy only the listed capacity-bounded positions; hold all remaining liquid currency as reserve/unallocated capital."
    return CapitalPlan(
        mode=effective_mode,
        recommendation=recommendation,
        bankroll=bankroll,
        positions=positions,
        reserve=round(reserve, 6),
        unallocated=round(max(0.0, available), 6),
        deployed=round(max(0.0, deployed), 6),
        simulation=simulation,
        objective=("Maximize explainable risk-adjusted expected profit while penalizing downside, uncertainty, "
                   "lockup, execution effort, liquidity, and correlated exposure."),
        objective_components={"expected_profit": simulation.expected_profit, "downside_p10": simulation.p10_profit,
                              "capital_locked": simulation.capital_locked, "reserve": reserve},
        opportunity_tiers=tiers,
        watchlist=watchlist,
        rejected=rejected,
        reason=reason,
        capital_currency=bankroll.currency,
        chaos_per_divine=chaos_per_divine,
        calibration_summary=calibration_summary,
    )
