# Installation

This page installs Steward on the server where Immich runs, step by step. It takes about 15
minutes. If you already know Docker Compose, the [short version](#short-version) is at the end.

Steward runs as two Docker containers: the app itself (the web page and its API) and a
PostgreSQL database. A third, optional one, the [worker](workers.md), runs the modules that are
neural networks; you can add it later. The images are ready-made and downloaded from GitHub
Container Registry (`ghcr.io/ivamic/immich-steward-core` for `amd64` and `arm64`,
`ghcr.io/ivamic/immich-steward-worker` for `amd64`); you can also
[build them yourself](updating.md#building-the-images-from-source).

## What you need

- **A Linux server with Docker.** Usually the machine where Immich runs. Check that Docker and
  its Compose plugin are installed: `docker compose version` should print `v2.x` or newer. If it
  doesn't, install [Docker Engine](https://docs.docker.com/engine/install/) first.
- **Immich v3.x**, reachable from that server over the network.
- **Internet access** on the server (to download the images) and in your browser (the map is
  loaded from OpenFreeMap).
- **Disk space and memory:** about 1 GB for the app; a few GB more for the database of a big
  library (similar photos keep 17 KB per photo); another 4 GB if you add the worker. The app
  itself needs a few hundred MB of RAM.

All commands below are typed in a terminal on the server (for example over SSH).

## 1. Download the app

```sh
git clone https://github.com/Ivamic/immich-steward.git
cd immich-steward
```

This creates the folder `immich-steward` with `compose.yaml` (which containers to start) and
`.env.example` (an example of the settings). All later commands are run in this folder.

No `git`? Install it with `sudo apt install git` (Debian, Ubuntu) or your system's package
manager.

## 2. Configure

Make your own settings file from the example and open it in a text editor:

```sh
cp .env.example .env
nano .env
```

(In `nano`, save with **Ctrl+O**, Enter, and quit with **Ctrl+X**.)

Set at least these four values:

| Setting | What to put there |
|---|---|
| `STEWARD_IMMICH_URL` | The address of Immich **as the server sees it**, e.g. `http://192.168.1.10:2283`. Do not use `localhost`: inside a container it means the container itself. See [how to find the address](#the-address-of-immich). |
| `STEWARD_SECRET_KEY` | A random secret of at least 32 characters. It encrypts the Immich keys the app stores. Make one with `openssl rand -hex 32` and paste the output. Keep it: changing it later signs everybody out. |
| `DB_PASSWORD` | The database password, letters and digits only. Make one with `openssl rand -hex 16`. |
| `STEWARD_PORT` | The port of the web page on the server, `8780` by default. Change it only if that port is taken. |

All other settings are optional; [Configuration](configuration.md) explains each of them. The
lines at the end under "Development only" are not used by Docker and can stay as they are.

### The address of Immich

Use the address of the server in your home network and the port of Immich (`2283` unless you
changed it), the same address you would type in a browser on another computer. To find the
server's address:

```sh
hostname -I
```

The first number, e.g. `192.168.1.10`, is usually the one. Check it from the server:
`curl http://192.168.1.10:2283/api/server/version` should print the Immich version.

**Immich on the same server, in its own Docker Compose project** (the usual case): the address
above works. Alternatively you can connect Steward to Immich's Docker network and use the name of
the Immich container. Create a file `compose.override.yaml` next to `compose.yaml`:

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
Immich with, for the **Open in Immich** links in the photo card, e.g.
`STEWARD_IMMICH_PUBLIC_URL=http://192.168.1.10:2283`.

## 3. Start

```sh
docker compose up -d
```

The first start downloads the images, which takes a minute or two. `-d` keeps the app running
in the background after you close the terminal; it also starts again after a reboot.

Check that it runs:

```sh
docker compose ps
```

Both containers, `core` and `db`, should be listed; after about half a minute `core` shows
`healthy`. If it shows `unhealthy` or keeps restarting, see
[Troubleshooting](troubleshooting.md#core-is-unhealthy-or-restarting).

## 4. Sign in

Open `http://<address of the server>:8780` in your browser, e.g. `http://192.168.1.10:8780`, and
sign in with your **Immich email and password**.

- The password is checked by Immich and is not stored. On the first sign-in the app creates an
  API key named `immich-steward …` in your Immich account and keeps it encrypted; later sign-ins
  reuse it.
- If you sign in to Immich through OAuth and have no password, use **Sign in with an API key
  instead**: create a key in Immich (Account Settings → API Keys) with the permissions listed on
  the sign-in page.
- Every member of the family signs in with their own Immich account and sees only their own
  library.

Within a minute after the first sign-in the app reads your library from Immich (a few seconds
for thousands of photos; the **Processing** page has a button to start it right away). After
that it checks Immich for changes every 15 minutes.

Nothing is written to Immich until you save a location for a photo. Saved locations get the tag
`steward/estimated` in Immich, so you can always find them there.

## What next

- [Using the app](usage.md): the gallery, the photo card and the keyboard keys.
- [Workers](workers.md): turn on GeoCLIP and similar photos. Without a worker the app suggests
  places from the photos taken shortly before and after (time neighbors) and lets you pick a
  point on the map or search an address.
- [Updating](updating.md): how to get new versions.

## Short version

```sh
git clone https://github.com/Ivamic/immich-steward.git
cd immich-steward
cp .env.example .env      # set STEWARD_IMMICH_URL, STEWARD_SECRET_KEY and DB_PASSWORD
docker compose up -d
```

Then open `http://<your-server>:8780`. For the worker, set `STEWARD_WORKER_TOKEN` and start with
`docker compose --profile worker up -d` (see [Workers](workers.md)).
