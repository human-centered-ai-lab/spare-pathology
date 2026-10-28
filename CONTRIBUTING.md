# Contributing

Use Python 3.11 or 3.12 and Node.js 24 LTS. Keep changes focused and include regression coverage for behavior changes. Do not commit participant data, credentials, uploaded images, notebooks, or generated build files.

## Setup and checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
ruff check app tests
python -m pytest
```

Backend tests use isolated SQLite databases and temporary file storage. Browser tests create a separate runtime under `instance/e2e/` and do not use the development database:

```bash
./scripts/setup_xopat.sh
npm --prefix tests/e2e ci
(cd tests/e2e && npx playwright install --with-deps chromium)
(cd tests/e2e && npm test)
```

Build the frontend before browser tests. Install `requirements-notebook.txt` only when working on notebook integration. For XOpat, run `./scripts/setup_xopat.sh`; it builds the vendored viewer and the pinned OpenSeadragon fork. Third-party changes should be documented in `THIRD_PARTY_NOTICES.md`.

Dependency checks:

```bash
pip-audit
npm --prefix frontend audit
npm --prefix tests/e2e audit
npm --prefix vendor/xopat audit --omit=dev
```

## Release process

1. Update `app/version.py`, frontend and browser-test package versions and lockfiles, Docker image metadata/tag, and `CHANGELOG.md` together.
2. Run backend tests, lint, the production frontend build, browser tests, and dependency audits.
3. On a clean Docker host, run the quick start, check `/healthz`, upload a small dataset, complete a participant evaluation, and export CSV. Test a restart with existing storage.
4. Review the upgrade notes and ensure the repository contains no local data or secrets.
5. Commit the reviewed changes, tag the release `v1.0.0`, and create the GitHub release using the changelog entry. Publishing is a maintainer action; CI builds and tests without pushing images or creating releases.
