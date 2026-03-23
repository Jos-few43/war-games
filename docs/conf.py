# Configuration file for the Sphinx documentation builder.

import os
from pathlib import Path

# -- Path setup --------------------------------------------------------------

project_root = Path(__file__).parent.parent
docs_dir = Path(__file__).parent

# Add project root to path so Sphinx can import wargames
import sys

sys.path.insert(0, str(project_root))

# -- Project information -----------------------------------------------------

project = 'War Games'
copyright = '2024-2026, War Games Contributors'
author = 'War Games Contributors'

release = '0.1.0'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.autosummary',
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_furo'
html_static_path = ['_static']
html_title = 'War Games'

html_theme_options = {
    'sidebar': {
        'width': '280px',
    },
    'navigation_depth': 4,
}

# -- Autodoc configuration ---------------------------------------------------

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
}

autodoc_type_aliases = {
    'Agent': 'wargames.teams.agent.Agent',
    'GameConfig': 'wargames.config.GameConfig',
    'RoundResult': 'wargames.models.RoundResult',
}

# -- Napoleon configuration --------------------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = {}

# -- Intersphinx configuration -----------------------------------------------

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'crewai': ('https://docs.crewai.com/', None),
    'litellm': ('https://docs.litellm.ai/', None),
    'textual': ('https://textual.textualize.io/', None),
}

# -- Todo configuration -----------------------------------------------------

todo_include_todos = True
