# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). While the version is 0.x, anything may change
between releases.

## [Unreleased]

### Added

- Workers: separate processes that run heavy location modules for the core, on the same server
  or on another computer (they only connect to the core, which gives them the photos). Shared
  token `STEWARD_WORKER_TOKEN`, job queue with priorities, retries and leases.
- **GeoCLIP** location module: suggests up to five areas by the look of a photo. Runs
  automatically on photos without a location while a worker is connected
  (`STEWARD_AUTO_MODULES`), or on request with **Run** in the photo card.
- Optional `worker` service in Docker Compose (CPU), with a model cache, a memory limit and an
  option to wait while the machine is busy (`STEWARD_WORKER_MAX_LOAD`).
- GeoCLIP suggestions are shown by confidence: below 25 % they are hidden as noise, 25–50 % are
  folded as weak ("probably only the region is right"), from 75 % they are marked as confident
  (`STEWARD_GEOCLIP_*`). The thresholds come from a check on photos with known locations.
- Confidence of every suggestion as a percentage next to its bar.
- Workers and the progress of module runs on the Library page.

## [0.1.0] - 2026-10-17

First usable version: review photos without location by hand, with suggestions from photos
taken close in time.

### Added

- Sign-in with an Immich email and password (the app creates and keeps its own API key) or
  with an API key. Each user sees only their own library. Sessions last 90 days and are
  extended on use.
- Sync of assets and albums from Immich v3.x: automatic every 15 minutes, full sync daily or on
  request.
- Gallery with a month timeline and scrubber, filters by group (without location, with
  location, skipped, not applicable), type, camera, album, dates and archive.
- Photo card: large map, address search (Photon), coordinate input (decimal or degrees),
  photo viewer with full-size zoom, keyboard shortcuts.
- Writing locations to Immich: a five-second window to cancel, history of changes with undo,
  the tag `steward/estimated` on every written location.
- "Skip" and "not applicable" marks that keep photos out of the to-do list.
- Location module contract and the first module, **time neighbors**: located photos within
  ±3 hours, interpolation between the photos before and after, the route drawn on the map with a
  before/after gradient, previews of the neighbor photos, cameras that can be excluded.
- Docker Compose setup (app + PostgreSQL with pgvector) and an installation guide
  ([docs/install.md](docs/install.md)).
- English and Russian user interface.

[Unreleased]: https://github.com/Ivamic/immich-steward/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Ivamic/immich-steward/releases/tag/v0.1.0
