# Steward for Immich: documentation

Steward puts your photos without GPS back on the map: several independent modules suggest where
each one was taken, all on one map, and you pick. It runs on your own server, next to
[Immich](https://immich.app).

> **The project is under active development.** Things may break or change between versions.
> The app writes to Immich only when you save a location, and every write can be undone, but
> keep a backup of your Immich library anyway.

## Where to start

| You want to… | Read |
|---|---|
| Install the app for the first time | [Installation](install.md): step by step, with every command explained |
| Learn how to work with it: the gallery, the photo card, the suggestions, the keys | [Using the app](usage.md) |
| Turn on GeoCLIP and similar photos, or use another computer or a graphics card to speed them up | [Workers](workers.md) |
| Look up a setting | [Configuration](configuration.md): every setting in one place |
| Update to a new version, back up, remove the app | [Updating and maintenance](updating.md) |
| Know what leaves your server, open the app from outside your home | [Privacy and security](privacy.md) |
| Fix a problem | [Troubleshooting](troubleshooting.md) |

What changed in each version: [changelog](../CHANGELOG.md).

## A few words used in these pages

- **Server**: the computer where Immich and Steward run, usually at home, always on.
- **Docker** and **Docker Compose**: the programs that start Steward on the server in
  *containers*, isolated boxes with everything the app needs. You type a few `docker compose …`
  commands; you don't have to know Docker well.
- **`.env`**: a text file with your settings (the address of Immich, passwords), next to
  `compose.yaml` in the folder of the app.
- **Module**: one way of guessing where a photo was taken. *Time neighbors* looks at the photos
  taken shortly before and after; *GeoCLIP* recognizes the place by its look; *similar photos*
  finds photos of the same place in your library.
- **Worker**: a separate program that runs the modules that are neural networks (GeoCLIP and
  similar photos). It is optional and can run on the server or on another computer.
- **Suggestion**: a place a module proposes for a photo. Nothing is written to Immich until you
  choose one (or pick a point yourself) and save it.
