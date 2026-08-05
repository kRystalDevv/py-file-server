"""Textual screen definitions for the operator console."""

from .base import ConfirmShutdownScreen
from .dashboard import DashboardScreen
from .logs import LogsScreen
from .public_access import PublicAccessScreen
from .qr import QRFullscreenScreen
from .settings import SettingsScreen
from .transfers import TransfersScreen

__all__ = [
    "ConfirmShutdownScreen",
    "DashboardScreen",
    "LogsScreen",
    "PublicAccessScreen",
    "QRFullscreenScreen",
    "SettingsScreen",
    "TransfersScreen",
]
