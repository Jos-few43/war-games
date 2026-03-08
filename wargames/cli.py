import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from wargames.crawler.cve import NVDCrawler
from wargames.crawler.exploitdb import ExploitDBCrawler
from wargames.config import load_config
from wargames.engine.sandbox import SandboxRunner
from wargames.models import MatchOutcome
from wargames.output.db import Database


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="wargames", description="War Games - LLM Red/Blue Team Competition")
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    start_p = sub.add_parser("start", help="Start a new season")
    start_p.add_argument("--config", default="config/default.toml", help="Config file path")

    # attach
    sub.add_parser("attach", help="Attach TUI to running game")

    # status
    sub.add_parser("status", help="Show game status")

    # pause / resume
    sub.add_parser("pause", help="Pause the running game")
    sub.add_parser("resume", help="Resume a paused game")

    # crawl
    crawl_p = sub.add_parser("crawl", help="Run vulnerability crawler")
    crawl_p.add_argument("--sources", default="nvd,exploitdb", help="Comma-separated sources")

    # report
    report_p = sub.add_parser("report", help="View a round report")
    report_p.add_argument("round_number", type=int, help="Round number to view")

    # export
    export_p = sub.add_parser("export", help="Export season results")
    export_p.add_argument("--format", default="markdown", choices=["markdown", "json"])
    export_p.add_argument("--output", default=None, help="Output file path (default: stdout)")

    # ladder
    sub.add_parser("ladder", help="Show model ELO leaderboard")

    # sandbox
    sandbox_p = sub.add_parser("sandbox", help="Run a single-round sandbox game")
    sandbox_p.add_argument("--config", default="config/default.toml", help="Config file path")
    sandbox_p.add_argument(
        "--loadout", default=None,
        help="Loadout overrides: red=aggressive,blue=defensive",
    )

    return parser.parse_args(argv)


def _default_db_path() -> Path:
    return Path("~/.local/share/wargames/state.db").expanduser()


def _send_signal(sig: int):
    """Send a signal to the running worker."""
    pid_file = Path("~/.local/share/wargames/worker.pid").expanduser()
    if not pid_file.exists():
        print("No running worker found.")
        sys.exit(1)
    pid = int(pid_file.read_text())
    import os
    os.kill(pid, sig)
    print(f"Signal sent to worker (PID {pid}).")


def main(argv: list[str] | None = None):
    args = parse_args(argv)

    if args.command == "start":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        from wargames.worker import Worker
        config = load_config(Path(args.config))
        worker = Worker(config)
        asyncio.run(worker.run())

    elif args.command == "attach":
        from wargames.tui.app import WarGamesTUI
        db_path = Path("~/.local/share/wargames/state.db").expanduser()
        app = WarGamesTUI(db_path=str(db_path))
        app.run()

    elif args.command == "status":
        db_path = Path("~/.local/share/wargames/state.db").expanduser()

        async def _status():
            db = Database(db_path)
            await db.init()
            stats = await db.get_season_stats()
            current_round = await db.get_game_state("current_round") or "0"
            await db.close()
            print(f"Current round: {current_round}")
            print(f"Red wins: {stats['red_wins']}")
            print(f"Blue wins: {stats['blue_wins']}")
            print(f"Auto wins: {stats['auto_wins']}")
            print(f"Total rounds: {stats['total_rounds']}")

        asyncio.run(_status())

    elif args.command == "pause":
        _send_signal(signal.SIGUSR1)

    elif args.command == "resume":
        _send_signal(signal.SIGUSR2)

    elif args.command == "crawl":
        sources = [s.strip() for s in args.sources.split(",")]
        db_path = _default_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)

        async def _crawl():
            db = Database(db_path)
            await db.init()
            total = 0
            if "nvd" in sources:
                crawler = NVDCrawler()
                results = await crawler.fetch()
                await crawler.store(db, results)
                print(f"NVD: {len(results)} CVEs")
                total += len(results)
            if "exploitdb" in sources:
                crawler = ExploitDBCrawler()
                results = await crawler.fetch()
                await crawler.store(db, results)
                print(f"ExploitDB: {len(results)} CVEs")
                total += len(results)
            await db.close()
            print(f"Total: {total} CVEs crawled")

        asyncio.run(_crawl())

    elif args.command == "report":
        db_path = _default_db_path()

        async def _report():
            db = Database(db_path)
            await db.init()
            try:
                result = await db.get_round(args.round_number)
            except KeyError:
                print(f"Round {args.round_number} not found.")
                await db.close()
                return
            await db.close()

            print(f"=== Round {result.round_number} ===")
            print(f"Phase: {result.phase.name}  |  Outcome: {result.outcome.value}")
            print(f"Score: Red {result.red_score} — Blue {result.blue_score} (threshold {result.blue_threshold})")
            print()

            if result.red_draft or result.blue_draft:
                print("-- Draft --")
                for pick in result.red_draft:
                    print(f"  RED  {pick.resource_name} ({pick.resource_category})")
                for pick in result.blue_draft:
                    print(f"  BLUE {pick.resource_name} ({pick.resource_category})")
                print()

            print("-- Attacks --")
            for a in result.attacks:
                status = "HIT" if a.success else "MISS"
                sev = f" [{a.severity.value}]" if a.severity else ""
                print(f"  T{a.turn}: {status}{sev} +{a.points}pts -- {a.description[:80]}")
            print()

            print("-- Defenses --")
            for d in result.defenses:
                status = "BLOCKED" if d.blocked else "MISSED"
                print(f"  T{d.turn}: {status} -{d.points_deducted}pts -- {d.description[:80]}")
            print()

            if result.bug_reports:
                print("-- Bug Reports --")
                for b in result.bug_reports:
                    print(f"  [{b.severity.value}] {b.title}")
                print()

            if result.patches:
                print("-- Patches --")
                for p in result.patches:
                    print(f"  {p.title} -- fixes: {p.fixes[:60]}")

        asyncio.run(_report())

    elif args.command == "export":
        db_path = _default_db_path()

        async def _export():
            db = Database(db_path)
            await db.init()
            results = await db.get_all_rounds()
            await db.close()

            if not results:
                print("No rounds found.")
                return

            if args.format == "json":
                import json
                data = {
                    "rounds": [r.model_dump(mode="json") for r in results],
                    "summary": {
                        "total_rounds": len(results),
                        "red_wins": sum(1 for r in results if r.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN, MatchOutcome.RED_CRITICAL_WIN)),
                        "blue_wins": sum(1 for r in results if r.outcome in (MatchOutcome.BLUE_WIN, MatchOutcome.BLUE_DECISIVE_WIN)),
                    },
                }
                output = json.dumps(data, indent=2)
            else:
                lines = ["# Season Report", ""]
                lines.append("| Round | Phase | Outcome | Red | Blue |")
                lines.append("|-------|-------|---------|-----|------|")
                for r in results:
                    lines.append(f"| {r.round_number} | {r.phase.name} | {r.outcome.value} | {r.red_score} | {r.blue_score} |")
                lines.append("")
                red_w = sum(1 for r in results if r.outcome in (MatchOutcome.RED_WIN, MatchOutcome.RED_AUTO_WIN, MatchOutcome.RED_CRITICAL_WIN))
                blue_w = sum(1 for r in results if r.outcome in (MatchOutcome.BLUE_WIN, MatchOutcome.BLUE_DECISIVE_WIN))
                lines.append(f"**Red wins:** {red_w}  |  **Blue wins:** {blue_w}  |  **Total:** {len(results)}")
                output = "\n".join(lines)

            if args.output:
                Path(args.output).write_text(output)
                print(f"Exported to {args.output}")
            else:
                print(output)

        asyncio.run(_export())

    elif args.command == "ladder":
        db_path = _default_db_path()

        async def _ladder():
            db = Database(db_path)
            await db.init()
            ratings = await db.get_all_ratings()
            await db.close()

            if not ratings:
                print("No ratings yet. Run a season first.")
                return

            header = f"{'Rank':>4}  {'Model':<30}  {'Rating':>7}  {'W':>5}  {'L':>5}  {'D':>5}  Last Played"
            print(header)
            print("-" * len(header))
            for rank, row in enumerate(ratings, start=1):
                last = row.get("last_played") or "—"
                print(
                    f"{rank:>4}  {row['model_name']:<30}  {row['rating']:>7.1f}"
                    f"  {row['wins']:>5}  {row['losses']:>5}  {row['draws']:>5}  {last}"
                )

        asyncio.run(_ladder())

    elif args.command == "sandbox":
        config = load_config(Path(args.config))

        # Parse --loadout into a dict, e.g. "red=aggressive,blue=defensive"
        loadout_overrides: dict[str, str] | None = None
        if args.loadout:
            loadout_overrides = {}
            for item in args.loadout.split(","):
                item = item.strip()
                if "=" in item:
                    key, _, value = item.partition("=")
                    loadout_overrides[key.strip()] = value.strip()

        runner = SandboxRunner(config)

        async def _sandbox():
            result = await runner.run(loadout_overrides=loadout_overrides)

            print(f"=== Sandbox Round ===")
            print(f"Phase: {result.phase.name}  |  Outcome: {result.outcome.value}")
            print(f"Score: Red {result.red_score} — Blue {result.blue_score} (threshold {result.blue_threshold})")
            print()

            if result.red_draft or result.blue_draft:
                print("-- Draft --")
                for pick in result.red_draft:
                    print(f"  RED  {pick.resource_name} ({pick.resource_category})")
                for pick in result.blue_draft:
                    print(f"  BLUE {pick.resource_name} ({pick.resource_category})")
                print()

            print("-- Attacks --")
            for a in result.attacks:
                status = "HIT" if a.success else "MISS"
                sev = f" [{a.severity.value}]" if a.severity else ""
                print(f"  T{a.turn}: {status}{sev} +{a.points}pts -- {a.description[:80]}")
            print()

            print("-- Defenses --")
            for d in result.defenses:
                status = "BLOCKED" if d.blocked else "MISSED"
                print(f"  T{d.turn}: {status} -{d.points_deducted}pts -- {d.description[:80]}")
            print()

            if result.bug_reports:
                print("-- Bug Reports --")
                for b in result.bug_reports:
                    print(f"  [{b.severity.value}] {b.title}")
                print()

            if result.patches:
                print("-- Patches --")
                for p in result.patches:
                    print(f"  {p.title} -- fixes: {p.fixes[:60]}")

        asyncio.run(_sandbox())


if __name__ == "__main__":
    main()
