# Agent Guide

Purpose: give agentic coding tools the exact commands, conventions, and edge cases
for this Flask DXF layer validator. Keep changes consistent with current behavior.

Project summary
- Flask web app that uploads .dxf/.zip files, validates layers vs JSON rules.
- Primary rules: odisha_layers.json; optional ppa_layers.json or custom upload.
- UI is server-rendered (Jinja2 templates) with small JS/CSS.

Repository layout (key files)
- app.py: Flask routes + DXF validation logic (core behavior).
- odisha_layers.json: master validation rules (single source of truth).
- ppa_layers.json: alternative ruleset.
- templates/: index.html, results.html, admin.html (Jinja2).
- static/css/style.css: UI styling.
- static/js/: client-side scripts (if any).
- uploads/: temp storage (auto-cleaned after processing).
- tests/: empty directory; no formal test suite yet.

Build, run, lint, test

Environment setup
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run locally
```bash
python app.py
# http://localhost:8080
# http://localhost:8080/admin
```

Docker
```bash
docker build -t dxf-layer-validator .
docker run -p 8080:8080 dxf-layer-validator
```

Lint (flake8)
```bash
flake8 app.py --max-line-length=120 --ignore=E203,W503
```

Type checking (mypy)
```bash
mypy app.py --ignore-missing-imports
```

Tests
- There is no formal test suite in this repo.
- Use manual validation against known DXF samples (see checklist below).
- For a single test, create a tiny script in a temp location and run `python`.
  Example:
  ```bash
  python -c "import ezdxf; print(ezdxf.__version__)"
  ```

If you add a test suite, document these in README and update this file:
- Run all tests: (command here)
- Run single test: (command here, e.g., pytest path::test_name)

Code style and conventions

Python version
- Target Python 3.14+ (per README).

Imports
- Order: standard library, third-party, local.
- Use absolute imports; avoid circular imports in app.py.
- Example:
  ```python
  import os
  import json
  from flask import Flask
  import ezdxf
  ```

Formatting
- PEP 8, 4 spaces, line length 100-120.
- Keep large functions coherent; if app.py grows too large, extract helpers.
- Use blank lines to separate logical sections within functions.

Naming
- Functions/variables: snake_case.
- Constants: UPPER_SNAKE_CASE.
- Routes: short, noun-based, e.g., /upload, /admin.
- Classes: PascalCase (if any).

Types and data shapes
- Validation rules are dictionaries loaded from JSON.
- Keep rule keys as-is ("Layer Name", "Color Code", "Type", "Requirement").
- When adding new rule fields, update any code that assumes key presence.

Error handling
- Prefer explicit exceptions with a clear message for user-facing errors.
- Cleanup temp files on both success and failure (see upload_file flow).
- Use flash() with categories: error, warning, success.
- Always use try/except around file operations and DXF parsing.

DXF validation behavior (core logic)
- Unit validation: $INSUNITS=6, $LUNITS=2, $AUNITS=0; warn if $LUPREC!=2.
- Layer pattern matching converts placeholders like BLK_n to regex digits.
- Color rules:
  - "Any"/"NA"/"N/A" are always valid.
  - "RGB r,g,b" uses true_color matching (colors.rgb2int).
  - "As per Sub-Occupancy" derives allowed colors from BLK_n_FLR_n_BLT_UP_AREA.
- Entity fallback: if layer color is invalid, accept the layer only if all
  entities have explicit valid colors (not ByLayer/ByBlock).

Entity type + geometry checks
- Type mapping is in ENTITY_TYPE_MAPPING; keep it authoritative.
- Polygon layers must be closed; area calculated via ezdxf helpers.
- Text layers validate content by layer suffix (CAPACITY_L, VOLTAGE_KV, etc.).

Security and configuration
- SECRET_KEY is pulled from env; default is dev-only.
- Upload limit is 100 MB.
- Always use secure_filename and restrict to .dxf/.zip.
- Never log or expose file paths from user uploads.

UI behavior
- Results page expects layer data with status/messages and data_attributes.
- Admin page updates odisha_layers.json; validate JSON before saving.
- Avoid breaking server-rendered flow or template variable names.
- Flash messages use Bootstrap alert classes (error=danger, warning=warning, success=success).

Data files
- Do not hardcode new validation rules in Python unless rule is generic (units,
  geometry, or formatting rules). JSON remains source of truth.
- If you add new rulesets, keep them alongside odisha_layers.json and update
  rules_source handling.
- Always validate JSON syntax before writing to disk.

Manual validation checklist (quick)
- Valid DXF: all green.
- Invalid units: $INSUNITS!=6 triggers error.
- Color mismatch: wrong layer color yields error.
- Entity override: invalid layer color but all entities explicit valid -> valid.
- Sub-occupancy: BLT_UP_AREA colors feed occupancy validation.
- ZIP upload: first .dxf found is processed.
- Admin save: JSON syntax errors show clear message.

Cursor / Copilot rules
- No .cursor/rules, .cursorrules, or .github/copilot-instructions.md found in
  this repo at time of writing. If added later, mirror them here.

Notes for agentic changes
- Avoid large refactors; focus on correctness and clarity.
- If modifying validation logic, update error messages for user clarity.
- Keep uploads cleaned even on exceptions; users upload large files.
- Test manually with sample DXF files after any validation logic changes.
- When adding features, check both / (upload) and /admin (rules) pages.

Last updated: Jan 2026
