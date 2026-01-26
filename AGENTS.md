# Agent Guide for DXF Layer Extractor

This document provides guidelines for AI coding agents working on this Flask-based DXF layer extraction application.

## Project Overview

A Python Flask web application that extracts and displays layer information from DXF (Drawing Exchange Format) files using the ezdxf library.

**Tech Stack:**
- Python 3.14+
- Flask 3.0.0
- ezdxf 1.3.0 (supports DXF R12-R2018+)
- Jinja2 templates
- Vanilla JavaScript (no frameworks)

---

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development server (with debug mode)
python app.py

# Access at http://localhost:8080
```

### Testing
```bash
# Manual test with a DXF file
python -c "from app import extract_layers; print(extract_layers('/path/to/file.dxf'))"

# Test specific function
python -c "from app import allowed_file; print(allowed_file('test.dxf'))"
```

### Code Quality
```bash
# Format code (if black is installed)
pip install black
black app.py

# Lint (if flake8 is installed)
pip install flake8
flake8 app.py --max-line-length=100

# Type checking (if mypy is installed)
pip install mypy
mypy app.py
```

---

## Code Style Guidelines

### 1. Imports
- **Order:** Standard library → Third-party → Local imports
- **Style:** One import per line for clarity
- **Example:**
  ```python
  import os
  from flask import Flask, render_template, request
  from werkzeug.utils import secure_filename
  import ezdxf
  ```

### 2. Formatting
- **Line Length:** Max 100 characters
- **Indentation:** 4 spaces (no tabs)
- **Quotes:** Single quotes for strings, unless docstrings (use triple double quotes)
- **Blank Lines:** 2 blank lines between top-level functions/classes
- **Comments:** Use inline comments sparingly; prefer docstrings

### 3. Naming Conventions
- **Functions/Variables:** `snake_case` (e.g., `extract_layers`, `dxf_path`)
- **Constants:** `UPPER_SNAKE_CASE` (e.g., `ALLOWED_EXTENSIONS`, `MAX_CONTENT_LENGTH`)
- **Classes:** `PascalCase` (if added in future)
- **Private/Internal:** Prefix with underscore `_internal_function()`
- **Flask Routes:** Use descriptive names matching URL paths

### 4. Documentation
- **All functions must have docstrings** with Args, Returns, and Raises sections
- **Format:**
  ```python
  def function_name(param):
      """
      Brief description of what the function does
      
      Args:
          param: Description of parameter
          
      Returns:
          dict: Description of return value
          
      Raises:
          Exception: When this exception occurs
      """
  ```

### 5. Error Handling
- **Always use try-except blocks** for external operations (file I/O, DXF parsing)
- **Catch specific exceptions first:** `ezdxf.DXFStructureError` before generic `Exception`
- **Clean up resources:** Use `finally` or ensure file cleanup in except blocks
- **User-friendly messages:** Convert technical errors to readable flash messages
- **Example:**
  ```python
  filepath = None
  try:
      filepath = save_file()
      process_file(filepath)
  except SpecificError as e:
      flash(f'Specific error: {str(e)}', 'error')
  finally:
      if filepath and os.path.exists(filepath):
          os.remove(filepath)
  ```

### 6. Flask-Specific Guidelines
- **Route handlers:** Include HTTP methods explicitly `@app.route('/', methods=['GET'])`
- **Flash messages:** Always specify category: `flash('message', 'error')` or `flash('message', 'success')`
- **Redirects:** Use `url_for()` instead of hardcoded URLs
- **Configuration:** Use `app.config` for all settings
- **Security:** Always use `secure_filename()` for user uploads

### 7. DXF Processing
- **Use ezdxf library** (never suggest Kabeja or outdated libraries)
- **Handle DXF version gracefully:** Catch `ezdxf.DXFVersionError` separately
- **Always clean up uploaded files:** Delete after processing or on error
- **Validate file extension** before processing

### 8. File Organization
```
layerslist/
├── app.py              # Main Flask application (keep under 200 lines)
├── requirements.txt    # Pinned dependencies
├── templates/          # Jinja2 HTML templates
│   ├── index.html     # Upload form
│   └── results.html   # Results display
├── uploads/           # Temporary storage (auto-cleaned)
├── venv/              # Virtual environment (not in git)
├── .gitignore         # Ignore patterns
└── README.md          # User-facing documentation
```

---

## Important Constraints

### Do NOT:
1. Add unnecessary dependencies (keep requirements.txt minimal)
2. Use Java/Kabeja or any unmaintained DXF libraries
3. Add Lombok or similar code generation tools
4. Store uploaded files permanently
5. Use relative imports for the main app.py file
6. Add database dependencies unless explicitly requested
7. Create files without reading existing code first

### DO:
1. Keep the application simple and focused on layer extraction
2. Validate all user inputs (file size, extension, content)
3. Provide clear error messages to users
4. Clean up temporary files in all code paths
5. Use environment variables for secrets (`SECRET_KEY`)
6. Test with real DXF files before committing
7. Follow Python PEP 8 style guidelines

---

## Testing Guidelines

### Manual Testing Checklist:
1. Upload valid DXF file → Should display sorted layers
2. Upload non-DXF file → Should show error message
3. Upload file > 100MB → Should show size limit error
4. Upload corrupted DXF → Should show parsing error
5. No file selected → Should show validation error

### Test DXF Files:
- Sample file location: `/home/pkurane/Documents/Utility/drawing_template.dxf`
- Test with multiple DXF versions (R12, R2000, R2010+)

---

## Common Tasks

### Adding a New Route:
```python
@app.route('/new-route', methods=['GET', 'POST'])
def new_handler():
    """Brief description"""
    # Implementation
    return render_template('template.html')
```

### Adding a New Feature:
1. Update requirements.txt if new dependency needed
2. Add function with proper docstring
3. Update templates if UI change required
4. Test with real DXF files
5. Update README.md with new feature

### Debugging:
- Check Flask debug output in console
- Verify file permissions for uploads/ directory
- Confirm virtual environment is activated
- Check DXF file version with: `doc.dxfversion`

---

## Future Enhancements (Planned)

When implementing these, maintain current code style:
- Layer metadata (color, linetype, on/off status)
- Entity count per layer
- CSV export functionality
- SVG preview/thumbnail generation
- Batch upload support
- REST API endpoint (`/api/layers`)

---

**Last Updated:** 2026-01-26
**Maintained by:** Agentic coding assistants
