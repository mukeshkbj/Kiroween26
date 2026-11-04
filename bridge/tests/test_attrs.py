from seance_bridge.attrs import attrs_from_byte


def test_protected_flag():
    assert attrs_from_byte(0x80).protected is True
    assert attrs_from_byte(0x00).protected is False


def test_numeric_flag():
    assert attrs_from_byte(0x40).numeric is True
    assert attrs_from_byte(0x80).numeric is False


def test_non_display_is_hidden():
    # display bits 00 => non-display (hidden)
    assert attrs_from_byte(0x80).hidden is True      # protected + non-display
    assert attrs_from_byte(0x40).hidden is True      # numeric + non-display (password-ish)
    # display bits 01 => normal display, not hidden
    assert attrs_from_byte(0x88).hidden is False     # protected + normal display


def test_intensified_flag():
    # display bits 11 => intensified
    assert attrs_from_byte(0x98).intensified is True  # protected + intensified
    assert attrs_from_byte(0x88).intensified is False


def test_mdt_flag():
    assert attrs_from_byte(0x82).mdt is True        # protected + mdt
    assert attrs_from_byte(0x80).mdt is False
