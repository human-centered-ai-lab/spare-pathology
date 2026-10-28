"""Generate per-study Jupyter notebooks with template analysis code."""

import os

from flask import current_app


def _ensure_notebooks_dir():
    os.makedirs(current_app.config['NOTEBOOKS_DIR'], exist_ok=True)


def notebook_path(study_id: int) -> str:
    return os.path.join(current_app.config['NOTEBOOKS_DIR'], f'study_{study_id}.ipynb')


def csv_path(study_id: int) -> str:
    return os.path.join(current_app.config['NOTEBOOKS_DIR'], f'study_{study_id}.csv')


def get_or_create_notebook(study_id: int) -> str:
    """Return the path to the study notebook, creating it if needed."""
    _ensure_notebooks_dir()
    path = notebook_path(study_id)
    if not os.path.isfile(path):
        _create_template_notebook(study_id, path)
    return path


def export_csv_for_notebook(study_id: int) -> str:
    """Write the CSV export next to the notebook and return the path."""
    from app.services.export_service import generate_csv

    _ensure_notebooks_dir()
    path = csv_path(study_id)
    csv_string, _, _ = generate_csv(study_id)
    with open(path, 'w') as f:
        f.write(csv_string)
    return path


def _create_template_notebook(study_id: int, path: str):
    import nbformat

    nb = nbformat.v4.new_notebook()
    nb.metadata['kernelspec'] = {
        'display_name': 'Python 3',
        'language': 'python',
        'name': 'python3',
    }

    cells = [
        nbformat.v4.new_markdown_cell(
            f'# Study {study_id} - Analysis Notebook\n\n'
            'This notebook is pre-configured to load evaluation data for this study.\n'
            'Edit freely — your changes are saved automatically by Jupyter.'
        ),
        nbformat.v4.new_code_cell(
            'import pandas as pd\n'
            'import numpy as np\n'
            'import pygwalker as pyg'
        ),
        nbformat.v4.new_markdown_cell(
            '## Load Data\n\n'
            'The CSV is exported from the app and saved alongside this notebook.\n'
            'To use locally, just place the CSV in the same folder as this notebook.'
        ),
        nbformat.v4.new_code_cell(
            f'STUDY_ID = {study_id}\n'
            f'CSV_FILE = "study_{study_id}.csv"\n'
            '\n'
            'df = pd.read_csv(CSV_FILE)\n'
            'print(f"Loaded {len(df)} rows, {df.shape[1]} columns")\n'
            'df.head()'
        ),
        nbformat.v4.new_markdown_cell(
            '## Interactive Explorer\n\n'
            'Drag and drop columns to build charts. '
            'Your chart configurations are saved in the notebook.'
        ),
        nbformat.v4.new_code_cell(
            'walker = pyg.walk(df)'
        ),
        nbformat.v4.new_markdown_cell(
            '## Custom Analysis\n\n'
            'Add your own analysis cells below. The `df` DataFrame contains all '
            'rating data for this study.'
        ),
        nbformat.v4.new_code_cell(''),
    ]

    nb.cells = cells

    with open(path, 'w') as f:
        nbformat.write(nb, f)
