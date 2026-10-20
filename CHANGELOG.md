# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). While the version is 0.x, anything may change
between releases.

## [Unreleased]

## [0.2.5] - 2026-10-21

### Fixed

- "Recognize a part of the photo" is offered for videos too: the part is cut from the frame of
  the preview, the one GeoCLIP looks at for the whole video. Before, the button was missing.

## [0.2.4] - 2026-10-21

GeoCLIP can look at a part of the photo only; the gallery returns to the photo you came from,
and its timeline is labeled as in Immich.

### Added

- **Recognize a part of the photo**: next to GeoCLIP's Run again, a window shows the photo in
  full size (zoom with the wheel, move it with the right or middle button or with Space held)
  to draw a frame around the part to look at, e.g. a building behind a crowd. The result is
  shown as its own block, "GeoCLIP — part of the photo", next to the one for the whole photo,
  with dashed markers on the map; hovering it outlines the part on the photo. The key R opens
  the window. Runs on a part do not count in the Library page, the filters or the automatic
  runs. Any worker can do them: the app cuts the part from the full-size photo itself.
- Time neighbors: "Only this camera" keeps the photos of the photo's own camera only, on the
  next photos as well.

### Changed

- Back from a photo, the gallery opens where that photo is (the last one viewed, after
  stepping through others), like Immich's `?at=`; the browser's back button returns there too.
- The timeline scrubber labels a year at January, as Immich does, instead of at December, and
  shows a dot per month.
- Keyboard shortcuts work whatever the keyboard layout: on a Cyrillic one, for instance, the
  key of R is R.

## [0.2.3] - 2026-10-20

The reason why GeoCLIP failed on a photo is kept and shown, with a way to find those photos
and run them again; workers on other computers, with Docker or an NVIDIA GPU, are documented.

### Added

- Installation guide: workers on other computers in the home network, with Docker (Linux,
  Windows) or on an NVIDIA GPU (Windows, Linux), how to check, stop and update them
  ([docs/install.md](docs/install.md#workers-on-other-computers)).
- The Library page lists photos a module failed on by reason, with links to show them and to
  run them again.
- Gallery filter "Not processed": photos whose latest run of GeoCLIP failed, for any or one
  reason; the photo card then steps through them.
- "Open in Immich" link in the photo card. `STEWARD_IMMICH_PUBLIC_URL` sets the address used
  in the browser when `STEWARD_IMMICH_URL` is not reachable from it (e.g. a container name).

### Fixed

- When the app could not get a photo from Immich (a broken file, for instance), its GeoCLIP run
  waited for three time-outs of 5 minutes and failed as "lease_expired", without the reason.
  Now it fails at once with the reason; when Immich does not answer at all, the photo waits in
  the queue without using up its attempts.
- A worker reports a request the app refused instead of dropping the job silently.
- Two workers with the same name on different computers shared one entry, and stopping one
  showed the other as gone. Now the second one is refused while the first runs, with a clear
  message in its log.
- On Windows, a worker stopped with Ctrl+C now writes "stopped" to its log, as on Linux.

## [0.2.2] - 2026-10-18

### Added

- Ready-made Docker images on GitHub Container Registry, published for every release:
  `ghcr.io/ivamic/immich-steward-core` (`amd64`, `arm64`) and
  `ghcr.io/ivamic/immich-steward-worker` (`amd64`). `docker compose up -d` downloads them, so
  the images no longer have to be built on the server; `--build` still builds them from source.
- `STEWARD_VERSION` in `.env` to stay on a particular release.
- `THIRD_PARTY_NOTICES.md`: licenses of the software inside the images (also in `/app` of the
  images).

### Changed

- Updating is now `git pull`, `docker compose pull` and `docker compose up -d`
  ([docs/install.md](docs/install.md#updating)).

## [0.2.1] - 2026-10-18

### Changed

- The app has its own icon (a map pin with a picture) instead of the default Svelte logo.
- README: screenshots, how to give feedback and contribute, how to support the project.

### Added

- Security policy (`SECURITY.md`) with private vulnerability reporting.

## [0.2.0] - 2026-10-18

GeoCLIP suggests locations by the look of a photo, in a worker on the server or on another
computer; a photo card where the map always stays in view.

### Added

- Workers: separate processes that run heavy location modules for the core, on the same server
  or on another computer (they only connect to the core, which gives them the photos). Shared
  token `STEWARD_WORKER_TOKEN`, job queue with priorities, retries and leases.
- **GeoCLIP** location module: suggests up to five areas by the look of a photo. Runs
  automatically on photos without a location while a worker is connected
  (`STEWARD_AUTO_MODULES`; accounts take turns, newest photos first), or on request with **Run**
  in the photo card.
- Optional `worker` service in Docker Compose (CPU), with a model cache, a memory limit and an
  option to wait while the machine is busy (`STEWARD_WORKER_MAX_LOAD`).
- GeoCLIP suggestions are shown by confidence: below 25 % they are hidden as noise, 25–50 % are
  folded as weak ("probably only the region is right"), from 75 % they are marked as confident
  (`STEWARD_GEOCLIP_*`). The thresholds come from a check on photos with known locations.
- Confidence of every suggestion as a percentage next to its bar.
- Gallery filter "Confident GeoCLIP guess": photos without a location that GeoCLIP places
  confidently, ready to be checked and saved one after another.
- Gallery markers: a pin on a white disc for photos with a location (instead of a hard to see
  green dot), an orange crosshair for confident GeoCLIP guesses.
- Workers and the progress of module runs on the Library page.

### Changed

- Photo card in three columns that fill the window: the map always stays in view, the panel to
  pick the location and the suggestions scroll on their own, the photo and its details are on
  the right. On medium screens the two side columns become tabs; on small screens everything is
  stacked. Compact suggestion rows; hovering a row highlights its marker and the other way round.
  A click on a suggestion row shows it on the map without picking it; hovering a neighbor's
  thumbnail shows it enlarged.
- The main actions (Save, Skip, Not applicable) are at the top of the panel and bigger; Save turns
  green as soon as a point is picked, so that it is not forgotten.

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

[Unreleased]: https://github.com/Ivamic/immich-steward/compare/v0.2.5...HEAD
[0.2.5]: https://github.com/Ivamic/immich-steward/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/Ivamic/immich-steward/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Ivamic/immich-steward/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Ivamic/immich-steward/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Ivamic/immich-steward/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Ivamic/immich-steward/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ivamic/immich-steward/releases/tag/v0.1.0
