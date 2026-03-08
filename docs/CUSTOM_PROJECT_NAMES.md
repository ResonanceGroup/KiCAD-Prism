# Custom Project Names and Metadata

KiCAD Prism supports project-level display metadata through `.prism.json` and related API endpoints.

## What Is Configurable

Current project metadata fields include:
- `project_name`: display name shown in the UI
- `description`: project description shown in workspace and detail views

These fields live alongside path mappings in `.prism.json`.

Example:

```json
{
  "project_name": "Power Distribution Board",
  "description": "48 V input board for lab power routing.",
  "paths": {
    "schematic": "board.kicad_sch",
    "pcb": "board.kicad_pcb",
    "designOutputs": "Design-Outputs",
    "manufacturingOutputs": "Manufacturing-Outputs",
    "documentation": "docs",
    "thumbnail": "assets/thumbnail",
    "readme": "README.md",
    "jobset": "Outputs.kicad_jobset"
  }
}
```

## Resolution Rules

Display name resolution uses this order:
1. `.prism.json` `project_name`
2. imported project display name from registry
3. project folder or repo-derived fallback name

Description resolution uses this order:
1. `.prism.json` `description`
2. registry description
3. backend fallback such as `Project <name>`

## Primary API

The main settings flow is the config endpoint:

### Get effective config

```http
GET /api/projects/{project_id}/config
```

Returns:
- `config`: effective configuration, including `project_name` and `description`
- `resolved`: resolved absolute paths
- `source`: `explicit` or `auto-detected`

### Update config

```http
PUT /api/projects/{project_id}/config
Content-Type: application/json

{
  "project_name": "Power Distribution Board",
  "description": "48 V input board for lab power routing.",
  "schematic": "board.kicad_sch",
  "pcb": "board.kicad_pcb"
}
```

This is the preferred path for project settings because it updates metadata and path mapping together.

## Compatibility Endpoints

Separate name endpoints still exist for compatibility:

```http
GET /api/projects/{project_id}/name
PUT /api/projects/{project_id}/name
```

They remain useful for narrow integrations, but the main UI now prefers the config endpoint.

## UI Behavior

Current frontend behavior:
- workspace cards and search use `display_name` when present
- project detail header uses the resolved display name from project detail/overview payloads
- project settings dialog edits `project_name`, `description`, and paths together

## Why Explicit Metadata Helps

Using `.prism.json` metadata has two practical benefits:
- clearer labels for monorepo subprojects and imported repos
- less ambiguity when several folders have similar technical filenames

It also avoids relying on inferred names from repository structure alone.

## Recommendations

- set `project_name` for any project whose folder name is not presentation-friendly
- keep `description` short and task-oriented so workspace search remains useful
- treat `.prism.json` as the canonical place for project-specific display metadata
