# Utility Scripts

This directory contains helper scripts for managing and analyzing the validation rules.

## analyze_layers.py

**Purpose:** Analyze layer name mappings between ppa_layers.json and ppa_cadtopdf.json

**What it does:**
- Reads the master layer rules from `ppa_layers.json`
- Reads the CAD-to-PDF layer mappings from `ppa_cadtopdf.json`
- Attempts to match layer names from cadtopdf against valid patterns in ppa_layers
- Reports which layers match and which don't

**Usage:**
```bash
cd /home/pkurane/projects/layerslist
python analyze_layers.py
```

**Output:**
- List of valid patterns from ppa_layers.json
- Match status for each layer in cadtopdf
- Summary statistics (total, matched, unmatched)
- List of unmatched layers that would be removed

## correct_layers.py

**Purpose:** Clean up ppa_cadtopdf.json by removing layers that don't match valid patterns

**What it does:**
- Same pattern matching logic as analyze_layers.py
- Creates a cleaned version: `ppa_cadtopdf_corrected.json`
- Removes layers that don't match any pattern in ppa_layers.json
- Preserves special layers listed in `ALWAYS_KEEP_LAYERS` (ELEVATION_PLAN_*, SECTION_PLAN_*, SERVICE_PLAN)

**Usage:**
```bash
cd /home/pkurane/projects/layerslist
python correct_layers.py
```

**Output:**
- New file: `ppa_cadtopdf_corrected.json`
- Summary of kept vs removed layers
- Examples of kept layers with their matched patterns

## Notes

- These scripts are for administrative/maintenance use only
- They help ensure CAD-to-PDF layer mappings stay in sync with validation rules
- Always review the corrected file before deploying
- Consider running analyze_layers.py first to preview changes
