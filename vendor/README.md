# Bundled image viewer

`xopat/` contains XOpat 2.3.1 from [RationAI/xopat](https://github.com/RationAI/xopat), used for SPaRE's deep-zoom image viewer. Its runtime libraries, modules, plugins, build sources, documentation, and license notices are retained.

SPaRE omits the upstream Cypress tests and screenshot baselines, example Docker deployments, GitHub workflows, and their unused configuration. The corresponding test dependencies and package scripts are removed. `comment-json` is classified as a runtime dependency so the production image can discard build tools.

Build the viewer with `scripts/setup_xopat.sh` from the repository root. SPaRE's integration tests live in `tests/e2e/`; use the upstream repository for XOpat's own development and test suite. See [third-party notices](../THIRD_PARTY_NOTICES.md) for licensing and the pinned OpenSeadragon revision.
