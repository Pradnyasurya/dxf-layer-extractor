# DXF Layer Extractor & Validator

A Flask web app that uploads DXF or ZIP files, extracts layers, and validates them against a master rule set in [odisha_layers.json](odisha_layers.json). It provides a public upload page and an admin page to update validation rules.

## Features

- Upload .dxf or .zip (containing .dxf) files
- Extract all layer names and summary statistics
- Validate layers against the master JSON rules
- Enforce DXF units ($INSUNITS, $LUNITS, $AUNITS) with clear error reporting
- Color validation with layer and entity-level fallback
- Admin UI to update validation rules
- Clean, minimal UI with server-side rendering

## Technology Stack

- **Backend**: Python 3.14+ + Flask 3.0
- **DXF Parser**: ezdxf 1.3
- **Frontend**: Jinja2 templates + Vanilla JS/CSS

## Quick Start

1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run the app:
   ```bash
   python app.py
   ```

3. Open the app:
   - Main UI: http://localhost:8080
   - Admin UI: http://localhost:8080/admin

## Usage

1. Upload a .dxf file or a .zip containing .dxf files.
2. Review the validation report for:
   - Extracted layers and counts
   - DXF version and units validation
   - Layer color compliance (including entity fallback)
3. Update rules on the admin page when requirements change.

## Validation Rules

Rules are defined in [odisha_layers.json](odisha_layers.json) and are the single source of truth. The app converts layer patterns like BLK_n_ to regex and validates:

- Layer name patterns
- Fixed and RGB color requirements
- Sub-occupancy color rules derived from BLT_UP_AREA layers
- Entity-level color overrides if layer color is invalid

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
├── app.py
├── odisha_layers.json
├── templates/
├── static/
└── uploads/
```

## License

MIT License

## Contributing

Pull requests are welcome. For major changes, please open an issue first.
