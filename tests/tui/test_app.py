import pytest
from wargames.tui.app import (
    WarGamesTUI,
    TeamPanel,
    LiveFeed,
    SeasonStats,
    TokenPanel,
    StrategyPanel,
    ScoreBreakdown,
    PerformancePanel,
)


def test_tui_app_instantiates():
    app = WarGamesTUI(db_path='/tmp/nonexistent.db')
    assert app.title == 'War Games'


def test_tui_has_required_widgets():
    from wargames.tui import app as app_module

    assert hasattr(app_module, 'TeamPanel')
    assert hasattr(app_module, 'LiveFeed')
    assert hasattr(app_module, 'SeasonStats')
    assert hasattr(app_module, 'TokenPanel')


def test_tui_has_new_strategy_panel():
    from wargames.tui import app as app_module

    assert hasattr(app_module, 'StrategyPanel')


def test_tui_has_score_breakdown():
    from wargames.tui import app as app_module

    assert hasattr(app_module, 'ScoreBreakdown')


def test_tui_has_performance_panel():
    from wargames.tui import app as app_module

    assert hasattr(app_module, 'PerformancePanel')


def test_strategy_panel_structure():
    panel = StrategyPanel()
    assert hasattr(panel, 'compose')


def test_score_breakdown_structure():
    panel = ScoreBreakdown()
    assert hasattr(panel, 'compose')


def test_performance_panel_structure():
    panel = PerformancePanel()
    assert hasattr(panel, 'compose')


def test_token_panel_structure():
    panel = TokenPanel()
    assert hasattr(panel, 'compose')
