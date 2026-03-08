# KiCAD Project Repository Structure

KiCAD Prism works with flexible repository layouts, but projects are easiest to operate when a few conventions are followed.

This document describes the recommended layout, not a hard requirement. If your repo differs, use `.prism.json` path mapping as described in [PATH-MAPPING.md](./PATH-MAPPING.md).

## Recommended Root Contents

| File or Folder | Purpose |
| --- | --- |
| `BoardName.kicad_pro` | Main KiCad project file |
| `BoardName.kicad_sch` | Root schematic |
| `BoardName.kicad_pcb` | PCB layout |
| `Outputs.kicad_jobset` | Workflow definition used by KiCAD Prism jobs |
| `README.md` | Project overview shown in the Overview tab |
| `Subsheets/` | Optional schematic subsheets |
| `docs/` | Optional markdown documentation tree |
| `assets/` | Images, thumbnails, renders |
| `Design-Outputs/` | Generated design artifacts |
| `Manufacturing-Outputs/` | Generated fabrication artifacts |

## Recommended Example Layout

```text
Board-Project-Repo/
├── BoardName.kicad_pro
├── BoardName.kicad_sch
├── BoardName.kicad_pcb
├── Outputs.kicad_jobset
├── README.md
├── Subsheets/
│   └── power-sheet.kicad_sch
├── assets/
│   ├── images/
│   ├── renders/
│   └── thumbnail/
├── docs/
│   ├── bringup.md
│   └── manufacturing-notes.md
├── Design-Outputs/
│   ├── BoardName.pdf
│   ├── BoardName_iBoM.html
│   └── 3DModel/
└── Manufacturing-Outputs/
    ├── Gerbers/
    ├── BOM/
    └── XY-Data/
```

## How KiCAD Prism Uses These Paths

- Overview tab reads `README.md` or another configured readme path
- Documentation tab reads the configured docs directory recursively
- Assets and downloads surfaces read configured design/manufacturing output directories
- workflow jobs look for the configured jobset file
- thumbnails are resolved from the configured thumbnail directory

## Flexible Layout Support

KiCAD Prism does not require this exact shape.

If your repository uses different names, define them in `.prism.json`, for example:

```json
{
  "paths": {
    "schematic": "hardware/main.kicad_sch",
    "pcb": "hardware/main.kicad_pcb",
    "documentation": "wiki",
    "designOutputs": "out/design",
    "manufacturingOutputs": "out/mfg",
    "thumbnail": "media/thumbs",
    "readme": "docs/overview.md",
    "jobset": "ci/Outputs.kicad_jobset"
  }
}
```

## Recommendations for Smooth Operation

- keep one clear root schematic and one clear PCB path per project
- store generated outputs in stable directories so users know where to find artifacts
- keep documentation in markdown if you want it rendered directly in the UI
- put thumbnail images in a dedicated subdirectory so selection is predictable
- use `.prism.json` instead of relying on auto-detection when a repo is non-standard

## Monorepos

For monorepo imports, each discovered subproject should still have a coherent local structure. Explicit `.prism.json` files for subprojects are especially useful because they remove ambiguity and reduce path auto-detection work.
