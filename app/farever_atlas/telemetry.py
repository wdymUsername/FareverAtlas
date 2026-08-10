"""Polling bridge output and producing immutable snapshots."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore

from .config import ASSET_ROOT, POIS_RELATIVE_PATH, PROJECT_ROOT, safe_float
from .currency_caps import enrich_currencies
from .pages.map.data import Snapshot
from .unit_traits import (
    is_boss_kind,
    is_critter_kind,
    is_elite_kind,
    is_miniboss_kind,
    is_spark_kind,
    is_unique_kind,
)


def _gatherable_size(name: str) -> str:
    blob = str(name or "").lower()
    if "small" in blob:
        return "small"
    if "medium" in blob:
        return "medium"
    if "large" in blob or "_big" in blob:
        return "large"
    return ""


def _looks_like_element_kind_id(name: str) -> bool:
    """Prefab/node ids like Madrigold_Small_Generic — not character display names."""
    trimmed = str(name or "").strip()
    if not trimmed or not trimmed.isascii():
        return True
    # Farever player names do not contain '_' or path separators.
    if "_" in trimmed or "/" in trimmed:
        return True
    lower = trimmed.lower()
    tokens = (
        "small",
        "medium",
        "large",
        "generic",
        "chestorb",
        "worldchest",
        "recipe",
    )
    if any(ch.isdigit() for ch in trimmed) and any(token in lower for token in tokens):
        return True
    return False


def _sanitize_player_display_name(name: object) -> str | None:
    if not isinstance(name, str):
        return None
    trimmed = name.strip()
    if not (1 <= len(trimmed) <= 64):
        return None
    if not trimmed.isascii() or not trimmed.isprintable():
        return None
    if _looks_like_element_kind_id(trimmed):
        return None
    return trimmed


class DataHub(QtCore.QObject):
    updated = QtCore.Signal(object)

    # The bridge writes on its own schedule, so polling at the same rate
    # aliases against it: some ticks see nothing and the next sees a sample
    # that is already stale, which the radar reads as an uneven sample rate and
    # renders as stuttering movement. Sampling several times per write costs a
    # stat() and pins detection to within a tick of the write landing.
    POLL_INTERVAL_MS = 33
    # Emitting on every poll would put the whole snapshot chain - radar
    # signatures, gather nav, the party strip - on a 30 Hz treadmill, when
    # nothing downstream changes until the bridge writes. Freshness is the
    # exception: staleness, the age readout and the waiting countdown all move
    # on wall-clock time, so emit at least this often whatever the bridge does.
    FRESHNESS_INTERVAL_MS = 100

    def __init__(self) -> None:
        super().__init__()
        self.live_file = PROJECT_ROOT / "native_bridge/farever-telemetry.json"
        self.asset_poi_file = ASSET_ROOT / POIS_RELATIVE_PATH
        self.state: dict[str, Any] = {}
        self.pois: list[dict[str, Any]] = []
        self._live_mtime_ns = -1
        self._poi_mtime_ns = -1
        self._last_good_monotonic: float | None = None
        self._active_poi_file = self.asset_poi_file
        self.online = True
        self._last_emit_monotonic = 0.0
        self.timer = QtCore.QTimer(self)
        # Coarse timers may be shifted by 5% and coalesced with other timers,
        # which is exactly the jitter this poll rate exists to avoid.
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.setInterval(self.POLL_INTERVAL_MS)
        self.timer.timeout.connect(self.poll)

    def start(self) -> None:
        if self.online:
            self.poll()
            self.timer.start()
        else:
            self._load_cached_pois()
            self._emit_offline()

    @QtCore.Slot(bool)
    def set_online(self, online: bool) -> None:
        self.online = online
        if online:
            self.poll()
            self.timer.start()
        else:
            self.timer.stop()
            self.state = {}
            self._load_cached_pois()
            self._emit_offline()

    def _load_cached_pois(self) -> None:
        try:
            payload = self._read_json(self.asset_poi_file)
            raw = payload.get("pois", []) if isinstance(payload, dict) else payload
            if isinstance(raw, list):
                self.pois = [item for item in raw if isinstance(item, dict)]
                self._active_poi_file = self.asset_poi_file
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            pass

    def _emit_offline(self) -> None:
        self.updated.emit(
            Snapshot(
                {},
                self.pois,
                False,
                "Offline",
                None,
                str(self.live_file),
                str(self._active_poi_file),
            )
        )

    @staticmethod
    def _read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _normalize_native(payload: dict[str, Any]) -> dict[str, Any]:
        position = payload.get("position", {})
        if not isinstance(position, dict):
            position = {}
        native_player = payload.get("player", {})
        if not isinstance(native_player, dict):
            native_player = {}
        # Main validation + reject prefab/world IDs (Madrigold_Small_Generic, etc.).
        # Keep this binding distinct from loop locals below — players/interactibles
        # must not overwrite the local player display name.
        player_name = _sanitize_player_display_name(native_player.get("name"))
        health = native_player.get("health")
        max_health = native_player.get("max_health")
        try:
            if float(max_health) <= 0:
                max_health = None
                hp_pct = 0.0
            else:
                hp_pct = float(health) / float(max_health)
        except (TypeError, ValueError):
            max_health = None
            hp_pct = 0.0
        party: list[dict[str, Any]] = []
        native_party = payload.get("party", [])
        if isinstance(native_party, list):
            for member in native_party:
                if not isinstance(member, dict):
                    continue
                member_position = member.get("position", {})
                if not isinstance(member_position, dict):
                    member_position = {}
                member_health = member.get("health")
                member_max_health = member.get("max_health")
                try:
                    member_hp_pct = (
                        float(member_health) / float(member_max_health)
                        if float(member_max_health) > 0
                        else 0.0
                    )
                except (TypeError, ValueError):
                    member_hp_pct = 0.0
                party.append(
                    {
                        "name": _sanitize_player_display_name(member.get("name")),
                        "uid": member.get("uid"),
                        "class": member.get("class"),
                        "level": member.get("level"),
                        "connected": member.get("connected", True),
                        "hero_valid": True,
                        "hp": member_health,
                        "max_hp": member_max_health,
                        "hp_pct": member_hp_pct,
                        "shield": member.get("shield"),
                        "x": member_position.get("x"),
                        "y": member_position.get("y"),
                        "z": member_position.get("z"),
                        "heading": member.get("heading", 0.0),
                        "distance": member.get("distance"),
                    }
                )
        enemies: list[dict[str, Any]] = []
        critters: list[dict[str, Any]] = []
        seen_critter_ids: set[str] = set()

        def _append_actor(row: dict[str, Any], *, bucket: list[dict[str, Any]]) -> None:
            position = row.get("position", {})
            if not isinstance(position, dict):
                position = {}
            actor_id = row.get("id")
            kind = row.get("kind")
            if not isinstance(actor_id, str) or not actor_id:
                return
            if kind is not None and not isinstance(kind, str):
                kind = None
            kind_text = kind or ""
            spark = bool(row.get("spark")) or is_spark_kind(kind_text)
            elite = bool(row.get("elite")) or is_elite_kind(kind_text)
            boss = bool(row.get("boss")) or is_boss_kind(kind_text)
            miniboss = bool(row.get("miniboss")) or is_miniboss_kind(kind_text)
            unique = bool(row.get("unique")) or is_unique_kind(kind_text)
            bucket.append(
                {
                    "id": actor_id,
                    "kind": kind_text,
                    "spark": spark,
                    "elite": elite,
                    "boss": boss,
                    "miniboss": miniboss,
                    "unique": unique,
                    "x": position.get("x"),
                    "y": position.get("y"),
                    "z": position.get("z"),
                }
            )

        native_critters = payload.get("critters", [])
        if isinstance(native_critters, list):
            for row in native_critters:
                if not isinstance(row, dict):
                    continue
                actor_id = row.get("id")
                if isinstance(actor_id, str) and actor_id:
                    seen_critter_ids.add(actor_id)
                _append_actor(row, bucket=critters)

        native_enemies = payload.get("enemies", [])
        if isinstance(native_enemies, list):
            for enemy in native_enemies:
                if not isinstance(enemy, dict):
                    continue
                enemy_id = enemy.get("id")
                kind = enemy.get("kind")
                if isinstance(kind, str) and is_critter_kind(kind):
                    if isinstance(enemy_id, str) and enemy_id in seen_critter_ids:
                        continue
                    _append_actor(enemy, bucket=critters)
                    if isinstance(enemy_id, str) and enemy_id:
                        seen_critter_ids.add(enemy_id)
                    continue
                _append_actor(enemy, bucket=enemies)
        players: list[dict[str, Any]] = []
        native_players = payload.get("players", [])
        if isinstance(native_players, list):
            for other in native_players:
                if not isinstance(other, dict):
                    continue
                other_position = other.get("position", {})
                if not isinstance(other_position, dict):
                    other_position = {}
                other_id = other.get("id")
                if not isinstance(other_id, str) or not other_id:
                    continue
                other_name = other.get("name")
                if not isinstance(other_name, str) or _looks_like_element_kind_id(
                    other_name
                ):
                    other_name = None
                class_name = other.get("class")
                if class_name is not None and not isinstance(class_name, str):
                    class_name = None
                uid = other.get("uid")
                if uid is not None and not isinstance(uid, str):
                    uid = None
                players.append(
                    {
                        "id": other_id,
                        "name": other_name,
                        "uid": uid,
                        "class": class_name or "",
                        "level": other.get("level"),
                        "x": other_position.get("x"),
                        "y": other_position.get("y"),
                        "z": other_position.get("z"),
                        "heading": other.get("heading", 0.0),
                        "distance": other.get("distance"),
                    }
                )
        interactibles: list[dict[str, Any]] = []
        native_interactibles = payload.get("interactibles", [])
        if isinstance(native_interactibles, list):
            for item in native_interactibles:
                if not isinstance(item, dict):
                    continue
                item_position = item.get("position", {})
                if not isinstance(item_position, dict):
                    item_position = {}
                item_id = item.get("id")
                kind = item.get("kind")
                item_name = item.get("name")
                if not isinstance(item_id, str) or not item_id:
                    continue
                if kind is not None and not isinstance(kind, str):
                    kind = None
                if item_name is not None and not isinstance(item_name, str):
                    item_name = None
                interactibles.append(
                    {
                        "id": item_id,
                        "kind": (kind or "gatherable").strip().lower() or "gatherable",
                        "name": item_name or "",
                        "size": _gatherable_size(item_name or ""),
                        "x": item_position.get("x"),
                        "y": item_position.get("y"),
                        "z": item_position.get("z"),
                        "live": True,
                    }
                )
        instance: dict[str, Any] = {
            "type": "unknown",
            "map_id": "",
            "is_rift": False,
            "is_dungeon": False,
            "is_world_map": False,
            "activity_kind": "",
        }
        native_instance = payload.get("instance")
        if isinstance(native_instance, dict):
            instance_type = native_instance.get("type")
            map_id = native_instance.get("map_id")
            activity_kind = native_instance.get("activity_kind")
            if isinstance(instance_type, str) and instance_type:
                instance["type"] = instance_type
            if isinstance(map_id, str):
                instance["map_id"] = map_id
            if isinstance(activity_kind, str):
                instance["activity_kind"] = activity_kind
            instance["is_rift"] = bool(native_instance.get("is_rift"))
            instance["is_dungeon"] = bool(native_instance.get("is_dungeon"))
            instance["is_world_map"] = bool(native_instance.get("is_world_map"))
        time_of_day: dict[str, Any] | None = None
        native_tod = payload.get("time_of_day")
        if isinstance(native_tod, dict):
            factor = safe_float(native_tod.get("factor"), float("nan"))
            elapsed = safe_float(native_tod.get("elapsed"), float("nan"))
            speed = safe_float(native_tod.get("speed"), float("nan"))
            if (
                math.isfinite(factor)
                and math.isfinite(elapsed)
                and math.isfinite(speed)
            ):
                time_of_day = {
                    "factor": factor % 1.0,
                    "elapsed": elapsed,
                    "speed": speed,
                    "paused": bool(native_tod.get("paused")),
                }
        return {
            "schema": 1,
            "bridge_version": payload.get("bridge_version"),
            "source_time": payload.get("timestamp_ms"),
            # The bridge numbers its samples, so a jump greater than one means
            # writes landed between polls and only the newest survived.
            "source_sequence": payload.get("sequence"),
            "locked": payload.get("state") == "connected",
            "sections": ["player"],
            "party": party,
            "enemies": enemies,
            "critters": critters,
            "players": players,
            "interactibles": interactibles,
            "instance": instance,
            "time_of_day": time_of_day,
            "completed_elements": payload.get("completed_elements", []),
            "completed_activities": payload.get("completed_activities", []),
            "player": {
                "name": player_name,
                "uid": native_player.get("uid"),
                "class": native_player.get("class"),
                "level": native_player.get("level"),
                "in_combat": native_player.get("in_combat"),
                "hp": health,
                "max_hp": max_health,
                "hp_pct": hp_pct,
                "shield": native_player.get("shield"),
                "energy": native_player.get("special_energy"),
                "hp_regen": native_player.get("health_regen"),
                "energy_regen": native_player.get("special_energy_regen"),
                "currencies": enrich_currencies(
                    native_player.get("currencies") or [],
                    native_player.get("currency_counters")
                    if isinstance(native_player.get("currency_counters"), dict)
                    else None,
                ),
                "x": position.get("x"),
                "y": position.get("y"),
                "z": position.get("z"),
                "heading": payload.get("rotation_z"),
                "camera_heading": payload.get("camera_yaw"),
            },
            "native_bridge": payload,
            "dps": payload.get("dps", {}),
        }

    def poll(self) -> None:
        if not self.online:
            return
        message = "Waiting for bridge output"
        connected = False
        age: float | None = None
        changed = False

        try:
            stat = self.live_file.stat()
            if stat.st_mtime_ns != self._live_mtime_ns:
                payload = self._read_json(self.live_file)
                if not isinstance(payload, dict) or payload.get("schema") != 1:
                    raise ValueError("unsupported live-state schema")
                self.state = self._normalize_native(payload)
                self._live_mtime_ns = stat.st_mtime_ns
                self._last_good_monotonic = time.monotonic()
                changed = True
            age = max(0.0, time.time() - stat.st_mtime)
            native_connected = (
                self.state.get("native_bridge", {}).get("state") == "connected"
            )
            connected = age < 2.0 and native_connected
            if connected:
                message = "Connected"
            elif age >= 2.0:
                message = f"Bridge output stale ({age:.1f}s)"
            else:
                message = "Waiting for live player data"
        except FileNotFoundError:
            pass
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            message = f"Live-state read error: {exc}"

        try:
            if self.asset_poi_file.is_file():
                if self._active_poi_file != self.asset_poi_file:
                    self._active_poi_file = self.asset_poi_file
                    self._poi_mtime_ns = -1
                stat = self.asset_poi_file.stat()
                if stat.st_mtime_ns != self._poi_mtime_ns:
                    payload = self._read_json(self.asset_poi_file)
                    raw = (
                        payload.get("pois", [])
                        if isinstance(payload, dict)
                        else payload
                    )
                    if isinstance(raw, list):
                        self.pois = [
                            item for item in raw if isinstance(item, dict)
                        ]
                    self._poi_mtime_ns = stat.st_mtime_ns
                    changed = True
        except FileNotFoundError:
            pass
        except (OSError, ValueError, json.JSONDecodeError):
            # Keep the last valid POI snapshot; live telemetry is more important.
            pass

        now = time.monotonic()
        if not changed and (now - self._last_emit_monotonic) < (
            self.FRESHNESS_INTERVAL_MS / 1000.0
        ):
            return
        self._last_emit_monotonic = now
        self.updated.emit(
            Snapshot(
                self.state,
                self.pois,
                connected,
                message,
                age,
                str(self.live_file),
                str(self._active_poi_file),
            )
        )
