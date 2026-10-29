# Configuration

Steward on the server is configured in the file `.env`, next to `compose.yaml` in the folder of
the app. Each line is `NAME=value`; a line starting with `#` is a comment and has no effect. The
file `example.env` (`.env.example` in the source) lists the same settings with short
explanations.

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

## Satellite imagery (in Settings)

Satellite imagery is set up in the app, not in `.env`: **Settings → Map sources**. Each family
member has their own sources and keys. Everything is off until switched on; switching a source on
means accepting the provider's terms (a short summary and a link are next to the switch). Keys are
stored encrypted with `STEWARD_SECRET_KEY` and shown masked; changing that secret makes them
unreadable, so they would have to be entered again.

| Source | Key | Free | Note |
|---|---|---|---|
| Sentinel-2 cloudless (EOX) | none | non-commercial use | 10 m per pixel, a layer per year (2016–2025) |
| Esri World Imagery | ArcGIS Location Platform | 2 million tiles a month | without pay-as-you-go the access closes until the next month, no bill |
| MapTiler Satellite | MapTiler Cloud | 100,000 requests a month, non-commercial | the service pauses until the next month; the MapTiler logo is shown on the map |

The browser loads the tiles straight from the provider, so **the key is visible in the browser**.
Restrict it to the address you open the app at (below, `http://192.168.1.10:8080` stands for
it), so that nobody else can use it.

### Esri World Imagery key

1. Create an account at [ArcGIS Location Platform](https://location.arcgis.com/) (an ArcGIS
   Online account does not work). No payment method is needed.
2. Open **Developer credentials → New developer credential**, type **API key**.
3. Where it is used: **Public application** (access to ArcGIS Location Services). Not one of the
   private applications: their tokens act with the rights of your account and must not reach a
   browser.
4. Item access: **No item access**.
5. Privileges: **Location services → Basemaps**, nothing else.
6. Expiration: the latest date allowed (one year ahead). Note it down: on that day the key stops
   working and a new one is needed. The tiles of Esri may still load with an expired key, but
   **Check** in the settings will say the key is not accepted.
7. Referrer URLs: the address you open the app at, exactly as in the address bar of the browser,
   for example `http://192.168.1.10:8080`; add each address you use (home network, VPN, a host
   name).
8. Item details: any title, e.g. `Steward for Immich — World Imagery`, and the expiration date in
   the summary to find it again in a year.
9. Copy the key, paste it in **Settings → Map sources → Esri World Imagery → Key**, press
   **Save**, then switch the source on. Save it from the address added in step 7: the app checks
   the key as from there.

Esri counts its month from the day your account's billing started; set that day in **Reset
monthly on day**, so that the count of the app starts anew with Esri's.

**How much is used.** Esri's own numbers are on the **Usage** page of Location Platform
(**Check your limits** in Settings opens it): **All services → Mapping → Basemap tiles** shows the
tiles of the current billing cycle and the share of the free tier used; the **Developer
credentials** tab shows them per key. The latest hours may come later. Esri gives no way for the
app to read these numbers, so Settings shows only the tiles the app itself loaded.

**Over the free 2 million tiles.** Pay-as-you-go is off for a new account and can be turned on
only with a payment method. While it is off there is **no bill**: Esri closes the access to the
basemaps until the next billing cycle, and the app moves to the next source. If you turn
pay-as-you-go on, there is no spending cap: tiles over the free amount cost $0.15 per 1,000.

**When the key expires**, create a new one the same way and save it in Settings.

### MapTiler Satellite key

1. Create an account at [MapTiler Cloud](https://cloud.maptiler.com/) (the free plan is enough
   for non-commercial use).
2. Open **Account → API keys → New key** and fill in the form:
   - **Name**: any, for example `immich-steward`.
   - **Description**: optional, for example `Satellite tiles for immich-steward`.
   - **Allowed user-agent header**: leave it empty. The tiles are loaded by your browser, and
     every browser sends its own user-agent.
   - **Allowed HTTP Origins**: the address of the app from your browser's address bar while the
     app is open, as host and port only: without `http://` or `https://` and without a path
     (MapTiler does not accept an origin with the scheme). The key then works only from there.
     If you open the app by IP address:

     ```
     192.168.1.10:8080
     ```

     If you open it in several ways (IP address, host name, VPN), put each on its own line:

     ```
     192.168.1.10:8080
     homeserver.local:8080
     ```

     Do not add the `?` placeholder: it lets through requests without an origin.
3. Press **Create**. If the app later says MapTiler refused the key, check that the origin
   has the same host and port as the address bar and no `http://` in front.
4. Copy the key, paste it in **Settings → Map sources → MapTiler Satellite → Key**, press
   **Save**, then switch the source on.

**How much is used.** MapTiler shows it on its
[Analytics](https://cloud.maptiler.com/account/analytics) page (also **Check your limits** next to
the source in Settings), per day: today's requests appear only the next day, so a new key shows 0
at first. On the free
plan the service pauses when the monthly requests are used up, until the next month; there is
no bill. With MapLibre every tile counts as a request: map sessions apply only to MapTiler's own
SDK.

Optionally, the exact usage can come from MapTiler: create a service token at **Account →
Credentials** and paste it under **Exact usage from MapTiler**. The token gives full access to
the MapTiler account; it stays on the app server, is never sent to the browser and is used only
to read the usage, at most every three hours or when **Refresh** is pressed.

### Switching by zoom

Under **Settings → Map sources → Switch by zoom** choose what the map shows far out (**Far**),
close up (**Close**) and the zoom at which it switches. Each can be the plain map or any source
that is on, for example the plain map far out and MapTiler from zoom 14. **Auto** over the map
turns the switching on; next to it the bar shows the choice (the part shown now in bold), and
the gear opens these settings.

What a zoom shows: 10 — a whole city, 12 — districts, 14 — streets are seen, 16 — single houses
stand apart, 18 — yards, cars and trees. Sentinel-2 (10 m per pixel) gets blurry past about 14;
Esri and MapTiler stay sharp much further.

### What the app counts

The app counts the tiles your browser loads for each source ("loaded by us"). It does not know
about other apps that use the same key, and tiles from the browser cache are counted too, so it is
only a rough estimate: the provider counts in its own way and its numbers may differ (for Esri,
for example, the app may count more). The exact usage is on the provider's own page (**Check your
limits** next to the source). A percentage of the limit is shown only when the provider tells the
usage (MapTiler with a service token). When a provider refuses the key or closes the access, the
source is marked in Settings and over the map, and **Auto** takes the next source.

## Suggestions

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_TIME_NEIGHBORS_WINDOW_HOURS` | `3` | Time neighbors: photos with a location taken up to this many hours before or after count. |
| `STEWARD_TIME_NEIGHBORS_NEARBY_MINUTES` | `15` | The gallery marks a photo without a location when a photo with one was taken up to this many minutes before or after (the clock badge and the *Located photo nearby* filter). |
| `STEWARD_GEOCLIP_MIN_CONFIDENCE` | `0.25` | GeoCLIP suggestions below this confidence (0 to 1) are hidden. |
| `STEWARD_GEOCLIP_WEAK_BELOW` | `0.5` | GeoCLIP suggestions below this are folded as weak. |
| `STEWARD_GEOCLIP_CONFIDENT_FROM` | `0.75` | GeoCLIP suggestions from this are marked as confident and counted by the gallery filter *Confident GeoCLIP guess*. |
| `STEWARD_SIMILAR_MIN_CONFIDENCE` | `0.2` | The same three limits for similar photos. Their confidence is how often such a match turned out right within 1 km on a real family library: 0.8 means about 8 times out of 10. |
| `STEWARD_SIMILAR_WEAK_BELOW` | `0.5` | |
| `STEWARD_SIMILAR_CONFIDENT_FROM` | `0.8` | Also the limit of the purple badge and the gallery filter *Similar photo with a location*. |
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

## Updates (in Settings)

Whether the app looks for a newer release is set in the app, not in `.env`: **Settings → Updates**,
for the whole installation. It is on by default: twice a day the server asks GitHub for the number
of the latest release (see [Privacy](privacy.md#what-leaves-your-server)), and a newer one shows up
in the header with a link to what is new. **Check now** asks at once, also while the check is off.

## Other

| Setting | Default | Meaning |
|---|---|---|
| `STEWARD_VERSION` | `0` (the newest 0.x release) | The version of the images to download. Set an exact one only to stay on it; see [Updating](updating.md#staying-on-a-version). |
| `STEWARD_LOG_LEVEL` | `info` | How much the app and the worker write to their logs: `debug`, `info`, `warning`, `error`. |
| `DB_USER`, `DB_NAME` | `steward` | The user and name of the app's database. Usually left as they are. |
| `DB_PORT`, `STEWARD_DATABASE_URL` | — | For development only (running the app outside Docker); not used by `docker compose`. |
