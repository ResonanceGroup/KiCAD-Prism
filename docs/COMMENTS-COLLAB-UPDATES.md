# Comments Collaboration Model

This document describes the current comments architecture in KiCAD Prism.

## Current Behavior

Comments are database-backed for live application use.

- source of truth: SQLite comment store
- export artifact: `.comments/comments.json` inside the project repository
- REST helper URLs are generated per project so KiCad or external tooling can target the correct API endpoints

The export action generates the JSON artifact. Git commit and push operations remain a separate user workflow.

## Backend Model

### Storage

`CommentsStoreService` keeps comments and replies in SQLite with per-project isolation.

Key behavior:
- bootstraps from an existing `.comments/comments.json` once when needed
- supports comment create, update, reply, and delete operations
- exports JSON atomically back into the repository

### API Surface

Comments endpoints live under `/api/projects/{project_id}`:

- `GET /comments`
- `POST /comments`
- `PATCH /comments/{comment_id}`
- `POST /comments/{comment_id}/replies`
- `DELETE /comments/{comment_id}`
- `POST /comments/push`

`POST /comments/push` now means export the current DB-backed state to `.comments/comments.json`. It does not perform a Git push.

### Helper URLs

`GET /api/projects/{project_id}/comments/source-urls` returns helper URLs for external integration:

- `list_url`
- `patch_url_template`
- `reply_url_template`
- `delete_url_template`

Base URL resolution priority:
1. explicit `base_url` query parameter
2. `COMMENTS_API_BASE_URL`
3. request host and forwarded headers

## Frontend Behavior

Current UI behavior includes:
- import dialog shows comment-source helper URLs after import
- visualizer exposes the same URLs through a persistent popover
- users can copy list, patch, reply, and delete templates directly
- export action is labeled `Generate JSON`

## Hosting Notes

### LAN or remote access

If users or tools connect from another machine, helper URLs must resolve to a reachable backend host.

Use either:
- `COMMENTS_API_BASE_URL=http://reachable-host:8000`
- or access the backend using the same host/IP that external clients will use, so request-derived URLs are correct

### Repository workflow

After generating `.comments/comments.json`, use normal Git commands to stage, commit, and push the artifact if you want it versioned in the repository.

## Recommended Usage

- use the web UI and SQLite store for normal collaboration
- generate `.comments/comments.json` when you need a repository artifact for downstream tools or KiCad-side workflows
- keep backend URL generation explicit with `COMMENTS_API_BASE_URL` when deploying behind LAN IPs, reverse proxies, or non-default hosts
