# Installing immich-steward on your server

> **The project is under active development.** Things may break or change between versions.
> The app writes to Immich only when you save a location, and every write can be undone, but
> keep a backup of your Immich library anyway.

immich-steward runs as two Docker containers: the app itself (API and web UI) and a
PostgreSQL database with pgvector, plus an optional third one, the
[worker](#worker-optional) for the location modules that are neural networks. Ready-made images are published on GitHub
Container Registry (`ghcr.io/ivamic/immich-steward-core` for `amd64` and `arm64`,
`ghcr.io/ivamic/immich-steward-worker` for `amd64`); you can also
[build them from source](#building-the-images-from-source).

## Requirements

- A Linux machine with [Docker Engine](https://docs.docker.com/engine/install/) and the
  Compose plugin (`docker compose version` prints v2.x). Usually the same machine as Immich.
- Immich **v3.x**, reachable from that machine over the network.
- Internet access to download the images and in your browser (the map is loaded from
  OpenFreeMap).
- About 1 GB of free disk space (another 4 GB for the worker and its models, and a few GB for
  the database of a big library: similar photos keep 17 KB per photo); the
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
- Saving a photo rotated in the app to Immich needs the `asset.edit.get`, `asset.edit.create` and
  `asset.edit.delete` permissions. Keys the app creates from now on have them; a key created by
  an earlier version needs them added in Immich (Account Settings → API Keys → edit the key).

Within a minute after the first sign-in the app reads your library from Immich (a few seconds
for thousands of photos; the Processing page has a button to start it right away). It then checks
for changes every 15 minutes.

Nothing is written to Immich until you save a location for a photo. Saved locations get the tag
`steward/estimated` in Immich, so you can always find them there.

## Worker (optional)

Two location modules are neural networks, so they run in a separate container, the *worker*,
which takes photos one by one in the background:

- **GeoCLIP** suggests where a photo was taken by its look: landmarks, cities, landscapes, all
  over the world. It looks at the photos without a location. Its suggestions are orange squares.
- **Similar photos** finds photos of the same place in your own library: the same street, house,
  view or room, from another angle or in another season. It needs every photo of the library: the
  ones with a location are what it searches among, so the worker takes them first, then the
  photos without a location. Its suggestions are green diamonds, with thumbnails of the similar
  photos. The search runs when you open a photo, so it always includes the locations you have
  set since.

What it needs (measured on an Intel Core i3-13100 next to Immich):

- for GeoCLIP about 1 GB of RAM, up to 3 GB at its peak; for similar photos about 1.2 GB, 2 GB
  while loading (the container is limited to 6 GB); a 1.4 GB image;
- on their first use, the models are downloaded from Hugging Face into the volume
  `immich-steward_model-cache` (CLIP 1.7 GB, MegaLoc 0.9 GB), then loaded for a minute or two;
- with 2 CPU threads, about 0.8 seconds per photo for GeoCLIP and 0.3 to 0.6 seconds for similar
  photos. The first pass of similar photos over a library of 100,000 photos takes a day or two
  in the background; a [GPU worker](#worker-on-an-nvidia-gpu) does it in about an hour.

When several family members use the app, their photos are processed in turns. Similar photos
only ever searches the library of the person who looks at the photo.

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
| `STEWARD_WORKER_MODULES` | `similar,geoclip` | Modules the worker on the server runs, the photos of the first one first (photos you start a module on from a card always go first). |
| `STEWARD_WORKER_ONE_MODEL` | `false` | `true`: one model in memory at a time. With the order above, the worker finishes one module's photos before it loads the other model; a limit of `4g` is then enough. |
| `STEWARD_WORKER_MEMORY_LIMIT` | `6g` | Memory limit of the worker container. |
| `STEWARD_GEOCLIP_MIN_CONFIDENCE` | `0.25` | GeoCLIP suggestions below this confidence are hidden; up to `STEWARD_GEOCLIP_WEAK_BELOW` (`0.5`) they are folded as weak; from `STEWARD_GEOCLIP_CONFIDENT_FROM` (`0.75`) they are marked as confident and counted by the gallery filter. |
| `STEWARD_SIMILAR_MIN_CONFIDENCE` | `0.2` | The same for similar photos (`STEWARD_SIMILAR_WEAK_BELOW` `0.5`, `STEWARD_SIMILAR_CONFIDENT_FROM` `0.8`). Their confidence is how often such a match turned out right within 1 km on a real family library: 0.8 means about 8 times out of 10. |
| `STEWARD_SIMILAR_INCLUDE_ESTIMATED` | `true` | Similar photos also searches among the photos whose location you set in the app. `false`: only among locations recorded by cameras. Applies at once. |
| `STEWARD_AUTO_MODULES` | `geoclip,similar` | Modules that run automatically on photos without a location (`similar` also on the photos with one: they are its search index, and go first). Empty: only when started with **Run** in a photo card. |

A model is unloaded from memory after 10 minutes without work. Photos never leave your server:
the worker gets them from the app, not from the internet.

When a photo is rotated or edited in Immich (or rotated and saved from the photo card), the
modules look at it again.

## Workers on other computers

A worker does not have to run on the server. It can run on any computer in your home network:
a desktop that is on in the evening, a laptop, a second server. The worker connects to the app
itself (nothing has to connect to the worker), takes photos without a location one by one,
gets each photo from the app and sends back the result. It never sees your Immich API key.

Several workers can run at the same time, each takes its own photos. For example, the worker on
the server works in the background day and night, and a desktop helps while it is on. When a
worker is stopped, its current photo goes back to the queue right away; when a computer simply
goes to sleep, after 5 minutes.

### Before you start

1. **The app must have a worker token.** On the server, `STEWARD_WORKER_TOKEN` in `.env` must be
   set (see [Worker](#worker-optional)). If you have just set it, apply it with
   `docker compose up -d` (or `docker compose --profile worker up -d`).
2. **The other computer must reach the app** at the same address you open in your browser, e.g.
   `http://192.168.1.10:8780`. If the server has a firewall, allow port `8780` from your home
   network.
3. **Choose how to run it.** With an NVIDIA graphics card, use the
   [GPU worker](#worker-on-an-nvidia-gpu): it is several times faster. Otherwise use Docker
   (Docker Engine on Linux or Docker Desktop on Windows) and about 4 GB of disk space: the image
   (1.4 GB) and the models (CLIP 1.7 GB, MegaLoc 0.9 GB), which are downloaded from Hugging Face
   on their first use.

In the examples below, replace `192.168.1.10:8780` with the address of your server and
`your-token` with the value of `STEWARD_WORKER_TOKEN` from the server's `.env`.

### Start a worker with Docker on Linux

```sh
docker run -d --name steward-worker --restart unless-stopped \
  -e STEWARD_CORE_URL=http://192.168.1.10:8780 \
  -e STEWARD_WORKER_TOKEN=your-token \
  -e STEWARD_WORKER_NAME=desktop \
  -e STEWARD_WORKER_THREADS=4 \
  -v steward-models:/models \
  ghcr.io/ivamic/immich-steward-worker:0.3.2
```

### Start a worker with Docker on Windows (PowerShell, Docker Desktop)

```powershell
docker run -d --name steward-worker --restart unless-stopped `
  -e STEWARD_CORE_URL=http://192.168.1.10:8780 `
  -e STEWARD_WORKER_TOKEN=your-token `
  -e STEWARD_WORKER_NAME=desktop `
  -e STEWARD_WORKER_THREADS=4 `
  -v steward-models:/models `
  ghcr.io/ivamic/immich-steward-worker:0.3.2
```

With `--restart unless-stopped`, the worker starts again together with Docker, e.g. after a
reboot, until you stop it.

- `STEWARD_WORKER_NAME` is the name shown on the **Library** page. The app tells workers apart
  by their names, so give every worker its own name (not `server`, which the worker on the
  server uses). A second worker with the name of a running one is refused until the first
  stops.
- `STEWARD_WORKER_THREADS` is the number of CPU threads for the models: more is faster, but leaves
  less for other programs on that computer.
- The volume `steward-models` keeps the models, so they are downloaded only once.
- The worker runs both modules, the photos of similar photos first;
  `-e STEWARD_WORKER_MODULES=geoclip,similar` changes the order, `geoclip` alone limits it to
  one module. On a computer short of memory, add `-e STEWARD_WORKER_ONE_MODEL=true`.
- On Linux, `-e STEWARD_WORKER_MAX_LOAD=0.8` makes the worker wait while the computer is busy.

### Check that it works

```sh
docker logs --tail 20 steward-worker
```

| In the log | Meaning |
|---|---|
| `registered with the core as …` | Connected. The worker is listed on the **Library** page. |
| `GeoCLIP loaded on cpu …` or `MegaLoc loaded on cpu …`, then `job … done in … s` | Working on photos. The first load takes a few minutes (the model is downloaded). |
| `HTTP 401 worker_unauthorized` | The token differs from `STEWARD_WORKER_TOKEN` on the server. |
| `HTTP 503 workers_disabled` | The app has no worker token: set `STEWARD_WORKER_TOKEN` on the server and run `docker compose up -d` there. |
| `another running worker is called …` | That name is taken by a worker that is running now on another computer: choose another `STEWARD_WORKER_NAME` (or `--name`). A restarted worker is known as the same one: it keeps its id in the models volume (`/models/steward-worker.id`; from source: `~/.cache/steward-worker/<name>.id`, or `STEWARD_WORKER_ID_FILE`). |
| `ConnectError` | The app is not reachable at that address: check the address, the port and the firewall. |

A worker with no photos to do just waits, that is normal.

### Stop, update, remove the Docker worker

Stop the worker:

```sh
docker stop steward-worker
```

Start it again:

```sh
docker start steward-worker
```

Update it to a new version: remove the container, then run the `docker run` command above
again with the new version number instead of `0.3.2` at its end. The models stay in the volume.

```sh
docker rm -f steward-worker
```

Remove it completely, together with the downloaded models:

```sh
docker rm -f steward-worker
docker volume rm steward-models
```

Keep the worker version the same as the app's version.

### Worker on an NVIDIA GPU

The published worker image uses the CPU only: a GPU build contains NVIDIA's proprietary
libraries, which we do not distribute. On a computer with an NVIDIA graphics card, install the
worker from source instead; the GPU build of PyTorch is downloaded during the installation.

Measured on a laptop with an RTX 3060 Laptop GPU (6 GB), connected to the server over the home
network: about 0.25 seconds per photo for GeoCLIP, some 10,000 photos an hour (the server's CPU
worker next to it needs 0.8 seconds), and 0.1 seconds for similar photos. Both models together
take about 4 GB of video memory.

What it needs:

- an NVIDIA graphics card with at least 4 GB of video memory and a current driver (version 580
  or newer, check with `nvidia-smi`);
- [Git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/);
- about 6 GB of disk space: 3.2 GB for the installation and the models (CLIP 1.7 GB, MegaLoc
  0.9 GB), which are downloaded on their first use.

In the examples below, replace `192.168.1.10:8780` with the address of your server,
`your-token` with the value of `STEWARD_WORKER_TOKEN` from the server's `.env`, and `0.3.2` with
the version of the app on your server.

#### GPU worker on Windows (PowerShell)

Install once:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
git clone --branch v0.3.2 https://github.com/Ivamic/immich-steward.git D:\steward-worker
cd D:\steward-worker
uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra cuda
```

Open a new PowerShell window after `winget` so that `git` and `uv` are found.

Start the worker (every time; it runs while the window is open):

```powershell
cd D:\steward-worker
$env:STEWARD_WORKER_TOKEN = "your-token"
.\.venv\Scripts\steward-worker --core http://192.168.1.10:8780 --modules similar,geoclip --name laptop
```

#### GPU worker on Linux (bash)

Install once (Git is usually installed already; otherwise `sudo apt install git`):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
git clone --branch v0.3.2 https://github.com/Ivamic/immich-steward.git ~/steward-worker
cd ~/steward-worker
uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra cuda
```

Start the worker (every time; it runs while the terminal is open):

```sh
cd ~/steward-worker
export STEWARD_WORKER_TOKEN=your-token
.venv/bin/steward-worker --core http://192.168.1.10:8780 --modules similar,geoclip --name desktop
```

#### Check, stop, update the GPU worker

The log is printed in the window. `GeoCLIP loaded on cuda` (or `MegaLoc loaded on cuda`) means the worker uses the graphics
card; `loaded on cpu` means PyTorch did not find it (check the driver with `nvidia-smi`). The
other messages are the same as in the [table above](#check-that-it-works).

Stop the worker with **Ctrl+C**. Its current photo goes back to the queue, and the **Library**
page shows the worker as not connected right away.

Update to a new version (replace `0.3.2` with the new version), on Windows:

```powershell
cd D:\steward-worker
git fetch --tags
git checkout v0.3.2
uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra cuda
```

On Linux:

```sh
cd ~/steward-worker
git fetch --tags
git checkout v0.3.2
uv sync --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra cuda
```

To remove the worker, delete the folder (`D:\steward-worker` or `~/steward-worker`) and the
downloaded models: the folders `models--openai--clip-vit-large-patch14` and
`models--gberton--MegaLoc` in
`%USERPROFILE%\.cache\huggingface\hub` on Windows or in `~/.cache/huggingface/hub` on Linux.

### Security

The worker token and the photos travel over plain HTTP. That is fine inside your home network
or a VPN (e.g. WireGuard), but do not connect workers to the app over the internet without HTTPS.
Anyone who has the token can get photos from the app, so keep it secret.

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
`docker-compose.yml`). Your browser does not know that name, so also set the address you open
Immich with, for the **Open in Immich** links in photo cards, e.g.
`STEWARD_IMMICH_PUBLIC_URL=http://192.168.1.10:2283`. Then run `docker compose up -d` again.

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
- **The models** of GeoCLIP and of similar photos (MegaLoc) are downloaded from Hugging Face
  (`huggingface.co`) when the worker loads them for the first time; later loads only check for
  updates there.
- **Photos never leave your server.** Location suggestions are computed from your own library and
  by the local models.

## Updating

`git pull` gets the new `compose.yaml`, which names the new version of the images.
Don't skip it: `compose.yaml` pins the image version, so `docker compose pull` alone downloads
the same version you already have.

The version is pinned on purpose. The project is at an early stage, and a new version may need
changes in `compose.yaml` itself: new settings, services or volumes. Updating the images and
`compose.yaml` together keeps them in step.

Without the worker:

```sh
cd immich-steward
git pull
docker compose pull
docker compose up -d
```

With the worker:

```sh
cd immich-steward
git pull
docker compose --profile worker pull
docker compose --profile worker up -d
```

Old images can be removed afterwards with `docker image prune`. See the
[changelog](../CHANGELOG.md) for what is new and whether `.env` needs new settings.

To stay on a version, set `STEWARD_VERSION` in `.env` (e.g. `STEWARD_VERSION=0.3.2`).

If you changed `compose.yaml` yourself, `git pull` may stop with a conflict. Move your changes
to `.env` or to a `compose.override.yaml` file, which Docker Compose reads automatically and
`git pull` doesn't touch.

`STEWARD_VERSION=latest` (or `0.3` for the newest 0.3.x) makes `docker compose pull` fetch new
images without `git pull`. We don't recommend it while the project is at an early stage: a new
image may need a newer `compose.yaml` than the one you have, and the app may fail to start.

## Building the images from source

Instead of downloading the images, you can build them on your server (a few minutes, about
2 GB of disk space during the build, internet access for the packages). Run the same commands
with `--build`.

Without the worker:

```sh
docker compose up -d --build
```

With the worker:

```sh
docker compose --profile worker up -d --build
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
loads the model, which takes a few minutes. The **Library** page shows what each worker is
doing: downloading the model, loading it into memory (with the time so far), working, or
waiting for jobs; it also shows when background runs are paused. Look at
`docker compose logs --tail 40 worker`:
`GeoCLIP loaded` and then `done in … s` lines mean it works. An error there (out of memory, no
access to `huggingface.co`) tells what is wrong.

**Some photos failed in GeoCLIP.** The **Library** page lists the failed photos by reason.
**Show** opens them in the gallery (the photo card has a link to open the photo in Immich), and
**Run again** queues them once more, e.g. after fixing a file in Immich. "Immich could not give
the photo" usually means a broken or unsupported file: Immich cannot make its preview either.

**Password sign-in is refused although the password is right.** Password login may be turned
off on your Immich server (OAuth only). Sign in with an API key instead.

**The map stays empty.** Your browser needs access to `tiles.openfreemap.org`.
