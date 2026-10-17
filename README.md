# immich-steward

> **Status: early design stage.** Nothing is ready to install yet.

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

Planned modules:

- **Time neighbors** — photos taken shortly before/after with the same camera that
  already have GPS (capture time, file name sequence, device model).
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

## Planned architecture

- Backend: Python (FastAPI), PostgreSQL with pgvector.
- Runs with Docker Compose next to your Immich server.
- ML modules run in workers: on the server CPU, or on a separate machine with a GPU.
- Web UI: timeline gallery with filters, photo view with a map, keyboard-driven review.
- English UI with translations (Russian from the start).

## License

[GNU Affero General Public License v3.0](LICENSE).

## AI assistance

This project is developed with the help of AI tools (Claude by Anthropic).
All code is reviewed and maintained by a human author.

## Disclaimer

This is an independent community project. It is not affiliated with or endorsed by the
Immich project or FUTO.
