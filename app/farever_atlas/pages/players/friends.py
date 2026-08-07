"""Persistent friends list under user_data/friends/."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore

from ...config import PROJECT_ROOT, safe_int
from .steam import farever_uid_to_steamid64, normalize_steamid64

FRIENDS_DIR = PROJECT_ROOT / "user_data" / "friends"
FRIENDS_STORE_PATH = FRIENDS_DIR / "friends.json"
FRIENDS_CACHE_DIR = FRIENDS_DIR / "cache"


class FriendStore(QtCore.QObject):
    """JSON-backed friends roster keyed by Farever uid."""

    changed = QtCore.Signal()

    def __init__(self, file_path: Path | None = None) -> None:
        super().__init__()
        self.file_path = file_path or FRIENDS_STORE_PATH
        self.last_error = ""
        self._friends: list[dict[str, Any]] = []
        self._by_uid: dict[str, dict[str, Any]] = {}
        self._load()

    def all(self) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._friends]

    def uids(self) -> set[str]:
        return set(self._by_uid)

    def get(self, uid: object) -> dict[str, Any] | None:
        key = str(uid or "").strip()
        entry = self._by_uid.get(key)
        return dict(entry) if entry is not None else None

    def contains(self, uid: object) -> bool:
        return str(uid or "").strip() in self._by_uid

    def contains_player(self, player: dict[str, Any]) -> bool:
        """True if uid, friend_key, or name-keyed friend matches this player."""
        uid = str(player.get("uid") or "").strip()
        if uid and uid in self._by_uid:
            return True
        friend_key = str(player.get("friend_key") or "").strip()
        if friend_key and friend_key in self._by_uid:
            return True
        name = str(player.get("name") or "").strip().lower()
        if name and f"name:{name}" in self._by_uid:
            return True
        return False

    def find_by_name(self, name: object) -> dict[str, Any] | None:
        want = str(name or "").strip().lower()
        if not want:
            return None
        key = f"name:{want}"
        entry = self._by_uid.get(key)
        if entry is not None:
            return dict(entry)
        for friend in self._friends:
            if str(friend.get("name") or "").strip().lower() == want:
                return dict(friend)
        return None

    def add_from_player(self, player: dict[str, Any]) -> bool:
        uid = str(player.get("uid") or "").strip()
        if not uid:
            return False
        # Prefer upgrading a prior name-only friend instead of duplicating.
        name = str(player.get("name") or "").strip()
        if not uid.startswith("name:") and name:
            name_key = f"name:{name.lower()}"
            name_existing = self._by_uid.get(name_key)
            if name_existing is not None and uid not in self._by_uid:
                return self._upgrade_name_friend(name_existing, player)

        steamid64 = farever_uid_to_steamid64(uid)
        if steamid64 is None:
            steamid64_text = normalize_steamid64(player.get("steamid64")) or ""
        else:
            steamid64_text = str(steamid64)
        existing = self._by_uid.get(uid)
        now = int(time.time())
        payload = {
            "uid": uid,
            "steamid64": steamid64_text,
            "name": name or "Unknown",
            "class": str(player.get("class") or "").strip(),
            "level": safe_int(player.get("level"), 0),
            "note": str(existing.get("note") or "") if existing else "",
            "added_at": (
                safe_int(existing.get("added_at"), now) if existing else now
            ),
            "updated_at": now,
        }
        if existing is None:
            self._friends.append(payload)
        else:
            index = self._friends.index(existing)
            self._friends[index] = payload
        self._reindex()
        return self._save()

    def _upgrade_name_friend(
        self, name_existing: dict[str, Any], player: dict[str, Any]
    ) -> bool:
        uid = str(player.get("uid") or "").strip()
        if not uid or uid.startswith("name:"):
            return False
        steamid64 = farever_uid_to_steamid64(uid)
        if steamid64 is None:
            steamid64_text = normalize_steamid64(player.get("steamid64")) or ""
        else:
            steamid64_text = str(steamid64)
        now = int(time.time())
        payload = {
            "uid": uid,
            "steamid64": steamid64_text or str(name_existing.get("steamid64") or ""),
            "name": str(player.get("name") or name_existing.get("name") or "").strip()
            or "Unknown",
            "class": str(player.get("class") or name_existing.get("class") or "").strip(),
            "level": safe_int(
                player.get("level"), safe_int(name_existing.get("level"), 0)
            ),
            "note": str(name_existing.get("note") or ""),
            "added_at": safe_int(name_existing.get("added_at"), now),
            "updated_at": now,
        }
        try:
            index = self._friends.index(name_existing)
        except ValueError:
            self._friends.append(payload)
        else:
            self._friends[index] = payload
        self._reindex()
        return self._save()

    def update_seen(self, player: dict[str, Any]) -> bool:
        uid = str(player.get("uid") or "").strip()
        name = str(player.get("name") or "").strip()
        existing = self._by_uid.get(uid) if uid else None
        if existing is None and name:
            name_key = f"name:{name.lower()}"
            name_existing = self._by_uid.get(name_key)
            if name_existing is not None and uid and not uid.startswith("name:"):
                return self._upgrade_name_friend(name_existing, player)
            existing = name_existing
        if existing is None:
            return False
        character_class = str(player.get("class") or "").strip()
        level = safe_int(player.get("level"), 0)
        changed = False
        if name and name != existing.get("name"):
            existing["name"] = name
            changed = True
        if character_class and character_class != existing.get("class"):
            existing["class"] = character_class
            changed = True
        if level > 0 and level != safe_int(existing.get("level"), 0):
            existing["level"] = level
            changed = True
        steamid64 = farever_uid_to_steamid64(uid)
        if steamid64 is not None and str(existing.get("steamid64") or "") != str(
            steamid64
        ):
            existing["steamid64"] = str(steamid64)
            changed = True
        if changed:
            existing["updated_at"] = int(time.time())
            return self._save()
        return False

    def remove(self, uid: object) -> bool:
        key = str(uid or "").strip()
        if key not in self._by_uid:
            return False
        self._friends = [entry for entry in self._friends if entry.get("uid") != key]
        self._reindex()
        return self._save()

    def _reindex(self) -> None:
        self._by_uid = {
            str(entry.get("uid") or ""): entry
            for entry in self._friends
            if str(entry.get("uid") or "").strip()
        }

    def _save(self) -> bool:
        self.last_error = ""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"friends": self._friends}
            text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
            tmp_path = self.file_path.with_suffix(".json.tmp")
            tmp_path.write_text(text, encoding="utf-8")
            tmp_path.replace(self.file_path)
        except OSError as exc:
            self.last_error = str(exc)
            return False
        self.changed.emit()
        return True

    def _load(self) -> None:
        self.last_error = ""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            FRIENDS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.last_error = str(exc)
            self._friends = []
            self._reindex()
            return
        if not self.file_path.is_file() or self.file_path.stat().st_size == 0:
            self._friends = []
            self._reindex()
            return
        try:
            payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.last_error = str(exc)
            self._friends = []
            self._reindex()
            return
        raw = payload.get("friends", []) if isinstance(payload, dict) else []
        if not isinstance(raw, list):
            self._friends = []
            self._reindex()
            return
        friends: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            uid = str(item.get("uid") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            steamid64 = normalize_steamid64(item.get("steamid64")) or ""
            if not steamid64:
                decoded = farever_uid_to_steamid64(uid)
                steamid64 = str(decoded) if decoded is not None else ""
            friends.append(
                {
                    "uid": uid,
                    "steamid64": steamid64,
                    "name": str(item.get("name") or "").strip() or "Unknown",
                    "class": str(item.get("class") or "").strip(),
                    "level": safe_int(item.get("level"), 0),
                    "note": str(item.get("note") or "").strip(),
                    "added_at": safe_int(item.get("added_at"), 0),
                    "updated_at": safe_int(item.get("updated_at"), 0),
                }
            )
        self._friends = friends
        self._reindex()
