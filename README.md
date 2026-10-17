# immich-steward

> **Status: under active development.** An early version: manual review of photos without
> location and suggestions from photos taken close in time already work; the other modules are
> still to come. Expect bugs and changes between versions, and keep a backup of your Immich
> library before writing locations to it.

A self-hosted companion app for [Immich](https://immich.app) that helps you restore
missing information in your photo library — and lets *you* decide what is written back.

The first tool finds out **where photos without GPS data were taken**.

Typical use case: a family photo archive with scanned prints, old digital cameras
without GPS, or messenger downloads that lost their metadata.

## Idea

The app combines several independent **location detection modules**. Each module
proposes one or more candidate locations, and all candidates are shown together on a
map, color-coded by module and numbered by rank. You review them, pick one, or place a
point manually.

Modules:

- **Time neighbors** *(available)* — photos taken shortly before/after that already have a
  location; the route between them is drawn on the map.

Planned:

- **GeoCLIP** — worldwide image geolocation by a neural network, running locally.
- **Similar photos in your library** — visual similarity to your own geotagged photos.
- **Landmarks** — your own library of recognizable places: mark a landmark once on a
  geotagged photo, and the app looks for it in photos without location.
- **LLM reasoning** (Img2Loc-style) — a vision-language model reasons over the photo
  plus the evidence collected by the other modules.
- **External services** — optional cloud recognizers, one module per service.

New modules can be added later as plugins.

## Principles

- **Nothing is written to Immich automatically.** Coordinates are sent only after you
  confirm a location. Every change can be undone.
- **Local first.** Default modules run on your own hardware. Modules that send images
  to third-party services are never run automatically — only on an explicit request,
  with a clear warning about what is sent and where.
- **Region-based search.** If the whole picture is misleading (for example, a crowd in
  front of a monument), select a part of the image and run detection on that region only.
- **"Not applicable" flag.** Mark photos where a location makes no sense, so they never
  show up in your to-do list again.

## Installation

immich-steward runs with Docker Compose next to your Immich server (Immich v3.x):

```sh
git clone https://github.com/Ivamic/immich-steward.git
cd immich-steward
cp .env.example .env      # set STEWARD_IMMICH_URL, STEWARD_SECRET_KEY and DB_PASSWORD
docker compose up -d --build
```

Then open `http://<your-server>:8780` and sign in with your Immich account.
See [docs/install.md](docs/install.md) for the details: configuration, Immich on the same
machine, updating, backup and troubleshooting.

## Architecture

- Backend: Python (FastAPI), PostgreSQL with pgvector.
- Runs with Docker Compose next to your Immich server.
- ML modules will run in workers: on the server CPU, or on a separate machine with a GPU.
- Web UI: timeline gallery with filters, photo view with a map, keyboard-driven review.
- English UI with translations (Russian from the start).

## Development

Repository layout:

| Path | Contents |
|---|---|
| `core/` | Core service: Python package `steward` (FastAPI), Alembic migrations, tests |
| `frontend/` | Web UI: SvelteKit single-page app; translations in `frontend/messages/` |
| `docker/` | Dockerfile of the core image (it also contains the built web UI) |
| `compose.yaml` | Core service + PostgreSQL with pgvector |
| `docs/` | User documentation (installation) |

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 24 with pnpm, Docker.
Run all commands from the repository root unless stated otherwise.

```sh
cp .env.example .env            # then set DB_PASSWORD and STEWARD_DATABASE_URL

# Database only, exposed on localhost
docker compose -f compose.yaml -f compose.dev.yaml up -d db

# Core service on http://127.0.0.1:8080
uv sync
uv run alembic -c core/alembic.ini upgrade head
uv run python -m steward --reload

# Web UI dev server on http://localhost:5173 (proxies /api to the core)
cd frontend && pnpm install && pnpm dev
```

Checks (the same as in CI):

```sh
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
cd frontend && pnpm check && pnpm lint && pnpm test && pnpm check:licenses
```

Database integration tests run when `STEWARD_TEST_DATABASE_URL` is set.

Full stack in Docker (UI on http://localhost:8780 by default):

```sh
docker compose up -d --build
```

### Translations

UI strings live in `frontend/messages/<locale>.json`; English (`en.json`) is the source.
A new string must be added to every locale file at once — a test checks that all locales
have the same keys and placeholders.

## License

Copyright (C) 2026 Ivamic.

[GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`).

## AI assistance

This project is developed with the help of AI tools (Claude by Anthropic).
All code is reviewed and maintained by a human author.

## Disclaimer

This is an independent community project. It is not affiliated with or endorsed by the
Immich project or FUTO.
