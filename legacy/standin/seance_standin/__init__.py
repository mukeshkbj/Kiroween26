"""Seance Insurance TN3270 stand-in (presentation layer only).

The business logic is the real COBOL program SEANCSVC on TK4-. See
legacy/standin/README.md for what is real vs stand-in.
"""
from .app import InsuranceApp
from .cobol_client import CobolClient, Policy
from .screens import VOLATILE_REGIONS, all_screens
from .server import StandinServer, serve

__all__ = [
    "InsuranceApp", "CobolClient", "Policy", "VOLATILE_REGIONS",
    "all_screens", "StandinServer", "serve",
]
