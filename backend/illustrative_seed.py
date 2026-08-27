"""Optional development seed for local README / demo captures.

Enabled only when DEUSCFO_ILLUSTRATIVE_SEED is set to 1/true/yes/on.
The packaged launcher does not set this flag. Production evidence gates,
filters, and allocator math are unchanged; the seed is an extra candidate
that still has to clear `_effective_mode` and `build_capital_plan`.

Every user-visible field we control is labeled illustrative / non-observed.
While the flag is on, live candidates are replaced so a README capture is
one deterministic position instead of a mix of seed and market rows.
Exploratory Currency Exchange paper ideas are also omitted for that capture
so the DEPLOY recommendation, allocation, and paper flow stay on screen.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import List

from opportunity import InvestableOpportunity

ENV_FLAG = "DEUSCFO_ILLUSTRATIVE_SEED"

REASON_PREFIX = (
    "ILLUSTRATIVE / NON-OBSERVED INPUTS. This plan includes a deterministic "
    "development seed — it is not a live market observation. "
)


def seed_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def illustrative_opportunity(chaos_per_divine: float) -> InvestableOpportunity:
    """One Divine per unit so quantity × price matches displayed Divine values."""
    cpd = max(float(chaos_per_divine), 1.0)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    returns = [20.0] * 100
    durations = [8.0] * 100
    return InvestableOpportunity(
        id="illustrative-seed-doctor",
        strategy_type="demo.illustrative_buy",
        entry_item="The Doctor · illustrative / non-observed",
        exit_item="Headhunter · illustrative / non-observed",
        category="divination",
        current_price=cpd,
        realistic_entry_price=cpd,
        realistic_exit_price=round(cpd * 1.20, 6),
        expected_return=20.0,
        expected_profit_per_unit=0.20,
        expected_roi_per_lock_hour=0.025,
        win_probability=0.85,
        expected_duration=8.0,
        duration_distribution=durations,
        downside_percentile=-5.0,
        historical_sample_size=100,
        historical_returns=returns,
        confidence=0.85,
        liquidity={"tier": "high", "volume": 1000},
        execution_effort=0.0,
        minimum_capital=1.0,
        maximum_reasonable_capital=10.0,
        opportunity_capacity=10.0,
        correlation_group="illustrative-seed",
        created_at=now.isoformat(),
        last_validated_at=now.isoformat(),
        expected_half_life=8.0,
        expires_at=(now + timedelta(days=30)).isoformat(),
        tier="A",
        status="ACTIVE",
        strategy_status="Validated",
        metadata={
            "illustrative": True,
            "non_observed": True,
            "reconstruction_dependent": False,
            "paper_only_reconstructed": False,
        },
    )


def apply_illustrative_seed(
    opportunities: List[InvestableOpportunity],
    chaos_per_divine: float,
) -> List[InvestableOpportunity]:
    if not seed_enabled():
        return opportunities
    return [illustrative_opportunity(chaos_per_divine)]


def label_plan_reason(reason: str) -> str:
    if not seed_enabled():
        return reason
    if reason.startswith("ILLUSTRATIVE"):
        return reason
    return REASON_PREFIX + reason
