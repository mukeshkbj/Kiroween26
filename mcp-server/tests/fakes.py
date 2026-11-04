"""Compatibility shim: the fakes now live in ``seance_mcp.fake`` (contracts section 2.2)."""
from seance_mcp.fake import (  # noqa: F401
    H,
    HN,
    P,
    PARSER,
    U,
    UN,
    FakePort,
    ScreenSpec,
    logon_screen,
    menu_screen,
    rc,
)
