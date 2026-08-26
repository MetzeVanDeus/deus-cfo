"""Small, declarative strategy providers for normalized opportunities."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import validation
from pydantic import BaseModel, Field

from opportunity import InvestableOpportunity

_EXECUTION_QUOTE_MAX_AGE = timedelta(hours=24)


class ProfitRoute(BaseModel):
    """Execution-aware route values with explicit units.

    Money fields are Chaos or Chaos/set; rates are dimensionless ratios or
    Chaos/hour; durations are elapsed hours; capacities are complete units
    named by ``capacity_units``; confidence fields are [0, 1].
    """
    model_config = {"extra": "forbid"}

    transformation_id: str
    name: str
    strategy_family: str = "transformation"
    status: str = "theoretical"
    league: str | None = None
    category: str = "Transformation"
    total_input_cost: float = Field(description="Chaos for one base batch")
    realistic_output_value: float = Field(description="Expected liquidated Chaos for one base batch")
    gross_profit: float = Field(description="Chaos per base batch before explicit execution friction")
    expected_net_profit: float = Field(description="Safe expected net Chaos per base batch")
    theoretical_net_profit: float | None = Field(default=None, description="Theoretical expected net Chaos per base batch")
    executable_net_profit: float | None = Field(default=None, description="Exact-depth executable net Chaos per base batch")
    actual_net_profit: float | None = Field(default=None, description="Observed journal net Chaos per completed batch")
    roi: float = Field(description="Dimensionless net return / input capital")
    theoretical_roi: float | None = Field(default=None, description="Dimensionless theoretical ROI from reference prices")
    executable_roi: float | None = Field(default=None, description="Dimensionless ROI from exact executable depth")
    capital_required: float = Field(description="Chaos required for one base batch")
    capacity: float = Field(description="Recommended complete batches in capacity_units")
    capacity_units: str = "capital"
    active_execution_time: float = Field(description="Hands-on execution effort in hours per base batch")
    capital_lock_time: float = Field(description="Elapsed hours until capital can be released per base batch")
    elapsed_cycle_time: float = Field(description="Elapsed cycle duration in hours used for ROI/time and allocator duration")
    profit_per_active_hour: float = Field(description="Expected net Chaos per active execution hour")
    roi_per_lock_hour: float = Field(description="Dimensionless ROI divided by capital_lock_time in hours")
    profit_per_set: float | None = Field(default=None, description="Expected net Chaos per complete set, when applicable")
    budget_capacity: int = Field(default=0, description="Largest positive-safe batch fitting the stated Chaos budget")
    recommended_capacity: int = Field(default=0, description="Largest positive-safe batch recommended after all constraints")
    estimated_sets_per_lock_hour: float = Field(default=0.0, description="Complete sets per capital-lock hour")
    market_capacity: int = Field(default=0, description="Largest positive-safe batch supported by exact market depth")
    time_horizon_hours: float = Field(default=0.0, description="Evaluation horizon in elapsed hours")
    capacity_assumptions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="Overall confidence in [0, 1]")
    pricing_confidence: float = Field(default=0.0, description="Price evidence confidence in [0, 1]")
    strategy_confidence: float = Field(default=0.0, description="Transformation-definition confidence in [0, 1]")
    execution_risk: float = Field(default=0.0, description="Execution risk in [0, 1]")
    liquidity: dict[str, Any] = Field(default_factory=dict)
    source: str = "unverified"
    verified_version: str = "unverified"
    poe_patch: str | None = None
    verification_metadata: dict[str, Any] = Field(default_factory=dict)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    costs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    execution_steps: list[str] = Field(default_factory=list)

    def to_investable(
        self,
        *,
        status: str = "Experimental",
        max_batch: int = 1,
        bankroll: float = 0.0,
        chaos_per_divine: float = 1.0,
    ) -> InvestableOpportunity:
        """Adapt this route to the existing allocator contract."""
        if chaos_per_divine <= 0:
            raise ValueError("positive chaos_per_divine is required")
        duration = max(0.25, self.elapsed_cycle_time)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=duration)).isoformat(timespec="seconds")
        created_at = now.isoformat(timespec="seconds")
        entry_chaos = self.total_input_cost
        exit_chaos = self.realistic_output_value
        expected_profit_chaos = self.expected_net_profit
        entry_divine = entry_chaos / chaos_per_divine
        return InvestableOpportunity(
            id=self.transformation_id,
            strategy_type="divination_card" if self.strategy_family == "divination_card" else "transformation",
            entry_item=self.inputs[0].get("item", self.inputs[0].get("reward_item", self.transformation_id)) if self.inputs else self.transformation_id,
            exit_item=self.outputs[0].get("item", self.outputs[0].get("reward_item")) if self.outputs else None,
            category=self.category,
            current_price=entry_chaos,
            realistic_entry_price=entry_chaos,
            realistic_exit_price=exit_chaos,
            expected_return=self.roi * 100,
            expected_profit_per_unit=expected_profit_chaos / chaos_per_divine,
            expected_roi_per_lock_hour=self.roi_per_lock_hour,
            win_probability=max(0.0, min(1.0, self.confidence)),
            expected_duration=duration,
            duration_distribution=[duration],
            downside_percentile=-self.execution_risk * 100,
            upside_percentile=max(0.0, self.roi * 100),
            historical_sample_size=0,
            confidence=self.confidence,
            liquidity=self.liquidity,
            execution_effort=float(len(self.execution_steps)),
            minimum_capital=entry_divine,
            maximum_reasonable_capital=entry_divine * max_batch,
            opportunity_capacity=self.capacity * entry_divine,
            correlation_group=self.strategy_family,
            created_at=created_at,
            last_validated_at=created_at,
            expected_half_life=duration,
            expires_at=expires_at,
            tier="WATCH" if status == StrategyLifecycle.EXPERIMENTAL.value else "B",
            strategy_status=status,
            metadata={
                "profit_route": self.model_dump(),
                "allocation_cap": bankroll * 0.02 if status == StrategyLifecycle.EXPERIMENTAL.value else bankroll,
                "source": self.source,
                "verification_metadata": self.verification_metadata,
                "capacity_units": self.capacity_units,
                "capacity_assumptions": self.capacity_assumptions,
            },
        )
class StrategyLifecycle(StrEnum):
    EXPERIMENTAL = "Experimental"
    VALIDATED = "Validated"
    REJECTED = "Rejected"
    DEPRECATED = "Deprecated"


@dataclass(frozen=True)
class StrategyMetadata:
    strategy_id: str
    status: StrategyLifecycle = StrategyLifecycle.EXPERIMENTAL
    experimental_allocation_cap: float = 0.02
    validation_sample_size: int = 0

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id is required")
        if not 0 < self.experimental_allocation_cap <= 1:
            raise ValueError("experimental_allocation_cap must be in (0, 1]")
        if self.validation_sample_size < 0:
            raise ValueError("validation_sample_size cannot be negative")

    def allocation_cap(self, bankroll: float) -> float:
        if bankroll < 0:
            raise ValueError("bankroll cannot be negative")
        return bankroll * self.experimental_allocation_cap if self.status == StrategyLifecycle.EXPERIMENTAL else bankroll




class StrategyProvider(Protocol):
    """A provider consumes context and emits normalized opportunities."""

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]: ...
_ALLOWED_RECIPE_KEYS = {
    "id", "name", "strategy_family", "status", "inputs", "deterministic_costs", "probabilistic_costs",
    "outputs", "expected_execution_time_hours", "expected_sale_time_hours", "requirements", "risk_model",
    "max_batch", "experimental_note", "source", "verified_version", "manual_actions",
    "category", "sale_fee_rate", "output_discount_rate", "strategy_confidence",
}
_ALLOWED_LIFECYCLE = {item.value for item in StrategyLifecycle}
_MAX_OUTCOMES = 8


def _components(value: Any, field_name: str, probabilities: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = []
    for component in value:
        if not isinstance(component, dict) or set(component) - {"item", "quantity", "probability", "category"}:
            raise ValueError(f"{field_name} contains an unsupported component")
        if not isinstance(component.get("item"), str) or not component["item"].strip():
            raise ValueError(f"{field_name} item is required")
        quantity = component.get("quantity")
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            raise ValueError(f"{field_name} quantity must be positive")
        if probabilities:
            probability = component.get("probability")
            if not isinstance(probability, (int, float)) or not 0 < probability <= 1:
                raise ValueError(f"{field_name} probability is required")
        elif "probability" in component:
            raise ValueError(f"{field_name} cannot have probabilities")
        result.append(dict(component))
    return result


def validate_transformation(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one finite, explicitly modeled transformation record."""
    if not isinstance(record, Mapping):
        raise ValueError("transformation must be an object")
    unknown = set(record) - _ALLOWED_RECIPE_KEYS
    if unknown:
        raise ValueError(f"unmodelled transformation fields: {sorted(unknown)}")
    required = {"id", "name", "inputs", "deterministic_costs", "probabilistic_costs", "outputs", "expected_execution_time_hours", "risk_model"}
    missing = required - set(record)
    if missing:
        raise ValueError(f"incomplete transformation: missing {sorted(missing)}")
    if not isinstance(record["id"], str) or not record["id"]:
        raise ValueError("transformation id is required")
    if record.get("status", StrategyLifecycle.EXPERIMENTAL.value) not in _ALLOWED_LIFECYCLE:
        raise ValueError("unknown strategy lifecycle")
    if "steps" in record or "outcomes" in record:
        raise ValueError("complex or unmodelled outcomes are not supported")
    inputs = _components(record["inputs"], "inputs")
    deterministic = _components(record["deterministic_costs"], "deterministic_costs")
    probabilistic = _components(record["probabilistic_costs"], "probabilistic_costs", True)
    outputs = _components(record["outputs"], "outputs", True)
    if not inputs or not deterministic or not outputs:
        raise ValueError("inputs, deterministic costs, and outputs are required")
    for field_name, values in (("probabilistic_costs", probabilistic), ("outputs", outputs)):
        if values and abs(sum(item["probability"] for item in values) - 1.0) > 1e-9:
            raise ValueError(f"{field_name} probabilities must sum to 1")
    if len(outputs) > _MAX_OUTCOMES or len(probabilistic) > _MAX_OUTCOMES:
        raise ValueError("too many outcomes for finite model")
    execution_time = record["expected_execution_time_hours"]
    if not isinstance(execution_time, (int, float)) or execution_time <= 0:
        raise ValueError("expected_execution_time_hours must be positive")
    risk_model = record["risk_model"]
    if not isinstance(risk_model, Mapping) or risk_model.get("kind") not in {"deterministic", "finite_outcome"}:
        raise ValueError("risk_model must explicitly identify a finite model")
    result = dict(record)
    result.setdefault("status", StrategyLifecycle.EXPERIMENTAL.value)
    result.setdefault("strategy_family", "transformation")
    result.setdefault("category", "Transformation")
    result.setdefault("requirements", {})
    result.setdefault("manual_actions", [])
    result.setdefault("source", "unverified")
    result.setdefault("verified_version", "unverified")
    result.setdefault("expected_sale_time_hours", 0.0)
    result.setdefault("sale_fee_rate", 0.0)
    result.setdefault("output_discount_rate", 0.0)
    result.setdefault("max_batch", 1)
    if not isinstance(result["requirements"], Mapping) or not isinstance(result["manual_actions"], list):
        raise ValueError("requirements and manual_actions are incomplete")
    if not isinstance(result["max_batch"], int) or result["max_batch"] < 1:
        raise ValueError("max_batch must be a positive integer")
    for name in ("expected_sale_time_hours", "sale_fee_rate", "output_discount_rate"):
        if not isinstance(result[name], (int, float)) or result[name] < 0:
            raise ValueError(f"{name} must be non-negative")
    if result["sale_fee_rate"] >= 1 or result["output_discount_rate"] >= 1:
        raise ValueError("sale and output discounts must be below 1")
    if "strategy_confidence" in result and (
        not isinstance(result["strategy_confidence"], (int, float))
        or not 0 <= result["strategy_confidence"] <= 1
    ):
        raise ValueError("strategy_confidence must be between 0 and 1")
    return result


class TransformationRegistry:
    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            self.register(record)

    @classmethod
    def from_json(cls, path: str | Path) -> "TransformationRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("transformation file must contain a list")
        return cls(payload)



    def register(self, record: Mapping[str, Any]) -> None:
        normalized = validate_transformation(record)
        if normalized["id"] in self._records:
            raise ValueError(f"duplicate transformation: {normalized['id']}")
        self._records[normalized["id"]] = normalized

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self._records.values())

def default_transformation_registry() -> TransformationRegistry:
    return TransformationRegistry.from_json(Path(__file__).with_name("transformations.experimental.json"))


class TransformationStrategyProvider:
    """Evaluate finite, data-defined transformations into profit routes."""

    def __init__(self, registry: TransformationRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        prices = context.get("prices", {})
        price_records = context.get("price_records", {})
        requested_category = context.get("category")
        league = context.get("league")
        routes: list[ProfitRoute] = []
        for recipe in self.registry.records():
            if recipe["status"] in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}:
                continue
            if requested_category and recipe.get("category", "Transformation") != requested_category:
                continue
            all_costs = recipe["inputs"] + recipe["deterministic_costs"] + recipe["probabilistic_costs"]
            components = all_costs + recipe["outputs"]
            priced = [
                _price_info(
                    prices,
                    price_records,
                    item["item"],
                    item.get("category") or recipe.get("category"),
                )
                for item in components
            ]
            if any(value is None for value in priced):
                continue
            cost_info = priced[:len(all_costs)]
            output_info = priced[len(all_costs):]
            fixed_count = len(recipe["inputs"]) + len(recipe["deterministic_costs"])
            cost = sum(
                item["quantity"] * info["price"]
                for item, info in zip(all_costs[:fixed_count], cost_info[:fixed_count], strict=True)
            )
            cost += sum(
                item["quantity"] * item["probability"] * info["price"]
                for item, info in zip(recipe["probabilistic_costs"], cost_info[fixed_count:], strict=True)
            )
            discount = float(recipe["output_discount_rate"])
            output_value = sum(
                item["quantity"] * item["probability"] * info["price"] * (1 - discount)
                for item, info in zip(recipe["outputs"], output_info, strict=True)
            )
            if cost <= 0 or output_value <= 0:
                continue
            sale_fee = float(recipe["sale_fee_rate"])
            execution_cost = float(recipe["risk_model"].get("execution_cost_chaos", 0) or 0)
            net = output_value * (1 - sale_fee) - cost - execution_cost
            duration = float(recipe["expected_execution_time_hours"])
            sale_time = float(recipe["expected_sale_time_hours"])
            total_time = max(0.25, duration + sale_time)
            lifecycle = StrategyLifecycle(recipe["status"])
            strategy_confidence = float(recipe.get(
                "strategy_confidence",
                0.8 if lifecycle == StrategyLifecycle.VALIDATED else 0.5,
            ))
            risk_model = recipe["risk_model"]
            execution_risk = float(risk_model.get("execution_risk", risk_model.get("risk_score", 0.0)) or 0)
            execution_risk = max(0.0, min(1.0, execution_risk))
            pricing_confidence = min(info["confidence"] for info in priced)
            confidence = pricing_confidence * strategy_confidence * (1 - execution_risk)
            source_values = {str(info["source"]) for info in priced}
            source = next(iter(source_values)) if len(source_values) == 1 else "mixed"
            # Aggregate snapshot volume is reference liquidity, not executable depth.
            market_capacity = budget_capacity = recommended_capacity = 0

            component_volumes = {
                f"{item.get('category') or recipe['category']}:{item['item']}": info["volume"]
                for item, info in zip(components, priced, strict=True)
                if info.get("volume") is not None and info["volume"] > 0
            }
            liquidity_volume = min(component_volumes.values()) if component_volumes else 0.0
            liquidity = {
                "tier": validation.liquidity_tier(liquidity_volume),
                "volume": liquidity_volume,
                "components": component_volumes,
            }
            reasons = [
                "deterministic finite-outcome transformation",
                f"definition source: {recipe['source']} ({recipe['verified_version']})",
            ]
            reasons.append("positive expected net profit" if net > 0 else "negative expected net profit")
            if pricing_confidence < 0.7:
                reasons.append("pricing confidence is below 70%")
            if recipe["manual_actions"]:
                reasons.append(f"{len(recipe['manual_actions'])} manual action(s) required")
            reasons.append("exact executable depth unavailable; executable capacity is zero")
            routes.append(ProfitRoute(
                transformation_id=recipe["id"],
                name=recipe["name"],
                strategy_family=recipe["strategy_family"],
                status="theoretical",
                league=league,
                category=recipe["category"],
                total_input_cost=cost,
                realistic_output_value=output_value,
                gross_profit=output_value - cost,
                expected_net_profit=net,
                theoretical_net_profit=net,
                executable_net_profit=None,
                roi=net / cost,
                theoretical_roi=net / cost,
                capital_required=cost,
                capacity=float(recommended_capacity),
                active_execution_time=duration,
                capital_lock_time=total_time,
                elapsed_cycle_time=total_time,
                profit_per_active_hour=net / max(0.25, duration),
                roi_per_lock_hour=(net / cost) / total_time,
                budget_capacity=budget_capacity,
                recommended_capacity=recommended_capacity,
                estimated_sets_per_lock_hour=0.0,
                market_capacity=market_capacity,
                time_horizon_hours=float(context.get("capacity_horizon_hours", 0) or 0),
                capacity_assumptions=["aggregate reference volume is not exact executable depth"],
                confidence=confidence,
                pricing_confidence=pricing_confidence,
                strategy_confidence=strategy_confidence,
                execution_risk=execution_risk,
                liquidity=liquidity,
                reasons=reasons,
                source=source,
                verified_version=recipe["verified_version"],
                verification_metadata={
                    "definition_source": recipe["source"],
                    "verified_version": recipe["verified_version"],
                    "price_sources": sorted(source_values),
                    "price_observations": [info.get("observation_type") for info in priced],
                    "observed_at": [info.get("observed_at") for info in priced if info.get("observed_at")],
                },
                inputs=recipe["inputs"],
                costs=recipe["deterministic_costs"] + recipe["probabilistic_costs"],
                outputs=recipe["outputs"],
                execution_steps=recipe["manual_actions"],
            ))
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        bankroll = float(context.get("bankroll", 0) or 0)
        chaos_per_divine = float(context.get("chaos_per_divine", 1) or 1)
        definitions = {record["id"]: record for record in self.registry.records()}
        return [
            route.to_investable(
                status=definitions[route.transformation_id]["status"],
                max_batch=definitions[route.transformation_id]["max_batch"],
                bankroll=bankroll,
                chaos_per_divine=chaos_per_divine,
            )
            for route in self.evaluate(context)
            if route.expected_net_profit > 0
        ]


def _price_info(
    prices: Mapping[str, Any],
    records: Mapping[str, Any],
    item: str,
    category: str | None = None,
) -> dict[str, Any] | None:
    keys = [f"{category}:{item}", item] if category else [item]
    value = next((prices[key] for key in keys if key in prices), None)
    record = next((records[key] for key in keys if key in records), None)
    if value is None and record is not None:
        value = record
    if isinstance(value, Mapping):
        record = value if record is None else record
        price = next((value.get(name) for name in ("price_chaos", "realistic_buy", "realistic_sell", "price")), None)
        volume = value.get("volume")
    else:
        price = value
        volume = None
    if not isinstance(price, (int, float)) or price <= 0:
        return None
    if isinstance(record, Mapping):
        grade = str(record.get("confidence_grade", "")).upper()
        confidence = record.get("confidence")
        confidence = float(confidence) if isinstance(confidence, (int, float)) else {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4}.get(grade, 0.0)
        source = record.get("source", "unknown")
        volume = record.get("volume", volume)
        return {
            "price": float(price), "volume": volume, "confidence": max(0.0, min(1.0, confidence)),
            "source": source, "observation_type": record.get("observation_type"), "observed_at": record.get("observed_at"),
        }
    return {"price": float(price), "volume": volume, "confidence": 0.0, "source": "request", "observation_type": None, "observed_at": None}
class DivCardRecipe(BaseModel):
    """Typed public shape for one versioned divination-card reward."""

    model_config = {"extra": "forbid"}

    id: str
    card: str
    set_size: int
    card_market_key: str
    reward_type: str
    reward_item: str
    reward_quantity: float
    reward_market_key: str
    variant: str
    corrupted: bool
    item_level: int | None
    special_conditions: list[str]
    deterministic: bool
    trusted_distribution: bool = False
    verified_version: str
    poe_patch: str
    source: str
    manual_actions: list[str]
    expected_execution_time_hours: float = 0.25
    expected_sale_time_hours: float = 0.25
    execution_risk: float = 0.0
    strategy_confidence: float = 1.0
    max_batch: int = 1

_DIV_CARD_ALLOWED_KEYS = {
    "id", "card", "set_size", "card_market_key", "reward_type", "reward_item",
    "reward_quantity", "reward_market_key", "variant", "corrupted", "item_level",
    "special_conditions", "deterministic", "trusted_distribution", "outcomes",
    "verified_version", "poe_patch", "source", "manual_actions", "expected_execution_time_hours",
    "expected_sale_time_hours", "execution_risk", "strategy_confidence", "max_batch",
}


def validate_div_card_recipe(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one explicit, canonical-keyed divination-card reward."""
    if not isinstance(record, Mapping):
        raise ValueError("divination-card recipe must be an object")
    unknown = set(record) - _DIV_CARD_ALLOWED_KEYS
    if unknown:
        raise ValueError(f"unmodelled divination-card fields: {sorted(unknown)}")
    required = {
        "id", "card", "set_size", "card_market_key", "reward_type", "reward_item",
        "reward_quantity", "reward_market_key", "variant", "corrupted", "item_level",
        "special_conditions", "deterministic", "verified_version", "poe_patch", "source", "manual_actions",
    }
    missing = required - set(record)
    if missing:
        raise ValueError(f"incomplete divination-card recipe: missing {sorted(missing)}")
    for field in ("id", "card", "reward_type", "reward_item", "card_market_key", "reward_market_key",
                  "verified_version", "poe_patch", "source"):
        if not isinstance(record[field], str) or not record[field].strip():
            raise ValueError(f"{field} is required")
    for field in ("card_market_key", "reward_market_key"):
        if ":" not in record[field] or record[field].startswith(":") or record[field].endswith(":"):
            raise ValueError(f"{field} must be a canonical category:item key")
    if not isinstance(record["set_size"], int) or record["set_size"] <= 0:
        raise ValueError("set_size must be a positive integer")
    if not isinstance(record["reward_quantity"], (int, float)) or record["reward_quantity"] <= 0:
        raise ValueError("reward_quantity must be positive")
    if not isinstance(record["variant"], str) or not isinstance(record["corrupted"], bool):
        raise ValueError("variant and corrupted must be typed")
    if record["item_level"] is not None and (
        not isinstance(record["item_level"], int) or record["item_level"] < 0
    ):
        raise ValueError("item_level must be a non-negative integer or null")
    if not isinstance(record["special_conditions"], list) or not all(
        isinstance(item, str) and item.strip() for item in record["special_conditions"]
    ):
        raise ValueError("special_conditions must be a list of non-empty strings")
    if not isinstance(record["deterministic"], bool):
        raise ValueError("deterministic must be boolean")
    if record["deterministic"] and (
        record["corrupted"]
        or any(token in record["reward_type"].casefold() for token in ("random", "influenced", "corrupted"))
        or any(token in condition.casefold() for condition in record["special_conditions"]
               for token in ("random", "influenced", "corrupted"))
    ):
        raise ValueError("random, corrupted, and influenced rewards are not deterministic")
    if not isinstance(record["manual_actions"], list) or not all(
        isinstance(item, str) and item.strip() for item in record["manual_actions"]
    ):
        raise ValueError("manual_actions must be a list of non-empty strings")
    result = dict(record)
    result.setdefault("trusted_distribution", False)
    result.setdefault("outcomes", [])
    result.setdefault("expected_execution_time_hours", 0.25)
    result.setdefault("expected_sale_time_hours", 0.25)
    result.setdefault("execution_risk", 0.0)
    result.setdefault("strategy_confidence", 1.0)
    result.setdefault("max_batch", 1)
    if not isinstance(result["trusted_distribution"], bool) or not isinstance(result["outcomes"], list):
        raise ValueError("trusted_distribution and outcomes are invalid")
    if result["deterministic"] and result["outcomes"]:
        raise ValueError("deterministic recipes cannot also define outcomes")
    if not result["deterministic"]:
        if not result["trusted_distribution"] or not result["outcomes"]:
            raise ValueError("non-deterministic rewards require a trusted finite distribution")
        total = 0.0
        for outcome in result["outcomes"]:
            if not isinstance(outcome, Mapping):
                raise ValueError("outcomes must contain objects")
            allowed = {"reward_item", "reward_quantity", "reward_market_key", "probability", "reward_type"}
            if set(outcome) - allowed or not {"reward_item", "reward_quantity", "reward_market_key", "probability"} <= set(outcome):
                raise ValueError("outcome fields are incomplete")
            if not isinstance(outcome["reward_market_key"], str) or ":" not in outcome["reward_market_key"]:
                raise ValueError("outcome reward_market_key must be canonical")
            if not isinstance(outcome["reward_quantity"], (int, float)) or outcome["reward_quantity"] <= 0:
                raise ValueError("outcome reward_quantity must be positive")
            if not isinstance(outcome["probability"], (int, float)) or not 0 < outcome["probability"] <= 1:
                raise ValueError("outcome probability must be in (0, 1]")
            total += float(outcome["probability"])
        if abs(total - 1.0) > 1e-9:
            raise ValueError("outcome probabilities must sum to 1")
    for field in ("expected_execution_time_hours", "expected_sale_time_hours", "execution_risk", "strategy_confidence"):
        if not isinstance(result[field], (int, float)) or result[field] < 0:
            raise ValueError(f"{field} must be non-negative")
    if not isinstance(result["max_batch"], int) or result["max_batch"] < 1:
        raise ValueError("max_batch must be a positive integer")
    if result["execution_risk"] > 1 or result["strategy_confidence"] > 1:
        raise ValueError("execution_risk and strategy_confidence must be at most 1")
    return result


STALE_RECIPE_POLICY = "reject"


class DivCardRegistry:
    """Versioned registry with a separate Path of Exile verification patch."""

    def __init__(
        self,
        records: Sequence[Mapping[str, Any]] = (),
        *,
        version: str = "unverified",
        source: str = "unverified",
        poe_patch: str | None = None,
        verified_leagues: Sequence[str] = (),
    ) -> None:
        records = tuple(records)
        if not all(isinstance(value, str) and value.strip() for value in (version, source)):
            raise ValueError("registry version and source are required")
        if poe_patch is None:
            patches = {str(record.get("poe_patch", "")).strip() for record in records}
            if len(patches) != 1 or not next(iter(patches), ""):
                raise ValueError("registry poe_patch is required when recipes do not share one patch")
            poe_patch = next(iter(patches))
        if not isinstance(poe_patch, str) or not poe_patch.strip():
            raise ValueError("registry poe_patch is required")
        if not all(isinstance(league, str) and league.strip() for league in verified_leagues):
            raise ValueError("verified_leagues must contain non-empty league names")
        self.version = version
        self.source = source
        self.poe_patch = poe_patch
        self.verified_leagues = frozenset(verified_leagues)
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            normalized = validate_div_card_recipe(record)
            if normalized["verified_version"] != self.version:
                if STALE_RECIPE_POLICY == "reject":
                    raise ValueError(
                        f"stale divination-card recipe {normalized['id']} from {normalized['source']}: "
                        f"verified_version {normalized['verified_version']} != registry version {self.version}"
                    )
                continue
            if normalized["poe_patch"] != self.poe_patch:
                if STALE_RECIPE_POLICY == "reject":
                    raise ValueError(
                        f"stale divination-card recipe {normalized['id']} from {normalized['source']}: "
                        f"poe_patch {normalized['poe_patch']} != registry patch {self.poe_patch}"
                    )
                continue
            if normalized["id"] in self._records:
                raise ValueError(f"duplicate divination-card recipe: {normalized['id']}")
            self._records[normalized["id"]] = normalized

    @classmethod
    def from_json(cls, path: str | Path) -> "DivCardRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {"version", "source", "poe_patch", "verified_leagues", "recipes"}
        if not isinstance(payload, Mapping) or set(payload) != required:
            raise ValueError(
                "divination-card registry must contain version, source, poe_patch, "
                "verified_leagues, and recipes"
            )
        if not isinstance(payload["recipes"], list) or not isinstance(payload["verified_leagues"], list):
            raise ValueError("divination-card recipes and verified_leagues must be lists")
        return cls(
            payload["recipes"],
            version=payload["version"],
            source=payload["source"],
            poe_patch=payload["poe_patch"],
            verified_leagues=payload["verified_leagues"],
        )

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self._records.values())


def default_div_card_registry() -> DivCardRegistry:
    return DivCardRegistry.from_json(Path(__file__).with_name("div_card_recipes.json"))


def _exact_price_info(
    prices: Mapping[str, Any], records: Mapping[str, Any], key: str,
) -> dict[str, Any] | None:
    """Price only the exact canonical key; never fall back to item names."""
    value = prices.get(key)
    record = records.get(key)
    if value is None:
        value = record
    if isinstance(value, Mapping):
        record = value if record is None else record
        price = next((value.get(name) for name in ("price_chaos", "realistic_buy", "realistic_sell", "price")), None)
    else:
        price = value
    if not isinstance(price, (int, float)) or not math.isfinite(float(price)) or price <= 0:
        return None
    record = record if isinstance(record, Mapping) else {}
    grade = str(record.get("confidence_grade", "")).upper()
    confidence = record.get("confidence")
    confidence = float(confidence) if isinstance(confidence, (int, float)) else {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4}.get(grade, 0.0)
    return {
        "price": float(price),
        "confidence": max(0.0, min(1.0, confidence)),
        "source": record.get("source", "request"),
        "observed_at": record.get("observed_at"),
    }


def _consume_depth(levels: Any, quantity: float, *, buy: bool) -> tuple[float, float] | None:
    if not isinstance(levels, list) or quantity <= 0:
        return None
    remaining = float(quantity)
    total = 0.0
    filled = 0.0
    for level in levels:
        if not isinstance(level, Mapping):
            return None
        price, available = level.get("price"), level.get("quantity")
        if not isinstance(price, (int, float)) or not isinstance(available, (int, float)) or price <= 0 or available <= 0:
            return None
        take = min(remaining, float(available))
        total += take * float(price)
        filled += take
        remaining -= take
        if remaining <= 1e-9:
            return total, filled
    return None


def _quote_info(execution_prices: Mapping[str, Any], key: str, *, side: str) -> dict[str, Any] | None:
    quote = execution_prices.get(key)
    if not isinstance(quote, Mapping) or not isinstance(quote.get("stale", False), bool) or quote.get("stale", False):
        return None
    levels = quote.get("buy_levels" if side == "buy" else "sell_levels")
    fee = quote.get("buy_fee_rate" if side == "buy" else "sell_fee_rate", quote.get("fee_rate", 0))
    if not isinstance(fee, (int, float)) or isinstance(fee, bool) or not 0 <= fee < 1:
        return None
    if not isinstance(levels, list) or not levels:
        return None
    observed_at = quote.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at:
        return None
    try:
        parsed_observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed_observed_at.tzinfo is None:
        return None
    now = datetime.now(timezone.utc)
    if parsed_observed_at > now or now - parsed_observed_at > _EXECUTION_QUOTE_MAX_AGE:
        return None
    confidence = quote.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        return None
    source = quote.get("source")
    if not isinstance(source, str) or not source:
        return None
    return {"levels": levels, "fee": float(fee), "observed_at": observed_at,
            "confidence": float(confidence), "source": source, "stale": quote.get("stale", False)}

def evaluate_batch_ladder(
    *,
    set_size: int,
    outcomes: Sequence[Mapping[str, Any]],
    buy_quote: Mapping[str, Any] | None,
    sell_quotes: Sequence[Mapping[str, Any] | None],
    max_batch: int,
    budget_chaos: float,
    time_horizon_hours: float,
    capital_lock_time: float,
) -> list[dict[str, Any]]:
    """Evaluate mutually exclusive outcomes conditionally, then weight EV.

    Each branch must have depth for its full conditional reward quantity;
    branches are not sold simultaneously. Expected quantities are retained
    for audit while conditional liquidation values are probability-weighted.
    """
    if not buy_quote or len(sell_quotes) != len(outcomes) or any(quote is None for quote in sell_quotes):
        return []
    ladder: list[dict[str, Any]] = []
    for batch_size in range(1, max(0, int(max_batch)) + 1):
        buy_fill = _consume_depth(buy_quote["levels"], batch_size * set_size, buy=True)
        if buy_fill is None:
            break
        input_cost = buy_fill[0] * (1 + float(buy_quote["fee"]))
        if budget_chaos > 0 and input_cost > budget_chaos + 1e-9:
            break
        if batch_size * capital_lock_time > time_horizon_hours + 1e-9:
            break
        output_value = 0.0
        liquidation_values: list[float] = []
        outcome_capacities: list[int] = []
        expected_quantities: list[float] = []
        for outcome, quote in zip(outcomes, sell_quotes, strict=True):
            sell_fill = _consume_depth(quote["levels"], batch_size * float(outcome["reward_quantity"]), buy=False)
            if sell_fill is None:
                return ladder
            liquidation = sell_fill[0] * (1 - float(quote["fee"]))
            liquidation_values.append(liquidation)
            expected_quantities.append(batch_size * float(outcome["reward_quantity"]) * float(outcome["probability"]))
            outcome_capacities.append(int(sum(float(level["quantity"]) for level in quote["levels"]) // float(outcome["reward_quantity"])))
            output_value += float(outcome["probability"]) * liquidation
        net = output_value - input_cost
        previous_net = ladder[-1]["safe_net_chaos"] if ladder else 0.0
        if net <= 0 or net - previous_net <= 0:
            break
        ladder.append({
            "batch_size": batch_size,
            "input_cost_chaos": input_cost,
            "executable_output_chaos": output_value,
            "safe_net_chaos": net,
            "roi": net / input_cost,
            "liquidation_values_chaos": liquidation_values,
            "outcome_capacities": outcome_capacities,
            "expected_quantities": expected_quantities,
        })
    return ladder
class DivinationCardStrategyProvider:
    """Evaluate deterministic/trusted div-card sets using exact market keys and depth."""

    def __init__(self, registry: DivCardRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        prices = context.get("prices", {})
        records = context.get("price_records", {})
        execution_prices = context.get("execution_prices", {})
        active_version = context.get("active_registry_version")
        active_poe_patch = context.get("active_poe_patch")
        league = context.get("league")
        horizon = max(0.0, float(context.get("capacity_horizon_hours", 24) or 24))
        budget = context.get("budget_chaos")
        if budget is None and context.get("bankroll") is not None:
            budget = float(context.get("bankroll", 0) or 0) * float(context.get("chaos_per_divine", 1) or 1)
        budget = max(0.0, float(budget or 0))
        routes: list[ProfitRoute] = []
        for recipe in self.registry.records():
            reasons = ["versioned structured div-card registry"]
            if active_version is not None and active_version != self.registry.version:
                continue
            if active_poe_patch is not None and active_poe_patch != recipe["poe_patch"]:
                continue
            if recipe["deterministic"]:
                outcomes = [{
                    "reward_item": recipe["reward_item"], "reward_quantity": recipe["reward_quantity"],
                    "reward_market_key": recipe["reward_market_key"], "probability": 1.0,
                    "reward_type": recipe["reward_type"],
                }]
                reasons.append("deterministic reward eligibility verified")
            else:
                outcomes = recipe["outcomes"]
                reasons.append("trusted finite-outcome reward distribution verified")
            reasons.append(f"verified against PoE patch {recipe['poe_patch']}")
            card_price = _exact_price_info(prices, records, recipe["card_market_key"])
            if card_price is None:
                reasons.append(f"missing market price: {recipe['card_market_key']}")
            theoretical_cost = card_price["price"] * recipe["set_size"] if card_price else None
            theoretical_output = 0.0
            theoretical_confidences = [card_price["confidence"]] if card_price else []
            for outcome in outcomes:
                reward_price = _exact_price_info(prices, records, outcome["reward_market_key"])
                if reward_price is None:
                    reasons.append(f"missing market price: {outcome['reward_market_key']}")
                    theoretical_output = None
                    break
                theoretical_output += float(outcome["probability"]) * float(outcome["reward_quantity"]) * reward_price["price"]
                theoretical_confidences.append(reward_price["confidence"])
            theoretical_roi = (
                (theoretical_output - theoretical_cost) / theoretical_cost
                if theoretical_cost and theoretical_output is not None else None
            )
            theoretical_net = (theoretical_output * (1 - float(recipe.get("sale_fee_rate", 0))) - theoretical_cost) if theoretical_output is not None and theoretical_cost else None
            active_time = float(recipe["expected_execution_time_hours"])
            capital_lock_time = max(0.25, active_time + float(recipe["expected_sale_time_hours"]))
            buy_quote = _quote_info(execution_prices, recipe["card_market_key"], side="buy")
            sell_quotes = [_quote_info(execution_prices, outcome["reward_market_key"], side="sell") for outcome in outcomes]
            if not buy_quote:
                reasons.append(f"missing buy depth: {recipe['card_market_key']}")
            for outcome, quote in zip(outcomes, sell_quotes, strict=True):
                if not quote:
                    reasons.append(f"missing sell bid depth: {outcome['reward_market_key']}")
            first_buy = _consume_depth(buy_quote["levels"], recipe["set_size"], buy=True) if buy_quote else None
            executable_cost = first_buy[0] * (1 + buy_quote["fee"]) if first_buy and buy_quote else None
            executable_output = None
            first_liquidations: list[float] = []
            if first_buy and buy_quote and all(sell_quotes):
                executable_output = 0.0
                for outcome, quote in zip(outcomes, sell_quotes, strict=True):
                    fill = _consume_depth(quote["levels"], float(outcome["reward_quantity"]), buy=False)
                    if fill is None:
                        executable_output = None
                        break
                    liquidation = fill[0] * (1 - quote["fee"])
                    first_liquidations.append(liquidation)
                    executable_output += float(outcome["probability"]) * liquidation
            executable_roi = (
                (executable_output - executable_cost) / executable_cost
                if executable_cost and executable_output is not None else None
            )
            market_ladder = evaluate_batch_ladder(
                set_size=recipe["set_size"], outcomes=outcomes, buy_quote=buy_quote,
                sell_quotes=sell_quotes, max_batch=recipe.get("max_batch", 1), budget_chaos=0,
                time_horizon_hours=float("inf"), capital_lock_time=capital_lock_time,
            )
            budget_ladder = evaluate_batch_ladder(
                set_size=recipe["set_size"], outcomes=outcomes, buy_quote=buy_quote,
                sell_quotes=sell_quotes, max_batch=recipe.get("max_batch", 1), budget_chaos=budget,
                time_horizon_hours=float("inf"), capital_lock_time=capital_lock_time,
            )
            recommended_ladder = evaluate_batch_ladder(
                set_size=recipe["set_size"], outcomes=outcomes, buy_quote=buy_quote,
                sell_quotes=sell_quotes, max_batch=recipe.get("max_batch", 1), budget_chaos=budget,
                time_horizon_hours=horizon, capital_lock_time=capital_lock_time,
            )
            market_capacity = len(market_ladder)
            budget_capacity = len(budget_ladder) if budget > 0 else market_capacity
            recommended_capacity = len(recommended_ladder)
            net = float(executable_output - executable_cost) if executable_output is not None and executable_cost is not None else 0.0
            if executable_output is not None:
                reasons.append("depth-aware executable buy and probability-weighted liquidation quotes")
            else:
                reasons.append("executable depth unavailable; scalable capacity is zero")
            if theoretical_roi is not None and executable_output is None:
                reasons.append("theoretical pricing is available; execution remains unverified")
            reasons.append("positive executable set profit" if net > 0 else "no positive executable profit")
            if market_capacity < 1 and buy_quote and all(sell_quotes):
                reasons.append("no positive-safe batch remains after cumulative depth evaluation")
            status = (
                "executable" if executable_output is not None and executable_cost is not None and market_capacity > 0
                else "non_executable" if executable_output is not None and executable_cost is not None
                else "theoretical" if theoretical_roi is not None
                else "insufficient_evidence"
            )
            quote_confidences = [buy_quote["confidence"]] + [quote["confidence"] for quote in sell_quotes if quote] if buy_quote else []
            quote_sources = [buy_quote["source"]] + [quote["source"] for quote in sell_quotes if quote] if buy_quote else []
            quote_times = [buy_quote["observed_at"]] + [quote["observed_at"] for quote in sell_quotes if quote] if buy_quote else []
            pricing_confidence = min(quote_confidences) if quote_confidences else 0.0
            strategy_confidence = float(recipe["strategy_confidence"])
            confidence = pricing_confidence * strategy_confidence if quote_confidences else 0.0
            unique_sources = sorted(set(quote_sources))
            source = unique_sources[0] if len(unique_sources) == 1 else "mixed" if unique_sources else recipe["source"]
            input_cost = executable_cost if executable_cost is not None else theoretical_cost
            output_value = executable_output if executable_output is not None else theoretical_output
            outcome_outputs = []
            outcome_liquidation = []
            for index, outcome in enumerate(outcomes):
                quote = sell_quotes[index]
                capacity = int(sum(float(level["quantity"]) for level in quote["levels"]) // float(outcome["reward_quantity"])) if quote else 0
                outcome_outputs.append({**outcome, "liquidation_capacity_sets": capacity})
                outcome_liquidation.append({"probability": float(outcome["probability"]), "capacity_sets": capacity})
            route = ProfitRoute(
                transformation_id=recipe["id"], name=f"{recipe['card']} set arbitrage",
                strategy_family="divination_card", status=status, league=league, category="DivinationCard",
                total_input_cost=float(input_cost or 0), realistic_output_value=float(output_value or 0),
                gross_profit=float((output_value or 0) - (input_cost or 0)), expected_net_profit=net,
                roi=float(executable_roi or 0), theoretical_roi=theoretical_roi, executable_roi=executable_roi,
                capital_required=float(executable_cost or theoretical_cost or 0), capacity=float(recommended_capacity),
                theoretical_net_profit=theoretical_net,
                executable_net_profit=net if executable_output is not None else None,
                capacity_units="sets", active_execution_time=active_time, capital_lock_time=capital_lock_time,
                elapsed_cycle_time=capital_lock_time,
                profit_per_active_hour=float(net / max(0.25, active_time)),
                roi_per_lock_hour=float((executable_roi or 0) / capital_lock_time),
                profit_per_set=float(net), budget_capacity=budget_capacity,
                recommended_capacity=recommended_capacity, estimated_sets_per_lock_hour=float(1 / capital_lock_time) if market_capacity else 0.0,
                market_capacity=market_capacity, time_horizon_hours=horizon,
                capacity_assumptions=["capacity is measured in complete sets", "buy and sell depth are consumed cumulatively", "unknown or stale depth produces zero scalable sets"],
                reasons=list(reasons), confidence=confidence, pricing_confidence=pricing_confidence,
                strategy_confidence=strategy_confidence, execution_risk=float(recipe["execution_risk"] if buy_quote else 1.0),
                liquidity={"tier": validation.liquidity_tier(float(market_capacity)), "volume": market_capacity, "capacity_units": "sets", "outcomes": outcome_liquidation},
                source=source, verified_version=recipe["verified_version"], poe_patch=recipe["poe_patch"],
                verification_metadata={
                    "registry_version": self.registry.version, "registry_source": self.registry.source,
                    "definition_source": recipe["source"], "verified_version": recipe["verified_version"],
                    "poe_patch": recipe["poe_patch"], "active_poe_patch": active_poe_patch,
                    "manual_actions": list(recipe["manual_actions"]), "variant": recipe["variant"],
                    "corrupted": recipe["corrupted"], "item_level": recipe["item_level"],
                    "special_conditions": list(recipe["special_conditions"]), "card_market_key": recipe["card_market_key"],
                    "reward_market_keys": [outcome["reward_market_key"] for outcome in outcomes],
                    "quote_sources": sorted(set(quote_sources)), "quote_timestamps": sorted(set(quote_times)),
                    "outcome_liquidation": outcome_liquidation, "batch_ladder": recommended_ladder,
                    "eligibility": "deterministic" if recipe["deterministic"] else "trusted_finite_distribution",
                },
                inputs=[{"item": recipe["card"], "market_key": recipe["card_market_key"], "quantity": recipe["set_size"]}],
                costs=[{"item": recipe["card"], "market_key": recipe["card_market_key"], "quantity": recipe["set_size"], "side": "buy"}],
                outputs=outcome_outputs, execution_steps=list(recipe["manual_actions"]),
            )
            routes.append(route)
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        definitions = {record["id"]: record for record in self.registry.records()}
        bankroll = float(context.get("bankroll", 0) or 0)
        chaos_per_divine = float(context.get("chaos_per_divine", 1) or 1)
        return [
            route.to_investable(
                status="Validated",
                max_batch=max(1, route.recommended_capacity),
                bankroll=bankroll,
                chaos_per_divine=chaos_per_divine,
            )
            for route in self.evaluate(context)
            if route.expected_net_profit > 0 and route.market_capacity > 0 and route.recommended_capacity > 0
            and definitions[route.transformation_id]["deterministic"] in (True, False)
        ]


_DETERMINISTIC_LIFECYCLE = {item.value for item in StrategyLifecycle}
_DETERMINISTIC_COMPONENT_KEYS = {"item", "item_id", "market_key", "quantity", "category"}
_DETERMINISTIC_RECORD_KEYS = {
    "id", "name", "inputs", "outputs", "conversion_costs", "friction_chaos",
    "status", "category", "source", "verified_version", "poe_patch",
    "strategy_confidence", "max_batch", "expected_execution_time_hours",
    "expected_sale_time_hours", "sale_fee_rate", "output_discount_rate",
    "manual_actions",
}


def _deterministic_components(value: Any, field_name: str, *, one: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or (one and len(value) != 1):
        raise ValueError(f"{field_name} must be a non-empty list")
    result: list[dict[str, Any]] = []
    for component in value:
        if not isinstance(component, Mapping) or set(component) - _DETERMINISTIC_COMPONENT_KEYS:
            raise ValueError(f"{field_name} contains an unsupported component")
        item = component.get("item")
        market_key = component.get("market_key")
        quantity = component.get("quantity")
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} item is required")
        if not isinstance(market_key, str) or not market_key.strip():
            raise ValueError(f"{field_name} market_key is required")
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or not math.isfinite(float(quantity)) or quantity <= 0:
            raise ValueError(f"{field_name} quantity must be positive")
        result.append(dict(component))
    return result


def _validate_deterministic_record(record: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError(f"{kind} transformation must be an object")
    unknown = set(record) - _DETERMINISTIC_RECORD_KEYS
    if unknown:
        raise ValueError(f"unmodelled {kind} fields: {sorted(unknown)}")
    required = {"id", "name", "inputs", "outputs", "source", "verified_version"}
    missing = required - set(record)
    if missing:
        raise ValueError(f"incomplete {kind} transformation: missing {sorted(missing)}")
    if not isinstance(record["id"], str) or not record["id"].strip():
        raise ValueError(f"{kind} transformation id is required")
    if record.get("status", StrategyLifecycle.VALIDATED.value) not in _DETERMINISTIC_LIFECYCLE:
        raise ValueError("unknown strategy lifecycle")
    if not isinstance(record["source"], str) or not record["source"].strip() or record["source"] == "unverified":
        raise ValueError(f"{kind} source must be verified")
    if not isinstance(record["verified_version"], str) or not record["verified_version"].strip() or record["verified_version"] == "unverified":
        raise ValueError(f"{kind} verified_version is required")
    result = dict(record)
    result["inputs"] = _deterministic_components(record["inputs"], "inputs")
    result["outputs"] = _deterministic_components(record["outputs"], "outputs", one=True)
    result["conversion_costs"] = _deterministic_components(record.get("conversion_costs", []), "conversion_costs") if record.get("conversion_costs") else []
    result.setdefault("status", StrategyLifecycle.VALIDATED.value)
    result.setdefault("category", "Transformation")
    result.setdefault("poe_patch", None)
    result.setdefault("strategy_confidence", 1.0)
    result.setdefault("max_batch", 1)
    result.setdefault("friction_chaos", 0.0)
    result.setdefault("expected_execution_time_hours", 0.25)
    result.setdefault("expected_sale_time_hours", 0.0)
    result.setdefault("sale_fee_rate", 0.0)
    result.setdefault("output_discount_rate", 0.0)
    result.setdefault("manual_actions", [])
    for field in ("friction_chaos", "expected_execution_time_hours", "expected_sale_time_hours", "sale_fee_rate", "output_discount_rate", "strategy_confidence"):
        value = result[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or value < 0:
            raise ValueError(f"{field} must be non-negative")
    if result["expected_execution_time_hours"] <= 0:
        raise ValueError("expected_execution_time_hours must be positive")
    if result["sale_fee_rate"] >= 1 or result["output_discount_rate"] >= 1 or result["strategy_confidence"] > 1:
        raise ValueError("fee, discount, and strategy_confidence values are out of range")
    if not isinstance(result["max_batch"], int) or result["max_batch"] < 1:
        raise ValueError("max_batch must be a positive integer")
    if not isinstance(result["manual_actions"], list):
        raise ValueError("manual_actions must be a list")
    return result


class DeterministicTransformationRegistry:
    """Verified, exact-key transformations used by the bounded graph providers."""

    def __init__(self, records: Sequence[Mapping[str, Any]] = (), *, kind: str = "deterministic") -> None:
        self.kind = kind
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            self.register(record)

    def register(self, record: Mapping[str, Any]) -> None:
        normalized = _validate_deterministic_record(record, kind=self.kind)
        if normalized["id"] in self._records:
            raise ValueError(f"duplicate transformation: {normalized['id']}")
        self._records[normalized["id"]] = normalized

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self._records.values())


class AssemblyTransformationRegistry:
    """Registry for explicit part/whole recipes; no recipe is inferred."""

    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            self.register(record)

    def register(self, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping):
            raise ValueError("assembly transformation must be an object")
        allowed = _DETERMINISTIC_RECORD_KEYS | {"parts", "whole", "direction"}
        unknown = set(record) - allowed
        if unknown:
            raise ValueError(f"unmodelled assembly fields: {sorted(unknown)}")
        if "parts" not in record or "whole" not in record:
            raise ValueError("assembly transformation requires parts and whole")
        parts = _deterministic_components(record["parts"], "parts")
        whole = _deterministic_components(record["whole"], "whole", one=True)
        direction = record.get("direction", "assemble")
        if direction not in {"assemble", "disassemble", "both"}:
            raise ValueError("direction must be assemble, disassemble, or both")
        normalized = {
            key: value for key, value in record.items()
            if key in _DETERMINISTIC_RECORD_KEYS
        }
        normalized.update({"inputs": parts, "outputs": whole})
        normalized = _validate_deterministic_record(normalized, kind="assembly")
        normalized["direction"] = direction
        normalized["parts"] = parts
        normalized["whole"] = whole
        if normalized["id"] in self._records:
            raise ValueError(f"duplicate transformation: {normalized['id']}")
        self._records[normalized["id"]] = normalized

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self._records.values())


class VendorTransformationRegistry(DeterministicTransformationRegistry):
    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        super().__init__(records, kind="vendor")


class SixLinkRegistry:
    """Registry for known item identities and deterministic linking methods."""

    def __init__(self, records: Sequence[Mapping[str, Any]] = ()) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        for record in records:
            self.register(record)

    def register(self, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping):
            raise ValueError("six-link transformation must be an object")
        allowed = _DETERMINISTIC_RECORD_KEYS | {
            "item_id", "base", "linked", "linking_costs", "linking_method",
        }
        unknown = set(record) - allowed
        if unknown:
            raise ValueError(f"unmodelled six-link fields: {sorted(unknown)}")
        required = {"id", "name", "item_id", "base", "linked", "linking_method", "source", "verified_version"}
        missing = required - set(record)
        if missing:
            raise ValueError(f"incomplete six-link transformation: missing {sorted(missing)}")
        if not isinstance(record["item_id"], str) or not record["item_id"].strip():
            raise ValueError("six-link item_id is required")
        base = _deterministic_components([record["base"]], "base", one=True)
        linked = _deterministic_components([record["linked"]], "linked", one=True)
        if base[0].get("item_id", record["item_id"]) != record["item_id"] or linked[0].get("item_id", record["item_id"]) != record["item_id"]:
            raise ValueError("base and linked variants must identify the same item")
        normalized = {
            key: value for key, value in record.items()
            if key in _DETERMINISTIC_RECORD_KEYS
        }
        normalized.update({"inputs": base, "outputs": linked, "conversion_costs": record.get("linking_costs", [])})
        normalized = _validate_deterministic_record(normalized, kind="six-link")
        normalized["item_id"] = record["item_id"]
        normalized["linking_method"] = record["linking_method"]
        normalized["linking_costs"] = normalized["conversion_costs"]
        if not isinstance(normalized["linking_method"], str) or not normalized["linking_method"].strip():
            raise ValueError("linking_method is required")
        if normalized["id"] in self._records:
            raise ValueError(f"duplicate transformation: {normalized['id']}")
        self._records[normalized["id"]] = normalized

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(record) for record in self._records.values())


def default_assembly_registry() -> AssemblyTransformationRegistry:
    return AssemblyTransformationRegistry()


def default_vendor_registry() -> VendorTransformationRegistry:
    return VendorTransformationRegistry()


def default_six_link_registry() -> SixLinkRegistry:
    return SixLinkRegistry()


def _verified_component_price(context: Mapping[str, Any], component: Mapping[str, Any]) -> dict[str, Any] | None:
    info = _exact_price_info(
        context.get("prices", {}),
        context.get("price_records", {}),
        str(component["market_key"]),
    )
    minimum = float(context.get("minimum_strategy_confidence", 0.7) or 0.7)
    if info is None or info["confidence"] < minimum:
        return None
    value = context.get("prices", {}).get(str(component["market_key"]))
    record = context.get("price_records", {}).get(str(component["market_key"]))
    if not isinstance(record, Mapping):
        record = value if isinstance(value, Mapping) else {}
    volume = record.get("volume") if isinstance(record, Mapping) else None
    info["volume"] = float(volume) if isinstance(volume, (int, float)) and volume > 0 else None
    return info


def _deferred_route(
    record: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    route_id: str | None = None,
    name: str | None = None,
    inputs: Sequence[Mapping[str, Any]] | None = None,
    outputs: Sequence[Mapping[str, Any]] | None = None,
    conversion_costs: Sequence[Mapping[str, Any]] | None = None,
    friction_chaos: float | None = None,
) -> ProfitRoute | None:
    if record.get("poe_patch") and context.get("active_poe_patch") != record["poe_patch"]:
        return None
    inputs = list(inputs or record["inputs"])
    outputs = list(outputs or record["outputs"])
    conversion_costs = list(conversion_costs if conversion_costs is not None else record.get("conversion_costs", []))
    all_costs = inputs + conversion_costs
    prices = [_verified_component_price(context, item) for item in all_costs + outputs]
    if any(item is None for item in prices):
        return None
    cost_info = prices[:len(all_costs)]
    output_info = prices[len(all_costs):]
    material_cost = sum(float(item["quantity"]) * info["price"] for item, info in zip(all_costs, cost_info, strict=True))
    friction = float(record.get("friction_chaos", 0) if friction_chaos is None else friction_chaos)
    total_cost = material_cost + friction
    discount = float(record.get("output_discount_rate", 0))
    output_value = sum(float(item["quantity"]) * info["price"] for item, info in zip(outputs, output_info, strict=True)) * (1 - discount)
    sale_fee = float(record.get("sale_fee_rate", 0))
    net = output_value * (1 - sale_fee) - total_cost
    confidence_values = [item["confidence"] for item in prices if item is not None]
    pricing_confidence = min(confidence_values)
    strategy_confidence = float(record.get("strategy_confidence", 1.0))
    confidence = pricing_confidence * strategy_confidence
    capacities = [info["volume"] / float(component["quantity"]) for component, info in zip(all_costs + outputs, prices, strict=True) if info["volume"]]
    capacity = min([float(record.get("max_batch", 1)), *capacities]) if capacities else float(record.get("max_batch", 1))
    manual = list(record.get("manual_actions", []))
    source_values = sorted({str(info["source"]) for info in prices})
    source = source_values[0] if len(source_values) == 1 else "mixed"
    route_status = "manual_only" if manual else "theoretical"
    active_time = float(record["expected_execution_time_hours"])
    capital_lock_time = max(0.25, active_time + float(record.get("expected_sale_time_hours", 0)))
    # Snapshot volumes are reference liquidity; no exact executable ladder exists here.
    market_capacity = budget_capacity = recommended_capacity = 0

    reasons = [
        "verified deterministic transformation",
        f"definition source: {record['source']} ({record['verified_version']})",
        "positive expected net profit" if net > 0 else "negative expected net profit",
    ]
    if manual:
        reasons.append("manual-only execution; automatic allocation is disabled")
    reasons.append("exact executable depth unavailable; executable capacity is zero")
    return ProfitRoute(
        transformation_id=str(route_id or record["id"]),
        name=str(name or record["name"]),
        strategy_family=str(record.get("strategy_family", "deterministic")),
        status=route_status,
        league=context.get("league"),
        category=str(record.get("category", "Transformation")),
        total_input_cost=total_cost,
        realistic_output_value=output_value,
        gross_profit=output_value - total_cost,
        expected_net_profit=net,
        theoretical_net_profit=net,
        executable_net_profit=None,
        roi=net / total_cost if total_cost > 0 else 0.0,
        theoretical_roi=net / total_cost if total_cost > 0 else None,
        executable_roi=None,
        capital_required=total_cost,
        capacity=float(recommended_capacity),
        capacity_units="items",
        active_execution_time=active_time,
        capital_lock_time=capital_lock_time,
        elapsed_cycle_time=capital_lock_time,
        profit_per_active_hour=net / max(0.25, active_time),
        roi_per_lock_hour=(net / total_cost if total_cost > 0 else 0.0) / capital_lock_time,
        budget_capacity=budget_capacity,
        recommended_capacity=recommended_capacity,
        estimated_sets_per_lock_hour=0.0,
        market_capacity=market_capacity,
        time_horizon_hours=float(context.get("capacity_horizon_hours", 0) or 0),
        capacity_assumptions=["aggregate reference volume is not exact executable depth"],
        reasons=reasons,
        confidence=confidence,
        pricing_confidence=pricing_confidence,
        strategy_confidence=strategy_confidence,
        execution_risk=1.0 if manual else 0.0,
        liquidity={"tier": validation.liquidity_tier(capacity), "volume": capacity, "components": {
            str(component["market_key"]): info["volume"] for component, info in zip(all_costs + outputs, prices, strict=True)
            if info["volume"] is not None
        }},
        source=source,
        verified_version=str(record["verified_version"]),
        poe_patch=record.get("poe_patch"),
        verification_metadata={
            "definition_source": record["source"],
            "verified_version": record["verified_version"],
            "poe_patch": record.get("poe_patch"),
            "price_sources": source_values,
            "market_keys": [str(item["market_key"]) for item in all_costs + outputs],
            "linking_method": record.get("linking_method"),
        },
        inputs=[dict(item) for item in inputs],
        costs=[dict(item) for item in conversion_costs] + ([{"item": "execution friction", "quantity": 1, "chaos": friction}] if friction else []),
        outputs=[dict(item) for item in outputs],
        execution_steps=manual,
    )


class AssemblyStrategyProvider:
    def __init__(self, registry: AssemblyTransformationRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        requested = context.get("category")
        routes: list[ProfitRoute] = []
        for record in self.registry.records():
            if requested and requested not in {record.get("category", "Transformation"), "Transformation"}:
                continue
            if record["status"] in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}:
                continue
            directions = ("assemble", "disassemble") if record["direction"] == "both" else (record["direction"],)
            for direction in directions:
                inputs = record["parts"] if direction == "assemble" else record["whole"]
                outputs = record["whole"] if direction == "assemble" else record["parts"]
                route = _deferred_route(
                    record, context,
                    route_id=record["id"] if direction == "assemble" else f"{record['id']}:disassemble",
                    name=record["name"] if direction == "assemble" else f"{record['name']} (disassembly)",
                    inputs=inputs, outputs=outputs,
                )
                if route:
                    route.strategy_family = "deterministic_assembly"
                    route.verification_metadata["direction"] = direction
                    if direction == "assemble":
                        route.reasons.append(
                            "whole value exceeds part cost" if route.realistic_output_value > route.total_input_cost
                            else "whole value does not exceed part cost"
                        )
                    routes.append(route)
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        return [route.to_investable(status="Validated", max_batch=max(1, int(route.capacity)),
                                    bankroll=float(context.get("bankroll", 0) or 0),
                                    chaos_per_divine=float(context.get("chaos_per_divine", 1) or 1))
                for route in self.evaluate(context)
                if route.expected_net_profit > 0 and route.status != "manual_only"]


class VendorTransformationStrategyProvider:
    def __init__(self, registry: VendorTransformationRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        requested = context.get("category")
        routes = []
        for record in self.registry.records():
            if requested and requested not in {record.get("category", "Transformation"), "Transformation"}:
                continue
            if record["status"] in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}:
                continue
            route = _deferred_route(context=context, record=record)
            if route:
                route.strategy_family = "vendor_transformation"
                routes.append(route)
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        return [route.to_investable(status="Validated", max_batch=max(1, int(route.capacity)),
                                    bankroll=float(context.get("bankroll", 0) or 0),
                                    chaos_per_divine=float(context.get("chaos_per_divine", 1) or 1))
                for route in self.evaluate(context)
                if route.expected_net_profit > 0 and route.status != "manual_only"]


class ArbitrageGraphStrategyProvider:
    """Traverse verified item nodes with a small, loop-free edge bound."""

    def __init__(
        self,
        registries: Sequence[DeterministicTransformationRegistry | AssemblyTransformationRegistry] | DeterministicTransformationRegistry,
        *,
        max_edges: int = 3,
        min_edges: int = 1,
    ) -> None:
        if max_edges < 1 or max_edges > 3 or min_edges < 1 or min_edges > max_edges:
            raise ValueError("graph edge bounds must be between 1 and 3")
        self.registries = (registries,) if hasattr(registries, "records") else tuple(registries)
        self.max_edges = max_edges
        self.min_edges = min_edges

    def _edges(self) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        for registry in self.registries:
            for record in registry.records():
                if len(record["inputs"]) == 1 and len(record["outputs"]) == 1:
                    edges.append(record)
        return edges

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        requested = context.get("category")
        edges = [record for record in self._edges()
                 if record["status"] not in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}
                 and (not requested or requested in {"Transformation", "ArbitrageGraph", record.get("category", "Transformation")})]
        routes: list[ProfitRoute] = []

        def walk(path: list[dict[str, Any]], visited: set[str]) -> None:
            if len(path) >= self.min_edges:
                metadata = {
                    (edge["source"], edge["verified_version"], edge.get("poe_patch"))
                    for edge in path
                }
                if len(metadata) != 1:
                    return
                first, last = path[0], path[-1]
                scales = [1.0] * len(path)
                for index in range(len(path) - 1, 0, -1):
                    required = float(path[index]["inputs"][0]["quantity"]) * scales[index]
                    produced = float(path[index - 1]["outputs"][0]["quantity"])
                    ratio = required / produced
                    if ratio <= 0 or abs(ratio - round(ratio)) > 1e-9:
                        return
                    scales[index - 1] = ratio
                scaled_inputs = [{**first["inputs"][0], "quantity": first["inputs"][0]["quantity"] * scales[0]}]
                scaled_outputs = [{**last["outputs"][0], "quantity": last["outputs"][0]["quantity"] * scales[-1]}]
                conversion_costs: list[dict[str, Any]] = []
                friction = 0.0
                for edge, scale in zip(path, scales, strict=True):
                    conversion_costs.extend(
                        [{**cost, "quantity": cost["quantity"] * scale} for cost in edge.get("conversion_costs", [])]
                    )
                    friction += float(edge.get("friction_chaos", 0)) * scale
                synthetic = {
                    **first,
                    "id": "graph:" + ":".join(edge["id"] for edge in path),
                    "name": " → ".join(edge["name"] for edge in path),
                    "strategy_family": "bounded_arbitrage_graph",
                    "conversion_costs": conversion_costs,
                    "friction_chaos": friction,
                    "expected_execution_time_hours": sum(float(edge["expected_execution_time_hours"]) * scale for edge, scale in zip(path, scales, strict=True)),
                    "expected_sale_time_hours": sum(float(edge.get("expected_sale_time_hours", 0)) for edge in path),
                    "max_batch": min(int(edge.get("max_batch", 1)) for edge in path),
                    "manual_actions": [action for edge in path for action in edge.get("manual_actions", [])],
                }
                route = _deferred_route(
                    synthetic,
                    context,
                    route_id=synthetic["id"],
                    name=synthetic["name"],
                    inputs=scaled_inputs,
                    outputs=scaled_outputs,
                    conversion_costs=conversion_costs,
                    friction_chaos=friction,
                )
                if route:
                    route.strategy_family = "bounded_arbitrage_graph"
                    route.verification_metadata["graph_edges"] = [edge["id"] for edge in path]
                    route.reasons.append(f"bounded graph route ({len(path)} transformation edge(s), maximum {self.max_edges})")
                    routes.append(route)
            if len(path) == self.max_edges:
                return
            current = path[-1]["outputs"][0]["item"] if path else None
            for edge in edges:
                if edge["id"] in visited:
                    continue
                if current is not None and edge["inputs"][0]["item"] != current:
                    continue
                # A node may not be revisited; this prevents currency cycles.
                next_node = edge["outputs"][0]["item"]
                if next_node in {item["inputs"][0]["item"] for item in path}:
                    continue
                walk(path + [edge], visited | {edge["id"]})

        for edge in edges:
            walk([edge], {edge["id"]})
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        return [route.to_investable(status="Validated", max_batch=max(1, int(route.capacity)),
                                    bankroll=float(context.get("bankroll", 0) or 0),
                                    chaos_per_divine=float(context.get("chaos_per_divine", 1) or 1))
                for route in self.evaluate(context)
                if route.expected_net_profit > 0 and route.status != "manual_only"]


class DeterministicSixLinkStrategyProvider:
    def __init__(self, registry: SixLinkRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        requested = context.get("category")
        routes = []
        for record in self.registry.records():
            if requested and requested not in {record.get("category", "SixLink"), "Transformation"}:
                continue
            if record["status"] in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}:
                continue
            route = _deferred_route(context=context, record=record)
            if route:
                route.status = "manual_only"
                route.execution_risk = max(route.execution_risk, 1.0)
                route.reasons.append("manual-only six-link strategy; automatic allocation is disabled")
                route.strategy_family = "deterministic_six_link"
                route.category = record.get("category", "SixLink")
                route.verification_metadata["linking_method"] = record["linking_method"]
                routes.append(route)
        return routes

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        return []


class DeferredDeterministicStrategyProvider:
    """Single integration point for §16–19; empty defaults keep unknown recipes closed."""

    def __init__(
        self,
        assembly: AssemblyTransformationRegistry | None = None,
        vendor: VendorTransformationRegistry | None = None,
        six_link: SixLinkRegistry | None = None,
    ) -> None:
        self.assembly = assembly if assembly is not None else default_assembly_registry()
        self.vendor = vendor if vendor is not None else default_vendor_registry()
        self.six_link = six_link if six_link is not None else default_six_link_registry()

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        assembly = AssemblyStrategyProvider(self.assembly).evaluate(context)
        vendor = VendorTransformationStrategyProvider(self.vendor).evaluate(context)
        graph = ArbitrageGraphStrategyProvider((self.assembly, self.vendor), min_edges=2).evaluate(context)
        six_link = DeterministicSixLinkStrategyProvider(self.six_link).evaluate(context)
        return [*assembly, *vendor, *graph, *six_link]

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        definitions = [AssemblyStrategyProvider(self.assembly), VendorTransformationStrategyProvider(self.vendor),
                       ArbitrageGraphStrategyProvider((self.assembly, self.vendor), min_edges=2),
                       DeterministicSixLinkStrategyProvider(self.six_link)]
        opportunities: list[InvestableOpportunity] = []
        for provider in definitions:
            opportunities.extend(provider.discover(context))
        return opportunities


def default_deferred_strategy_provider() -> DeferredDeterministicStrategyProvider:
    return DeferredDeterministicStrategyProvider()


DeterministicAssemblyRegistry = AssemblyTransformationRegistry
DeterministicVendorRegistry = VendorTransformationRegistry
DeterministicSixLinkRegistry = SixLinkRegistry
DeterministicAssemblyStrategyProvider = AssemblyStrategyProvider
VendorStrategyProvider = VendorTransformationStrategyProvider
SixLinkStrategyProvider = DeterministicSixLinkStrategyProvider
