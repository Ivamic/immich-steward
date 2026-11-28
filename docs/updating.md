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

Workers on other computers are updated separately, see
[Updating a worker](workers.md#updating-a-worker). A worker that must be updated shows up on the
**Processing** page.

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

To keep a version, set it in `.env`, e.g. `STEWARD_VERSION=0.14.0`; remove the line to follow new
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

The locations themselves are written to Immich and are part of your Immich backup. What lives
only in the app — the history of the locations written (and with it undo), the directions, the
"skipped" and "not applicable" marks, the photos marked as showing no place, the groups you named
or changed and their folders, the settings — goes into the app's own backups. What the modules
computed (vectors, suggestions, comparisons) is not in them: after a restore the modules compute
it again, which takes hours on a large library but loses nothing.

### Nightly backups

**Settings → Backups.** Every night the app writes a backup (a `.json.gz` file) into the folder
`backups` next to `compose.yaml` and keeps the newest of the last 7 days and of the last 4 weeks;
the hour and how many are kept are set there, and **Back up now** makes one at once. The folder
is the line `./backups:/backups` under `core` in `compose.yaml`. An installation made before
0.15.0 has an older `compose.yaml` without it; to turn nightly backups on, add it — in
`compose.yaml` or in a file `compose.override.yaml` next to it, which updates leave alone:

```yaml
services:
  core:
    volumes:
      - ./backups:/backups
```

then, in the folder of `compose.yaml`:

```sh
mkdir -p backups && sudo chown 1000:1000 backups   # the app runs as user 1000
docker compose up -d
```

Copy the folder `backups` off the server from time to time (another disk, a NAS, e.g. with
`rsync` or `rclone`): a backup on the same disk does not survive the disk.

**Download a backup** in the same place makes one at any time, also without the folder.

Keep `.env` together with the backups: the API keys of map and street-level sources are in them
encrypted with `STEWARD_SECRET_KEY` and open only with the same key.

### Restore

Into a new installation (or the same one after the database was lost):

1. Install the app and sign in with each account once; let the first sync finish.
2. Run, in the folder of `compose.yaml`:

   ```sh
   docker compose exec core python -m steward.backup restore /backups/steward-backup-2026-11-28-0300.json.gz
   ```

   With a backup that is not in `backups`, copy it into the container first:
   `docker compose cp steward-backup-….json.gz core:/tmp/` and restore `/tmp/steward-backup-….json.gz`.
   `--dry-run` says what would be added without writing anything.

The restore adds what the backup holds and the database lacks, and leaves the rest as it is;
running it again is harmless. It lists what it could not place: accounts not signed in yet,
photos not found (e.g. still in a closed locked folder). Photos kept "as they are" in the list of
turned photos wait for the orientation module: run the restore again after it has looked at the
library.

### The whole database

For a copy of everything, the computed data included:

```sh
docker compose exec db pg_dump -U steward steward > steward-backup.sql
```

Use your values of `DB_USER` and `DB_NAME` if you changed them, and keep `.env` with it.

## Uninstalling

```sh
docker compose --profile worker down       # stops the app, keeps the data
docker compose --profile worker down -v    # also deletes the database and the model cache
```

Then delete the folder of the app. The app's API key stays in your Immich account: delete
`immich-steward …` under Account Settings → API Keys. Locations and tags written to Immich stay as
they are.
