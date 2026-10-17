# Installing immich-steward on your server

> **The project is under active development.** Things may break or change between versions.
> The app writes to Immich only when you save a location, and every write can be undone, but
> keep a backup of your Immich library anyway.

immich-steward runs as two Docker containers: the app itself (API and web UI) and a
PostgreSQL database with pgvector. Ready-made images are not published yet, so the app image is
built from source on your server. It takes a few minutes the first time.

## Requirements

- A Linux machine with [Docker Engine](https://docs.docker.com/engine/install/) and the
  Compose plugin (`docker compose version` prints v2.x). Usually the same machine as Immich.
- Immich **v3.x**, reachable from that machine over the network.
- Internet access during the build (packages are downloaded) and in your browser (the map is
  loaded from OpenFreeMap).
- About 2 GB of free disk space for the build; the running app needs a few hundred MB of RAM.

## 1. Get the code

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

## 3. Build and start

```sh
docker compose up -d --build
```

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
- **Photos never leave your server.** The current location suggestions (photos taken close in
  time) are computed from your own library.

## Updating

```sh
cd immich-steward
git pull
docker compose up -d --build
```

Old image layers can be removed afterwards with `docker image prune`.

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
docker compose down       # stops the app, keeps the data
docker compose down -v    # also deletes the database volume
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

**`core` is `unhealthy` or restarting.** See `docker compose logs core`. A missing
`STEWARD_IMMICH_URL`, `STEWARD_SECRET_KEY` or `DB_PASSWORD` is reported when the containers
start.

**Password sign-in is refused although the password is right.** Password login may be turned
off on your Immich server (OAuth only). Sign in with an API key instead.

**The map stays empty.** Your browser needs access to `tiles.openfreemap.org`.
