"""Polling bridge output and producing immutable snapshots."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore

from .config import ASSET_ROOT, PROJECT_ROOT
from .pages.map.data import Snapshot


class DataHub(QtCore.QObject):
    updated = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.live_file = PROJECT_ROOT / "native_bridge/farever-telemetry.json"
        self.asset_poi_file = ASSET_ROOT / "pois_W1_Siagarta.json"
        self.state: dict[str, Any] = {}
        self.pois: list[dict[str, Any]] = []
        self._live_mtime_ns = -1
        self._poi_mtime_ns = -1
        self._last_good_monotonic: float | None = None
        self._active_poi_file = self.asset_poi_file
        self.online = True
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
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
        name = native_player.get("name")
        if (
            not isinstance(name, str)
            or not (1 <= len(name) <= 64)
            or not name.isascii()
            or not name.isprintable()
        ):
            name = None
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
                        "name": member.get("name"),
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
        native_enemies = payload.get("enemies", [])
        if isinstance(native_enemies, list):
            for enemy in native_enemies:
                if not isinstance(enemy, dict):
                    continue
                enemy_position = enemy.get("position", {})
                if not isinstance(enemy_position, dict):
                    enemy_position = {}
                enemy_id = enemy.get("id")
                kind = enemy.get("kind")
                if not isinstance(enemy_id, str) or not enemy_id:
                    continue
                if kind is not None and not isinstance(kind, str):
                    kind = None
                enemies.append(
                    {
                        "id": enemy_id,
                        "kind": kind or "",
                        "x": enemy_position.get("x"),
                        "y": enemy_position.get("y"),
                        "z": enemy_position.get("z"),
                    }
                )
        return {
            "schema": 1,
            "bridge_version": payload.get("bridge_version"),
            "source_time": payload.get("timestamp_ms"),
            "locked": payload.get("state") == "connected",
            "sections": ["player"],
            "party": party,
            "enemies": enemies,
            "completed_elements": payload.get("completed_elements", []),
            "player": {
                "name": name,
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
                "x": position.get("x"),
                "y": position.get("y"),
                "z": position.get("z"),
                "heading": payload.get("rotation_z"),
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

        try:
            stat = self.live_file.stat()
            if stat.st_mtime_ns != self._live_mtime_ns:
                payload = self._read_json(self.live_file)
                if not isinstance(payload, dict) or payload.get("schema") != 1:
                    raise ValueError("unsupported live-state schema")
                self.state = self._normalize_native(payload)
                self._live_mtime_ns = stat.st_mtime_ns
                self._last_good_monotonic = time.monotonic()
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
        except FileNotFoundError:
            pass
        except (OSError, ValueError, json.JSONDecodeError):
            # Keep the last valid POI snapshot; live telemetry is more important.
            pass

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
