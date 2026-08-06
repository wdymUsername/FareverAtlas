"""Shared Atlas shell footer."""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets


def build_footer() -> QtWidgets.QWidget:
    """Connection status + page-specific status strip."""
    footer = QtWidgets.QWidget()
    footer.setObjectName("minimapFooter")
    footer_layout = QtWidgets.QHBoxLayout(footer)
    footer_layout.setContentsMargins(5, 0, 5, 0)
    footer_layout.setSpacing(8)

    connection = QtWidgets.QLabel("● Waiting for bridge")
    connection.setObjectName("connectionStatus")
    connection.setProperty("status", "waiting")
    connection.setTextFormat(QtCore.Qt.TextFormat.RichText)
    connection.setToolTip("Waiting for native_bridge/farever-telemetry.json")

    position = QtWidgets.QLabel("X —   Y —")
    position.setObjectName("positionStatus")
    position.setAlignment(
        QtCore.Qt.AlignmentFlag.AlignRight
        | QtCore.Qt.AlignmentFlag.AlignVCenter
    )

    footer_layout.addWidget(connection)
    footer_layout.addStretch(1)
    footer_layout.addWidget(position)
    return footer
