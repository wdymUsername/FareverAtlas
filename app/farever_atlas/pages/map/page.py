"""Map page contract and map-owned UI mixins."""

from __future__ import annotations

from .custom_waypoints import CustomWaypointMixin
from .dps_overlay import DpsOverlayMixin
from .filter_sidebar import FilterSidebarMixin
from .gather_nav import GatherNavMixin


class MapPageMixin(
    FilterSidebarMixin, CustomWaypointMixin, GatherNavMixin, DpsOverlayMixin
):
    """Map filters, waypoints, gather nav, and DPS overlay behavior."""


class MapPage:
    """Registered map page: shared context bar + body hosted by the shell."""

    PAGE_ID = "map"

    def __init__(self, context_bar, body) -> None:
        self.context_bar = context_bar
        self.body = body

    def on_activated(self) -> None:
        return None

    def on_deactivated(self) -> None:
        return None
