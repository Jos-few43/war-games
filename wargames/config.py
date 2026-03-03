from pathlib import Path
import tomli
from wargames.models import GameConfig


def load_config(path: Path) -> GameConfig:
    with open(path, "rb") as f:
        data = tomli.load(f)
    return GameConfig.model_validate(data)
