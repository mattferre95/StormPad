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
top of `site/script.js`.

Keep `DOWNLOAD_AVAILABLE` set to `false` during local development and until the
official DMG exists. In that state, download buttons show an availability
message and never start a request. Once the DMG is published at the configured
URL, set the flag to `true`. A click will then start the download and open the
accessible installation guide.

## GitHub Pages

`.github/workflows/pages.yml` contains a minimal Pages workflow. It uploads only
the `site/` directory and deploys that artifact. It is not enabled merely by
adding the file: repository Pages settings still need to be configured to use
GitHub Actions, and the workflow needs to be pushed before it can run.
