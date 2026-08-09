"""Shared Atlas shell footer."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..pages.map.status import GameTimeStatusWidget


def build_footer() -> QtWidgets.QWidget:
    """Time of day, bridge status, view mode, zoom, and coords."""
    footer = QtWidgets.QWidget()
    footer.setObjectName("minimapFooter")
    footer_layout = QtWidgets.QHBoxLayout(footer)
    footer_layout.setContentsMargins(5, 0, 5, 0)
    footer_layout.setSpacing(8)

    game_time = GameTimeStatusWidget()

    connection = QtWidgets.QLabel("● Waiting")
    connection.setObjectName("connectionStatus")
    connection.setProperty("status", "waiting")
    connection.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignLeft
        | QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    connection.setToolTip("Waiting for native_bridge/farever-telemetry.json")

    view_mode = QtWidgets.QLabel("")
    view_mode.setObjectName("viewModeStatus")
    view_mode.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignRight
        | QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    view_mode.setVisible(False)

    help_button = QtWidgets.QToolButton()
    help_button.setObjectName("mapHelpButton")
    help_button.setText("")
    help_button.setCheckable(True)
    help_button.setFixedSize(19, 21)
    help_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    help_button.setToolTip("Show map controls")

    zoom = QtWidgets.QLabel("—")
    zoom.setObjectName("zoomValue")
    zoom.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignRight
        | QtCore.Qt.AlignmentFlag.AlignVCenter
    )

    position = QtWidgets.QLabel("X —   Y —")
    position.setObjectName("positionStatus")
    position.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignRight
        | QtCore.Qt.AlignmentFlag.AlignVCenter
    )

    footer_layout.addWidget(
        game_time, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    footer_layout.addWidget(
        connection, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    footer_layout.addStretch(1)
    footer_layout.addWidget(
        view_mode, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
    )
    footer_layout.addWidget(zoom, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    footer_layout.addWidget(position, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    footer_layout.addWidget(help_button, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
    return footer
