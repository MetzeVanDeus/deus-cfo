"""Installed-version source and GitHub latest-release update checks."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("deuscfo.updates")

GITHUB_REPO = "MetzeVanDeus/deus-cfo"
DEFAULT_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DEFAULT_CACHE_SECONDS = 8 * 60 * 60
STABLE_VERSION = re.compile(r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")


class VersionError(RuntimeError):
    """The packaged runtime has no valid bundled VERSION authority."""


class UpdateCheckError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


_lock = asyncio.Lock()
_cache: dict[str, Any] | None = None
_checked_at = 0.0
_inflight: asyncio.Task | None = None


def reset_for_tests() -> None:
    """Clear cached GitHub results between tests."""
    global _cache, _checked_at, _inflight
    _cache = None
    _checked_at = 0.0
    _inflight = None


def cache_ttl_seconds() -> float:
    raw = os.environ.get("DEUSCFO_UPDATE_CACHE_SECONDS", str(DEFAULT_CACHE_SECONDS))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return float(DEFAULT_CACHE_SECONDS)


def latest_release_url() -> str:
    return os.environ.get("DEUSCFO_UPDATE_RELEASE_URL", DEFAULT_LATEST_URL).strip() or DEFAULT_LATEST_URL


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def version_file_path() -> Path:
    if is_packaged():
        meipass = getattr(sys, "_MEIPASS", None)
        if not meipass:
            raise VersionError("bundled VERSION path is unavailable")
        return Path(meipass) / "VERSION"
    override = os.environ.get("DEUSCFO_VERSION_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "VERSION"


def read_current_version() -> str:
    path = version_file_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        if is_packaged():
            raise VersionError(f"bundled VERSION is unavailable: {path}") from exc
        return ""
    if is_packaged() and parse_stable_version(value) is None:
        raise VersionError(f"bundled VERSION is invalid: {path}")
    return value


def parse_stable_version(value: str | None) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = STABLE_VERSION.fullmatch(value.strip())
    if not match:
        return None
    return int(match["major"]), int(match["minor"]), int(match["patch"])


def format_version(value: str | None) -> str:
    parsed = parse_stable_version(value)
    if parsed is None:
        return ""
    return f"{parsed[0]}.{parsed[1]}.{parsed[2]}"


def is_newer(candidate: str | None, current: str | None) -> bool:
    left = parse_stable_version(candidate)
    right = parse_stable_version(current)
    if left is None or right is None:
        return False
    return left > right


def _empty_status(*, error: str | None = None) -> dict[str, Any]:
    current = format_version(read_current_version()) or read_current_version()
    return {
        "current_version": current,
        "latest_version": None,
        "update_available": False,
        "release_url": None,
        "published_at": None,
        "error": error,
    }


def _status_from_release(release: dict[str, Any], *, error: str | None = None) -> dict[str, Any]:
    current = format_version(read_current_version()) or read_current_version()
    latest = format_version(release.get("latest_version"))
    return {
        "current_version": current,
        "latest_version": latest or None,
        "update_available": is_newer(latest, current),
        "release_url": release.get("release_url"),
        "published_at": release.get("published_at"),
        "error": error,
    }


def current_status() -> dict[str, Any]:
    if _cache is None:
        return _empty_status()
    current = format_version(read_current_version()) or read_current_version()
    latest = _cache.get("latest_version")
    return {
        "current_version": current,
        "latest_version": latest,
        "update_available": is_newer(latest, current),
        "release_url": _cache.get("release_url"),
        "published_at": _cache.get("published_at"),
        "error": _cache.get("error"),
    }


def _cache_is_fresh() -> bool:
    if _cache is None or _checked_at <= 0:
        return False
    return (time.monotonic() - _checked_at) < cache_ttl_seconds()


def _user_agent() -> str:
    version = format_version(read_current_version()) or "dev"
    return f"DeusCFO/{version} (+https://github.com/{GITHUB_REPO})"


def _parse_release_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise UpdateCheckError("malformed")
    if payload.get("draft") is True or payload.get("prerelease") is True:
        raise UpdateCheckError("ignored")
    tag = payload.get("tag_name")
    latest = format_version(tag if isinstance(tag, str) else None)
    if not latest:
        raise UpdateCheckError("malformed")
    html_url = payload.get("html_url")
    published_at = payload.get("published_at")
    return {
        "latest_version": latest,
        "release_url": html_url if isinstance(html_url, str) and html_url.startswith("https://") else None,
        "published_at": published_at if isinstance(published_at, str) else None,
    }


async def fetch_latest_release() -> dict[str, Any]:
    url = latest_release_url()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": _user_agent(),
                },
            )
    except httpx.HTTPError as exc:
        raise UpdateCheckError("unavailable") from exc
    except OSError as exc:
        raise UpdateCheckError("unavailable") from exc
    if response.status_code == 404:
        raise UpdateCheckError("unavailable")
    if response.status_code != 200:
        raise UpdateCheckError("unavailable")
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpdateCheckError("malformed") from exc
    return _parse_release_payload(payload)


async def _fetch_latest_release() -> dict[str, Any]:
    return await fetch_latest_release()


def _store(status: dict[str, Any]) -> dict[str, Any]:
    global _cache, _checked_at
    _cache = status
    _checked_at = time.monotonic()
    return status


async def refresh(*, force: bool = False) -> dict[str, Any]:
    async with _lock:
        if not force and _cache_is_fresh():
            return current_status()
        try:
            release = await _fetch_latest_release()
        except UpdateCheckError as exc:
            if exc.code == "ignored":
                return _store(_empty_status())
            if _cache is not None and _cache.get("latest_version"):
                return _store({**current_status(), "error": exc.code})
            return _store(_empty_status(error=exc.code))
        except Exception:
            log.debug("update check failed", exc_info=True)
            if _cache is not None and _cache.get("latest_version"):
                return _store({**current_status(), "error": "unavailable"})
            return _store(_empty_status(error="unavailable"))
        return _store(_status_from_release(release))


async def check_on_startup() -> None:
    try:
        await refresh()
    except Exception:
        log.debug("startup update check failed", exc_info=True)


def schedule_refresh_if_needed() -> None:
    global _inflight
    if _cache_is_fresh():
        return
    if _inflight is not None and not _inflight.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _inflight = loop.create_task(check_on_startup())


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(check_on_startup())
    try:
        yield
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if _inflight is not None and not _inflight.done():
            _inflight.cancel()
            with suppress(asyncio.CancelledError):
                await _inflight
