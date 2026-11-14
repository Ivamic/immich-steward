# Third-party notices

Steward for Immich (immich-steward) is licensed under the [GNU AGPL v3.0 or later](LICENSE). Its Docker images
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

Fonts and icons of the web UI (copied into the source, `frontend/src/lib/assets/fonts/` and
`frontend/src/lib/ui/icons.ts`):

- [IBM Plex Sans and IBM Plex Mono](https://github.com/IBM/plex) — © 2017 IBM Corp. with Reserved
  Font Name "Plex", SIL Open Font License 1.1 (OFL-1.1). WOFF2 subsets as published by
  [Fontsource](https://fontsource.org); the license text is next to the font files (`OFL.txt`).
- [Lucide](https://lucide.dev) icons (lucide-static 0.460.0) — ISC License; © Lucide
  Contributors 2022, portions © Cole Bemis 2013–2022 (Feather, MIT).

## Worker image (`immich-steward-worker`)

Python packages (in `/app/venv`), the main ones:

| Packages | License |
|---|---|
| [GeoCLIP](https://github.com/VicenteVivan/geo-clip) with its model weights and GPS gallery | MIT |
| [MegaLoc](https://github.com/gmberton/MegaLoc) model code (copied into the worker, see below) | MIT |
| [LightGlue](https://github.com/cvg/LightGlue) matcher code (copied into the worker, see below) | Apache-2.0 |
| [ALIKED](https://github.com/Shiaoming/ALIKED) keypoint extractor code (copied into the worker, see below) | BSD-3-Clause |
| PyTorch and torchvision (CPU build) | BSD-3-Clause |
| Transformers, Hugging Face Hub, safetensors, tokenizers | Apache-2.0 |
| NumPy, pandas, NetworkX, Jinja2 | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| Other dependencies (geopy, SymPy, tqdm, regex…) | MIT, BSD, Apache-2.0, MPL-2.0, PSF |

The image contains no NVIDIA libraries. The CLIP ViT-L/14 model (MIT) and the MegaLoc weights
(MIT, [gberton/MegaLoc](https://huggingface.co/gberton/MegaLoc)) are not part of the image: the
worker downloads them from Hugging Face on first use. The same goes for the weights of ALIKED
(BSD-3-Clause, [Shiaoming/ALIKED](https://github.com/Shiaoming/ALIKED)) and LightGlue (Apache-2.0,
[cvg/LightGlue](https://github.com/cvg/LightGlue)), downloaded from GitHub.

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

`worker/src/steward_worker/modules/lightglue_model.py` is the LightGlue matcher from
[cvg/LightGlue](https://github.com/cvg/LightGlue) (file `lightglue/lightglue.py`, commit `5a650c4`),
unchanged, under the Apache License 2.0:

```text
Copyright 2023 ETH Zurich

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

`worker/src/steward_worker/modules/aliked_model.py` is the ALIKED keypoint extractor from the same
repository (file `lightglue/aliked.py`, there adapted from
[Shiaoming/ALIKED](https://github.com/Shiaoming/ALIKED)), under the BSD 3-Clause License,
Copyright (c) 2022, Zhao Xiaoming; the full text is at the top of the file. Only its imports are
changed: three helpers come from `lightglue_utils.py` of the worker, written after
`lightglue/utils.py` (Apache-2.0), instead of that file and kornia.

## Services used at run time

Not included in the images, but used by default:
[OpenFreeMap](https://openfreemap.org) map tiles with data
© [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), and the
[Photon](https://photon.komoot.io) geocoder.
