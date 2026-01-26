# Agent Guide for DXF Layer Extractor & Validator

This document provides guidelines for AI coding agents working on this Flask-based DXF layer extraction and validation application.

## Project Overview

A Python Flask web application that uploads, extracts, and validates layer information from DXF files against a master JSON rule set (`odisha_layers.json`). It supports `.dxf` and `.zip` uploads.

**Tech Stack:**
- **Python:** 3.14+
- **Web Framework:** Flask 3.0.0
- **DXF Processing:** ezdxf 1.3.0
- **Frontend:** Jinja2 templates + Vanilla JS / CSS
- **Data:** JSON for master validation rules

---

## Build & Test Commands

### Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Running
```bash
python app.py
# Access at http://localhost:8080
# Admin panel at http://localhost:8080/admin
```

### Testing (Manual & Scripted)
```bash
# Quick sanity check
python -c "import ezdxf; print(ezdxf.__version__)"

# Manual validation test (create a temporary test script)
# See 'test_validation.py' pattern in previous context for inspiration
```

### Code Quality
```bash
# Linting
flake8 app.py --max-line-length=120 --ignore=E203,W503

# Type Checking
mypy app.py --ignore-missing-imports
```

---

## Code Style Guidelines

### 1. Imports & Structure
- **Order:** Standard Lib (`os`, `json`, `re`) → Third-party (`flask`, `ezdxf`) → Local.
- **Imports:** Absolute imports preferred.
- **Structure:** Keep `app.py` distinct. Move complex logic to helper modules if file exceeds 500 lines.

### 2. Formatting & Naming
- **Style:** PEP 8.
- **Indentation:** 4 spaces.
- **Line Length:** 100-120 chars.
- **Naming:** 
  - Variables/Functions: `snake_case` (e.g., `validate_dxf_content`)
  - Constants: `UPPER_SNAKE_CASE` (e.g., `ALLOWED_EXTENSIONS`)
  - Layer Regex Patterns: Handle `BLK_n_` → `BLK_\d+`.

### 3. Error Handling
- **File I/O:** Always use `try-finally` or `with` blocks to ensure temporary files/dirs are cleaned up.
- **DXF Parsing:** Catch `ezdxf.DXFStructureError` and `ezdxf.DXFVersionError` specifically.
- **User Feedback:** Use `flash()` messages with categories (`error`, `success`, `warning`).
- **Validation:** Do not crash on invalid DXF data; report it as a validation error.

### 4. Validation Logic (Crucial)
- **Master Data:** Rules are in `odisha_layers.json`.
- **Pattern Matching:** Layer names must be matched using regex (converting `n` to `\d+`).
- **Color Validation:**
  - **Fixed:** Match exact ACI (Integer).
  - **RGB:** Match `RGB r,g,b`.
  - **Sub-Occupancy:** Allowed colors are derived dynamically from `BLK_n_FLR_n_BLT_UP_AREA` layers found in the file.
- **Entity Fallback:** If Layer Color is invalid, check **ALL** entities on that layer. If all entities have valid explicit colors, the layer is considered **Valid**.

---

## File Organization

```
layerslist/
├── app.py              # Main application & validation logic
├── odisha_layers.json  # Master validation rules (updatable via admin)
├── requirements.txt    # Dependencies
├── templates/
│   ├── index.html      # Upload form
│   ├── results.html    # Validation report
│   └── admin.html      # Master data update page
├── uploads/            # Temporary storage (auto-cleaned)
└── AGENTS.md           # This guide
```

---

## Common Tasks & workflows

### 1. Updating Validation Rules
- The master JSON is the source of truth.
- Update it via the `/admin` route or direct file edit.
- Do NOT hardcode validation rules in Python unless checking generic DXF properties (Units/Precision).

### 2. Handling DXF Units
- **Strict Requirement:** 
  - `$INSUNITS` = 6 (Meters)
  - `$LUNITS` = 2 (Decimal)
  - `$AUNITS` = 0 (Decimal Degrees)
- Report exact values found if validation fails (e.g., "Found Millimeters (4)").

### 3. Adding New Routes
```python
@app.route('/new_feature')
def new_feature():
    try:
        # logic
        return render_template('new.html')
    except Exception as e:
        flash(f"Error: {e}", 'error')
        return redirect(url_for('index'))
```

---

## Testing Checklist
1. **Valid File:** Upload a perfect DXF. -> All Green.
2. **Invalid Units:** Change `$INSUNITS` to 4. -> Top-level Error.
3. **Color Mismatch:** Layer color 4 when 1 is required. -> Layer marked Invalid.
4. **Entity Override:** Layer color 4 (invalid), but Entities are color 1 (valid). -> Layer marked Valid.
5. **Sub-Occupancy:** Layer matches `BLT_UP_AREA` color. -> Valid.
6. **ZIP Upload:** Upload `.zip` containing `.dxf`. -> Extracts & Validates.

---

**Maintained by:** Agentic Coding Assistants
**Last Updated:** Jan 2026
