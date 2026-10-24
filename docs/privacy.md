# Privacy and security

## What leaves your server

- **Photos never leave your server** (or your home network, when a worker runs on another
  computer). Location suggestions are computed from your own library and by local models.
- **Map tiles** are loaded by your browser from OpenFreeMap (no account, no key): it sees which
  part of the map you look at. Another tile server can be set with `STEWARD_MAP_STYLE_URL`.
- **Address search** sends the typed text and the approximate map position from the app server to
  the public Photon geocoder (`photon.komoot.io`). Set `STEWARD_GEOCODER_URL=` (empty) to turn the
  search off, or point it to your own Photon.
- **The models** of GeoCLIP and of similar photos (MegaLoc) are downloaded from Hugging Face
  (`huggingface.co`) when a worker loads them for the first time; later loads only check for
  updates there.
- The **fonts and icons** of the web page come with the app; nothing else is loaded from other
  sites.

Modules that send a photo to an outside service may be added in the future. They will never run
on their own: you will start them for a photo yourself, and the app will show what is sent and
where.

## What the app writes to Immich

Only what you save: the location of a photo (and the tag `steward/estimated`), and the rotation
of a photo when you press **Save rotation in Immich**. Every location write is kept in the
history of the photo and can be undone.

## Your Immich password and API key

When you sign in with your Immich email and password, the password goes through the app to
Immich and is not stored. The app creates its own API key in your Immich account and keeps it
encrypted with `STEWARD_SECRET_KEY`; the key is never sent back to the browser. Each family
member's key gives access only to their own library.

## Access from outside your home network

The app has no protection of its own beyond the Immich sign-in. Keep it inside your home network
or a VPN (e.g. WireGuard, Tailscale). If you publish it on the internet, do so only through a
reverse proxy with HTTPS (the Immich password passes through the app when you sign in), and set
`STEWARD_COOKIE_SECURE=true` in `.env`.

## Workers

The worker token and the photos travel between the app and the workers over plain HTTP. That is
fine inside your home network or a VPN, but do not connect workers to the app over the internet
without HTTPS. Anyone who has the token can get photos from the app, so keep it secret.
