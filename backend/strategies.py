"""Small, declarative strategy providers for normalized opportunities."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import validation
from pydantic import BaseModel, Field

from opportunity import InvestableOpportunity


class ProfitRoute(BaseModel):
    """A priced, execution-aware result from one declarative transformation."""

    transformation_id: str
    name: str
    strategy_family: str = "transformation"
    league: str | None = None
    category: str = "Transformation"
    total_input_cost: float
    realistic_output_value: float
    gross_profit: float
    expected_net_profit: float
    roi: float
    capital_required: float
    capacity: float
    expected_execution_time: float
    expected_sale_time: float
    profit_per_hour: float
    profit_per_divine_hour: float = 0.0
    confidence: float = 0.0
    pricing_confidence: float = 0.0
    strategy_confidence: float = 0.0
    execution_risk: float = 0.0
    liquidity: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    source: str = "unverified"
    verified_version: str = "unverified"
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
        duration = max(0.25, self.expected_execution_time + self.expected_sale_time)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(hours=duration)).isoformat(timespec="seconds")
        created_at = now.isoformat(timespec="seconds")
        input_cost = self.total_input_cost / chaos_per_divine
        output_value = self.realistic_output_value / chaos_per_divine
        expected_profit = self.expected_net_profit / chaos_per_divine
        return InvestableOpportunity(
            id=self.transformation_id,
            strategy_type="transformation",
            entry_item=self.inputs[0]["item"] if self.inputs else self.transformation_id,
            exit_item=self.outputs[0]["item"] if self.outputs else None,
            category=self.category,
            current_price=input_cost,
            realistic_entry_price=input_cost,
            realistic_exit_price=output_value,
            expected_return=self.roi,
            expected_profit_per_unit=expected_profit,
            expected_profit_per_divine_hour=self.profit_per_divine_hour,
            win_probability=max(0.0, min(1.0, self.confidence)),
            expected_duration=duration,
            duration_distribution=[duration],
            downside_percentile=-self.execution_risk,
            upside_percentile=max(0.0, self.roi),
            historical_sample_size=0,
            confidence=self.confidence,
            liquidity=self.liquidity,
            execution_effort=float(len(self.execution_steps)),
            minimum_capital=input_cost,
            maximum_reasonable_capital=input_cost * max_batch,
            opportunity_capacity=self.capacity * input_cost,
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
            cost = sum(item["quantity"] * info["price"] for item, info in zip(all_costs[:fixed_count], cost_info[:fixed_count]))
            cost += sum(
                item["quantity"] * item["probability"] * info["price"]
                for item, info in zip(recipe["probabilistic_costs"], cost_info[fixed_count:])
            )
            discount = float(recipe["output_discount_rate"])
            output_value = sum(
                item["quantity"] * item["probability"] * info["price"] * (1 - discount)
                for item, info in zip(recipe["outputs"], output_info)
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
            capacity = float(recipe["max_batch"])
            volumes = [
                info["volume"] / item["quantity"]
                for item, info in zip(all_costs, cost_info)
                if info.get("volume") is not None and info["volume"] > 0
            ]
            if volumes:
                capacity = min(capacity, max(0.0, min(volumes)))
            reasons = [
                "deterministic finite-outcome transformation",
                f"definition source: {recipe['source']} ({recipe['verified_version']})",
            ]
            reasons.append("positive expected net profit" if net > 0 else "negative expected net profit")
            if pricing_confidence < 0.7:
                reasons.append("pricing confidence is below 70%")
            if recipe["manual_actions"]:
                reasons.append(f"{len(recipe['manual_actions'])} manual action(s) required")
            chaos_per_divine = float(context.get("chaos_per_divine", 0) or 0)
            routes.append(ProfitRoute(
                transformation_id=recipe["id"],
                name=recipe["name"],
                strategy_family=recipe["strategy_family"],
                league=league,
                category=recipe["category"],
                total_input_cost=cost,
                realistic_output_value=output_value,
                gross_profit=output_value - cost,
                expected_net_profit=net,
                roi=net / cost,
                capital_required=cost,
                capacity=capacity,
                expected_execution_time=duration,
                expected_sale_time=sale_time,
                profit_per_hour=net / total_time,
                profit_per_divine_hour=(net / chaos_per_divine) / total_time if chaos_per_divine > 0 else 0.0,
                confidence=confidence,
                pricing_confidence=pricing_confidence,
                strategy_confidence=strategy_confidence,
                execution_risk=execution_risk,
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
        return [
            route.to_investable(
                status=self.registry._records[route.transformation_id]["status"],
                max_batch=self.registry._records[route.transformation_id]["max_batch"],
                bankroll=bankroll,
                chaos_per_divine=chaos_per_divine,
            )
            for route in self.evaluate(context)
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
