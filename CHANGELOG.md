# Changelog

## 1.0.0

Initial open-source release of SPaRE under the GNU General Public License v3.0 (`GPL-3.0-only`).

- Adopted the SPaRE name (Synthetic Pathology Reader Evaluation) and `spare-pathology` repository/image name, with compatibility for existing databases, runtime user settings, browser themes, and pending ratings.
- Removed unused upstream viewer tests, screenshot baselines, example deployments, workflows, and Cypress dependencies from the bundled source.

- Study and participant management, configurable rating schemas, randomized image evaluation, and durable autosave.
- Dataset uploads, metadata filtering, native image viewing, and XOpat deep zoom.
- Reliable native-viewer initialization when image data arrives after the page loads.
- JSON-safe agreement statistics for constant or degenerate ratings.
- Progress reporting, agreement and group statistics, CSV exports, and optional notebooks.
- Explicit administrator bootstrap, private session secrets, and demo data disabled by default.
- Persistent upload state shared across workers, incomplete-upload checks, and atomic dataset publication.
- Input and path validation, participant-specific browser save queues, and closed-study write protection.
- Reproducible viewer revision, updated dependencies, deployment health checks, and automated release checks.
