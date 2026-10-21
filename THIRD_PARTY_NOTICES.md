# Third-party notices

immich-steward is licensed under the [GNU AGPL v3.0 or later](LICENSE). Its Docker images
also contain third-party software under its own licenses, all compatible with the AGPL. This
file summarizes them; the license texts are included in the packages themselves.

The source code of every published image is the repository at the tag of its version (see the
`org.opencontainers.image.source` and `org.opencontainers.image.revision` labels of the image).

## Base image (both images)

- [`python:3.12-slim`](https://hub.docker.com/_/python) — Python (PSF License) on Debian. The
  Debian packages come under their own licenses, listed in `/usr/share/doc/*/copyright`
  inside the image.

## Core image (`immich-steward-core`)

Python packages (in `/app/venv`):

| Packages | License |
|---|---|
| FastAPI, Pydantic, pydantic-core, pydantic-settings, SQLAlchemy, Alembic, Mako, anyio, annotated-types, annotated-doc, typing-inspection, h11, truststore, pgvector | MIT |
| Starlette, Uvicorn, httpx2, httpcore2, click, idna, MarkupSafe, pycparser, python-dotenv | BSD-3-Clause |
| asyncpg, opentelemetry-api | Apache-2.0 |
| cryptography | Apache-2.0 OR BSD-3-Clause |
| cffi | MIT-0 |
| Pillow (cutting a part of a photo) | MIT-CMU (HPND) |
| greenlet | MIT AND PSF-2.0 |
| typing_extensions | PSF-2.0 |

Web UI (bundled JavaScript in `/app/static`): Svelte and SvelteKit (MIT),
[MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) (BSD-3-Clause), Paraglide JS (MIT)
and their dependencies (MIT, ISC, BSD, Apache-2.0, MPL-2.0, BlueOak-1.0.0).

## Worker image (`immich-steward-worker`)

Python packages (in `/app/venv`), the main ones:

| Packages | License |
|---|---|
| [GeoCLIP](https://github.com/VicenteVivan/geo-clip) with its model weights and GPS gallery | MIT |
| [MegaLoc](https://github.com/gmberton/MegaLoc) model code (copied into the worker, see below) | MIT |
| PyTorch and torchvision (CPU build) | BSD-3-Clause |
| Transformers, Hugging Face Hub, safetensors, tokenizers | Apache-2.0 |
| NumPy, pandas, NetworkX, Jinja2 | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| Other dependencies (geopy, SymPy, tqdm, regex…) | MIT, BSD, Apache-2.0, MPL-2.0, PSF |

The image contains no NVIDIA libraries. The CLIP ViT-L/14 model (MIT) and the MegaLoc weights
(MIT, [gberton/MegaLoc](https://huggingface.co/gberton/MegaLoc)) are not part of the image: the
worker downloads them from Hugging Face on first use.

## Full list

Every Python package in an image with its license:

```sh
docker run --rm --entrypoint sh ghcr.io/ivamic/immich-steward-worker -c \
  "pip install --quiet --target /tmp/pl pip-licenses && \
   PYTHONPATH=/tmp/pl python -m piplicenses --python /app/venv/bin/python --with-urls"
```

(use `immich-steward-core` for the core image). The CI checks that all of them have licenses
compatible with the AGPL.

## Code copied into the source

`worker/src/steward_worker/modules/megaloc_model.py` is the MegaLoc model from
[gmberton/MegaLoc](https://github.com/gmberton/MegaLoc) (commit `5fe0dd6`), unchanged, under the
MIT license; parts of it are adapted by its authors from
[OpenGlue](https://github.com/ucuapps/OpenGlue) (MIT):

```text
MIT License

Copyright (c) 2024 Gabriele Berton, Carlo Masone

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Services used at run time

Not included in the images, but used by default:
[OpenFreeMap](https://openfreemap.org) map tiles with data
© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), and the
[Photon](https://photon.komoot.io) geocoder.
