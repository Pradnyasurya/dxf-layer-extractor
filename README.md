# DXF Layer Extractor & Validator

A Flask web app that uploads DXF or ZIP files, extracts layers, and validates them against a master rule set in [odisha_layers.json](odisha_layers.json). It provides a public upload page and an admin page to update validation rules.

## Features

- Upload .dxf or .zip (containing .dxf) files
- Extract all layer names and summary statistics
- Validate layers against the master JSON rules
- **DXF Layer Analysis Result Table** - View all layers with color codes, swatches, line types, and visibility
- **User Authentication** - Secure user accounts for managing file versions
  - User registration and login
  - User-specific version history and data isolation
  - Secure password hashing
- **Version Comparison Tool** - Compare two DXF versions to detect changes
  - Detects added, removed, and modified layers
  - Calculates area differences and position shifts
  - Classifies changes by significance (Critical/High/Medium/Low)
  - Auto-generates compliance insights for architects
  - Side-by-side version selection interface
- Enforce DXF units ($INSUNITS, $LUNITS, $AUNITS) with clear error reporting
- Color validation with layer and entity-level fallback
- Admin UI to update validation rules
- Clean, minimal UI with server-side rendering

## Technology Stack

- **Backend**: Python 3.14+ + Flask 3.0
- **Database**: SQLAlchemy + SQLite (for version tracking)
- **DXF Parser**: ezdxf 1.3
- **Frontend**: Jinja2 templates + Vanilla JS/CSS

## Quick Start

1. Copy the environment configuration:
   ```bash
   cp .env.example .env
   # Edit .env and update SECRET_KEY for production
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   python app.py
   ```

3. Open the app:
   - Main UI: http://localhost:8080
   - Admin UI: http://localhost:8080/admin
   - Version History: http://localhost:8080/versions
   - Compare Versions: http://localhost:8080/compare

## Usage

### Basic Validation
1. Upload a .dxf file or a .zip containing .dxf files.
2. Review the validation report for:
   - Extracted layers and counts
   - DXF version and units validation
   - Layer color compliance (including entity fallback)
   - DXF Layer Analysis Result table with all layers
3. Update rules on the admin page when requirements change.

### Version Comparison (for revised submissions)
1. Upload your initial DXF file (stored as Version 1)
2. Upload your revised DXF file (stored as Version 2)
3. Navigate to `/compare` or click "Compare Versions"
4. Select base version (older) and new version (revised)
5. Review the comparison report showing:
   - Added/removed/modified layers
   - Area changes (sq.m and percentage)
   - Position shifts (for setbacks and structures)
   - Significance classification
   - Compliance insights and warnings

## Development

### Testing
Run the test suite with pytest:
```bash
pytest tests/                    # Run all tests
pytest tests/ -v                 # Verbose output
pytest tests/ --cov=.           # With coverage report
pytest tests/test_file.py::test_name  # Run single test
```

### Linting
```bash
flake8 app.py comparison_engine.py --max-line-length=120 --ignore=E203,W503
black --check app.py comparison_engine.py    # Check formatting
black app.py comparison_engine.py            # Apply formatting
```

### Utility Scripts
See [UTILITIES.md](UTILITIES.md) for helper scripts to manage validation rules:
- `analyze_layers.py` - Analyze layer name mappings between JSON files
- `correct_layers.py` - Clean up and correct layer configurations

## Validation Rules

Rules are defined in [odisha_layers.json](odisha_layers.json) and are the single source of truth. The app converts layer patterns like BLK_n_ to regex and validates:

- Layer name patterns
- Fixed and RGB color requirements
- Sub-occupancy color rules derived from BLT_UP_AREA layers
- Entity-level color overrides if layer color is invalid

## Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/register` | GET, POST | User registration |
| `/login` | GET, POST | User login |
| `/logout` | GET | User logout |
| `/` | GET | Upload form for DXF/ZIP validation (Protected) |
| `/upload` | POST | Process uploaded file (Protected) |
| `/admin` | GET, POST | Manage validation rules JSON (Protected) |
| `/versions` | GET | View all stored DXF versions (Protected) |
| `/compare` | GET, POST | Select two versions to compare (Protected) |
| `/compare_result/<base>/<new>` | GET | View comparison results (Protected) |
| `/delete_version/<id>` | POST | Remove a stored version (Protected) |
| `/generate_fix_script` | POST | Download AutoLISP fix script (Protected) |

## Deployment

### Render

This repository already includes [render.yaml](render.yaml). Connect your repository to Render and deploy as a Web Service.

### Docker

Build and run:

```bash
docker build -t dxf-layer-validator .
docker run -p 8080:8080 dxf-layer-validator
```

## Project Structure

```
layerslist/
├── app.py                    # Flask app with routes and validation
├── comparison_engine.py      # DXF version comparison logic
├── odisha_layers.json        # Master validation rules
├── ppa_layers.json          # Alternative validation rules
├── dxf_versions.db          # SQLite database (auto-created)
├── requirements.txt         # Python dependencies
├── templates/
│   ├── index.html           # Upload page
│   ├── results.html         # Validation results
│   ├── admin.html           # Rules management
│   ├── versions.html        # Version history
│   ├── compare_select.html  # Version comparison selector
│   └── comparison_result.html # Comparison results
├── static/
│   └── css/style.css        # All styles including comparison UI
└── uploads/                 # Temp storage (auto-cleaned)
```

## License

MIT License

## Contributing

Pull requests are welcome. For major changes, please open an issue first.
