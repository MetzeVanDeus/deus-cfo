import pytest

import updates


@pytest.fixture(autouse=True)
def _isolate_update_checks(monkeypatch):
    async def blocked():
        raise updates.UpdateCheckError("unavailable")

    monkeypatch.setattr(updates, "_fetch_latest_release", blocked)
    updates.reset_for_tests()
