# Third-party notices

The project license applies to original SPaRE code. Dependencies and vendored assets retain their own licenses and copyright notices.

The OSCARS logo and European Union funding emblem in `docs/assets/` are official third-party marks used to acknowledge project funding. Their respective branding and emblem-use rules apply; they are not licensed under this project's GPLv3 license. Sources and communication guidance are linked in [the asset notes](docs/assets/README.md).

- **XOpat 2.3.1**, RationAI Research Group: bundled in `vendor/xopat`, under its [MIT license](vendor/xopat/LICENSE). Source: <https://github.com/RationAI/xopat>. The local package manifest classifies `comment-json` as a runtime dependency so build tools can be removed from the deployment image. Upstream tests, screenshot baselines, example deployments, workflows, and their unused configuration/dependencies are omitted; see [the vendor notes](vendor/README.md). Other bundled notices remain in the vendor tree.
- **OpenSeadragon, RationAI fork**: downloaded by `scripts/setup_xopat.sh` at commit `0866e108e9a383e173180ad639232c808f82f7d2`. Source: <https://github.com/RationAI/openseadragon>. Its license and notices are retained in the built viewer directory.
- **OpenSlide**: the Python bindings and native library are installed from the pinned Python requirements. The native library uses LGPL-2.1; the bindings and distribution retain their upstream notices. Source and licenses: <https://openslide.org/> and <https://github.com/openslide/openslide-python>.
- **Inter**, The Inter Project Authors: the logo wordmark uses outlined Inter Display SemiBold glyphs. The typeface is available under the [SIL Open Font License 1.1](https://github.com/rsms/inter/blob/master/LICENSE.txt). Source: <https://github.com/rsms/inter>.
- Frontend and Python dependencies are listed in the package manifests and requirements files. Their licenses are distributed with the installed packages.
