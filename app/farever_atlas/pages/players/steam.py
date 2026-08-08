"""Farever player uid ↔ Steam profile helpers and summary cache."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui

from ...config import APP_ID

# Public-universe individual SteamID64 base (high dword 0x01100001).
# Matches hlsteam `steam.User.fromUID32`: low=account id, high=0x01100001.
STEAMID64_BASE = 76561197960265728
_FAREVER_UID_RE = re.compile(r"^[Ss]([0-9A-Fa-f]+)$")
_USER_AGENT = "FareverAtlas/1.0"
_STEAM_SUMMARIES_URL = (
    "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
)
_STEAM_FRIEND_LIST_URL = (
    "https://api.steampowered.com/ISteamUser/GetFriendList/v1/"
)

# Steam communityvisibilitystate
_VIS_PRIVATE = 1
_VIS_FRIENDS = 2
_VIS_PUBLIC = 3

_PERSONA_LABELS = {
    0: "Offline",
    1: "Online",
    2: "Busy",
    3: "Away",
    4: "Snooze",
    5: "Looking to trade",
    6: "Looking to play",
}
_STEAMID64_RE = re.compile(r"^\d{5,20}$")


def normalize_steamid64(value: object) -> str | None:
    """Return a digits-only SteamID64 suitable for cache path segments."""
    text = str(value or "").strip()
    if not text or ".." in text or "/" in text or "\\" in text:
        return None
    if _STEAMID64_RE.fullmatch(text) is None:
        return None
    return text


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def farever_uid_to_steamid64(uid: object) -> int | None:
    """Decode Farever `st.Player.uid` to SteamID64.

    Farever stores Steam account ids as ``S`` + hex of the account id's
    **little-endian** bytes (mpman UserID / Steam platform). Example:
    account ``0x066cbe38`` → ``S38be6c06`` → SteamID64 ``76561198068055608``.
    """
    text = str(uid or "").strip()
    match = _FAREVER_UID_RE.fullmatch(text)
    if match is None:
        return None
    hexpart = match.group(1)
    if len(hexpart) % 2 == 1:
        hexpart = f"0{hexpart}"
    try:
        raw = bytes.fromhex(hexpart)
    except ValueError:
        return None
    if not raw:
        return None
    if len(raw) < 4:
        raw = raw + (b"\x00" * (4 - len(raw)))
    account_id = int.from_bytes(raw[:4], "little")
    if account_id <= 0:
        return None
    return STEAMID64_BASE + account_id


def steam_profile_urls(steamid64: int) -> tuple[str, str]:
    """Return (steam_app_url, browser_url) for a SteamID64."""
    sid = int(steamid64)
    return (
        f"steam://url/SteamIDPage/{sid}",
        f"https://steamcommunity.com/profiles/{sid}",
    )


def _resolve_steamid64(
    uid: object = None,
    *,
    steamid64: object = None,
) -> int | None:
    resolved = farever_uid_to_steamid64(uid)
    if resolved is not None:
        return resolved
    normalized = normalize_steamid64(steamid64)
    if normalized is None:
        return None
    return int(normalized)


def _launch_steam_url(url: str) -> bool:
    """Hand a steam:// (or other) URL to the Steam client.

    Prefers the ``steam`` CLI so the protocol string is passed intact — more
    reliable than QDesktopServices/xdg-open on Linux. Returns True if a launch
    was accepted (Steam may still ignore some legacy protocol paths).
    """
    text = str(url or "").strip()
    if not text:
        return False
    steam_bin = QtCore.QStandardPaths.findExecutable("steam")
    if steam_bin and QtCore.QProcess.startDetached(steam_bin, [text]):
        return True
    xdg = QtCore.QStandardPaths.findExecutable("xdg-open")
    if xdg and QtCore.QProcess.startDetached(xdg, [text]):
        return True
    return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(text)))


def open_steam_profile(
    uid: object = None,
    *,
    steamid64: object = None,
) -> bool:
    """Open Steam profile for a Farever uid or SteamID64.

    Prefers Steam app, else browser. Uses ``/profiles/<SteamID64>`` (Steam
    redirects to a vanity ``/id/...`` when the user has one). Returns True if
    any URL open was accepted.
    """
    resolved = _resolve_steamid64(uid, steamid64=steamid64)
    if resolved is None:
        return False
    steam_url, browser_url = steam_profile_urls(resolved)
    if _launch_steam_url(steam_url):
        return True
    return bool(QtGui.QDesktopServices.openUrl(QtCore.QUrl(browser_url)))


def steam_visibility_is_private(visibility: object) -> bool:
    try:
        value = int(visibility)
    except (TypeError, ValueError):
        return False
    return value in {_VIS_PRIVATE, _VIS_FRIENDS}


def steam_persona_label(summary: dict[str, Any] | None) -> tuple[str, str]:
    """Return (short_label, tooltip) for a cached Steam summary.

    Private / friends-only profiles often report Offline even when online —
    surface that explicitly so users are not misled.
    """
    if not isinstance(summary, dict) or not summary:
        return ("", "")
    visibility = summary.get("communityvisibilitystate", _VIS_PUBLIC)
    private = steam_visibility_is_private(visibility)
    state = 0
    try:
        state = int(summary.get("personastate", 0) or 0)
    except (TypeError, ValueError):
        state = 0
    game_id = str(summary.get("gameid") or "").strip()
    game_info = str(summary.get("gameextrainfo") or "").strip()
    in_farever = game_id == str(APP_ID)

    if private and state == 0:
        tip = (
            "Steam profile is private — Steam may show Offline even when "
            "the player is online."
        )
        return ("Private", tip)

    label = _PERSONA_LABELS.get(state, "Unknown")
    tip_bits = [label]
    if private:
        tip_bits.append(
            "Profile is private; Steam status can be incomplete."
        )
        if state == 0:
            label = "Private"
    if in_farever:
        label = "In Farever" if state != 0 or not private else label
        tip_bits.append("Playing Farever (Steam)")
    elif game_info:
        tip_bits.append(f"Playing {game_info}")
    return (label, " · ".join(tip_bits))


class SteamProfileCache(QtCore.QObject):
    """Disk-backed Steam GetPlayerSummaries cache + background refresh."""

    updated = QtCore.Signal()

    def __init__(self, cache_dir: Path, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._summaries: dict[str, dict[str, Any]] = {}
        self._avatars: dict[str, QtGui.QPixmap] = {}
        self._inflight = False
        self._pending_ids: list[str] = []
        self._api_key = ""
        # Pin the active QRunnable so its signals QObject is not GC'd mid-run.
        self._worker: _SteamSummariesWorker | None = None
        self._load_all()

    def set_api_key(self, key: object) -> None:
        self._api_key = str(key or "").strip()

    def has_api_key(self) -> bool:
        return bool(self._api_key)

    def summary(self, steamid64: object) -> dict[str, Any] | None:
        key = normalize_steamid64(steamid64)
        if key is None:
            return None
        entry = self._summaries.get(key)
        return dict(entry) if entry else None

    def avatar_pixmap(self, steamid64: object, size: int = 24) -> QtGui.QPixmap:
        key = normalize_steamid64(steamid64)
        if key is None:
            return QtGui.QPixmap()
        cached = self._avatars.get(key)
        if cached is not None and not cached.isNull():
            return cached.scaled(
                size,
                size,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        path = self.cache_dir / key / "avatar.jpg"
        try:
            path = path.resolve(strict=False)
            if self.cache_dir.resolve(strict=False) not in path.parents:
                return QtGui.QPixmap()
        except OSError:
            return QtGui.QPixmap()
        if not path.is_file():
            return QtGui.QPixmap()
        pixmap = QtGui.QPixmap(str(path))
        if pixmap.isNull():
            return QtGui.QPixmap()
        self._avatars[key] = pixmap
        return pixmap.scaled(
            size,
            size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )

    def request_refresh(
        self,
        steamids: list[str] | set[str],
        *,
        max_age_s: int = 300,
    ) -> None:
        if not self._api_key:
            return
        now = time.time()
        needed: list[str] = []
        for raw in steamids:
            sid = normalize_steamid64(raw)
            if sid is None:
                continue
            summary = self._summaries.get(sid)
            fetched = float(summary.get("fetched_at", 0) or 0) if summary else 0.0
            if summary is None or (now - fetched) >= max_age_s:
                needed.append(sid)
        if not needed:
            return
        for sid in needed:
            if sid not in self._pending_ids:
                self._pending_ids.append(sid)
        self._kick()

    def _kick(self) -> None:
        if self._inflight or not self._pending_ids or not self._api_key:
            return
        batch = self._pending_ids[:100]
        self._pending_ids = self._pending_ids[100:]
        self._inflight = True
        worker = _SteamSummariesWorker(self._api_key, batch, self.cache_dir)
        self._worker = worker
        worker.signals.finished.connect(self._on_worker_finished)
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_worker_finished(self, summaries: object) -> None:
        self._worker = None
        self._inflight = False
        changed = False
        if isinstance(summaries, dict):
            for sid, payload in summaries.items():
                if not isinstance(payload, dict):
                    continue
                key = normalize_steamid64(sid)
                if key is None:
                    continue
                self._summaries[key] = payload
                self._avatars.pop(key, None)
                changed = True
        if changed:
            self.updated.emit()
        self._kick()

    def _load_all(self) -> None:
        if not self.cache_dir.is_dir():
            return
        for child in self.cache_dir.iterdir():
            if not child.is_dir():
                continue
            key = normalize_steamid64(child.name)
            if key is None:
                continue
            meta = child / "summary.json"
            if not meta.is_file():
                continue
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            sid = normalize_steamid64(payload.get("steamid") or key)
            if sid is None:
                continue
            payload = dict(payload)
            payload["steamid"] = sid
            self._summaries[sid] = payload


class _SteamWorkerSignals(QtCore.QObject):
    finished = QtCore.Signal(object)


class _SteamSummariesWorker(QtCore.QRunnable):
    def __init__(self, api_key: str, steamids: list[str], cache_dir: Path) -> None:
        super().__init__()
        self.api_key = api_key
        self.steamids = steamids
        self.cache_dir = cache_dir
        self.signals = _SteamWorkerSignals()

    def run(self) -> None:  # noqa: N802
        result: dict[str, dict[str, Any]] = {}
        try:
            query = urllib.parse.urlencode(
                {
                    "key": self.api_key,
                    "steamids": ",".join(self.steamids),
                }
            )
            url = f"{_STEAM_SUMMARIES_URL}?{query}"
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=12) as response:
                    body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                return

            response_obj = payload.get("response") if isinstance(payload, dict) else None
            if not isinstance(response_obj, dict):
                response_obj = {}
            players = response_obj.get("players", [])
            if not isinstance(players, list):
                return
            now = int(time.time())
            for player in players:
                if not isinstance(player, dict):
                    continue
                sid = normalize_steamid64(player.get("steamid"))
                if sid is None:
                    continue
                summary = {
                    "steamid": sid,
                    "personaname": str(player.get("personaname") or ""),
                    "profileurl": str(player.get("profileurl") or ""),
                    "avatar": str(player.get("avatar") or ""),
                    "avatarmedium": str(player.get("avatarmedium") or ""),
                    "avatarfull": str(player.get("avatarfull") or ""),
                    "personastate": _safe_int(player.get("personastate"), 0),
                    "communityvisibilitystate": _safe_int(
                        player.get("communityvisibilitystate"), _VIS_PUBLIC
                    ),
                    "gameextrainfo": str(player.get("gameextrainfo") or ""),
                    "gameid": str(player.get("gameid") or ""),
                    "fetched_at": now,
                }
                folder = self.cache_dir / sid
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    (folder / "summary.json").write_text(
                        json.dumps(summary, indent=2) + "\n",
                        encoding="utf-8",
                    )
                except OSError:
                    pass
                avatar_url = summary.get("avatarmedium") or summary.get("avatar")
                if avatar_url:
                    self._download_avatar(str(avatar_url), folder / "avatar.jpg")
                result[sid] = summary
        finally:
            self.signals.finished.emit(result)

    @staticmethod
    def _download_avatar(url: str, path: Path) -> None:
        if not str(url).startswith(("https://", "http://")):
            return
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                data = response.read()
            path.write_bytes(data)
        except (urllib.error.URLError, TimeoutError, OSError):
            return


class SteamFriendListCache(QtCore.QObject):
    """Disk-backed GetFriendList cache for Steam-friend badge checks."""

    updated = QtCore.Signal()

    def __init__(self, cache_dir: Path, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self.cache_dir / "steam_friends.json"
        self._friend_ids: set[str] = set()
        self._fetched_at = 0.0
        self._cached_for_steamid64 = ""
        self._inflight = False
        self._api_key = ""
        self._steamid64 = ""
        # Pin the active QRunnable so its signals QObject is not GC'd mid-run.
        self._worker: _SteamFriendListWorker | None = None
        self._load()

    def set_api_key(self, key: object) -> None:
        self._api_key = str(key or "").strip()

    def set_steamid64(self, steamid64: object) -> None:
        next_id = normalize_steamid64(steamid64) or ""
        if next_id != self._steamid64:
            self._steamid64 = next_id
            if next_id != self._cached_for_steamid64:
                # Force a fresh fetch for the new account; keep old disk
                # until a successful response so offline still works.
                self._fetched_at = 0.0

    def has_credentials(self) -> bool:
        return bool(self._api_key and self._steamid64)

    def is_friend(self, steamid64: object) -> bool:
        if not self._steamid64 or self._steamid64 != self._cached_for_steamid64:
            return False
        key = normalize_steamid64(steamid64)
        if key is None:
            return False
        return key in self._friend_ids

    def request_refresh(self, *, max_age_s: int = 600) -> None:
        if not self.has_credentials():
            return
        now = time.time()
        same_account = self._cached_for_steamid64 == self._steamid64
        if same_account and self._fetched_at and (now - self._fetched_at) < max_age_s:
            return
        if self._inflight:
            return
        self._inflight = True
        worker = _SteamFriendListWorker(self._api_key, self._steamid64)
        self._worker = worker
        worker.signals.finished.connect(self._on_worker_finished)
        QtCore.QThreadPool.globalInstance().start(worker)

    def _on_worker_finished(self, payload: object) -> None:
        self._worker = None
        self._inflight = False
        if not isinstance(payload, dict):
            return
        if not payload.get("ok"):
            # Keep last good cache on 401 / network failure.
            return
        ids_raw = payload.get("ids")
        if not isinstance(ids_raw, list):
            return
        ids: set[str] = set()
        for item in ids_raw:
            sid = normalize_steamid64(item)
            if sid is not None:
                ids.add(sid)
        self._friend_ids = ids
        self._fetched_at = float(payload.get("fetched_at") or time.time())
        self._cached_for_steamid64 = str(payload.get("steamid64") or self._steamid64)
        self._save()
        self.updated.emit()

    def _save(self) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            text = (
                json.dumps(
                    {
                        "steamid64": self._cached_for_steamid64 or self._steamid64,
                        "fetched_at": int(self._fetched_at),
                        "friends": sorted(self._friend_ids),
                    },
                    indent=2,
                )
                + "\n"
            )
            tmp = self._cache_path.with_suffix(".json.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(self._cache_path)
        except OSError:
            return

    def _load(self) -> None:
        if not self._cache_path.is_file():
            return
        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        ids: set[str] = set()
        raw = payload.get("friends", [])
        if isinstance(raw, list):
            for item in raw:
                sid = normalize_steamid64(item)
                if sid is not None:
                    ids.add(sid)
        self._friend_ids = ids
        self._fetched_at = float(payload.get("fetched_at") or 0)
        self._cached_for_steamid64 = normalize_steamid64(payload.get("steamid64")) or ""


class _SteamFriendListWorker(QtCore.QRunnable):
    def __init__(self, api_key: str, steamid64: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.steamid64 = steamid64
        self.signals = _SteamWorkerSignals()

    def run(self) -> None:  # noqa: N802
        result: dict[str, Any] = {"ok": False, "ids": [], "fetched_at": 0}
        try:
            query = urllib.parse.urlencode(
                {
                    "key": self.api_key,
                    "steamid": self.steamid64,
                    "relationship": "friend",
                }
            )
            url = f"{_STEAM_FRIEND_LIST_URL}?{query}"
            request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=12) as response:
                    body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
            except urllib.error.HTTPError:
                return
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
                return

            friends_list = (
                payload.get("friendslist") if isinstance(payload, dict) else None
            )
            if not isinstance(friends_list, dict):
                return
            friends = friends_list.get("friends", [])
            if not isinstance(friends, list):
                return
            ids: list[str] = []
            for entry in friends:
                if not isinstance(entry, dict):
                    continue
                sid = normalize_steamid64(entry.get("steamid"))
                if sid is not None:
                    ids.append(sid)
            result = {
                "ok": True,
                "ids": ids,
                "fetched_at": int(time.time()),
                "steamid64": self.steamid64,
            }
        finally:
            self.signals.finished.emit(result)
