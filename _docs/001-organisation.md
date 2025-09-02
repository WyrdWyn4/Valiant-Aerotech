├─ planning/                      # Research + plans (Markdown-first)
│  ├─ research/                   # literature, notes, media
│  ├─ templates/                  # checklists, brief templates
│  └─ missions/
│     └─ circular-perimeter-hotspots/
│        ├─ brief.md              # what/why/success criteria/risks
│        ├─ geometry.geojson      # optional: shapes/regions/POIs
│        ├─ constraints.md        # airspace, altitude, time windows
│        ├─ checklists/           # pre-flight/flight/post-flight
│        └─ media/                # images/figures
│
├─ integration/                   # Data pipelines and analysis
│  ├─ pipelines/                  # scripts/notebooks/modules
│  ├─ configs/                    # dataset/task configs (YAML)
│  ├─ exports/                    # immutable results (by mission & date)
│  │  └─ circular-perimeter-hotspots/
│  │     └─ 2025-09-02/
│  │        ├─ results.csv
│  │        ├─ results.geojson
│  │        └─ export.README.md   # columns, units, coordinate frame, etc.
│  └─ data/                       # (small samples only; big via DVC/LFS)
│
├─ actuation/                     # Mission execution assets
│  ├─ lua/                        # onboard scripts
│  ├─ mission-planner/            # MP helpers (IronPython) and .waypoints
│  └─ missions/
│     └─ circular-perimeter-hotspots/
│        ├─ mission.lua
│        ├─ params.param          # optional: parameter set
│        └─ sample.waypoints
│
├─ missions/                      # "Task packs" that tie artifacts together
│  └─ circular-perimeter-hotspots/
│     └─ manifest.yaml            # points at exact files/commits from each area
│
├─ tools/                         # tiny CLIs (e.g., taskpack, link-check)
├─ docs/                          # how-tos, conventions
├─ .github/workflows/             # CI pipelines (path-scoped)
└─ README.md