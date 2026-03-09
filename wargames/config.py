from pathlib import Path
import tomli
from wargames.models import GameConfig, TournamentConfig


def load_config(path: Path) -> GameConfig:
    with open(path, "rb") as f:
        data = tomli.load(f)
    return GameConfig.model_validate(data)


def load_roster(path: Path) -> TournamentConfig:
    with open(path, "rb") as f:
        data = tomli.load(f)
    tournament_data = data.get("tournament", {})
    tournament_data["models"] = data.get("models", [])
    return TournamentConfig.model_validate(tournament_data)
