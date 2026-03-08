# Path Mapping and `.prism.json`

KiCAD Prism supports both convention-based repository layouts and explicit path configuration.

## Why `.prism.json` Exists

Without explicit config, the backend has to inspect the repository and infer where files live. That works for common layouts, but it is slower and less predictable on unusual repos or monorepos.

A complete `.prism.json` gives you:
- deterministic file resolution
- less path auto-detection work
- clearer project metadata
- fewer surprises when importing or syncing repositories

## Resolution Order

Current path resolution follows this order:
1. explicit `.prism.json`
2. auto-detection for missing fields
3. fallback legacy defaults where applicable

A key current behavior is that explicit fields are honored first, and only missing fields are auto-detected.

## Supported Fields

Top-level metadata:
- `project_name`
- `description`
- `workflows`

Path fields:
- `schematic`
- `pcb`
- `subsheets`
- `designOutputs`
- `manufacturingOutputs`
- `documentation`
- `thumbnail`
- `readme`
- `jobset`

## Example

```json
{
  "project_name": "Flight Controller Rev B",
  "description": "Main avionics control board.",
  "paths": {
    "schematic": "hardware/fc.kicad_sch",
    "pcb": "hardware/fc.kicad_pcb",
    "subsheets": "hardware/subsheets",
    "designOutputs": "outputs/design",
    "manufacturingOutputs": "outputs/manufacturing",
    "documentation": "docs",
    "thumbnail": "assets/thumbnail",
    "readme": "README.md",
    "jobset": "Outputs.kicad_jobset"
  }
}
```

## API Endpoints

### Get effective config

```http
GET /api/projects/{project_id}/config
```

Returns:
- `config`: effective path and metadata config
- `resolved`: resolved absolute paths
- `source`: `explicit` or `auto-detected`

### Preview auto-detection

```http
POST /api/projects/{project_id}/detect-paths
```

Returns a detected config plus validation without writing `.prism.json`.

### Save config

```http
PUT /api/projects/{project_id}/config
Content-Type: application/json

{
  "project_name": "Flight Controller Rev B",
  "description": "Main avionics control board.",
  "schematic": "hardware/fc.kicad_sch",
  "pcb": "hardware/fc.kicad_pcb",
  "documentation": "docs"
}
```

Saving config writes `.prism.json` in the project root.

## Auto-Detection Heuristics

If you do not provide a `.prism.json`, KiCAD Prism looks for common patterns such as:
- root `.kicad_sch` and `.kicad_pcb` files
- common docs folders like `docs`, `documentation`, `wiki`
- common output folders like `Design-Outputs`, `Manufacturing-Outputs`, `outputs`, `exports`
- common thumbnail/image directories under `assets`, `images`, or `renders`
- README-like files such as `README*` or `OVERVIEW*`

## Recommendations

- use explicit config for monorepos or non-standard layouts
- set `readme` and `documentation` explicitly if your documentation is not under `README.md` and `docs/`
- keep output directories stable across workflow runs
- store project metadata and path mapping together in `.prism.json`

## Validation and Troubleshooting

If a file is not showing up where expected:
1. call `GET /api/projects/{project_id}/config`
2. inspect `resolved` paths
3. run `POST /api/projects/{project_id}/detect-paths` to compare inferred values
4. save an explicit `.prism.json` if the repo layout is unusual

For schematic and PCB fields, glob-like values are supported where the backend expects them, but explicit file paths are usually the least ambiguous option.

## Related Docs

- [./KICAD-PRJ-REPO-STRUCTURE.md](./KICAD-PRJ-REPO-STRUCTURE.md)
- [./CUSTOM_PROJECT_NAMES.md](./CUSTOM_PROJECT_NAMES.md)
