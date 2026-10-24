# Updating and maintenance

## Updating

A new version is announced on the [releases page](https://github.com/Ivamic/immich-steward/releases);
the [changelog](../CHANGELOG.md) says what is new and whether `.env` needs new settings.

In the folder of the app, without the worker:

```sh
cd immich-steward
git pull
docker compose pull
docker compose up -d
```

With the worker on the server:

```sh
cd immich-steward
git pull
docker compose --profile worker pull
docker compose --profile worker up -d
```

What each line does: `git pull` gets the new `compose.yaml`, which names the new version of the
images; `pull` downloads the images; `up -d` restarts the containers with them. Database changes
are applied automatically when the app starts. Your settings in `.env` and your data are kept.

Don't skip `git pull`: `compose.yaml` names the version of the images, so `docker compose pull`
alone downloads the version you already have. The version is fixed on purpose: a new version may
need changes in `compose.yaml` itself (new settings, services or volumes), and updating both
together keeps them in step.

Workers on other computers are updated separately, see [Workers](workers.md).

Old images take disk space; remove them afterwards with:

```sh
docker image prune
```

### If `git pull` stops with a conflict

This happens when you changed `compose.yaml` yourself. Put your changes into `.env` or into a
file `compose.override.yaml` next to it, which Docker Compose reads automatically and `git pull`
doesn't touch. Then undo your changes to `compose.yaml` (`git checkout compose.yaml`) and run
`git pull` again.

### Staying on a version

To keep a version while `compose.yaml` moves on, set it in `.env`, e.g. `STEWARD_VERSION=0.4.0`.

`STEWARD_VERSION=latest` (or `0.4` for the newest 0.4.x) makes `docker compose pull` fetch new
images without `git pull`. We don't recommend it while the project is at an early stage: a new
image may need a newer `compose.yaml` than the one you have, and the app may fail to start.

## Building the images from source

Instead of downloading the images, you can build them on your server (a few minutes, about 2 GB
of disk space during the build, internet access for the packages). Add `--build` to the start
command.

Without the worker:

```sh
docker compose up -d --build
```

With the worker:

```sh
docker compose --profile worker up -d --build
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
