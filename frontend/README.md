# KiCAD Prism Frontend

This package contains the React/Vite frontend for KiCAD Prism.

## Responsibilities

- login and session bootstrap
- workspace and folder UI
- project detail surfaces: overview, history, visualizers, assets, docs, workflows
- comments helpers and import UX
- route-level chunking for the non-visualizer application shell

## Local Development

```bash
cd frontend
npm install
npm run dev
```

Default dev URL:

```text
http://127.0.0.1:5173
```

The frontend expects the backend API to be available at `http://127.0.0.1:8000` via the Vite proxy configuration.

## Scripts

- `npm run dev`: start the Vite dev server
- `npm run build`: type-check and build the production bundle
- `npm run lint`: run ESLint
- `npm run preview`: serve the built bundle locally

## Build Notes

- The app uses lazy route loading for the main non-visualizer surfaces.
- Auth and markdown runtimes are deferred out of the initial shell.
- Visualizer-related bundles remain isolated because that surface has different stability constraints.

## Directory Guide

- `src/App.tsx`: route shell, auth bootstrap, global providers
- `src/components/`: shared UI components and feature surfaces
- `src/pages/`: route-level pages
- `src/hooks/`: data and search hooks
- `public/`: static viewer assets and vendored visualizer artifacts
