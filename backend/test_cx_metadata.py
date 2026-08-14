import cx_metadata


def test_legacy_numeric_mapping_resolves_stored_metadata_paths():
    meta = "Metadata/Items/MapFragments/Scarabs/ScarabAbyssNew3"
    mapping = cx_metadata._normalize_mapping({
        "12": {"id": meta, "name": "Abyss Scarab of Edifice", "icon": "icon"}
    })

    assert list(mapping) == [meta]
    assert cx_metadata.resolve_name(mapping, meta) == "Abyss Scarab of Edifice"
    assert cx_metadata.resolve_short_id(mapping, meta) == "abyss-scarab-of-edifice"


def test_legacy_cx_ids_remain_queryable_without_current_static_mapping():
    legacy = "Metadata/Items/Scarabs/ScarabAbyssNew1"
    mapping = {}

    assert cx_metadata.resolve_name(mapping, legacy) == "Scarab Abyss New 1"
    assert legacy in cx_metadata.resolve_query_ids(mapping, {legacy}, "scarababyssnew1")
    assert legacy in cx_metadata.resolve_query_ids(mapping, {legacy}, "scarab-abyss-new-1")
