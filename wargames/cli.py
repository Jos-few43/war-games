import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from wargames.crawler.cve import NVDCrawler
from wargames.crawler.exploitdb import ExploitDBCrawler
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
        from wargames.config import load_config
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
        print(f"Viewing round {args.round_number}")
        # TODO: implement report viewer

    elif args.command == "export":
        print(f"Exporting in {args.format} format")
        # TODO: implement export


if __name__ == "__main__":
    main()
