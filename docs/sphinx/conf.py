"""Sphinx configuration for Contract Governor documentation."""

import os
import sys

# Add the contract-governor root to sys.path so autodoc can import modules
_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_here, "../..")))

from contract_governor import __version__  # noqa: E402

project = "Contract Governor"
copyright = "2024-2026, Evan Erwee"
author = "Evan Erwee"
release = __version__

extensions = [
    "sphinx.ext.autodoc",  # Auto-generate from docstrings
    "sphinx.ext.napoleon",  # Google/NumPy-style docstring support
    "sphinx.ext.viewcode",  # Add [source] links to generated docs
    "sphinx.ext.intersphinx",  # Cross-reference external docs (boto3, pydantic)
    "myst_parser",  # Parse .md files alongside .rst
]

# Napoleon settings (Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
    "member-order": "bysource",
}
autodoc_mock_imports = [
    "fastapi",
    "uvicorn",
    "httpx",
    "pydantic",
    "boto3",
    "botocore",
    "semver",
    "openapi_core",
    "django",
    "flask",
    "werkzeug",
    "starlette",
]

# LaTeX settings
latex_engine = "xelatex"
latex_elements = {
    "fontpkg": r"\usepackage{fontspec}",
    "preamble": r"""
\usepackage{newunicodechar}
\newunicodechar{✅}{[YES]}
\newunicodechar{❌}{[NO]}
\newunicodechar{⚠}{{!}}
\newunicodechar{→}{->}
\newunicodechar{📍}{}
\newunicodechar{💬}{}
\newunicodechar{🔗}{}
\newunicodechar{⏳}{}
\newunicodechar{🎯}{}
\newunicodechar{⭐}{*}
""",
}

# MyST (Markdown) settings
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

# Theme
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
}
html_static_path = ["_static"]

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Suppress warnings for missing references to mocked modules
suppress_warnings = ["autodoc.import"]
