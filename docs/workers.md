# Workers

Four modules are neural networks: **GeoCLIP**, **similar photos**, **matching details** and
**orientation**. They run in a
separate program, the *worker*, which takes photos one by one in the background and sends the
results to the app. The worker is optional: without it the app still suggests places from the
photos taken shortly before and after, and you can pick points on the map yourself.

- **GeoCLIP** suggests where a photo was taken by its look: landmarks, cities, landscapes, all
  over the world. It looks at the photos without a location. Its suggestions are orange squares.
- **Similar photos** finds photos of the same place in your own library: the same street, house,
  view or room, from another angle or in another season. It needs every photo of the library: the
  ones with a location are what it searches among, so the worker takes them first, then the
  photos without a location. Its suggestions are purple diamonds, with thumbnails of the similar
  photos. The search runs when you open a photo, so it always includes the locations you have
  set since.
- **Matching details** confirms what similar photos found: it compares a photo with its most
  similar photos point by point ([usage](usage.md#confirmed-by-details)). It suggests no
  places itself. By itself it runs only on a worker with a graphics card; a comparison
  started from a photo card runs on any worker.
- **Orientation** finds the photos that lie on their side, for the tab **Turned photos** of the
  Groups page ([usage](usage.md#turned-photos)). It looks at every photo once and is light: a
  fraction of a second per photo, also on a CPU.

Photos never leave your home network: the worker gets them from the app, not from the internet.

There are three ways to run a worker; you can combine them:

| Where | Speed | Effort |
|---|---|---|
| [On the server](#a-worker-on-the-server), next to the app | slow but steady, day and night | one line in `.env` |
| [On another computer with Docker](#a-worker-on-another-computer) | depends on that computer | one `docker run` command |
| [On a computer with an NVIDIA graphics card](#a-worker-on-an-nvidia-graphics-card) | fastest: a library of 100,000 photos in about an hour | install from source |

## A worker on the server

What it needs (measured on an Intel Core i3-13100 next to Immich):

- for GeoCLIP about 1 GB of RAM, up to 3 GB at its peak; for similar photos about 1.2 GB, 2 GB
  while loading (the container is limited to 6 GB); a 1.4 GB image;
- on their first use, the models are downloaded from Hugging Face into the volume
  `immich-steward_model-cache` (CLIP 1.7 GB, MegaLoc 0.9 GB), then loaded for a minute or two;
  those of matching details (50 MB) come from GitHub into the same volume;
- with 2 CPU threads, about 0.8 seconds per photo for GeoCLIP and 0.3 to 0.6 seconds for similar
  photos. The first pass of similar photos over a library of 100,000 photos takes a day or two in
  the background. Matching details started from a photo card takes about 12 seconds for a photo
  and its five most similar ones.

To start it:

1. In `.env`, set a shared secret for the workers: `STEWARD_WORKER_TOKEN=` followed by the output
   of `openssl rand -hex 32`. Every worker sends it to the app.
2. Start everything, including the worker:

   ```sh
   docker compose --profile worker up -d
   ```

   From now on use `--profile worker` with the other `docker compose` commands too (pull, down).
3. Open the **Processing** page: the worker is listed under *Workers*, with the progress of the
   modules.

How fast it works and how much it takes from Immich is set in `.env`: the number of CPU threads,
waiting while the server is busy, one model in memory at a time, which modules run automatically.
See [Configuration](configuration.md#worker-on-the-server).

When several family members use the app, their photos are processed in turns. Similar photos only
ever searches the library of the person who looks at the photo. A model is unloaded from memory
after 10 minutes without work. When a photo is rotated or edited in Immich (or rotated and saved
from the photo card), the modules look at it again.

## A worker on another computer

The quickest way: **Processing → Add a device** shows the commands below with your address, a
name and (for an administrator of Immich) the token filled in.

A worker does not have to run on the server. It can run on any computer in your home network: a
desktop that is on in the evening, a laptop, a second server. The worker connects to the app
itself (nothing has to connect to the worker), takes photos one by one, gets each photo from the
app and sends back the result. It never sees your Immich API key.

Several workers can run at the same time, each takes its own photos. For example, the worker on
the server works in the background day and night, and a desktop helps while it is on. When a
worker is stopped, its current photo goes back to the queue right away; when a computer simply
goes to sleep, after 5 minutes.

### Before you start

1. **The app must have a worker token.** On the server, `STEWARD_WORKER_TOKEN` in `.env` must be
   set (see [above](#a-worker-on-the-server)). If you have just set it, apply it on the server with
   `docker compose up -d` (or `docker compose --profile worker up -d`).
2. **The other computer must reach the app** at the same address you open in your browser, e.g.
   `http://192.168.1.10:8780` (port `8780`, not the Immich port `2283`). If the server has a
   firewall, allow port `8780` from your home network.
3. **Choose how to run it.** With an NVIDIA graphics card, use the
   [GPU worker](#a-worker-on-an-nvidia-graphics-card): it is several times faster. Otherwise use
   Docker (Docker Engine on Linux or Docker Desktop on Windows) and about 4 GB of disk space: the
   image (1.4 GB) and the models (CLIP 1.7 GB, MegaLoc 0.9 GB), which are downloaded from Hugging
   Face on their first use.

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
  ghcr.io/ivamic/immich-steward-worker:0
```

### Start a worker with Docker on Windows (PowerShell, Docker Desktop)

```powershell
docker run -d --name steward-worker --restart unless-stopped `
  -e STEWARD_CORE_URL=http://192.168.1.10:8780 `
  -e STEWARD_WORKER_TOKEN=your-token `
  -e STEWARD_WORKER_NAME=desktop `
  -e STEWARD_WORKER_THREADS=4 `
  -v steward-models:/models `
  ghcr.io/ivamic/immich-steward-worker:0
```

With `--restart unless-stopped`, the worker starts again together with Docker, e.g. after a
reboot, until you stop it.

- `STEWARD_WORKER_NAME` is the name shown on the **Processing** page. The app tells workers apart
  by their names, so give every worker its own name (not `server`, which the worker on the server
  uses). A second worker with the name of a running one is refused until the first stops.
- `STEWARD_WORKER_THREADS` is the number of CPU threads for the models: more is faster, but leaves
  less for other programs on that computer.
- The volume `steward-models` keeps the models, so they are downloaded only once.
- The worker runs all its modules, the photos of similar photos first;
  `-e STEWARD_WORKER_MODULES=geoclip,similar` changes the order, `geoclip` alone limits it to one
  module. On a computer short of memory, add `-e STEWARD_WORKER_ONE_MODEL=true`. Without a
  restart, the **Processing** page turns a module of a worker off and on (its switches): e.g.
  GeoCLIP only on the computer with a graphics card.
- On Linux, `-e STEWARD_WORKER_MAX_LOAD=0.8` makes the worker wait while the computer is busy.

All worker settings: [Configuration](configuration.md#worker-on-another-computer).

### Check that it works

```sh
docker logs --tail 20 steward-worker
```

| In the log | Meaning |
|---|---|
| `registered with the core as …` | Connected. The worker is listed on the **Processing** page. |
| `GeoCLIP loaded on cpu …` or `MegaLoc loaded on cpu …`, then `job … done in … s` | Working on photos. The first load takes a few minutes (the model is downloaded). |
| `HTTP 401 worker_unauthorized` | The token differs from `STEWARD_WORKER_TOKEN` on the server. |
| `HTTP 503 workers_disabled` | The app has no worker token: set `STEWARD_WORKER_TOKEN` on the server and run `docker compose up -d` there. |
| `… is not an immich-steward core (no worker API there)` | The address points to Immich or to another program, not to Steward: use the port of Steward (`8780` by default), not the one of Immich (`2283`). |
| `another running worker is called …` | That name is taken by a worker that is running now on another computer: choose another `STEWARD_WORKER_NAME` (or `--name`). A restarted worker is known as the same one: it keeps its id in the models volume (`/models/steward-worker.id`; from source: `~/.cache/steward-worker/<name>.id`, or `STEWARD_WORKER_ID_FILE`). |
| `the app on the server (…) recommends a newer worker than this one …` | The worker changed in a release since: update it to the version of the app. The message ends with the commands to do it. Releases that do not change the worker do not ask; an older worker of the same major version keeps working. |
| `ConnectError` | The app is not reachable at that address: check the address, the port and the firewall. |

A worker with no photos to do just waits; that is normal.

### Stop, update, remove the Docker worker

Stop the worker:

```sh
docker stop steward-worker
```

Start it again:

```sh
docker start steward-worker
```

To update it, see [Updating a worker](#updating-a-worker).

Remove it completely, together with the downloaded models:

```sh
docker rm -f steward-worker
docker volume rm steward-models
```

The image tag `0` follows the newest 0.x release, as the app on the server does.

## A worker on an NVIDIA graphics card

The published worker image uses the CPU only: a GPU build contains NVIDIA's proprietary
libraries, which we do not distribute. On a computer with an NVIDIA graphics card, install the
worker from source instead; the GPU build of PyTorch is downloaded during the installation.

Measured on a laptop with an RTX 3060 Laptop GPU (6 GB), connected to the server over the home
network: about 0.25 seconds per photo for GeoCLIP, some 10,000 photos an hour (the server's CPU
worker next to it needs 0.8 seconds), and 0.1 seconds for similar photos. Both models together
take about 4 GB of video memory. Matching details takes about 1 GB more and a couple of seconds
for a photo and its twenty most similar ones.

What it needs:

- an NVIDIA graphics card with at least 4 GB of video memory and a current driver (version 580
  or newer, check with `nvidia-smi`);
- [Git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/getting-started/installation/)
  (installed by the commands below);
- about 6 GB of disk space: 3.2 GB for the installation and the models (CLIP 1.7 GB, MegaLoc
  0.9 GB), which are downloaded on their first use.

The commands install the worker for Python 3.12, which uv downloads by itself if needed. If
`uv sync` asks for Microsoft Visual C++ Build Tools, see
[troubleshooting](troubleshooting.md#uv-sync-asks-for-microsoft-visual-c-build-tools).

In the examples below, replace `192.168.1.10:8780` with the address of your server,
`your-token` with the value of `STEWARD_WORKER_TOKEN` from the server's `.env`, and `0.13.1` with
the version of the app on your server (shown in **Settings → Updates**).

### GPU worker on Windows (PowerShell)

Install once:

```powershell
winget install --id Git.Git -e
winget install --id astral-sh.uv -e
```

Close PowerShell and open a new window, so that `git` and `uv` are found. Then:

```powershell
git clone --branch v0.13.1 https://github.com/Ivamic/immich-steward.git D:\steward-worker
cd D:\steward-worker
uv sync --python 3.12 --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra details --extra orientation --extra cuda
```

Start the worker (every time; it runs while the window is open):

```powershell
cd D:\steward-worker
$env:STEWARD_WORKER_TOKEN = "your-token"
.\.venv\Scripts\steward-worker --core http://192.168.1.10:8780 --modules similar,geoclip,details --name laptop
```

### GPU worker on Linux (bash)

Install once (Git is usually installed already; otherwise `sudo apt install git`):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
git clone --branch v0.13.1 https://github.com/Ivamic/immich-steward.git ~/steward-worker
cd ~/steward-worker
uv sync --python 3.12 --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra details --extra orientation --extra cuda
```

Start the worker (every time; it runs while the terminal is open):

```sh
cd ~/steward-worker
export STEWARD_WORKER_TOKEN=your-token
.venv/bin/steward-worker --core http://192.168.1.10:8780 --modules similar,geoclip,details --name desktop
```

### Start the GPU worker with one file

Instead of typing the commands every time, keep them in a file in the worker folder. Git does not
touch it, so it stays there after an update. The token is kept in it as plain text: keep the file
on your own computer only.

On Windows, create `D:\steward-worker\start-worker.cmd` (e.g. in Notepad, saved as *All files*):

```bat
@echo off
cd /d D:\steward-worker
set STEWARD_WORKER_TOKEN=your-token
set STEWARD_CORE_URL=http://192.168.1.10:8780
set STEWARD_WORKER_MODULES=similar,geoclip,details,orientation
set STEWARD_WORKER_NAME=laptop
.venv\Scripts\steward-worker.exe
pause
```

Start the worker with a double-click on the file. Stop it with **Ctrl+C** in its window rather than
by closing the window: then the app learns at once that the worker has stopped. `pause` keeps the
window open after the worker stops, so an error stays readable. To start the worker every time you
sign in to Windows, put a shortcut to the file into the startup folder (press **Win+R** and enter
`shell:startup`).

On Linux, create `~/steward-worker/start-worker.sh`:

```sh
#!/bin/sh
cd ~/steward-worker
export STEWARD_WORKER_TOKEN=your-token
export STEWARD_CORE_URL=http://192.168.1.10:8780
export STEWARD_WORKER_MODULES=similar,geoclip,details,orientation
export STEWARD_WORKER_NAME=desktop
exec .venv/bin/steward-worker
```

Make it executable and readable only by you, then start it:

```sh
chmod 700 ~/steward-worker/start-worker.sh
~/steward-worker/start-worker.sh
```

### Check, stop, update the GPU worker

The log is printed in the window. `GeoCLIP loaded on cuda` (or `MegaLoc loaded on cuda`) means
the worker uses the graphics card; `loaded on cpu` means PyTorch did not find it (check the
driver with `nvidia-smi`). The other messages are the same as in the
[table above](#check-that-it-works).

Stop the worker with **Ctrl+C**. Its current photo goes back to the queue, and the **Processing**
page shows the worker as not connected right away.

To update it, see [Updating a worker](#updating-a-worker).

To remove the worker, delete the folder (`D:\steward-worker` or `~/steward-worker`) and the
downloaded models: the folders `models--openai--clip-vit-large-patch14` and
`models--gberton--MegaLoc` in `%USERPROFILE%\.cache\huggingface\hub` on Windows or in
`~/.cache/huggingface/hub` on Linux.

## Updating a worker

**When.** Within a major version an older worker keeps working with a newer app, but it does not
have what the new release brought (e.g. a new module). When a release changes the worker, the
**Processing** page marks older workers with "version … available", and they say so in their
log; releases that do not change the worker ask nothing. A worker that is too old for the app is
shown there as not connected, with the reason.

**The worker on the server** is updated together with the app, by the same commands
([Updating](updating.md)):

```sh
docker compose --profile worker pull
docker compose --profile worker up -d
```

**A worker in Docker on another computer.** Download the new image and remove the container, then
start it again with the same `docker run` command as the first time (with your address, token
and name). The models stay in the volume `steward-models`. On Linux:

```sh
docker pull ghcr.io/ivamic/immich-steward-worker:0
docker rm -f steward-worker
docker run -d --name steward-worker --restart unless-stopped \
  -e STEWARD_CORE_URL=http://192.168.1.10:8780 \
  -e STEWARD_WORKER_TOKEN=your-token \
  -e STEWARD_WORKER_NAME=desktop \
  -e STEWARD_WORKER_THREADS=4 \
  -v steward-models:/models \
  ghcr.io/ivamic/immich-steward-worker:0
```

On Windows (PowerShell, Docker Desktop):

```powershell
docker pull ghcr.io/ivamic/immich-steward-worker:0
docker rm -f steward-worker
docker run -d --name steward-worker --restart unless-stopped `
  -e STEWARD_CORE_URL=http://192.168.1.10:8780 `
  -e STEWARD_WORKER_TOKEN=your-token `
  -e STEWARD_WORKER_NAME=desktop `
  -e STEWARD_WORKER_THREADS=4 `
  -v steward-models:/models `
  ghcr.io/ivamic/immich-steward-worker:0
```

**A worker on a graphics card (from source).** Stop it (**Ctrl+C** in its window), check out the
new version, install it with `uv sync`, then start it as before (e.g. with
[`start-worker.cmd`](#start-the-gpu-worker-with-one-file)). Replace `0.13.1` with the version of
the app: the page **About** (the **ⓘ** icon in the header) shows it. On Windows:

```powershell
cd D:\steward-worker
git fetch --tags
git checkout v0.13.1
uv sync --python 3.12 --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra details --extra orientation --extra cuda
```

On Linux:

```sh
cd ~/steward-worker
git fetch --tags
git checkout v0.13.1
uv sync --python 3.12 --frozen --no-dev --package steward-worker --extra geoclip --extra similar --extra details --extra orientation --extra cuda
```

Don't skip `uv sync` after `git checkout`: without it the old version keeps running. A new
release may add an `--extra` (a new module): take the command from this page of the new version.

If `git checkout` says *pathspec … did not match* or `git fetch` says *refusing to merge
unrelated histories*, the folder was cloned with a short history (`--depth 1`) and fetches only
the version it was made from. Fetch the new version by its name, then go on with `uv sync` as
above. On Windows:

```powershell
cd D:\steward-worker
git fetch --depth 1 origin tag v0.13.1
git checkout v0.13.1
```

On Linux:

```sh
cd ~/steward-worker
git fetch --depth 1 origin tag v0.13.1
git checkout v0.13.1
```

## Schedule

A worker can be given the hours it works in, for example only at night on a laptop or a server that is busy during the day. On the **Processing** page, open **Schedule** on the worker and paint the hours of the week (drag across the grid): painted hours it takes jobs, the others it waits. **Always** paints every hour, **Clear** none.

- Outside its hours the worker gets no background jobs; a job it already has it finishes. What you start yourself (**Run** in a photo card, a rotation) it still takes at once.
- The hours are those of the server's clock. The window shows the time zone and the time on the server now; set [`TZ`](configuration.md#workers-the-app-side) in `.env` to your zone, otherwise the server counts in UTC.
- The schedule belongs to the worker's name: it stays after a restart or an update, and is gone if you remove the worker.

## Security

The worker token and the photos travel over plain HTTP. That is fine inside your home network or
a VPN (e.g. WireGuard), but do not connect workers to the app over the internet without HTTPS.
Anyone who has the token can get photos from the app, so keep it secret.
