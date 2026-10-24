# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). While the version is 0.x, anything may change
between releases.

## [Unreleased]

### Added

- **Satellite imagery on the map**: Sentinel-2 cloudless by EOX (no key, a layer per year
  2016–2025), Esri World Imagery and MapTiler Satellite (with your own key). All off by default;
  set up in **Settings → Map sources** with a short summary of each provider's terms, the key
  (stored encrypted, shown masked, checked with the provider on saving), the tiles the app loaded
  with a reset (by hand or monthly), and for MapTiler optionally the exact usage with a service
  token. Over the map: choose the plain map or a source, **Auto by zoom** (a far and a near source)
  and labels over the imagery. A source whose key is refused or whose limit is used up is skipped.
  The browser loads the tiles straight from the provider; see
  [Privacy](docs/privacy.md) and [Configuration](docs/configuration.md#satellite-imagery-in-settings).

### Changed

- The map attribution is 12 px (Esri's minimum) and names the satellite source shown.

## [0.4.1] - 2026-10-25

### Security

- **Pillow 13.0.0** (was 12.3.0) in the core and worker images: it fixes many vulnerabilities in
  the image decoders (among them CVE-2026-112393, CVE-2026-112398, CVE-2026-112403,
  CVE-2026-112900 and CVE-2026-96639), reachable because the app decodes photos it gets from
  Immich. GeoCLIP 1.2.3 asks for Pillow below 13 only as a precaution; the app overrides that.
  Thanks to the user who reported it.
- The core and the worker decode only the formats Immich can send them: JPEG, PNG, WebP, AVIF,
  GIF and BMP in the core (Immich sends other originals, such as HEIC, RAW or TIFF, as a JPEG or
  WebP copy), JPEG, WebP and PNG in the worker (it gets only previews and parts cut by the
  core). Other formats that Pillow could open (TIFF, PDF, EPS, FlashPix and others) are refused
  as unreadable images.

## [0.4.0] - 2026-10-24

A new look: the app is now called **Steward for Immich**, has a new logo, light and dark themes,
and every screen is redesigned. What the app does and how it works stays the same.

### Added

- **Themes**: light, dark, or as in the system, switched in the header and remembered in the
  browser. In the dark theme the map is shown dimmed.
- **Keyboard shortcuts window**: press `?` in the photo card (or the keyboard button).
- **Shift+1…9** in the photo card shows a suggestion on the map without picking it.
- A **legend** of the modules on the map, and loading placeholders and empty states in the
  gallery and the suggestions.
- `STEWARD_MAP_STYLE_URL_DARK`: an own map style for the dark theme (by default the map is
  dimmed instead).

### Changed

- **New name and logo** shown in the app and in the README: "Steward for Immich". The
  repository, images, compose project and the `STEWARD_*` settings keep their names.
- **New design** of every screen: the gallery filters are a row of chips (the period and the
  processing errors open a small panel), the photo card has a toolbar with labelled previous /
  next buttons, the save, skip and not applicable buttons with their keys, and the suggestions
  show a confidence meter. The markers of the modules have their own shape and color; the
  similar photos module is now purple (green marks a confirmed location).
- Fonts (IBM Plex) and icons (Lucide) come with the app; nothing is loaded from other sites
  except the map tiles.
- After rotating a photo, a block under it saves the rotation in Immich or undoes it; for a
  video it explains that the rotation works in the card only.
- Camera names no longer repeat the make ("Canon EOS 550D", not "Canon Canon EOS 550D").

### Fixed

- Year labels of the timeline mark where the year begins; when there is no room, the label is
  left out instead of moving to a later month.
- Month titles in Russian ("Август 2019 г.", not "Август 2019 Г.").

### Upgrading

No database changes. Workers of 0.3.x work with this version; there is nothing new for them, so
updating them is optional.

## [0.3.2] - 2026-10-23

Smaller improvements: the modules in the photo card can be ordered and hidden, the failures of
every module can be found in the gallery, and the Library page is now two pages, Processing and
Settings.

### Added

- **Order of the modules in the photo card**, per account: on the new Settings page, drag a
  module by its handle (or use the arrows) and choose which modules the card shows. By default:
  time neighbors, similar photos, GeoCLIP. The suggestions are numbered in this order. A hidden
  module keeps running (pausing is separate); the card leaves it out of the list and the map and
  names it in one short line below the suggestions, where a click shows it in the card until the
  page is reloaded.
- **Next sync**: the Processing page shows when the next automatic sync and the next full one
  are due.
- **Processing errors of every module** in the gallery filter (it used to list GeoCLIP only):
  choose a module, or any module, then a reason. The reasons are grouped by whose trouble they
  are: the photo and Immich, the worker, the module itself. The failure counts of a module on the
  Processing page name the same group.

### Changed

- The Library page is split in two: **Processing** (the library and its sync, workers, modules,
  status) and **Settings** (the modules in the photo card for now). Old links to `/library` open
  Processing.
- The gallery filter "Not processed" is now called "Processing errors".

### Fixed

- The thumbnails of the neighbor photos in the suggestions and on the map follow the photo when
  it is rotated or edited in Immich (they could show the old thumbnail for a long time).
- The pause menu closes on a click outside it and on Esc.
- A worker started with the address of Immich instead of the app (port 2283 instead of 8780) says
  so in its log, instead of a bare "HTTP 404".

### Upgrading

The database gets a new table on start (migration 0019). Workers of 0.3.1 work with this
version; updating them is only needed for the clearer message about a wrong address.

## [0.3.1] - 2026-10-22

Improvements from using similar photos on a full library: background runs can be paused, the
Library page shows what each worker is doing, new photos are run first, and the photo card is
quicker to work with.

### Added

- **Pause**: the background runs of every worker module, or of one, can be paused on the Library
  page, for the whole installation. Runs started from a photo still go, and runs in progress are
  finished. While anything is paused, a thin bar above the gallery and the photo card says so,
  with a button to resume.
- **What a worker is doing**: the Library page shows whether each worker is downloading a model
  (only the first time), loading it into memory and for how long, working or waiting for jobs.
  The photo card says when the worker is loading the model of a module, so that a slow first
  photo does not look like nothing works. A worker of this version still works with an older
  app, and an older worker with this one.
- **New photos first**: photos that a sync finds new in the library are run before the rest of it,
  whatever the size of the queue (runs started from a photo still go first, and a pause holds
  them too). The photos of the first sync of an account are not "new".
- **Workers that are gone** can be removed from the Library page; those not seen for 30 days are
  removed by themselves. A removed worker that connects again shows up again.
- **Pause for a while**: besides "until resumed", a module or all of them can be paused for
  30 minutes, 1 hour, 12 hours or a day; the runs then resume by themselves.

### Fixed

- A restarted worker no longer waits up to 3 minutes with "another running worker is called
  …": on a stop it says goodbye at once (before the photo it works on is done, so Docker's 10 s
  are enough), and it keeps its id across restarts (in the models volume for Docker), so even a
  killed worker is let in again at once. The job a killed worker left goes back to the queue
  when it starts again, instead of after its lease (up to 5 minutes).
- Photos in the trash of Immich are no longer counted in the progress, the failures and the
  search index of the modules.
- Enter in the photo card saves the location even when a button pressed with the mouse keeps the
  focus (it used to press "Choose" of the suggestion again).

### Changed

- Suggestions are numbered through all the modules (1, 2, 3… in the list and on the map), the
  same as their keyboard keys; each module used to start from 1.
- The Library page has a block per module: its pause, the workers running it and what they are
  doing, the counts of its runs with a progress bar, its search index and failures. "Pause all"
  is above the modules.
- The top menu stays in view when scrolling.
- Each worker is a block on the Library page, with its state shown once; the module blocks say
  which workers run them.
- The worker no longer logs a deprecation warning of PyTorch about GeoCLIP's own code.
- Save notices are in the bottom left corner; when saving fast, only the newest one and failures
  are shown, the rest behind "N more notices".
- The Save / Skip / Not applicable buttons and the picked point stay in view in the photo card;
  only the search and the suggestions below them scroll.

## [0.3.0] - 2026-10-22

A second module in the worker finds photos of the same place in your own library; photos can be
rotated in the app and the rotation saved to Immich.

### Added

- **Similar photos**: the worker computes a vector of every photo with
  [MegaLoc](https://github.com/gmberton/MegaLoc), a model made for recognizing places, and the
  app suggests where the most similar photos with a location were taken, grouped by place, with
  their thumbnails (green diamonds on the map). It runs automatically: first on the photos with a
  location, which are what it searches among, then on the photos without one. The search runs
  when a photo is opened, so it always includes the locations set since; it only looks in the
  library of the person who looks at the photo. The Library page shows how much of the index is
  built. It also works on a part of the photo. Settings: `STEWARD_SIMILAR_MIN_CONFIDENCE`,
  `STEWARD_SIMILAR_WEAK_BELOW`, `STEWARD_SIMILAR_CONFIDENT_FROM`, and
  `STEWARD_SIMILAR_INCLUDE_ESTIMATED` (whether locations set in the app count, on by default).
- **Rotate a photo** in the card with the buttons under it or the keys `[` and `]`: the photo, the
  full-size view and the part picker show it rotated, and modules started then get it rotated.
  **Save rotation in Immich** turns it there too, as an Immich edit (the original file is not
  changed, other edits stay); this needs the `asset.edit.get`, `asset.edit.create` and
  `asset.edit.delete` permissions, which keys created from now on have.
- When a photo is rotated or edited in Immich, the next sync notices its new previews, and the
  worker modules (GeoCLIP too) look at it again.

### Changed

- The worker runs similar photos and GeoCLIP (`STEWARD_WORKER_MODULES`, default
  `similar,geoclip`); both run automatically (`STEWARD_AUTO_MODULES`, default `geoclip,similar`).
  The order of `STEWARD_WORKER_MODULES` is the priority of their background photos: the index
  of similar photos first by default. Photos started from a card still go first.
- `STEWARD_WORKER_ONE_MODEL=true` keeps one model in memory at a time, for machines short of
  memory. Otherwise both may be loaded at once, so the memory limit of the worker container is
  now 6 GB instead of 4 GB (`STEWARD_WORKER_MEMORY_LIMIT`).
- Each worker module has its own display thresholds; before, GeoCLIP's applied to all.
- Thumbnail addresses change with the previews, so the browser never shows old ones after a
  photo was rotated or edited.

### Fixed

- Photos edited in Immich (rotated, cropped) are shown and given to the modules as Immich shows
  them. Before, the app got their images from before the edits.

### Upgrade notes

- `git pull` is needed for the new `compose.yaml` (new settings, worker modules and memory
  limit). On the first start, the database migrations add the vectors table; on its first use,
  the worker downloads the MegaLoc model (0.9 GB).
- The first pass of similar photos over the library takes a while: about 0.3 to 0.6 seconds per
  photo on a server CPU (a day or two for 100,000 photos), about 0.1 seconds on an NVIDIA GPU.
  Until the photos with a location are in the index, similar photos has little to suggest.
- The vectors take about 17 KB per photo in the database (some 2 GB for 130,000 photos).
- To save rotations in Immich with a key created before this version, add the `asset.edit.*`
  permissions to it in Immich (Account Settings → API Keys).

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
  ([docs/workers.md](docs/workers.md#a-worker-on-another-computer)).
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
  ([docs/updating.md](docs/updating.md#updating)).

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

[Unreleased]: https://github.com/Ivamic/immich-steward/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/Ivamic/immich-steward/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Ivamic/immich-steward/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/Ivamic/immich-steward/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/Ivamic/immich-steward/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Ivamic/immich-steward/compare/v0.2.5...v0.3.0
[0.2.5]: https://github.com/Ivamic/immich-steward/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/Ivamic/immich-steward/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/Ivamic/immich-steward/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/Ivamic/immich-steward/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Ivamic/immich-steward/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Ivamic/immich-steward/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Ivamic/immich-steward/releases/tag/v0.1.0
