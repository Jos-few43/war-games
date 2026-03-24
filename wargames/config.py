from pathlib import Path

import tomli

from wargames.models import GameConfig, ScoringProfile, TournamentConfig

PRESET_DIR = Path(__file__).resolve().parent.parent / 'config' / 'scoring'


def load_scoring_preset(name: str) -> ScoringProfile:
    """Load a scoring preset by name from config/scoring/."""
    preset_path = PRESET_DIR / f'{name}.toml'
    if not preset_path.exists():
        raise FileNotFoundError(f'Scoring preset not found: {preset_path}')
    with open(preset_path, 'rb') as f:
        data = tomli.load(f)
    return ScoringProfile.model_validate(data)


def _build_scoring(raw_scoring: dict) -> ScoringProfile:
    """Build ScoringProfile from [scoring] TOML section, merging with preset."""
    preset_name = raw_scoring.pop('profile', 'balanced')
    base = load_scoring_preset(preset_name)
    if not raw_scoring:
        return base
    # Deep-merge: override base dict with any provided sub-sections
    base_dict = base.model_dump()
    for section, overrides in raw_scoring.items():
        if section in base_dict and isinstance(overrides, dict):
            base_dict[section].update(overrides)
        else:
            base_dict[section] = overrides
    return ScoringProfile.model_validate(base_dict)


def load_config(path: Path) -> GameConfig:
    with open(path, 'rb') as f:
        data = tomli.load(f)
    raw_scoring = data.pop('scoring', {})
    config = GameConfig.model_validate(data)
    config.scoring = _build_scoring(raw_scoring)
    return config


def load_roster(path: Path) -> TournamentConfig:
    with open(path, 'rb') as f:
        data = tomli.load(f)
    tournament_data = data.get('tournament', {})
    models = data.get('models', [])
    global_api_key = data.get('api_key', '') or tournament_data.get('api_key', '')
    for model in models:
        if global_api_key and not model.get('api_key'):
            model['api_key'] = global_api_key
    tournament_data['models'] = models
    return TournamentConfig.model_validate(tournament_data)
