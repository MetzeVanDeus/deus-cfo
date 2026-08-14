"""Small, declarative strategy providers for normalized opportunities."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from opportunity import InvestableOpportunity


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
    "id", "name", "status", "inputs", "deterministic_costs", "probabilistic_costs",
    "outputs", "expected_execution_time_hours", "requirements", "risk_model",
    "max_batch", "experimental_note",
}
_ALLOWED_LIFECYCLE = {item.value for item in StrategyLifecycle}
_MAX_OUTCOMES = 8


def _components(value: Any, field_name: str, probabilities: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    result = []
    for component in value:
        if not isinstance(component, dict) or set(component) - {"item", "quantity", "probability"}:
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
        result.append(component)
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
    result.setdefault("requirements", {})
    result.setdefault("max_batch", 1)
    if not isinstance(result["requirements"], Mapping) or not isinstance(result["max_batch"], int) or result["max_batch"] < 1:
        raise ValueError("requirements and max_batch are incomplete")
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
    """Evaluate registry records only; no universal opportunity algorithm."""

    def __init__(self, registry: TransformationRegistry) -> None:
        self.registry = registry

    def discover(self, context: Mapping[str, Any]) -> Sequence[InvestableOpportunity]:
        prices = context.get("prices", {})
        opportunities: list[InvestableOpportunity] = []
        current = context.get("now")
        if not isinstance(current, datetime):
            current = datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        created_at = current.isoformat(timespec="seconds")
        for recipe in self.registry.records():
            if recipe["status"] in {StrategyLifecycle.REJECTED.value, StrategyLifecycle.DEPRECATED.value}:
                continue
            input_item = recipe["inputs"][0]["item"]
            output_item = recipe["outputs"][0]["item"]
            entry_price = _price(prices, input_item)
            output_prices = [_price(prices, item["item"]) for item in recipe["outputs"]]
            cost_items = recipe["inputs"] + recipe["deterministic_costs"] + recipe["probabilistic_costs"]
            cost_prices = [_price(prices, item["item"]) for item in cost_items]
            if entry_price is None or any(price is None for price in output_prices + cost_prices):
                continue
            exit_price = sum(item["quantity"] * item["probability"] * price for item, price in zip(recipe["outputs"], output_prices))
            fixed_items = recipe["inputs"] + recipe["deterministic_costs"]
            cost = sum(item["quantity"] * price for item, price in zip(fixed_items, cost_prices))
            variable_prices = cost_prices[len(fixed_items):]
            cost += sum(item["quantity"] * item["probability"] * price for item, price in zip(recipe["probabilistic_costs"], variable_prices))
            if cost <= 0 or exit_price <= 0:
                continue
            duration = float(recipe["expected_execution_time_hours"])
            profit = exit_price - cost
            lifecycle = StrategyLifecycle(recipe["status"])
            metadata = StrategyMetadata(recipe["id"], lifecycle)
            expires_at = context.get("expiration")
            if not isinstance(expires_at, str):
                expires_at = (current + timedelta(hours=duration)).isoformat(timespec="seconds")
            opportunities.append(InvestableOpportunity(
                id=recipe["id"],
                strategy_type="transformation",
                entry_item=input_item,
                exit_item=output_item,
                category="Transformation",
                current_price=entry_price,
                realistic_entry_price=entry_price,
                realistic_exit_price=exit_price,
                expected_return=profit / cost,
                expected_profit_per_unit=profit,
                expected_profit_per_divine_hour=profit / duration,
                win_probability=sum(
                    item["probability"] for item, price in zip(recipe["outputs"], output_prices)
                    if item["quantity"] * price > cost
                ),
                expected_duration=duration,
                duration_distribution=[duration],
                downside_percentile=0.0,
                upside_percentile=max(0.0, profit / cost),
                historical_sample_size=0,
                confidence=float(context.get("confidence", 0.0)),
                liquidity=dict(context.get("liquidity", {})),
                execution_effort=0.0,
                minimum_capital=cost,
                maximum_reasonable_capital=cost * recipe["max_batch"],
                opportunity_capacity=recipe["max_batch"],
                correlation_group="Transformation",
                created_at=created_at,
                last_validated_at=created_at,
                expected_half_life=duration,
                expires_at=expires_at,
                historical_returns=[],
                tier="WATCH" if lifecycle == StrategyLifecycle.EXPERIMENTAL else "B",
                status="ACTIVE",
                rejection_reason=None,
                strategy_status=lifecycle.value,
                experimental_allocation_cap=metadata.experimental_allocation_cap,
                metadata={
                    "name": recipe["name"],
                    "requirements": recipe["requirements"],
                    "allocation_cap": metadata.allocation_cap(float(context.get("bankroll", 0))),
                },
            ))
        return opportunities


def _price(prices: Mapping[str, Any], item: str) -> float | None:
    value = prices.get(item)
    if isinstance(value, Mapping):
        value = value.get("realistic_buy", value.get("realistic_sell", value.get("price")))
    return float(value) if isinstance(value, (int, float)) and value > 0 else None
