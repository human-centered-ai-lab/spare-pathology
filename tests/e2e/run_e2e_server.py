#!/usr/bin/env python3
"""Standalone E2E test server.

Creates a fully isolated E2E runtime under instance/e2e:
- wipes instance/e2e/e2e_test.db
- wipes instance/e2e/uploads (datasets + protocol uploads)
- starts app with E2ETestConfig against that isolated storage

This guarantees Playwright runs never touch development DB/files.
"""

import os
import shutil
import sys
import logging

# Ensure the project root is on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, project_root)

from app.config import E2ETestConfig  # noqa: E402

# Fully isolate and reset E2E runtime
e2e_base_dir = os.path.join(project_root, 'instance', 'e2e')
uploads_dir = os.path.join(e2e_base_dir, 'uploads')
datasets_dir = os.path.join(uploads_dir, 'datasets')
db_path = os.path.join(e2e_base_dir, 'e2e_test.db')

os.makedirs(e2e_base_dir, exist_ok=True)

if os.path.exists(db_path):
    os.remove(db_path)
    print(f'Deleted existing E2E database: {db_path}')

if os.path.isdir(uploads_dir):
    shutil.rmtree(uploads_dir)
    print(f'Deleted existing E2E uploads directory: {uploads_dir}')

os.makedirs(datasets_dir, exist_ok=True)

from app import create_app  # noqa: E402

app = create_app(E2ETestConfig)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

if __name__ == '__main__':
    print('Starting E2E test server on http://localhost:5099')
    print(f'Database: {db_path}')
    print(f'Uploads: {uploads_dir}')
    print(f'Datasets: {datasets_dir}')
    app.run(host='127.0.0.1', port=5099, debug=False)
