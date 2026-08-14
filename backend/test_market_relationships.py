from datetime import datetime, timedelta, timezone

import market_relationships as relationships


def snapshot(timestamp, item_id, price, category="Currency", volume=100):
    return {
        "timestamp": timestamp.isoformat(),
        "category": category,
        "item_id": item_id,
        "price_chaos": price,
        "volume": volume,
    }


def test_market_event_requires_synchronized_category_movement():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(2):
        timestamp = start + timedelta(hours=index)
        for item in ("a", "b", "c"):
            rows.append(snapshot(timestamp, item, 100 if index == 0 else 110))

    events = relationships.detect_market_events(rows)

    assert len(events) == 1
    assert events[0].type == "category_price_move"
    assert events[0].affected_items == ["a", "b", "c"]
    assert events[0].sample_size == 3


def test_lagged_relationship_preserves_temporal_direction_and_holdout():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(14):
        timestamp = start + timedelta(hours=index)
        rows.append(snapshot(timestamp, "leader", 100 * 1.1**index))
        rows.append(snapshot(timestamp, "laggard", 100 * 1.05 ** max(0, index - 1)))

    result = relationships.investigate_lagged_relationship(
        rows, ("Currency", "leader"), ("Currency", "laggard"), 1
    )

    assert result["status"] == "potential_relationship"
    assert result["potential_leader"] == "Currency:leader"
    assert result["potential_laggard"] == "Currency:laggard"
    assert result["sample_size"] == 12
    assert result["train"]["directional_consistency"] == 1.0
    assert result["out_of_sample"]["directional_consistency"] == 1.0


def test_lagged_relationship_reports_insufficient_history():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(4):
        timestamp = start + timedelta(hours=index)
        rows.append(snapshot(timestamp, "leader", 100 + index))
        rows.append(snapshot(timestamp, "laggard", 100 + max(0, index - 1)))

    result = relationships.investigate_lagged_relationship(
        rows, ("Currency", "leader"), ("Currency", "laggard"), 1
    )

    assert result["status"] == "insufficient_data"
    assert result["reason"] == "insufficient_aligned_samples"
    assert result["potential_leader"] is None
    assert result["potential_laggard"] is None
