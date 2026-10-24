# Configuration

Steward on the server is configured in the file `.env`, next to `compose.yaml` in the folder of
the app. Each line is `NAME=value`; a line starting with `#` is a comment and has no effect. The
file `.env.example` lists the same settings with short explanations.

After changing `.env`, apply it:

```sh
docker compose up -d                       # without the worker
docker compose --profile worker up -d      # with the worker on the server
```

Only the settings in the first table are required; everything else has a default that suits most
homes.

## Required

| Setting | Meaning |
|---|---|
| `STEWARD_IMMICH_URL` | The address of Immich as the server sees it, e.g. `http://192.168.1.10:2283`. Not `localhost`: inside a container it means the container itself. See [Installation](install.md#the-address-of-immich). |
| `STEWARD_SECRET_KEY` | A random secret of at least 32 characters (`openssl rand -hex 32`). It encrypts the Immich API keys the app stores. Changing it signs everybody out. |
| `DB_PASSWORD` | The password of the app's database, letters and digits only (`openssl rand -hex 16`). |

## Access and Immich

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_PORT` | `8780` | The port of the web page on the server. |
| `STEWARD_IMMICH_PUBLIC_URL` | empty | The address of Immich in your browser, for the **Open in Immich** links, when it differs from `STEWARD_IMMICH_URL` (for example when that one is a container name, or Immich is published under a domain). Empty: the same as `STEWARD_IMMICH_URL`. |
| `STEWARD_COOKIE_SECURE` | `false` | Set to `true` when the app is opened over HTTPS through a reverse proxy. See [Privacy and security](privacy.md#access-from-outside-your-home-network). |
| `STEWARD_ESTIMATED_TAG` | `steward/estimated` | The Immich tag added to every location written by the app, so they can be told from the ones recorded by a camera. `a/b` creates a nested tag. Empty: no tag. |

## Map and address search

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_MAP_STYLE_URL` | OpenFreeMap Liberty | The map style ([MapLibre](https://maplibre.org) style URL). OpenFreeMap needs no account or key. |
| `STEWARD_MAP_STYLE_URL_DARK` | empty | A map style for the dark theme of the app. Empty: the map above, dimmed. |
| `STEWARD_GEOCODER_URL` | `https://photon.komoot.io` | The [Photon](https://github.com/komoot/photon) geocoder for the address search. Empty: the search field is turned off. A self-hosted Photon also works. |

## Suggestions

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_TIME_NEIGHBORS_WINDOW_HOURS` | `3` | Time neighbors: photos with a location taken up to this many hours before or after count. |
| `STEWARD_GEOCLIP_MIN_CONFIDENCE` | `0.25` | GeoCLIP suggestions below this confidence (0 to 1) are hidden. |
| `STEWARD_GEOCLIP_WEAK_BELOW` | `0.5` | GeoCLIP suggestions below this are folded as weak. |
| `STEWARD_GEOCLIP_CONFIDENT_FROM` | `0.75` | GeoCLIP suggestions from this are marked as confident and counted by the gallery filter *Confident GeoCLIP guess*. |
| `STEWARD_SIMILAR_MIN_CONFIDENCE` | `0.2` | The same three limits for similar photos. Their confidence is how often such a match turned out right within 1 km on a real family library: 0.8 means about 8 times out of 10. |
| `STEWARD_SIMILAR_WEAK_BELOW` | `0.5` | |
| `STEWARD_SIMILAR_CONFIDENT_FROM` | `0.8` | |
| `STEWARD_SIMILAR_INCLUDE_ESTIMATED` | `true` | Similar photos also searches among the photos whose location you set in the app. `false`: only among locations recorded by cameras. |

These only change what is shown: the modules keep their full results, so a change applies at once,
without running anything again.

## Workers: the app side

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_WORKER_TOKEN` | empty | The shared secret of the [workers](workers.md) (`openssl rand -hex 32`). Empty: workers are turned off. Every worker, on the server or elsewhere, must use the same value. |
| `STEWARD_AUTO_MODULES` | `geoclip,similar` | Modules that run automatically in the background on the photos without a location (similar photos also on the ones with a location: they are its search index, and go first). Empty: modules run only when started with **Run** in a photo card. |

## Worker on the server

These apply to the worker started with `docker compose --profile worker up -d`.

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_WORKER_MODULES` | `similar,geoclip` | Modules this worker runs; the photos of the first one go first (photos you start a module on from a card always go first). |
| `STEWARD_WORKER_THREADS` | `2` | CPU threads for the models. More is faster but leaves less for Immich. |
| `STEWARD_WORKER_MAX_LOAD` | empty | E.g. `0.8`: the worker waits while the server is busy (the load average per CPU is above 0.8), for instance while Immich converts videos. |
| `STEWARD_WORKER_ONE_MODEL` | `false` | `true`: one model in memory at a time. The worker then finishes one module's photos before it loads the other model; a memory limit of `4g` is enough. |
| `STEWARD_WORKER_MEMORY_LIMIT` | `6g` | The memory limit of the worker container. |

## Worker on another computer

A worker started with `docker run` or from source is configured with environment variables
(`-e NAME=value` for Docker) or with the options of the `steward-worker` command. See
[Workers](workers.md#a-worker-on-another-computer) for complete examples.

| Variable | Option | Default | Meaning |
|---|---|---|---|
| `STEWARD_CORE_URL` | `--core` | — | The address of the app, e.g. `http://192.168.1.10:8780`. Required. |
| `STEWARD_WORKER_TOKEN` | — | — | The worker token from the server's `.env`. Required. Only as a variable, so that it does not show in the list of processes. |
| `STEWARD_WORKER_NAME` | `--name` | the computer's name | The name shown on the **Processing** page. Every worker needs its own. |
| `STEWARD_WORKER_MODULES` | `--modules` | `similar,geoclip` | Modules to run; the photos of the first one go first. |
| `STEWARD_WORKER_THREADS` | `--threads` | `2` | CPU threads for the models. |
| `STEWARD_WORKER_MAX_LOAD` | `--max-load` | empty | Wait while the computer is busy (Linux only). |
| `STEWARD_WORKER_ONE_MODEL` | `--one-model` | `false` | One model in memory at a time. |
| `STEWARD_WORKER_UNLOAD_AFTER_MINUTES` | `--unload-after` | `10` | Free the memory of a model after this many minutes without work. |
| `STEWARD_WORKER_DEVICE` | `--device` | `auto` | Where the models run: `auto` (an NVIDIA graphics card when there is one), `cpu` or `cuda`. |
| `STEWARD_WORKER_ID_FILE` | `--id-file` | see the note | A file that keeps the id of the worker across restarts. In Docker: `/models/steward-worker.id`; from source: `~/.cache/steward-worker/<name>.id`. |

## Other

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_VERSION` | the version of `compose.yaml` | The version of the images to download. Set it only to stay on another release; see [Updating](updating.md#staying-on-a-version). |
| `STEWARD_LOG_LEVEL` | `info` | How much the app and the worker write to their logs: `debug`, `info`, `warning`, `error`. |
| `DB_USER`, `DB_NAME` | `steward` | The user and name of the app's database. Usually left as they are. |
| `DB_PORT`, `STEWARD_DATABASE_URL` | — | For development only (running the app outside Docker); not used by `docker compose`. |
