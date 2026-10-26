# Updating and maintenance

## Updating

A new version is announced in the app (a badge in the header, see **Settings → Updates**) and on
the [releases page](https://github.com/Ivamic/immich-steward/releases); its notes say what is new
and, under **Upgrade notes**, whether anything else is needed (usually nothing).

In the folder of the app, without the worker:

```sh
cd immich-steward
docker compose pull
docker compose up -d
```

With the worker on the server:

```sh
cd immich-steward
docker compose --profile worker pull
docker compose --profile worker up -d
```

`pull` downloads the new images, `up -d` restarts the containers with them. Database changes are
applied when the app starts. Your settings in `.env` and your data are kept.

This works because `compose.yaml` asks for the images of the **major version** (`0` now, later
`1`), not of one release, and stays the same within it: new settings get defaults in the app,
new services come as optional profiles. A change that needs more than `pull` comes only with a
new major version, and its release notes say what to do.

Workers on other computers are updated separately, see [Workers](workers.md). A worker that
must be updated shows up on the **Processing** page.

Old images take disk space; remove them afterwards with:

```sh
docker image prune
```

### Coming from 0.5 or older

Installs from before 0.6.0 were made with `git clone`, and their `compose.yaml` named one release.
Get the new `compose.yaml` once, then update as above:

```sh
cd immich-steward
curl -L -o compose.yaml https://github.com/Ivamic/immich-steward/releases/latest/download/compose.yaml
docker compose pull
docker compose up -d
```

(`git pull` does the same, if you prefer to keep the clone.) Your `.env` stays as it is. Two
things to check in it:

- A line `STEWARD_VERSION=…` keeps the old version: remove it.
- If you changed `compose.yaml` itself, move those changes into a file `compose.override.yaml`
  next to it, which Docker Compose reads automatically and an update never touches.

### Staying on a version

To keep a version, set it in `.env`, e.g. `STEWARD_VERSION=0.6.0`; remove the line to follow new
releases again. `docker compose pull` then keeps that version.

### Updating by itself

Tools such as Watchtower can run `docker compose pull` for you. It works, since the image tag
follows the major version, but we suggest updating by hand and reading the release notes first:
the app is at an early stage.

## Building the images from source

Instead of downloading the images, you can build them from a copy of the source (a few minutes,
about 2 GB of disk space during the build, internet access for the packages). In a clone of the
repository, with your `.env` next to `compose.yaml`:

```sh
git clone https://github.com/Ivamic/immich-steward.git
cd immich-steward
```

Without the worker:

```sh
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

With the worker:

```sh
docker compose -f compose.yaml -f compose.build.yaml --profile worker up -d --build
```

This is also the way to run the worker on `arm64` for now. The images built this way get the same
names as the published ones; `docker compose pull` replaces them with the published images again.

## Backup

The app's own data (accounts, encrypted API keys, the history of written locations, "skipped"
and "not applicable" marks, the results of the modules) lives in the Docker volume
`immich-steward_db-data`. The coordinates themselves are stored in Immich, so they are part of
your Immich backup.

Make a copy of the app's database:

```sh
docker compose exec db pg_dump -U steward steward > steward-backup.sql
```

Use your values of `DB_USER` and `DB_NAME` if you changed them. Keep `.env` together with the
backup: without the same `STEWARD_SECRET_KEY` the stored API keys cannot be decrypted (users would
simply sign in again).

Losing this database is not a disaster: the locations written to Immich stay there. You would
lose the history (and with it undo), the skipped and not applicable marks, and the modules would
process the photos again.

## Uninstalling

```sh
docker compose --profile worker down       # stops the app, keeps the data
docker compose --profile worker down -v    # also deletes the database and the model cache
```

Then delete the folder of the app. The app's API key stays in your Immich account: delete
`immich-steward …` under Account Settings → API Keys. Locations and tags written to Immich stay as
they are.
