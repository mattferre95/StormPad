# StormPad product site

This is a static HTML, CSS, and vanilla JavaScript site. It has no build step or
external dependencies.

## Preview locally

From the repository root, run:

```sh
python3 -m http.server 8080 --directory site
```

Then open `http://localhost:8080`.

## Product assets

The site uses copies of the approved repository assets:

- `assets/stormpad-icon.png` is copied from `assets/Stormpad_webapp.png`.
- `assets/stormpad-app.png` is copied from the sanitized approved application
  screenshot at `docs/screenshots/phase-5-1-3/share-button.png`.

Replace `site/assets/stormpad-app.png` with another approved sanitized
screenshot of the same name and aspect ratio to update the main product image.
Do not use captures containing personal notes.

## Download configuration

The clearly named `DOWNLOAD_URL` and `DOWNLOAD_AVAILABLE` constants are at the
top of `site/script.js`. They point to the published `v0.1.0-beta.1` GitHub
prerelease. A click starts the DMG download and opens the accessible
installation guide.

## GitHub Pages

`.github/workflows/pages.yml` contains the Pages workflow. It uploads only the
`site/` directory and deploys that artifact to the public StormPad website when
site files change on `main`.
