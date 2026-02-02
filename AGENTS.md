# Agent Guide

Purpose: Give agentic coding tools commands, conventions, and edge cases for this Flask DXF layer validator.

## Project Overview

Flask web app for DXF file validation against JSON rulesets. Supports version comparison and user management.

**Key Files:**
- `app.py` - Flask routes and validation logic
- `comparison_engine.py` - DXF version comparison engine
- `odisha_layers.json` - Master validation rules
- `templates/` - Jinja2 templates (index.html, results.html, admin.html, versions.html, compare_select.html, comparison_result.html)
- `tests/` - pytest test suite (test_smoke.py, test_validation.py)

## Build, Run, Lint, Test

**Setup:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Run locally:**
```bash
python app.py
# http://localhost:8080 - Upload
# http://localhost:8080/admin - Rules management
# http://localhost:8080/versions - Version history
# http://localhost:8080/compare - Version comparison
```

**Docker:**
```bash
docker build -t dxf-layer-validator .
docker run -p 8080:8080 dxf-layer-validator
```

**Lint:**
```bash
flake8 app.py comparison_engine.py --max-line-length=120 --ignore=E203,W503
```

**Type check:**
```bash
mypy app.py comparison_engine.py --ignore-missing-imports
```

**Tests:**
- No formal test suite exists yet.
- To create one, add pytest to requirements.txt, create test files in `tests/`, then run:
  ```bash
  pytest tests/                    # Run all tests
  pytest tests/test_file.py::test_name  # Run single test
  ```
- For quick validation: `python -c "import ezdxf; print(ezdxf.__version__)"`

## Code Style

**Python:** Target 3.14+

**Imports:**
```python
import os
import json
from typing import Dict, List

from flask import Flask
import ezdxf

from comparison_engine import DXFComparator
```

**Formatting:**
- PEP 8, 4 spaces, max line length 100-120
- Blank lines between logical sections
- Use absolute imports only

**Naming:**
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Routes: Short, noun-based (`/upload`, `/admin`)
- Classes: `PascalCase`

**Types:**
- Validation rules are dicts from JSON with keys: "Layer Name", "Color Code", "Type", "Requirement"
- Use type hints for function signatures
- Keep rule keys as-is (don't rename)

**Error Handling:**
- Use explicit exceptions with clear user-facing messages
- Always cleanup temp files (even on failure)
- Use `flash()` with categories: `error`, `warning`, `success`
- Wrap file operations and DXF parsing in try/except

## Core Validation Logic

**Unit Validation:** $INSUNITS=6, $LUNITS=2, $AUNITS=0; warn if $LUPREC!=2

**Layer Patterns:** BLK_n converts to regex `BLK_\d+`

**Color Rules:**
- "Any"/"NA"/"N/A" always valid
- "RGB r,g,b" uses true_color matching (colors.rgb2int)
- "As per Sub-Occupancy" derives from BLT_UP_AREA layer colors
- Entity fallback: If layer color invalid but all entities have explicit valid colors → valid

**Entity Types:** Use ENTITY_TYPE_MAPPING for authoritative type checks

**Geometry:**
- Polygon layers must be closed
- Calculate area via ezdxf helpers
- Text layers validate by suffix (CAPACITY_L, VOLTAGE_KV)

## Version Comparison (comparison_engine.py)

- `DXFComparator` detects added/removed/modified layers
- Metrics: entity count, area (sq.m), perimeter, centroid position
- Significance: critical/high/medium/low based on layer type
  - Critical: BLT_UP_AREA, COVERED_AREA, SETBACK, PLOT_BOUNDARY
  - High: STAIR, LIFT, HT_OF_BLDG, PLINTH_HEIGHT, BLDG_FOOT_PRINT
- Tolerance: Ignore changes < 0.01 sq.m or < 0.01m shift
- `generate_diff_svg()` creates overlay visualization

## Database Models

SQLite (auto-created on startup). Key tables:
- `versions` - file metadata (hash, upload_date, project_name, total_layers)
- `layer_snapshots` - per-layer metrics (area, entity_count, bounds, color)
- `comparison_results` - cached comparison results between versions
- `users` - user accounts with password hashing

## UI Behavior

- Results page needs: `layer_data` with status/messages, `data_attributes`, `layer_analysis` table
- Flash messages use Bootstrap classes: `error=danger`, `warning=warning`, `success=success`
- Admin page validates JSON before saving to odisha_layers.json
- Keep server-rendered flow intact; don't break template variable names

## Security

- SECRET_KEY from env (default is dev-only)
- MAX_CONTENT_LENGTH = 100 MB
- Always use `secure_filename()` and restrict to .dxf/.zip
- Never log or expose user upload file paths

## Manual Validation Checklist

Test these scenarios after any validation changes:
1. Valid DXF → all green
2. Invalid units ($INSUNITS≠6) → error
3. Color mismatch → error
4. Entity color override → valid if all entities have explicit colors
5. ZIP upload → first .dxf processed
6. Admin save → JSON syntax errors show clear message
7. Version storage → DXF stored in DB after upload
8. Version comparison → detects added/removed/modified layers
9. Comparison metrics → area diffs and shifts displayed correctly

## Agent Notes

- Avoid large refactors; focus on correctness
- Update error messages when modifying validation logic
- Always cleanup uploads/ directory, even on exceptions
- Check both `/` (upload) and `/admin` (rules) pages when making changes
- JSON files remain source of truth for rules; don't hardcode new rules in Python

## Cursor / Copilot Rules

No .cursor/rules, .cursorrules, or .github/copilot-instructions.md found. If added later, mirror them here.

Last updated: Feb 2026
