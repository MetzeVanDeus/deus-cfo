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


class ProfitRoute(BaseModel):
    """A priced, execution-aware result from one declarative transformation."""
    transformation_id: str
    name: str
    strategy_family: str = "transformation"
    status: str = "theoretical"
    league: str | None = None
    category: str = "Transformation"
    total_input_cost: float
    realistic_output_value: float
    gross_profit: float
    expected_net_profit: float
    roi: float
    theoretical_roi: float | None = None
    executable_roi: float | None = None
    capital_required: float
    capacity: float
    capacity_units: str = "capital"
    expected_execution_time: float
    expected_sale_time: float
    profit_per_hour: float
    profit_per_divine_hour: float = 0.0
    profit_per_set: float | None = None
    sets_possible_with_budget: int = 0
    estimated_sets_per_hour: float = 0.0
    market_capacity: int = 0
    capacity_horizon_hours: float = 0.0
    capacity_assumptions: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    pricing_confidence: float = 0.0
    strategy_confidence: float = 0.0
    execution_risk: float = 0.0
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
        duration = max(0.25, self.expected_execution_time + self.expected_sale_time)
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
            expected_profit_per_divine_hour=self.profit_per_divine_hour,
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
            capacity = float(recipe["max_batch"])
            volumes = [
                info["volume"] / item["quantity"]
                for item, info in zip(all_costs, cost_info, strict=True)
                if info.get("volume") is not None and info["volume"] > 0
            ]
            if volumes:
                capacity = min(capacity, max(0.0, min(volumes)))
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
            chaos_per_divine = float(context.get("chaos_per_divine", 0) or 0)
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

_DIV_CARD_ALLOWED_KEYS = {
    "id", "card", "set_size", "card_market_key", "reward_type", "reward_item",
    "reward_quantity", "reward_market_key", "variant", "corrupted", "item_level",
    "special_conditions", "deterministic", "trusted_distribution", "outcomes",
    "verified_version", "poe_patch", "source", "manual_actions", "expected_execution_time_hours",
    "expected_sale_time_hours", "execution_risk", "strategy_confidence",
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
        self.version = version
        self.source = source
        self.poe_patch = poe_patch
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
        if not isinstance(payload, Mapping) or set(payload) != {"version", "source", "poe_patch", "recipes"}:
            raise ValueError("divination-card registry must contain version, source, poe_patch, and recipes")
        if not isinstance(payload["recipes"], list):
            raise ValueError("divination-card recipes must be a list")
        return cls(
            payload["recipes"],
            version=payload["version"],
            source=payload["source"],
            poe_patch=payload["poe_patch"],
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
    if not isinstance(quote, Mapping):
        return None
    levels = quote.get("buy_levels" if side == "buy" else "sell_levels")
    fee = quote.get("buy_fee_rate" if side == "buy" else "sell_fee_rate", quote.get("fee_rate", 0))
    if not isinstance(fee, (int, float)) or not 0 <= fee < 1:
        return None
    if not isinstance(quote.get("observed_at"), str) or not quote["observed_at"]:
        return None
    confidence = quote.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        return None
    source = quote.get("source")
    if not isinstance(source, str) or not source:
        return None
    return {"levels": levels, "fee": float(fee), "observed_at": quote["observed_at"],
            "confidence": float(confidence), "source": source}


class DivinationCardStrategyProvider:
    """Evaluate deterministic/trusted div-card sets using exact market keys and depth."""

    def __init__(self, registry: DivCardRegistry) -> None:
        self.registry = registry

    def evaluate(self, context: Mapping[str, Any]) -> Sequence[ProfitRoute]:
        requested_category = context.get("category")
        if requested_category not in (None, "DivinationCard"):
            return []
        prices = context.get("prices", {})
        records = context.get("price_records", {})
        execution_prices = context.get("execution_prices", {})
        active_version = context.get("active_registry_version")
        active_poe_patch = context.get("active_poe_patch")
        league = context.get("league")
        horizon = float(context.get("capacity_horizon_hours", 24) or 24)
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
            buy_quote = _quote_info(execution_prices, recipe["card_market_key"], side="buy")
            buy_fill = _consume_depth(buy_quote["levels"], recipe["set_size"], buy=True) if buy_quote else None
            executable_cost = buy_fill[0] * (1 + buy_quote["fee"]) if buy_fill and buy_quote else None
            sell_fills = []
            sell_capacity: list[int] = []
            quote_confidences = [buy_quote["confidence"]] if buy_quote else []
            quote_sources = [buy_quote["source"]] if buy_quote else []
            quote_times = [buy_quote["observed_at"]] if buy_quote else []
            if not buy_quote or buy_fill is None:
                reasons.append(f"missing buy depth: {recipe['card_market_key']}")
            if buy_quote:
                for outcome in outcomes:
                    sell_quote = _quote_info(execution_prices, outcome["reward_market_key"], side="sell")
                    sell_fill = _consume_depth(sell_quote["levels"], float(outcome["reward_quantity"]), buy=False) if sell_quote else None
                    if sell_fill is None or sell_quote is None:
                        reasons.append(f"missing sell bid depth: {outcome['reward_market_key']}")
                        sell_fills = []
                        break
                    sell_fills.append((float(outcome["probability"]), sell_fill[0] * (1 - sell_quote["fee"])))
                    sell_capacity.append(int(sum(float(level["quantity"]) for level in sell_quote["levels"]) // float(outcome["reward_quantity"])))
                    quote_confidences.append(sell_quote["confidence"])
                    quote_sources.append(sell_quote["source"])
                    quote_times.append(sell_quote["observed_at"])
            executable_output = sum(value for _, value in sell_fills) if sell_fills and len(sell_fills) == len(outcomes) else None
            executable_roi = (
                (executable_output - executable_cost) / executable_cost
                if executable_cost and executable_output is not None else None
            )
            market_capacity = 0
            if buy_quote and buy_fill and sell_capacity:
                buy_capacity = int(sum(float(level["quantity"]) for level in buy_quote["levels"]) // recipe["set_size"])
                market_capacity = min([buy_capacity, *sell_capacity])
            total_time = max(0.25, float(recipe["expected_execution_time_hours"]) + float(recipe["expected_sale_time_hours"]))
            sets_per_hour = 1.0 / total_time if market_capacity else 0.0
            budget_sets = int(budget // executable_cost) if executable_cost and executable_cost > 0 else 0
            time_sets = int(sets_per_hour * horizon)
            sets_possible = min(budget_sets, market_capacity, time_sets) if market_capacity else 0
            net = (executable_output - executable_cost) if executable_output is not None and executable_cost is not None else 0.0
            if buy_quote and executable_output is not None:
                reasons.append("depth-aware executable buy and liquidation quotes")
            else:
                reasons.append("executable depth unavailable; scalable capacity is zero")
            if theoretical_roi is not None and executable_output is None:
                reasons.append("theoretical pricing is available; execution remains unverified")
            if net > 0:
                reasons.append("positive executable set profit")
            else:
                reasons.append("no positive executable profit")
            status = (
                "executable" if executable_output is not None and executable_cost is not None and market_capacity > 0 and net > 0
                else "non_executable" if executable_output is not None and executable_cost is not None
                else "theoretical" if theoretical_roi is not None
                else "insufficient_evidence"
            )
            pricing_confidence = min(quote_confidences) if quote_confidences else 0.0
            strategy_confidence = float(recipe["strategy_confidence"])
            confidence = pricing_confidence * strategy_confidence if quote_confidences else 0.0
            source = next(iter(set(quote_sources)), recipe["source"]) if quote_sources else recipe["source"]
            input_cost = executable_cost if executable_cost is not None else theoretical_cost
            output_value = executable_output if executable_output is not None else theoretical_output
            route = ProfitRoute(
                transformation_id=recipe["id"],
                name=f"{recipe['card']} set arbitrage",
                strategy_family="divination_card",
                status=status,
                league=league,
                category="DivinationCard",
                total_input_cost=float(input_cost or 0),
                realistic_output_value=float(output_value or 0),
                gross_profit=float((output_value or 0) - (input_cost or 0)),
                expected_net_profit=float(net),
                roi=float(executable_roi or 0),
                theoretical_roi=theoretical_roi,
                executable_roi=executable_roi,
                capital_required=float(executable_cost or theoretical_cost or 0),
                capacity=float(market_capacity),
                capacity_units="sets",
                expected_execution_time=float(recipe["expected_execution_time_hours"]),
                expected_sale_time=float(recipe["expected_sale_time_hours"]),
                profit_per_hour=float(net / total_time),
                profit_per_divine_hour=(net / float(context["chaos_per_divine"]) / total_time
                                        if context.get("chaos_per_divine", 0) > 0 else 0.0),
                profit_per_set=float(net),
                sets_possible_with_budget=sets_possible,
                estimated_sets_per_hour=float(sets_per_hour),
                market_capacity=market_capacity,
                capacity_horizon_hours=horizon,
                capacity_assumptions=[
                    "capacity is measured in complete sets",
                    "buy and sell depth are exact quote levels",
                    "unknown depth produces zero scalable sets",
                ],
                reasons=list(reasons),
                confidence=confidence,
                pricing_confidence=pricing_confidence,
                strategy_confidence=strategy_confidence,
                execution_risk=float(recipe["execution_risk"] if buy_quote else 1.0),
                liquidity={
                    "tier": validation.liquidity_tier(float(market_capacity)),
                    "volume": market_capacity,
                    "capacity_units": "sets",
                },
                source=source,
                verified_version=recipe["verified_version"],
                poe_patch=recipe["poe_patch"],
                verification_metadata={
                    "registry_version": self.registry.version,
                    "registry_source": self.registry.source,
                    "definition_source": recipe["source"],
                    "verified_version": recipe["verified_version"],
                    "poe_patch": recipe["poe_patch"],
                    "active_poe_patch": active_poe_patch,
                    "manual_actions": list(recipe["manual_actions"]),
                    "variant": recipe["variant"],
                    "corrupted": recipe["corrupted"],
                    "item_level": recipe["item_level"],
                    "special_conditions": list(recipe["special_conditions"]),
                    "card_market_key": recipe["card_market_key"],
                    "reward_market_keys": [outcome["reward_market_key"] for outcome in outcomes],
                    "quote_sources": sorted(set(quote_sources)),
                    "quote_timestamps": sorted(set(quote_times)),
                    "eligibility": "deterministic" if recipe["deterministic"] else "trusted_finite_distribution",
                },
                inputs=[{"item": recipe["card"], "market_key": recipe["card_market_key"], "quantity": recipe["set_size"]}],
                costs=[{"item": recipe["card"], "market_key": recipe["card_market_key"], "quantity": recipe["set_size"], "side": "buy"}],
                outputs=[dict(outcome) for outcome in outcomes],
                execution_steps=list(recipe["manual_actions"]),
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
                max_batch=max(1, route.market_capacity),
                bankroll=bankroll,
                chaos_per_divine=chaos_per_divine,
            )
            for route in self.evaluate(context)
            if route.expected_net_profit > 0 and route.market_capacity > 0 and route.sets_possible_with_budget > 0
            and definitions[route.transformation_id]["deterministic"] in (True, False)
        ]
