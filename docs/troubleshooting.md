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

Your `compose.yaml` is from version 0.2.1 or older, which only built the images locally. Get the
current one as described in [Coming from 0.5 or older](updating.md#coming-from-05-or-older).

### "The database was updated by a newer version of Steward"

The app stops with this message when an older version starts on a database that a newer one has
already changed, usually because `.env` names an older version (`STEWARD_VERSION=…`). Remove that
line, or set the newer version, then run `docker compose pull` and `docker compose up -d`.

### Unknown settings in the log

`docker compose logs core` warns about `STEWARD_…` names in `.env` that the app does not know: a
typo, or a setting that was renamed (the warning then says the new name). The app ignores them, so
fix the name for the setting to have an effect.

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

### The Map page shows no photos

It shows the photos with a location only, under its filters (type, camera, album, period): reset
the filters, or zoom out. Photos get their location from Immich after a sync.

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
Also look at the switches of the module on the **Processing** page: a worker with the module
turned off takes none of its jobs.

### A photo card says that no worker runs the module

No worker that runs this module is connected right now, or the module is turned off for the
connected ones on the **Processing** page. Start one (see [Workers](workers.md)) or turn the module
on; the run waits in the queue until then.

### A video does not play

The app plays the video Immich plays in its own web app: its encoded version when Immich made
one, otherwise the original. If a video plays in Immich but not here, open an issue. If it plays
in neither, the browser cannot decode it (e.g. HEVC from an iPhone in some browsers): have Immich
encode such videos (Immich: **Administration → Settings → Video transcoding**, the transcode
policy).

### Some photos failed in a module

The **Processing** page lists the failed photos of each module by reason. **Show** opens them in
the gallery (the photo card has a link to open the photo in Immich), and **Run again** queues them
once more, e.g. after fixing a file in Immich. "Immich could not give the photo" usually means a
broken or unsupported file: Immich cannot make its preview either.

## Groups

### The Groups page is empty, or only shows progress

Groups appear once the photos have been compared with each other. The first pass takes about 40 ms
per photo, more than an hour for 100 000 photos, and goes on in the background; the page shows how far
it got. Only photos with a vector take part: without a [worker](workers.md) running **Similar photos**
there are no groups. See [Groups](usage.md#groups).

### "This group no longer exists"

Groups are built again in the background. A group goes when none of its photos are found together any
more, for example when you took all of them out. Go back to the list: its photos are in other groups,
or in none. A group whose photos are all marked as showing no sign of a place stays, under the view
**No sign of a place**.

### Search by description says that smart search is off

*Maybe no sign of a place → By description* uses the smart search of Immich. Turn on machine
learning and smart search in Immich (Administration → Settings → Machine Learning) and let Immich
process the library; the other tab, **Alike but far apart**, works without it.

### The app marks too many photos with "no sign of a place"

In **No sign of a place → Marked by the app**, bring back what does show the place: the app does not
mark those photos again. **Settings → Groups** sets how alike a photo must be to your marks (higher
gives fewer marks), or turns the marks of the app off; they then go at the next rebuild.

### A place set from a group is wrong

**Undo** in the notice of the save, or in the card of a photo, puts back what the photos had. The spot
of a group comes from photos with a location; if those are wrong, it is wrong too. **Apart from the main
spot** and **Spread out on the map** help to find them.

## The locked folder

### "Immich refused password sign-in"

Connecting the [locked folder](usage.md#the-locked-folder) needs a password sign-in to Immich: Immich
opens the folder only to a signed-in session, never to an API key. If your Immich allows OAuth only
(*Administration → Settings → Authentication*), the folder cannot be connected.

### "Wrong PIN code" or a pause after several tries

It is the PIN code of Immich (*Account settings → PIN code*), not your password. After 5 wrong codes
in a row the app waits 5 minutes before the next try; Immich itself does not limit them.

### "Connect the locked folder again"

Immich ended the session of the app: your password changed, or the device *Steward* was removed in
Immich (*Account settings → Authorized devices*). Connect the folder again in **Settings → Locked
folder**.

### The folder closes by itself

That is meant: after `STEWARD_LOCKED_IDLE_MINUTES` (15) without a click or key press in the app, and
when you sign out. While workers have its photos it stays open, up to an hour. A longer time can be
set in `.env` ([Configuration](configuration.md#access-and-immich)), up to 60 minutes.

### Photos moved into the locked folder still show in the gallery

Until the folder is connected and opened, or until the daily full sync, the app may still take them
for timeline photos; the first time it fails to get such a photo's image it hides it. A full sync
(**Full sync** on the **Processing** page) sets everything right at once.

## Still stuck?

Open an [issue](https://github.com/Ivamic/immich-steward/issues) with the versions of Steward and
Immich, what you did and what you saw, and the relevant lines of the logs (remove addresses and
names you don't want to share).
