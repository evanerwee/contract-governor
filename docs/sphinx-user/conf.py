"""Sphinx configuration for Contract Governor User Documentation."""

project = "Contract Governor — User Guide"
copyright = "2026, Evan Erwee"
author = "Evan Erwee"
release = "1.3.144"

extensions = [
    "myst_parser",  # Parse .md files
    "sphinx.ext.intersphinx",  # Cross-reference developer docs
]

# MyST (Markdown) settings
source_suffix = {".rst": "restructuredtext", ".md": "markdown"}

# Theme
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "navigation_depth": 3,
    "collapse_navigation": False,
}
html_static_path = ["_static"]

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
""",
}

# Intersphinx: link to Python docs
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

suppress_warnings = ["ref.any"]
