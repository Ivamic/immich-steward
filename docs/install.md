# Installing immich-steward on your server

> **The project is under active development.** Things may break or change between versions.
> The app writes to Immich only when you save a location, and every write can be undone, but
> keep a backup of your Immich library anyway.

immich-steward runs as two Docker containers: the app itself (API and web UI) and a
PostgreSQL database with pgvector, plus an optional third one, the
[GeoCLIP worker](#geoclip-worker-optional). Ready-made images are published on GitHub
Container Registry (`ghcr.io/ivamic/immich-steward-core` for `amd64` and `arm64`,
`ghcr.io/ivamic/immich-steward-worker` for `amd64`); you can also
[build them from source](#building-the-images-from-source).

## Requirements

- A Linux machine with [Docker Engine](https://docs.docker.com/engine/install/) and the
  Compose plugin (`docker compose version` prints v2.x). Usually the same machine as Immich.
- Immich **v3.x**, reachable from that machine over the network.
- Internet access to download the images and in your browser (the map is loaded from
  OpenFreeMap).
- About 1 GB of free disk space (another 3 GB for the GeoCLIP worker and its model); the
  running app needs a few hundred MB of RAM.

## 1. Get the code

The repository holds `compose.yaml` and the example settings that match the images:

```sh
git clone https://github.com/Ivamic/immich-steward.git
cd immich-steward
```

## 2. Configure

```sh
cp .env.example .env
```

Edit `.env` and set at least these values:

| Setting | What to put there |
|---|---|
| `STEWARD_IMMICH_URL` | Address of Immich **as seen from the containers**, e.g. `http://192.168.1.10:2283`. Do not use `localhost`: inside a container it means the container itself. See [Immich on the same machine](#immich-on-the-same-machine). |
| `STEWARD_SECRET_KEY` | A random secret, at least 32 characters. It encrypts the Immich API keys stored by the app. Generate one with `openssl rand -hex 32`. Keep it: changing it later signs everybody out. |
| `DB_PASSWORD` | Database password, letters and digits only, e.g. `openssl rand -hex 16`. |
| `STEWARD_PORT` | Port of the web UI on this machine, `8780` by default. |

The other settings are optional and explained in `.env.example`. The lines at the end under
"Development only" are not used by Docker and can stay as they are.

## 3. Start

```sh
docker compose up -d
```

The images are downloaded on the first start.

Check that both containers are running and the app is healthy:

```sh
docker compose ps
```

`core` should show `healthy` after about half a minute. Database migrations run automatically
every time the app starts.

## 4. Sign in

Open `http://<your-server>:8780` and sign in with your **Immich email and password**.

- The password is checked by Immich and is not stored. On the first sign-in the app creates an
  API key named `immich-steward …` in your Immich account and keeps it encrypted; later
  sign-ins reuse it.
- If you sign in to Immich through OAuth and have no password, use **Sign in with an API key
  instead**: create a key in Immich (Account Settings → API Keys) with the permissions listed on
  the sign-in page.
- Every member of the family signs in with their own Immich account and sees only their own
  library.

Within a minute after the first sign-in the app reads your library from Immich (a few seconds
for thousands of photos; the Library page has a button to start it right away). It then checks
for changes every 15 minutes.

Nothing is written to Immich until you save a location for a photo. Saved locations get the tag
`steward/estimated` in Immich, so you can always find them there.

## GeoCLIP worker (optional)

GeoCLIP suggests where a photo was taken by its look: landmarks, cities, landscapes. It is a
neural network, so it runs in a separate container, the *worker*, which takes photos without a
location one by one in the background. Results appear in the photo card as orange squares.

What it needs (measured on an Intel Core i3-13100 next to Immich):

- about 1 GB of RAM while working, up to 3 GB at its peak (the container is limited to 4 GB),
  and a 1.4 GB image;
- on its first start, the CLIP model (1.7 GB) is downloaded from Hugging Face into the volume
  `immich-steward_model-cache`, then loaded for a minute or two;
- about 0.8 seconds per photo with 2 CPU threads: some 4,000 photos an hour, in the background.

When several family members use the app, their photos are processed in turns.

To start it:

1. Set a shared secret for the worker in `.env`, e.g. `STEWARD_WORKER_TOKEN=` followed by the
   output of `openssl rand -hex 32`.
2. Start everything, including the worker:

   ```sh
   docker compose --profile worker up -d
   ```

3. Open the **Library** page: the worker is listed under *Workers*, with the progress of the runs.

Settings in `.env` (see `.env.example`):

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_WORKER_THREADS` | `2` | CPU threads for the model. More is faster but leaves less for Immich. |
| `STEWARD_WORKER_MAX_LOAD` | empty | E.g. `0.8`: the worker waits while the machine is busy (load average per CPU above 0.8), for instance while Immich transcodes videos. |
| `STEWARD_WORKER_MEMORY_LIMIT` | `4g` | Memory limit of the worker container. |
| `STEWARD_GEOCLIP_MIN_CONFIDENCE` | `0.25` | GeoCLIP suggestions below this confidence are hidden; up to `STEWARD_GEOCLIP_WEAK_BELOW` (`0.5`) they are folded as weak; from `STEWARD_GEOCLIP_CONFIDENT_FROM` (`0.75`) they are marked as confident and counted by the gallery filter. |
| `STEWARD_AUTO_MODULES` | `geoclip` | Modules that run automatically on photos without a location. Empty: only when started with **Run** in a photo card. |

The model is unloaded from memory after 10 minutes without work. Photos never leave your server:
the worker gets them from the app, not from the internet.

## Immich on the same machine

If Immich runs on the same machine, the simplest choice is the machine's LAN address in
`STEWARD_IMMICH_URL` (e.g. `http://192.168.1.10:2283`).

Alternatively, attach the app to Immich's Docker network and use the name of the Immich
container. Create `compose.override.yaml` next to `compose.yaml`:

```yaml
services:
  core:
    networks: [default, immich]

networks:
  immich:
    external: true
    name: immich_default   # check with: docker network ls
```

and set `STEWARD_IMMICH_URL=http://immich_server:2283` (the container name from Immich's
`docker-compose.yml`). Then run `docker compose up -d` again.

## Access from outside your home network

The app has no protection of its own beyond the Immich sign-in. Keep it inside your home network
or VPN. If you publish it, do so only through a reverse proxy with HTTPS (the Immich password
passes through the app when you sign in), and set `STEWARD_COOKIE_SECURE=true` in `.env`.

## What leaves your server

- **Map tiles** are loaded by your browser from OpenFreeMap (no account, no key). Another tile
  server can be set with `STEWARD_MAP_STYLE_URL`.
- **Address search** sends the typed text and the approximate map position from the app server
  to the public Photon geocoder (`photon.komoot.io`). Set `STEWARD_GEOCODER_URL=` (empty) to turn
  address search off, or point it to your own Photon.
- **The GeoCLIP model** is downloaded from Hugging Face (`huggingface.co`) when the worker loads
  it for the first time; later loads only check for updates there.
- **Photos never leave your server.** Location suggestions are computed from your own library and
  by the local GeoCLIP model.

## Updating

```sh
cd immich-steward
git pull                                    # compose.yaml now names the new version
docker compose --profile worker pull        # without --profile worker if you don't use it
docker compose --profile worker up -d
```

Old images can be removed afterwards with `docker image prune`. See the
[changelog](../CHANGELOG.md) for what is new and whether `.env` needs new settings.

To stay on a version, set `STEWARD_VERSION` in `.env` (e.g. `STEWARD_VERSION=0.2.2`).

## Building the images from source

Instead of downloading the images, you can build them on your server (a few minutes, about
2 GB of disk space during the build, internet access for the packages). Run the same commands
with `--build`:

```sh
docker compose up -d --build                      # or: docker compose --profile worker up -d --build
```

This is also the way to run the worker on `arm64` for now. The images built this way get the
same names as the published ones; `docker compose pull` replaces them with the published images
again.

## Backup

The app's own data — accounts, encrypted API keys, the history of written locations, "skipped"
and "not applicable" marks — lives in the Docker volume `immich-steward_db-data`. The
coordinates themselves are stored in Immich.

```sh
docker compose exec db pg_dump -U steward steward > steward-backup.sql
```

Use the values of `DB_USER` and `DB_NAME` if you changed them. Keep `.env` together with the
backup: without the same `STEWARD_SECRET_KEY` the stored API keys cannot be decrypted (users
would simply sign in again).

## Uninstalling

```sh
docker compose --profile worker down       # stops the app, keeps the data
docker compose --profile worker down -v    # also deletes the database and the model cache
```

The app's API key stays in your Immich account: delete `immich-steward …` under Account
Settings → API Keys. Locations and tags written to Immich stay as they are.

## Troubleshooting

**"The Immich server does not respond".** Check the connection from inside the app container:

```sh
docker compose exec core python -c "import os, urllib.request; print(urllib.request.urlopen(os.environ['STEWARD_IMMICH_URL'] + '/api/server/version', timeout=5).read())"
```

If this fails while Immich opens fine in your browser:

- `STEWARD_IMMICH_URL` uses `localhost` or `127.0.0.1` — use the LAN address instead.
- A firewall on the machine blocks the Immich port for Docker networks.
- A Docker network overlaps your home network (for example both use `192.168.0.0/20`): compare
  `docker network inspect immich-steward_default` with your LAN and, if needed, set
  `default-address-pools` in `/etc/docker/daemon.json`.
- Docker Desktop (Windows, macOS) sometimes cannot reach devices of the local network; a Linux
  server is the intended setup.

**`pull access denied for immich-steward-core`.** Your `compose.yaml` is from version 0.2.1 or
older, which only built the images locally. Run `git pull` to get the current one, or build
with `docker compose up -d --build`.

**`core` is `unhealthy` or restarting.** See `docker compose logs core`. A missing
`STEWARD_IMMICH_URL`, `STEWARD_SECRET_KEY` or `DB_PASSWORD` is reported when the containers
start.

**The GeoCLIP queue grows, but nothing is done.** On its first start the worker downloads and
loads the model, which takes a few minutes. Look at `docker compose logs --tail 40 worker`:
`GeoCLIP loaded` and then `done in … s` lines mean it works. An error there (out of memory, no
access to `huggingface.co`) tells what is wrong.

**Password sign-in is refused although the password is right.** Password login may be turned
off on your Immich server (OAuth only). Sign in with an API key instead.

**The map stays empty.** Your browser needs access to `tiles.openfreemap.org`.
