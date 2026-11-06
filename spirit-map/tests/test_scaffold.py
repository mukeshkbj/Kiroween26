import seance_spirit


def test_package_imports() -> None:
    assert seance_spirit.__version__


def test_fake_app_is_available() -> None:
    from seance_mcp.fake import fake_insurance

    assert fake_insurance().current == "menu"
