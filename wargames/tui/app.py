from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, RichLog
from textual.containers import Horizontal, Vertical
import aiosqlite
from wargames.tui.bridge import EventBridge


class TeamPanel(Static):
    """Displays a team's name, model, score, and draft picks."""

    def __init__(self, team: str, **kwargs):
        super().__init__(**kwargs)
        self.team = team

    def compose(self) -> ComposeResult:
        yield Static(f"  {self.team.upper()} TEAM", classes="team-title")
        yield Static("Score: --", id=f"{self.team}-score")
        yield Static("Draft: --", id=f"{self.team}-draft")


class LiveFeed(RichLog):
    """Scrolling log of turn-by-turn match events."""
    pass


class SeasonStats(Static):
    """Win/loss record and phase info."""

    def compose(self) -> ComposeResult:
        yield Static("SEASON STATS", classes="section-title")
        yield Static("Red wins: --", id="red-wins")
        yield Static("Blue wins: --", id="blue-wins")
        yield Static("Auto wins: --", id="auto-wins")
        yield Static("Phase: --", id="current-phase")


class RecentReports(Static):
    """Last N round summaries."""

    def compose(self) -> ComposeResult:
        yield Static("RECENT ROUNDS", classes="section-title")
        yield Static("No rounds yet.", id="recent-list")


class WarGamesTUI(App):
    TITLE = "War Games"
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
    """

    BINDINGS = [
        ("d", "show_drafts", "Draft log"),
        ("r", "show_reports", "Reports"),
        ("p", "toggle_pause", "Pause"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: str, bridge: EventBridge | None = None, **kwargs):
        super().__init__(**kwargs)
        self.db_path = db_path
        self._bridge = bridge
        self._paused = False
        self.title = "War Games"

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="teams"):
            yield TeamPanel("red")
            yield TeamPanel("blue")
        yield LiveFeed(id="feed", highlight=True, markup=True)
        with Horizontal(id="bottom"):
            yield SeasonStats()
            yield RecentReports()
        yield Footer()

    def on_mount(self):
        self.set_interval(2.0, self.refresh_data)
        self.set_interval(0.5, self.consume_events)

    def consume_events(self):
        """Drain bridge and write events to live feed."""
        if not self._bridge:
            return
        for event_type, data in self._bridge.drain():
            feed = self.query_one("#feed", LiveFeed)
            if event_type == "draft_complete":
                red_tools = ", ".join(data.get("red", []))
                blue_tools = ", ".join(data.get("blue", []))
                feed.write(f"[bold]DRAFT[/] Red: {red_tools}")
                feed.write(f"[bold]DRAFT[/] Blue: {blue_tools}")
            elif event_type == "attack":
                turn = data.get("turn", "?")
                success = data.get("success", False)
                pts = data.get("points", 0)
                color = "green" if success else "red"
                desc = str(data.get("description", ""))[:80]
                feed.write(f"[{color}]T{turn} ATK[/] {'HIT' if success else 'MISS'} (+{pts}) {desc}")
            elif event_type == "defense":
                turn = data.get("turn", "?")
                blocked = data.get("blocked", False)
                color = "blue" if blocked else "yellow"
                feed.write(f"[{color}]T{turn} DEF[/] {'BLOCKED' if blocked else 'MISSED'}")
            elif event_type == "round_complete":
                outcome = data.get("outcome", "?")
                score = data.get("red_score", "?")
                feed.write(f"[bold]━━━ ROUND COMPLETE: {outcome} (score: {score}) ━━━[/]")

    async def refresh_data(self):
        """Poll SQLite for latest state and update widgets."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                # Season stats
                cursor = await db.execute(
                    "SELECT "
                    "COUNT(*) as total, "
                    "SUM(CASE WHEN outcome='red_win' THEN 1 ELSE 0 END) as red_wins, "
                    "SUM(CASE WHEN outcome='blue_win' THEN 1 ELSE 0 END) as blue_wins, "
                    "SUM(CASE WHEN outcome='red_auto_win' THEN 1 ELSE 0 END) as auto_wins "
                    "FROM rounds"
                )
                row = await cursor.fetchone()
                if row:
                    self.query_one("#red-wins", Static).update(f"Red wins: {row['red_wins']}")
                    self.query_one("#blue-wins", Static).update(f"Blue wins: {row['blue_wins']}")
                    self.query_one("#auto-wins", Static).update(f"Auto wins: {row['auto_wins']}")

                # Current phase
                cursor = await db.execute(
                    "SELECT value FROM game_state WHERE key='current_phase'"
                )
                phase_row = await cursor.fetchone()
                if phase_row:
                    self.query_one("#current-phase", Static).update(f"Phase: {phase_row['value']}")

                # Latest round for scores
                cursor = await db.execute(
                    "SELECT * FROM rounds ORDER BY round_number DESC LIMIT 1"
                )
                latest = await cursor.fetchone()
                if latest:
                    self.query_one("#red-score", Static).update(f"Score: {latest['red_score']}")

                # Recent rounds
                cursor = await db.execute(
                    "SELECT round_number, outcome, red_score FROM rounds ORDER BY round_number DESC LIMIT 5"
                )
                recent = await cursor.fetchall()
                if recent:
                    lines = []
                    for r in recent:
                        lines.append(f"R{r['round_number']}: {r['outcome']} (score: {r['red_score']})")
                    self.query_one("#recent-list", Static).update("\n".join(lines))

        except Exception:
            pass  # DB may not exist yet

    def action_quit(self):
        self.exit()

    def action_show_drafts(self):
        feed = self.query_one("#feed", LiveFeed)
        feed.write("[Draft log - not yet implemented]")

    def action_show_reports(self):
        feed = self.query_one("#feed", LiveFeed)
        feed.write("[Reports - not yet implemented]")

    def action_toggle_pause(self):
        feed = self.query_one("#feed", LiveFeed)
        if self._paused:
            self._paused = False
            feed.write("[bold green]RESUMED[/]")
            self.sub_title = ""
        else:
            self._paused = True
            feed.write("[bold yellow]PAUSED[/]")
            self.sub_title = "PAUSED"
