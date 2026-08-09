"""Proximity toasts for special enemies and wild critters."""

from __future__ import annotations

import math
from typing import Any

from ...config import safe_float
from ...cull_limits import (
    DEFAULT_CRITTER_XY_M,
    DEFAULT_CRITTER_Z_M,
    DEFAULT_ENEMY_XY_M,
    DEFAULT_ENEMY_Z_M,
)
from ...display_names import format_unit_tooltip_name
from ...toast import notify


class ProximityAlertsMixin:
    """Spot special enemies / wild critters and toast when they enter range."""

    SPOT_TOAST_MS = 10_000

    def _init_proximity_alert_state(self) -> None:
        # Actor ids currently in alert range that have already fired this stay.
        self._proximity_seen_ids: set[str] = set()
        # Actor ids with a toast still on screen (blocks re-stacking).
        self._proximity_toast_ids: set[str] = set()

    def _proximity_alert_tick(self, snapshot: Any = None) -> None:
        player = self._proximity_player_position(snapshot)
        if player is None:
            self._proximity_seen_ids.clear()
            return

        state = self._proximity_snapshot_state(snapshot)
        enemies = state.get("enemies", [])
        critters = state.get("critters", [])
        if not isinstance(enemies, list):
            enemies = []
        if not isinstance(critters, list):
            critters = []

        radar = getattr(self, "radar", None)
        enemy_xy = float(
            getattr(radar, "enemy_xy_m", DEFAULT_ENEMY_XY_M)
            if radar is not None
            else DEFAULT_ENEMY_XY_M
        )
        enemy_z = float(
            getattr(radar, "enemy_z_fade", DEFAULT_ENEMY_Z_M)
            if radar is not None
            else DEFAULT_ENEMY_Z_M
        )
        critter_xy = float(
            getattr(radar, "critter_xy_m", DEFAULT_CRITTER_XY_M)
            if radar is not None
            else DEFAULT_CRITTER_XY_M
        )
        critter_z = float(
            getattr(radar, "critter_z_fade", DEFAULT_CRITTER_Z_M)
            if radar is not None
            else DEFAULT_CRITTER_Z_M
        )

        in_range: set[str] = set()

        for enemy in enemies:
            if not isinstance(enemy, dict):
                continue
            if not self._proximity_is_special_enemy(enemy):
                continue
            actor_id = str(enemy.get("id") or "").strip()
            if not actor_id:
                continue
            if not self._proximity_in_range(
                player, enemy, xy_m=enemy_xy, z_m=enemy_z
            ):
                continue
            in_range.add(actor_id)
            self._proximity_maybe_alert_enemy(actor_id, enemy)

        for critter in critters:
            if not isinstance(critter, dict):
                continue
            actor_id = str(critter.get("id") or "").strip()
            if not actor_id:
                continue
            if not self._proximity_in_range(
                player, critter, xy_m=critter_xy, z_m=critter_z
            ):
                continue
            in_range.add(actor_id)
            self._proximity_maybe_alert_critter(actor_id, critter)

        # Drop ids that left range so a later re-entry can alert again.
        self._proximity_seen_ids &= in_range | self._proximity_toast_ids

    def _proximity_maybe_alert_enemy(
        self, actor_id: str, enemy: dict[str, Any]
    ) -> None:
        if actor_id in self._proximity_seen_ids or actor_id in self._proximity_toast_ids:
            self._proximity_seen_ids.add(actor_id)
            return
        kind = str(enemy.get("kind") or "")
        name = format_unit_tooltip_name(kind) if kind else "Enemy"
        self._proximity_fire_toast(
            actor_id,
            f"{name} spotted nearby!",
            kind="warning",
        )

    def _proximity_maybe_alert_critter(
        self, actor_id: str, critter: dict[str, Any]
    ) -> None:
        if actor_id in self._proximity_seen_ids or actor_id in self._proximity_toast_ids:
            self._proximity_seen_ids.add(actor_id)
            return
        unit_kind = str(critter.get("kind") or "")
        name = format_unit_tooltip_name(unit_kind) if unit_kind else "Critter"
        payload = {
            "id": actor_id,
            "kind": unit_kind,
            "x": safe_float(critter.get("x")),
            "y": safe_float(critter.get("y")),
            "z": safe_float(critter.get("z")),
            "spark": bool(critter.get("spark")),
        }

        def _navigate() -> None:
            navigate = getattr(self, "force_navigate_to_critter", None)
            if callable(navigate):
                navigate(payload)

        self._proximity_fire_toast(
            actor_id,
            f"{name} spotted nearby!",
            kind="info",
            action_label="Navigate",
            on_action=_navigate,
        )

    def _proximity_fire_toast(
        self,
        actor_id: str,
        message: str,
        *,
        kind: str,
        action_label: str | None = None,
        on_action=None,
    ) -> None:
        self._proximity_seen_ids.add(actor_id)
        self._proximity_toast_ids.add(actor_id)

        def _on_dismiss() -> None:
            self._proximity_toast_ids.discard(actor_id)

        notify(
            self,  # type: ignore[arg-type]
            message,
            kind=kind,
            duration_ms=self.SPOT_TOAST_MS,
            action_label=action_label,
            on_action=on_action,
            on_dismiss=_on_dismiss,
        )

    @staticmethod
    def _proximity_is_special_enemy(enemy: dict[str, Any]) -> bool:
        if bool(enemy.get("spark")):
            return True
        return bool(
            enemy.get("boss")
            or enemy.get("miniboss")
            or enemy.get("unique")
            or enemy.get("elite")
        )

    @staticmethod
    def _proximity_in_range(
        player: dict[str, float],
        actor: dict[str, Any],
        *,
        xy_m: float,
        z_m: float,
    ) -> bool:
        px = safe_float(player.get("x"), math.nan)
        py = safe_float(player.get("y"), math.nan)
        pz = safe_float(player.get("z"), math.nan)
        ax = safe_float(actor.get("x"), math.nan)
        ay = safe_float(actor.get("y"), math.nan)
        az = safe_float(actor.get("z"), pz)
        if not (math.isfinite(px) and math.isfinite(py) and math.isfinite(ax) and math.isfinite(ay)):
            return False
        if xy_m > 0.0 and math.hypot(ax - px, ay - py) > xy_m:
            return False
        if (
            z_m > 0.0
            and math.isfinite(pz)
            and math.isfinite(az)
            and abs(az - pz) > z_m
        ):
            return False
        return True

    def _proximity_snapshot_state(self, snapshot: Any = None) -> dict[str, Any]:
        snap = snapshot if snapshot is not None else getattr(self, "latest_snapshot", None)
        state = getattr(snap, "state", None) if snap is not None else None
        return state if isinstance(state, dict) else {}

    def _proximity_player_position(
        self, snapshot: Any = None
    ) -> dict[str, float] | None:
        getter = getattr(self, "_current_player_position", None)
        if callable(getter) and snapshot is None:
            player = getter()
            if isinstance(player, dict):
                return player
        state = self._proximity_snapshot_state(snapshot)
        player = state.get("player", {})
        if not isinstance(player, dict):
            return None
        x = safe_float(player.get("x"), math.nan)
        y = safe_float(player.get("y"), math.nan)
        z = safe_float(player.get("z"), 0.0)
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return {"x": x, "y": y, "z": z}
