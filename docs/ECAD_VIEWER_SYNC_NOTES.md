# ecad-viewer Sync Notes

This document tracks the current upstream sync reference for the vendored visualizer assets.

## Current Reference

- sync date: 2026-02-27
- upstream ref used for the Prism vendor refresh: `origin/main`
- upstream commit used for the current refactor baseline: `a85abd4`

## Vendored Artifacts

The current sync updated:
- `frontend/public/ecad-viewer.js`
- `frontend/public/glyph-full.js`
- `frontend/public/3d-viewer.js`

## Scope Notes

Visualizer code is intentionally treated as a higher-risk surface than the rest of the app.

That means:
- general frontend cleanup should avoid changing vendored visualizer assets unless the task is explicitly a visualizer/vendor sync
- performance or bundle work outside the visualizer should isolate viewer-specific chunks rather than rewriting the viewer surface itself

If you need to update visualizer behavior, treat it as a dedicated task with explicit validation.
