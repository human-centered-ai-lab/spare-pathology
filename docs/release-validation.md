# Version 1.0.0 validation

Validated on 2026-10-28 using Python 3.11, Node.js 24, Chromium, and local persistent SQLite storage.

| Check | Result |
| --- | --- |
| Backend tests | 584 passed |
| Browser end-to-end tests | 45 passed |
| Python lint | Passed |
| Frontend lint and TypeScript/production build | Passed |
| Python dependency audit, including optional notebooks | No known vulnerabilities reported |
| Frontend and browser-test dependency audits | No known vulnerabilities reported |
| XOpat runtime dependency audit | No known vulnerabilities reported |
| Compose configuration and shell syntax | Passed |
| Nginx configuration and production startup scripts | Passed |

Browser coverage includes login/logout, password changes, user and study management, dataset upload and selection, question configuration, evaluation charts, participant scoring and navigation, resume/scroll behavior, submission, read-only review, CSV export, test-account reset, failed-save recovery after reload, isolation of pending saves between participants, a narrow viewport, native image rendering after delayed data, navigation and resizing, and XOpat rendering and keyboard navigation.

The README capture session also verified native viewing of a real 4096 × 4096 GTEx region, fit-to-window and actual-size zoom, persistence of all six selected ratings, and a filtered evaluation dashboard. Backend regressions verify strict JSON serialization when total scores or individual questions have constant ratings. Screenshot dimensions, image decoding, and local documentation links were checked.

The SPaRE rename was checked with existing and fresh database paths, explicit database overrides, new and legacy Compose UID/GID settings, and idempotent configuration generation. Browser regressions cover migration of the theme and pending ratings from SynEval, conflicting old/new queues (including different retry versions), and isolation between accounts. All five README screenshots were recaptured, and the README was checked on desktop and mobile in light and dark themes.

A separate production-stack check ran the startup scripts with two application workers, two tile workers, and Nginx. It verified a fresh private administrator, concurrent chunk uploads, activation, participant scoring, authenticated tiles across services, final submission, CSV export, and refusal of post-submission edits. Concurrent image requests returned the same rating. After a shutdown and restart, sessions, study state, ratings, and exports remained intact. Optional notebooks were generated in configured storage and opened through the proxy; unauthenticated notebook API requests were rejected.

The Docker daemon was unavailable in the validation environment, so the container image itself was not built or started here. The checked-in CI workflow builds the image and runs Compose startup and restart checks on GitHub's Linux runners. Python 3.12 is also covered by that workflow; the local test run used 3.11.

The backend suite emits one expected SQLAlchemy warning while testing a duplicate composite primary key. The frontend build reports a large administrator-study bundle; it still builds successfully. Dependency audits cover installed Python packages, the frontend/test npm trees, and XOpat's production npm dependencies, not a formal security audit of every vendored browser asset or upstream build tool.

The upstream XOpat and OpenSeadragon development/build dependency trees still report npm advisories. These packages are used while building trusted sources and are removed from the production image; XOpat's production dependency audit reports zero vulnerabilities. The repository does not claim a clean audit for all upstream development tooling.

## Publication audit

The publication tree contains approximately 31.5 MiB: 24.3 MiB of bundled viewer sources/libraries and 5.4 MiB of README screenshots, with the application, tests, and documentation making up the remainder. Unused upstream viewer tests, screenshot baselines, example deployments, workflows, and Cypress dependencies were removed. No individual file exceeds 10 MiB.

The trimmed viewer was rebuilt with a fresh dependency install and a fresh checkout of the pinned OpenSeadragon revision. All 45 browser tests passed against that build. After removing development dependencies as the Dockerfile does, the viewer's tile-rendering and keyboard-navigation test passed again.

Local databases, uploaded datasets, generated notebooks, virtual environments, dependency installs, build outputs, browser results, and debug traces are excluded from Git. No runtime database, whole-slide image, or credential file was found in the publication tree. A credential-pattern scan of the current files and 1,118 historical text blobs found no matches; this is a targeted check, not a guarantee that every possible secret format is detectable.

## GitHub publication

The public repository is `human-centered-ai-lab/spare-pathology`. Its release documentation and container source metadata use that address. The publication starts with a single root commit named `initial commit`, authored by Robert Harb, rather than importing the development history.

```bash
git clone https://github.com/human-centered-ai-lab/spare-pathology.git
```

GitHub Actions runs backend, browser, and Docker checks on pushes and pull requests. Current run results are available in the repository's Actions tab; the validation results above describe checks completed during local release preparation.
