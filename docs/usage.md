# Using the app

This page shows how to go through your photos without a location: find them in the gallery,
look at the suggestions in the photo card, and save the right place. The app is made to be used
mostly with the keyboard, but everything works with the mouse too.

The pages are at the top: **Gallery**, **Processing** and **Settings**. On the right are the
language and the theme (light, dark, or as in your system).

## The gallery

The gallery shows your photos by month, newest first. By default it shows the photos
**without a location**: your to-do list.

- **Filters** are the row of buttons at the top. Which photos to show: *Without location*,
  *With location*, *Skipped*, *Not applicable* (several can be on at once). *Confident GeoCLIP
  guess* leaves the photos for which GeoCLIP is fairly sure where they were taken; *Located
  photo nearby* leaves the photos taken within 15 minutes of a photo with a location, whose place
  is almost surely known. Both are a good place to start. Then the type (photos, videos), the camera, the album, the **Period** and the
  **Processing errors** of the modules. *Reset* brings the default filters back.
- **Badges** in the corner of a photo: a pin means the photo has a location; a blue clock means
  a photo with a location was taken within 15 minutes, filled when by the same camera (the
  stronger hint) and outlined when by another one, such as a phone; an orange crosshair means
  GeoCLIP has a confident guess for it; a play sign marks a video. The 15 minutes are a setting
  (`STEWARD_TIME_NEIGHBORS_NEARBY_MINUTES`).
- **The timeline** on the right shows the years. Click or drag on it to jump to a month.
- Click a photo to open its card. When you come back, the gallery opens at the same place.

The filter is kept in the address of the page, so a filtered view can be bookmarked.

### Several photos at once

Hover a photo and click the circle in its top left corner to choose it. While some photos are
chosen, a click on another photo chooses it too instead of opening it; **Shift** + click chooses
everything from the photo clicked before (for example a series taken in a row). **Esc** or the
cross in the bar clears the choice.

A bar at the bottom shows how many photos are chosen (how many of them already have a location,
how many are videos) and what can be done with all of them:

- **Set location** opens a map like the one in the photo card: click the map, type coordinates,
  search an address, or pick a suggestion (keys **1–9**, **Enter** saves). The suggestions come
  only from what the app already knows, so they appear at once for any number of photos:
  - the places of the chosen photos that already have a location (several close to each other
    are one suggestion, "4 of the chosen photos are here");
  - the photos with a location taken just before the first chosen photo and just after the
    last one;
  - the **confident** results of the modules that already ran on the chosen photos; the same
    place for several photos is one suggestion, "for 3 photos". Nothing is run for this.

  Photos that already have a location keep it, unless you tick **Overwrite it also on the … that
  already have a location**: then the dialog is a tool to correct a wrong place on many photos.
  The save waits a few seconds, as in the card, and can be cancelled. Once saved, **Undo** in its
  notice puts back what each photo had before, except for photos whose location was changed
  since (in Immich or here).
- **Rotate left**, **Rotate right**, **Rotate 180°** turn the chosen photos in Immich, as **Save
  rotation in Immich** in the card does (an Immich edit; the original file is not changed). It runs
  in the background with its progress in a notice; you can go on working. The photos being turned
  are dimmed with a spinner in the gallery, as are the photos whose location is being saved (a
  clock while the save can still be cancelled). Videos are not turned:
  the notice says how many were left out. The API key needs the `asset.edit` permissions.
- **Skip for now** and **Location not applicable** mark all the chosen photos.

## The photo card

The card has three columns: the **map** on the left, the **panel** with the actions and the
suggestions in the middle, and the **photo** with its details on the right. On a narrow screen
the panel and the details share one column with tabs.

### Choose the place

There are several ways to put a point on the map:

- **Choose a suggestion**: the **Choose** button of a suggestion, or its number key **1** to
  **9**.
- **Click the map.** Drag the point to correct it.
- **Search an address or a place** in the search field (e.g. "Kotor, old town").
- **Type coordinates** in the coordinates field, e.g. `42.4249, 18.7713` (latitude, longitude),
  and press Enter.

The picked point is a pin with a green dot. The grey pin is the location the photo already has
in Immich, if any.

**Copying coordinates.** The copy button in the coordinates field copies the picked point, and
the one next to the location in the details copies the location the photo already has, e.g. to
paste it into the field of another photo or into a map site. It also works when the app is
opened over plain `http://`; if the browser still refuses, the coordinates are selected and Ctrl+C
copies them.

### Satellite imagery

Three satellite sources can be connected, each off until you switch it on:

- **Sentinel-2 cloudless** by EOX: no key, 10 m per pixel, a layer per year (2016–2025).
- **Esri World Imagery**: sharp (1 m or better), with your own free ArcGIS Location Platform key.
- **MapTiler Satellite**: sharp, with your own free MapTiler Cloud key (non-commercial use).

How to get the keys and switch the sources on:
[Configuration → Satellite imagery](configuration.md#satellite-imagery-in-settings).

Once a satellite source is switched on in **Settings → Map sources**, a bar above the map
chooses the **base map**: the plain **Map** (the default) or a satellite source (for Sentinel-2
also the year; the latest is shown first). Sources that cannot be used are greyed out; hover them
for the reason (no key, key not accepted, limit used up).

- **Auto** on the right of the bar shows whether the base map switches by itself. When on, the
  map shows the "far" source when zoomed out and the "near" one from the zoom set in Settings
  (by default Sentinel-2 up to zoom 13, Esri or MapTiler from 14), and the bar highlights the
  source shown now. This saves the limited tiles of the sharper sources. A source that does not
  work is skipped for the next one. Choosing a base map by hand turns Auto off. Before **Auto**
  the bar shows the current zoom and what Auto switches between ("Zoom 15 · Map → MapTiler from
  zoom 14"); hover them for what a zoom level shows. The gear after it opens these settings.
- **Labels over imagery** keeps the names of places, streets and water over the photo. Buildings,
  bridges, borders and the icons of shops and the like are not drawn over imagery.

- **Heat map** colors the map where your photos with a location are, in violet: the more photos,
  the brighter. When you know there are already many photos of a place, it helps to find it on
  the map quickly. It is off until you turn it on, and is in the bar over every map, also
  without satellite sources. Only your own photos count, the filters of the gallery do not
  apply.

- **Areas** sets how the circles of the suggestions are drawn: **Fill** (tinted, as by
  default), **Outline** (only the border, so the imagery under it stays clear) or **None**. It is
  in the bar whenever the map has such circles, also without satellite sources.

The choice is remembered in the browser. In the dark theme the imagery is not dimmed.

### Save, skip or mark as not applicable

| Button | Key | What it does |
|---|---|---|
| **Save location** | Enter | Writes the point to Immich and opens the next photo. |
| **Skip for now** | S | Moves the photo out of the to-do list into *Skipped*; you can come back to it later. |
| **Location not applicable** | N | For photos where a place makes no sense: documents, screenshots, close-ups. They never come back to the to-do list. |
| **Back to the to-do list** | U | For a skipped or not applicable photo: puts it back. |

**Saving can be cancelled.** After you save, a notice in the bottom left corner counts down a few
seconds before the location is written to Immich; **Cancel** stops it. After it is written, the
notice offers **Undo**, and the card keeps a **Location history** with an **Undo the last change**
button. Undo puts back the location the photo had before (or none).

Every location the app writes gets the tag `steward/estimated` in Immich, so you can always tell
them from the ones recorded by a camera.

### Suggestions

Below the actions the modules list where they think the photo was taken. Every module has its
own color and marker shape on the map, and the suggestions are numbered across all of them: the
number on the map, in the list and the key are the same.

- **Time neighbors** (blue circles): photos with a location taken shortly before and after this
  one, usually during the same trip. The map shows their route: purple before the photo, orange
  after, brighter when closer in time. A suggestion "on the way between" two photos lies on the
  dashed line between them; a click near that line lands on it. Under **Devices** you can leave
  out another camera whose clock was wrong, or use **Only this camera**. A photo you saved a
  moment ago counts at once, while its save can still be cancelled.
- **Similar photos** (purple diamonds): photos of your own library that look like this one and
  have a location: the same street, house or view. The thumbnails show which ones; hover a
  thumbnail to enlarge it.
- **GeoCLIP** (orange squares): recognizes the place by its look, anywhere in the world. Its
  answer is an area, so the circle around it is wide.

**Confidence.** The bars next to a suggestion show how sure the module is: one bar is weak, two
are normal, three (green, with the word *confident*) are confident. The percentage is the
module's own score and is comparable only within one module. Weak suggestions are folded under
"*N more weak suggestions*": they usually get only the region right. The circle on the map
(and the ± distance) is how far off the suggestion may be.

Hover a suggestion in the list to highlight it on the map, and the other way round. Click a
suggestion (not its **Choose** button), or press **Shift** and its number, to move the map to it
without picking it.

**Run again** starts a module on this photo once more, ahead of the background queue (for
example after you excluded a camera). If no worker runs that module right now, the card says so
and the run waits.

**Recognize a part of the photo** (key **R** for GeoCLIP) runs the module on a frame you draw:
useful when people or a car cover most of the picture and the place is only in the background.

Modules can be hidden in the card or put in another order on the **Settings** page; a hidden
module keeps running, and a line under the suggestions lets you show it for a while.

### The photo

Click the photo (or press **Z**) to see it in full size. **[** and **]** rotate it if it is on its
side: the modules started after that get it rotated. The rotation is kept only in the card until
you press **Save rotation in Immich** (photos only, not videos); **Undo rotation** turns it back.
Saving the rotation needs the API key permissions `asset.edit.get`, `asset.edit.create` and
`asset.edit.delete`; keys created by Steward 0.3.0 and later have them.

The details below the photo show when it was taken, the camera, the albums and its current
location. **Open in Immich** (the arrow in the top right corner) opens the photo in Immich in a
new tab.

### Keyboard keys

Press **?** in the card to see them all.

| Key | Action |
|---|---|
| 1 … 9 | Choose a suggestion |
| Shift + 1 … 9 | Show a suggestion on the map without choosing it |
| Enter | Save the location |
| ← → | Previous / next photo |
| S | Skip for now |
| N | Location not applicable |
| U | Back to the to-do list |
| Z | Enlarge the photo |
| R | Recognize a part of the photo (GeoCLIP) |
| [ ] | Rotate the photo |
| Esc | Back to the gallery |
| ? | The list of keys |

The keys work with any keyboard layout. A typical round: look at the map, press the number of
the right suggestion, then Enter; the next photo opens.

## Processing

The **Processing** page shows how the work goes:

- **Library**: how many photos and videos there are, how many have no location, when the app
  last read your library from Immich and when it does next. **Sync now** reads the changes right
  away; **Full sync** also notices photos deleted in Immich.
- **Workers**: which [workers](workers.md) are connected and what each is doing now (waiting for
  jobs, downloading or loading a model, working). A worker that has not been seen for a while can
  be removed from the list.
- **Modules**: for GeoCLIP and similar photos, how many photos are done, running, queued and
  failed. Failures are grouped by reason; **Show** opens those photos in the gallery and **Run
  again** queues them once more.
- **Pause**: holds the background runs of one module or of all, until you resume or for a
  while (30 minutes to a day), for example while you watch a film on the same server. Runs started
  from a photo card still go.

## Settings

**Settings** holds the order of the modules in the photo card and which of them are shown, and
the **map sources**: satellite imagery, their keys, how many tiles the app loaded, and which
sources Auto uses far out and close up. Each family member has their own. How to get the keys:
[Configuration](configuration.md#satellite-imagery-in-settings).
