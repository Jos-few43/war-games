import aiosqlite
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Label, RichLog, Static

from wargames.tui.bridge import EventBridge


class TeamPanel(Static):
    """Displays a team's name, model, score, and draft picks."""

    def __init__(self, team: str, **kwargs):
        super().__init__(**kwargs)
        self.team = team

    def compose(self) -> ComposeResult:
        yield Static(f'  {self.team.upper()} TEAM', classes='team-title')
        yield Static('Score: --', id=f'{self.team}-score')
        yield Static('Draft: --', id=f'{self.team}-draft')


class LiveFeed(RichLog):
    """Scrolling log of turn-by-turn match events."""

    pass


class SeasonStats(Static):
    """Win/loss record and phase info."""

    def compose(self) -> ComposeResult:
        yield Static('SEASON STATS', classes='section-title')
        yield Static('Red wins: --', id='red-wins')
        yield Static('Blue wins: --', id='blue-wins')
        yield Static('Auto wins: --', id='auto-wins')
        yield Static('Phase: --', id='current-phase')


class RecentReports(Static):
    """Last N round summaries."""

    def compose(self) -> ComposeResult:
        yield Static('RECENT ROUNDS', classes='section-title')
        yield Static('No rounds yet.', id='recent-list')


class TokenPanel(Static):
    """Live token usage and cost display."""

    def compose(self) -> ComposeResult:
        yield Static('TOKENS & COST', classes='section-title')
        yield Static('Red: -- tokens ($--)', id='red-tokens')
        yield Static('Blue: -- tokens ($--)', id='blue-tokens')
        yield Static('Total cost: $--', id='total-cost')


class WarGamesTUI(App):
    TITLE = 'War Games'
    CSS = """
    Screen {
        layout: vertical;
    }
    #teams {
        height: 7;
        layout: horizontal;
    }
    TeamPanel {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    .team-title {
        text-style: bold;
        color: $text;
    }
    .section-title {
        text-style: bold;
        color: $accent;
    }
    #feed {
        height: 1fr;
        border: solid $primary;
    }
    #bottom {
        height: 10;
        layout: horizontal;
    }
    SeasonStats {
        width: 1fr;
        border: solid $secondary;
        padding: 0 1;
    }
    RecentReports {
        width: 1fr;
        border: solid $secondary;
        padding: 0 1;
    }
    TokenPanel {
        width: 1fr;
        border: solid $warning;
        padding: 0 1;
    }
    StrategyPanel {
        width: 1fr;
        border: solid $success;
        padding: 0 1;
    }
    ScoreBreakdown {
        width: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    PerformancePanel {
        width: 1fr;
        border: solid $accent;
        padding: 0 1;
    }
    #sidebar {
        width: 25;
        layout: vertical;
    }
    #main {
        layout: horizontal;
        height: 1fr;
    }
    #feed {
        width: 1fr;
        border: solid $primary;
    }
    """

    BINDINGS = [
        ('d', 'show_drafts', 'Draft log'),
        ('r', 'show_reports', 'Reports'),
        ('p', 'toggle_pause', 'Pause'),
        ('q', 'quit', 'Quit'),
    ]

    def __init__(self, db_path: str, bridge: EventBridge | None = None, **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path
        self._bridge = bridge
        self._paused = False
        self.title = 'War Games'

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id='teams'):
            yield TeamPanel('red')
            yield TeamPanel('blue')
        with Horizontal(id='main'):
            yield LiveFeed(id='feed', highlight=True, markup=True)
            with Vertical(id='sidebar'):
                yield StrategyPanel()
                yield ScoreBreakdown()
                yield PerformancePanel()
        with Horizontal(id='bottom'):
            yield SeasonStats()
            yield RecentReports()
            yield TokenPanel()
        yield Footer()

    def on_mount(self):
        self.set_interval(2.0, self.refresh_data)
        self.set_interval(0.5, self.consume_events)

    def consume_events(self):
        """Drain bridge and write events to live feed."""
        if not self._bridge:
            return
        for event_type, data in self._bridge.drain():
            feed = self.query_one('#feed', LiveFeed)
            if event_type == 'draft_complete':
                red_tools = ', '.join(data.get('red', []))
                blue_tools = ', '.join(data.get('blue', []))
                feed.write(f'[bold]DRAFT[/] Red: {red_tools}')
                feed.write(f'[bold]DRAFT[/] Blue: {blue_tools}')
            elif event_type == 'attack':
                turn = data.get('turn', '?')
                success = data.get('success', False)
                pts = data.get('points', 0)
                color = 'green' if success else 'red'
                desc = str(data.get('description', ''))[:80]
                feed.write(
                    f'[{color}]T{turn} ATK[/] {"HIT" if success else "MISS"} (+{pts}) {desc}'
                )
            elif event_type == 'defense':
                turn = data.get('turn', '?')
                blocked = data.get('blocked', False)
                color = 'blue' if blocked else 'yellow'
                feed.write(f'[{color}]T{turn} DEF[/] {"BLOCKED" if blocked else "MISSED"}')
            elif event_type == 'round_complete':
                outcome = data.get('outcome', '?')
                score = data.get('red_score', '?')
                feed.write(f'[bold]━━━ ROUND COMPLETE: {outcome} (score: {score}) ━━━[/]')
            elif event_type == 'token_usage':
                team = data.get('team', '?')
                tokens = data.get('tokens', 0)
                cost = data.get('cost', 0.0)
                feed.write(f'[dim]TOKENS {team}: {tokens:,} (${cost:.4f})[/]')

    async def refresh_data(self):
        """Poll SQLite for latest state and update widgets."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                # Season stats
                cursor = await db.execute(
                    'SELECT '
                    'COUNT(*) as total, '
                    "SUM(CASE WHEN outcome='red_win' THEN 1 ELSE 0 END) as red_wins, "
                    "SUM(CASE WHEN outcome='blue_win' THEN 1 ELSE 0 END) as blue_wins, "
                    "SUM(CASE WHEN outcome='red_auto_win' THEN 1 ELSE 0 END) as auto_wins "
                    'FROM rounds'
                )
                row = await cursor.fetchone()
                if row:
                    self.query_one('#red-wins', Static).update(f'Red wins: {row["red_wins"]}')
                    self.query_one('#blue-wins', Static).update(f'Blue wins: {row["blue_wins"]}')
                    self.query_one('#auto-wins', Static).update(f'Auto wins: {row["auto_wins"]}')

                # Current phase
                cursor = await db.execute("SELECT value FROM game_state WHERE key='current_phase'")
                phase_row = await cursor.fetchone()
                if phase_row:
                    self.query_one('#current-phase', Static).update(f'Phase: {phase_row["value"]}')

                # Latest round for scores
                cursor = await db.execute('SELECT * FROM rounds ORDER BY round_number DESC LIMIT 1')
                latest = await cursor.fetchone()
                if latest:
                    self.query_one('#red-score', Static).update(f'Score: {latest["red_score"]}')

                # Recent rounds
                cursor = await db.execute(
                    'SELECT round_number, outcome, red_score FROM rounds ORDER BY round_number DESC LIMIT 5'
                )
                recent = await cursor.fetchall()
                if recent:
                    lines = []
                    for r in recent:
                        lines.append(
                            f'R{r["round_number"]}: {r["outcome"]} (score: {r["red_score"]})'
                        )
                    self.query_one('#recent-list', Static).update('\n'.join(lines))

                # Token usage
                try:
                    cursor = await db.execute(
                        'SELECT team, SUM(prompt_tokens + completion_tokens) as total_tokens, '
                        'SUM(cost) as total_cost FROM token_usage GROUP BY team'
                    )
                    token_rows = await cursor.fetchall()
                    for tr in token_rows:
                        team = tr['team']
                        if team in ('red', 'blue'):
                            self.query_one(f'#{team}-tokens', Static).update(
                                f'{team.title()}: {tr["total_tokens"]:,} tokens (${tr["total_cost"]:.4f})'
                            )

                    cursor = await db.execute(
                        'SELECT COALESCE(SUM(cost), 0) as total FROM token_usage'
                    )
                    cost_row = await cursor.fetchone()
                    if cost_row:
                        self.query_one('#total-cost', Static).update(
                            f'Total cost: ${cost_row["total"]:.4f}'
                        )
                except Exception:
                    pass  # token_usage table may not exist yet

                # Strategy counts
                try:
                    cursor = await db.execute(
                        'SELECT team, COUNT(*) as count FROM strategies WHERE active=1 GROUP BY team'
                    )
                    strat_rows = await cursor.fetchall()
                    for sr in strat_rows:
                        team = sr['team']
                        if team in ('red', 'blue'):
                            self.query_one(f'#{team}-strategies', Static).update(
                                f'{team.title()}: {sr["count"]} active'
                            )

                    cursor = await db.execute(
                        'SELECT content, win_rate FROM strategies ORDER BY win_rate DESC LIMIT 1'
                    )
                    top_strat = await cursor.fetchone()
                    if top_strat:
                        content = (
                            top_strat['content'][:30] + '...'
                            if len(top_strat['content']) > 30
                            else top_strat['content']
                        )
                        self.query_one('#top-strategy', Static).update(
                            f'Top: {content} ({top_strat["win_rate"]:.1%})'
                        )
                except Exception:
                    pass

                # Score breakdown
                try:
                    cursor = await db.execute(
                        'SELECT SUM(points) as total FROM attacks WHERE success=1'
                    )
                    attack_pts = await cursor.fetchone()
                    if attack_pts and attack_pts['total']:
                        self.query_one('#attack-points', Static).update(
                            f'Attacks: {attack_pts["total"]} pts'
                        )

                    cursor = await db.execute('SELECT SUM(points_earned) as total FROM defenses')
                    defense_pts = await cursor.fetchone()
                    if defense_pts and defense_pts['total']:
                        self.query_one('#defense-points', Static).update(
                            f'Defenses: {defense_pts["total"]} pts'
                        )

                    cursor = await db.execute(
                        "SELECT COUNT(*) as count FROM rounds WHERE outcome='red_auto_win'"
                    )
                    auto_wins = await cursor.fetchone()
                    if auto_wins:
                        self.query_one('#auto-wins-count', Static).update(
                            f'Auto wins: {auto_wins["count"]}'
                        )
                except Exception:
                    pass

                # Performance metrics
                try:
                    cursor = await db.execute(
                        'SELECT model_name, rating FROM model_ratings ORDER BY rating DESC'
                    )
                    ratings = await cursor.fetchall()
                    for i, r in enumerate(ratings[:2]):
                        model = r['model_name']
                        rating = r['rating']
                        if i == 0:
                            self.query_one('#red-elo', Static).update(f'Red ELO: {rating:.0f}')
                        else:
                            self.query_one('#blue-elo', Static).update(f'Blue ELO: {rating:.0f}')

                    cursor = await db.execute(
                        'SELECT '
                        'CAST(SUM(CASE WHEN outcome LIKE "%red_win%" THEN 1 ELSE 0 END) AS FLOAT) / '
                        'NULLIF(COUNT(*), 0) * 100 as win_rate '
                        'FROM rounds'
                    )
                    win_rate_row = await cursor.fetchone()
                    if win_rate_row and win_rate_row['win_rate']:
                        self.query_one('#win-rate', Static).update(
                            f'Win rate: {win_rate_row["win_rate"]:.1f}%'
                        )
                except Exception:
                    pass

        except Exception:
            pass  # DB may not exist yet

    def action_quit(self):
        self.exit()

    def action_show_drafts(self):
        feed = self.query_one('#feed', LiveFeed)
        feed.write('[Draft log - not yet implemented]')

    def action_show_reports(self):
        feed = self.query_one('#feed', LiveFeed)
        feed.write('[Reports - not yet implemented]')

    def action_toggle_pause(self):
        feed = self.query_one('#feed', LiveFeed)
        if self._paused:
            self._paused = False
            feed.write('[bold green]RESUMED[/]')
            self.sub_title = ''
        else:
            self._paused = True
            feed.write('[bold yellow]PAUSED[/]')
            self.sub_title = 'PAUSED'


class StrategyPanel(Static):
    """Real-time strategy visualization."""

    def compose(self) -> ComposeResult:
        yield Static('STRATEGIES', classes='section-title')
        yield Static('Red: -- active', id='red-strategies')
        yield Static('Blue: -- active', id='blue-strategies')
        yield Static('Top win-rate: --', id='top-strategy')


class ScoreBreakdown(Static):
    """Detailed scoring analytics."""

    def compose(self) -> ComposeResult:
        yield Static('SCORE BREAKDOWN', classes='section-title')
        yield Static('Attacks: -- pts', id='attack-points')
        yield Static('Defenses: -- pts', id='defense-points')
        yield Static('Auto wins: --', id='auto-wins-count')


class PerformancePanel(Static):
    """Win-rate trends and ELO ratings."""

    def compose(self) -> ComposeResult:
        yield Static('PERFORMANCE', classes='section-title')
        yield Static('Red ELO: --', id='red-elo')
        yield Static('Blue ELO: --', id='blue-elo')
        yield Static('Win rate: --', id='win-rate')
