# Troubleshooting

The logs of the app usually tell what is wrong. In the folder of the app:

```sh
docker compose logs --tail 50 core      # the app
docker compose logs --tail 50 worker    # the worker on the server
```

## Installation and start

### `core` is `unhealthy` or restarting

See `docker compose logs core`. A missing `STEWARD_IMMICH_URL`, `STEWARD_SECRET_KEY` or
`DB_PASSWORD` is reported when the containers start: set them in `.env` (see
[Installation](install.md#2-configure)) and run `docker compose up -d` again.

### "The Immich server does not respond"

Check the connection from inside the app container:

```sh
docker compose exec core python -c "import os, urllib.request; print(urllib.request.urlopen(os.environ['STEWARD_IMMICH_URL'] + '/api/server/version', timeout=5).read())"
```

If this fails while Immich opens fine in your browser:

- `STEWARD_IMMICH_URL` uses `localhost` or `127.0.0.1`: use the address of the server in your
  home network instead (see [Installation](install.md#the-address-of-immich)).
- A firewall on the server blocks the Immich port for Docker networks.
- A Docker network overlaps your home network (for example both use `192.168.0.0/20`): compare
  `docker network inspect immich-steward_default` with your network and, if needed, set
  `default-address-pools` in `/etc/docker/daemon.json`.
- Docker Desktop (Windows, macOS) sometimes cannot reach devices of the local network; a Linux
  server is the intended setup.

### `pull access denied for immich-steward-core`

Your `compose.yaml` is from version 0.2.1 or older, which only built the images locally. Run
`git pull` to get the current one, or build with `docker compose up -d --build`.

## Signing in

### Password sign-in is refused although the password is right

Password login may be turned off on your Immich server (OAuth only). Sign in with an API key
instead: **Sign in with an API key instead** on the sign-in page lists the permissions the key
needs.

### "Save rotation in Immich" fails

The app's API key lacks the permissions `asset.edit.get`, `asset.edit.create` and
`asset.edit.delete`. Keys created by an app older than 0.3.0 don't have them: add them in Immich
(Account Settings → API Keys → edit the key `immich-steward …`).

## The map and the address search

### The map stays empty

Your browser needs access to `tiles.openfreemap.org` (or to the tile server set in
`STEWARD_MAP_STYLE_URL`).

### The address search finds nothing

The app server needs access to `photon.komoot.io` (or to the geocoder set in
`STEWARD_GEOCODER_URL`). An empty `STEWARD_GEOCODER_URL` turns the search off.

## Workers and modules

### The GeoCLIP or similar photos queue grows, but nothing is done

On its first start the worker downloads and loads the models, which takes a few minutes. The
**Processing** page shows what each worker is doing: downloading the model, loading it into memory
(with the time so far), working, or waiting for jobs; it also shows when background runs are
paused. Look at `docker compose logs --tail 40 worker`: `GeoCLIP loaded` and then `done in … s`
lines mean it works. An error there (out of memory, no access to `huggingface.co`) tells what is
wrong.

A worker on another computer: see the [table of log messages](workers.md#check-that-it-works).

### A photo card says that no worker runs the module

No worker that runs this module is connected right now. Start one (see [Workers](workers.md)); the
run waits in the queue until then.

### Some photos failed in a module

The **Processing** page lists the failed photos of each module by reason. **Show** opens them in
the gallery (the photo card has a link to open the photo in Immich), and **Run again** queues them
once more, e.g. after fixing a file in Immich. "Immich could not give the photo" usually means a
broken or unsupported file: Immich cannot make its preview either.

## Still stuck?

Open an [issue](https://github.com/Ivamic/immich-steward/issues) with the versions of Steward and
Immich, what you did and what you saw, and the relevant lines of the logs (remove addresses and
names you don't want to share).
