# Configuration file for the Sphinx documentation builder.

import os
import sys
sys.path.insert(0, os.path.abspath('..'))  # add project root to path

project = 'pylineament'
copyright = '2025, Epo Prasetya Kusumah'
author = 'Epo Prasetya Kusumah'
release = '1.0.0'

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autodoc',       # auto-generate docs from docstrings
    'sphinx.ext.napoleon',      # support NumPy/Google docstring style
    'sphinx.ext.viewcode',      # add "view source" links
    'sphinx.ext.autosummary',   # summary tables
]

autosummary_generate = True
autodoc_member_order = 'bysource'
add_module_names = False

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'  # readthedocs style
html_static_path = ['_static']
