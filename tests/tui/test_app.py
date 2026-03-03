import pytest
from wargames.tui.app import WarGamesTUI, TeamPanel, LiveFeed, SeasonStats


def test_tui_app_instantiates():
    app = WarGamesTUI(db_path="/tmp/nonexistent.db")
    assert app.title == "War Games"


def test_tui_has_required_widgets():
    from wargames.tui import app as app_module
    assert hasattr(app_module, "TeamPanel")
    assert hasattr(app_module, "LiveFeed")
    assert hasattr(app_module, "SeasonStats")
