"""Codex page scaffold: empty context bar and placeholder body."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class CodexPageMixin:
    """Codex page construction (placeholder until content lands)."""

    def _init_codex_page(self) -> None:
        # Context bar (shell-hosted) and body (page stack) are separate so the
        # shell can swap toolbars independently of page content.
        self.codex_toolbar = QtWidgets.QWidget()
        self.codex_toolbar.setObjectName("codexToolbar")
        self.codex_toolbar.setFixedHeight(46)
        toolbar_layout = QtWidgets.QHBoxLayout(self.codex_toolbar)
        toolbar_layout.setContentsMargins(7, 0, 7, 0)
        toolbar_layout.setSpacing(7)
        toolbar_layout.addStretch(1)

        self.codex_body = QtWidgets.QWidget()
        self.codex_body.setObjectName("codexPage")
        body_layout = QtWidgets.QVBoxLayout(self.codex_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        placeholder = QtWidgets.QLabel("Codex — coming soon")
        placeholder.setObjectName("codexPlaceholder")
        placeholder.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        body_layout.addWidget(placeholder, 1)


class CodexPage:
    """Registered codex page: shared context bar + body hosted by the shell."""

    PAGE_ID = "codex"

    def __init__(self, context_bar, body) -> None:
        self.context_bar = context_bar
        self.body = body

    def on_activated(self) -> None:
        return None

    def on_deactivated(self) -> None:
        return None
