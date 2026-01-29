"""
DXF Layer Extractor & Validator

A Flask web application that uploads, extracts, and validates layer information
from DXF files against a master JSON rule set (odisha_layers.json).
Supports .dxf and .zip uploads with comprehensive validation.
"""

import os
import json
import zipfile
import re
import shutil
from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename
import ezdxf
from ezdxf import colors
from ezdxf.math import area

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB upload limit
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MASTER_JSON'] = os.path.join(os.path.dirname(__file__), 'odisha_layers.json')
ALLOWED_EXTENSIONS = {'dxf', 'zip'}

# Layers to ignore during validation (AutoCAD standard + user defined)
IGNORED_LAYERS = {
    '0', 'Defpoints',
    'PLAN', 'WALL', 'elevation', 'TEXT', 'column', 'dim', 'HATCH', 'IC',
    'sec-slab', 'Chajja', 'win', 'BUA TOTAL', 'FORMAT LINE', 'SEC LINE',
    'ele-1', 'SEC WALL', 'SEC DIM', 'rm text', 'TEXT-D-W', 'ELE-2',
    'ELE-3', 'LANDSCAPE', 'dw text', 'Dim.', 'WALL.', 'ELE', 'layer',
    'Layer2', 'WINDOWS', 'LS-Tree', 'RM TXT'
}

# Allowed DXF entity types for each JSON rule type
ENTITY_TYPE_MAPPING = {
    "Polygon": {'LWPOLYLINE', 'POLYLINE', 'HATCH', 'MPOLYGON'},
    "Line": {'LINE', 'LWPOLYLINE', 'POLYLINE'},
    "Text": {'TEXT', 'MTEXT'},
    "Dimension": {'DIMENSION', 'ARC_DIMENSION', 'LEADER', 'MLEADER'},
}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has a valid extension (.dxf or .zip)"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_layer_pattern(pattern_name):
    """Convert JSON layer name pattern to regex, replacing 'n' placeholders with digit matchers"""
    # Replace 'n' placeholders with regex digit patterns
    escaped = re.escape(pattern_name)
    # Replace 'n' with '\d+' (one or more digits)
    # Replace 'n' placeholders in specific contexts (e.g., BLK_n, _n_, =n)
    # Avoids replacing 'n' in words like 'Green' or 'Open'
    regex_pattern = pattern_name
    regex_pattern = regex_pattern.replace('BLK_n', r'BLK_-?\d+')
    regex_pattern = regex_pattern.replace('_n_', r'_-?\d+_')
    if regex_pattern.endswith('_n'):
        regex_pattern = regex_pattern[:-2] + r'_-?\d+'
    regex_pattern = regex_pattern.replace('=n', r'=-?\d+')
    
    # Special case: "STAIR_n" at end or middle
    regex_pattern = regex_pattern.replace('STAIR_n', r'STAIR_-?\d+')
    regex_pattern = regex_pattern.replace('RAMP_n', r'RAMP_-?\d+')
    regex_pattern = regex_pattern.replace('LIFT_n', r'LIFT_-?\d+')
    regex_pattern = regex_pattern.replace('UNIT_n', r'UNIT_-?\d+')
    regex_pattern = regex_pattern.replace('FLIGHT_n', r'FLIGHT_-?\d+')
    regex_pattern = regex_pattern.replace('LANDING_n', r'LANDING_-?\d+')
    regex_pattern = regex_pattern.replace('ROOM_n', r'ROOM_-?\d+')
    regex_pattern = regex_pattern.replace('FACADE_n', r'FACADE_-?\d+')
    regex_pattern = regex_pattern.replace('AREA_n', r'AREA_-?\d+')
    regex_pattern = regex_pattern.replace('CTI_n', r'CTI_-?\d+')
    regex_pattern = regex_pattern.replace('OHEL_n', r'OHEL_-?\d+')
    
    # If no placeholders were found, use strict pattern matching
    if regex_pattern == pattern_name:
        return f"^{re.escape(pattern_name)}$"
    
    return f"^{regex_pattern}$"

def calculate_entity_area(entity):
    """Calculate area of a closed entity (LWPOLYLINE, POLYLINE, HATCH, MPOLYGON)"""
    try:
        dxftype = entity.dxftype()
        if dxftype == 'LWPOLYLINE':
            if entity.is_closed:
                # Use ezdxf's internal area calculation if available (newer versions)
                # or manually calculate polygon area
                with entity.points("xy") as points:
                    if len(points) < 3: return 0.0
                    # shoelace formula for polygon area
                    return abs(area(points))
        elif dxftype == 'POLYLINE':
             if entity.is_closed:
                # 2D Polyline only
                points = [v.dxf.location[:2] for v in entity.vertices]
                if len(points) < 3: return 0.0
                return abs(area(points))
        elif dxftype == 'HATCH':
            # Hatch area is complex, simplified for single boundary
            return entity.area if hasattr(entity, 'area') else 0.0
    except Exception:
        pass
    return 0.0

def validate_text_content(text_str, layer_name):
    """Validate text content based on layer name suffixes"""
    clean_text = text_str.strip().upper()
    
    # Rule 1: Capacity (CAPACITY_L=n) -> Expect Integer
    if 'CAPACITY_L' in layer_name:
        # Allow "1000", "1000L", "1000 L"
        match = re.match(r'^(\d+)\s*L?$', clean_text)
        if not match:
            return False, "Expected numeric capacity (e.g. '5000' or '5000L')"
            
    # Rule 2: Voltage (VOLTAGE_KV=n) -> Expect Number
    elif 'VOLTAGE_KV' in layer_name:
        # Allow "11", "11KV", "11 KV", "11.5"
        match = re.match(r'^(\d+(\.\d+)?)\s*(KV)?$', clean_text)
        if not match:
             return False, "Expected numeric voltage (e.g. '11' or '11KV')"
             
    # Rule 3: Height/Width/Slope (General number check)
    elif any(x in layer_name for x in ['_HEIGHT', '_WIDTH', '_SLOPE']):
        # Simple number check
        match = re.match(r'^(\d+(\.\d+)?)\s*[A-Z%]*$', clean_text)
        if not match:
            return False, "Expected numeric value"
            
    return True, None

def validate_dxf_content(doc, master_rules):
    """Validate DXF content against master rules, checking units and layer specifications"""
    errors = []
    warnings = []
    
    # Master rules passed as argument

    
    # 1. Validate DXF unit settings (must be Meters, Decimal, Decimal Degrees)
    units = doc.header.get('$INSUNITS', 0)
    if units != 6:
        unit_names = {0: 'Unitless', 1: 'Inches', 2: 'Feet', 4: 'Millimeters', 5: 'Centimeters', 6: 'Meters'}
        found_unit = unit_names.get(units, f"Custom ({units})")
        errors.append(f"Drawing unit must be Meter ($INSUNITS=6). Found: {found_unit}")
        
    lunits = doc.header.get('$LUNITS', 0)
    if lunits != 2:
        lunit_names = {1: 'Scientific', 2: 'Decimal', 3: 'Engineering', 4: 'Architectural', 5: 'Fractional'}
        found_lunit = lunit_names.get(lunits, str(lunits))
        errors.append(f"Drawing unit length type must be Decimal ($LUNITS=2). Found: {found_lunit}")
        
    aunits = doc.header.get('$AUNITS', 0)
    if aunits != 0:
        aunit_names = {0: 'Decimal Degrees', 1: 'Deg/Min/Sec', 2: 'Gradians', 3: 'Radians', 4: 'Surveyor'}
        found_aunit = aunit_names.get(aunits, str(aunits))
        errors.append(f"Drawing unit angle type must be Decimal Degrees ($AUNITS=0). Found: {found_aunit}")
        
    # Check linear unit precision (warning only)
    luprec = doc.header.get('$LUPREC', 0)
    if luprec != 2:
        warnings.append(f"Linear unit precision should be 0.00 ($LUPREC=2). Found: {luprec}")

    # 2. Perform layer analysis and validation
    dxf_layers = {layer.dxf.name: layer for layer in doc.layers}
    
    # Extract allowed occupancy colors from BLT_UP_AREA layers
    occupancy_colors = set()
    blt_up_pattern = re.compile(r'^BLK_-?\d+_FLR_-?\d+_BLT_UP_AREA$')
    
    for name, layer in dxf_layers.items():
        if blt_up_pattern.match(name):
            occupancy_colors.add(layer.dxf.color)
            # Include true color if present
            if layer.dxf.hasattr('true_color'):
                occupancy_colors.add(layer.dxf.true_color)

    # Compile regex patterns from master rules for efficient matching
    compiled_rules = []
    mandatory_rules = []
    
    for rule in master_rules:
        pattern = parse_layer_pattern(rule['Layer Name'])
        compiled_rule = {
            'regex': re.compile(pattern),
            'rule': rule
        }
        compiled_rules.append(compiled_rule)
        
        # Track mandatory rules
        if rule.get('Requirement', '').lower().startswith('mandatory'):
            mandatory_rules.append(compiled_rule)

    # 3. Check for Missing Mandatory Layers
    existing_layer_names = set(dxf_layers.keys())
    for mr in mandatory_rules:
        rule = mr['rule']
        regex = mr['regex']
        
        # Check if any existing layer matches this mandatory rule
        match_found = False
        for layer_name in existing_layer_names:
            if regex.match(layer_name):
                match_found = True
                break
        
        if not match_found:
            errors.append(f"Missing Mandatory Layer: {rule['Layer Name']} (Feature: {rule.get('Feature', 'Unknown')})")

    # Validate each layer in the DXF
    validated_layers = []
    
    for name, layer in dxf_layers.items():
        # Ignore special and excluded layers
        if name in IGNORED_LAYERS:
            continue
            
        matched_rules = []
        for cr in compiled_rules:
            if cr['regex'].match(name):
                matched_rules.append(cr['rule'])
        
        layer_info = {
            'name': name,
            'status': 'valid',
            'messages': []
        }
        
        if not matched_rules:
            layer_info['status'] = 'warning'
            layer_info['messages'].append("Layer not found in master guidelines")
            warnings.append(f"Layer '{name}': Unknown layer not in guidelines")
        else:
            # Check if layer matches ANY of the allowed configurations
            # If multiple rules match, we allow the layer if it satisfies ANY of them
            # This handles cases where the same layer name pattern is used for multiple features with different colors
            
            valid_match_found = False
            allowed_colors = []
            allowed_types = []
            
            for rule in matched_rules:
                required_color = rule['Color Code']
                required_type = rule['Type'] # Keep track of types too
                allowed_colors.append(required_color)
                allowed_types.append(required_type)
                
                current_color = layer.dxf.color
                current_true_color = layer.dxf.true_color if layer.dxf.hasattr('true_color') else None
                
                color_valid = False
                
                if required_color in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                    if current_color in occupancy_colors or (current_true_color is not None and current_true_color in occupancy_colors):
                        color_valid = True
                    elif not occupancy_colors:
                        color_valid = False 
                    else:
                        color_valid = False
                elif required_color.startswith("RGB"):
                    try:
                        parts = [int(x.strip()) for x in required_color.replace('RGB', '').split(',')]
                        if len(parts) == 3:
                            expected_int = colors.rgb2int((parts[0], parts[1], parts[2]))
                            if current_true_color == expected_int:
                                color_valid = True
                    except:
                        pass
                elif required_color in ["Any", "NA", "N/A", "ANY"]:
                    color_valid = True
                else:
                    # Handle complex color codes like "1, 2, 3", "1 (M)"
                    try:
                        allowed_list = []
                        for part in str(required_color).split(','):
                            match = re.search(r'(\d+)', part)
                            if match:
                                allowed_list.append(int(match.group(1)))
                        
                        if current_color in allowed_list:
                            color_valid = True
                    except:
                        pass
                
                if color_valid:
                    valid_match_found = True
                    # If color matched, we still need to validate Entity Type and Geometry for this rule
                    # But we don't break immediately if we want to support "multiple valid rules" scenarios fully
                    # However, strictly speaking, if it matches a rule name and color, it SHOULD match that rule's type.
                    # Let's keep valid_match_found = True but flag issues if Type/Geometry fail.
                    break
            
            # --- Enhanced Validation: Entity Type & Geometry ---
            # We check against the BEST matching rule (where color matched). 
            # If no color matched, we check against ALL matched rules (ambiguous, but best effort).
            
            rules_to_check = []
            if valid_match_found:
                # Find the specific rule that matched color
                for rule in matched_rules:
                    # Re-verify color match to find the specific rule
                    # (Refactoring note: could optimize to capture this index above)
                    r_color = rule['Color Code']
                    c_valid = False
                    
                    # ... (Simple logic copy to re-confirm) ...
                    # For simplicity, if we found a valid match, we assume the first rule 
                    # that matches color is the intended one.
                    # Or we just check all matched rules? 
                    # Better: Check all matched rules. If ANY is fully valid (Color + Type + Geometry), it's Valid.
                    pass
                rules_to_check = matched_rules # Check all candidate rules
            else:
                rules_to_check = matched_rules

            # Reset status to re-evaluate based on Type/Geometry
            # If valid_match_found was True (Color OK), we start as Valid, but might downgrade to Error/Warning
            # If valid_match_found was False (Color Fail), we start as Error.
            
            final_layer_status = 'valid' if valid_match_found else 'error'
            type_errors = []
            geometry_errors = []
            
            # Retrieve entities once
            msp = doc.modelspace()
            layer_entities = msp.query(f'*[layer=="{name}"]')
            
            # --- Phase 2: Data Extraction & Validation ---
            layer_data = [] # To store "Area: 50sqm" or "Text: 5000L"
            total_layer_area = 0.0
            text_values = []
            
            if len(layer_entities) == 0:
                 # Empty layer - usually not an error unless mandatory (handled elsewhere), but good to note
                 pass
            else:
                # For each candidate rule, check if entities comply
                # We need at least ONE rule where (Color matches AND Type matches AND Geometry matches)
                
                fully_compliant_rule_found = False
                
                # Check for "Single Value" constraint (from user request 2)
                is_single_value_layer = any('VOLTAGE' in r['Layer Name'] for r in rules_to_check)
                
                for rule in rules_to_check:
                    required_type = rule.get('Type')
                    required_color = rule.get('Color Code')
                    
                    # 1. Check Color (Reuse previous result logic ideally, but re-evaluating for clarity)
                    # ... We already know if 'valid_match_found' (color ok) for at least one rule.
                    
                    # Let's simplify: 
                    # If Color is Wrong -> Error (already handled).
                    # If Color is OK -> Check Type & Geometry.
                    
                    valid_dxf_types = ENTITY_TYPE_MAPPING.get(required_type)
                    if not valid_dxf_types and required_type:
                        # Fallback for unknown types or "Any"
                        valid_dxf_types = set() 
                    
                    rule_type_valid = True
                    rule_geometry_valid = True
                    rule_text_valid = True
                    
                    current_type_errors = []
                    current_geometry_errors = []
                    current_text_errors = []
                    
                    # Reset calculations for this rule iteration
                    current_rule_area = 0.0
                    current_rule_texts = []
                    
                    for e in layer_entities:
                        dxftype = e.dxftype()
                        
                        # Type Check
                        if valid_dxf_types and dxftype not in valid_dxf_types:
                             rule_type_valid = False
                             current_type_errors.append(f"Invalid Entity: Found '{dxftype}' on layer requiring '{required_type}'")
                        
                        # Geometry Check (Closed Polygon) & Area Calculation
                        if required_type == "Polygon" and dxftype in ('LWPOLYLINE', 'POLYLINE', 'HATCH'):
                            is_closed = False
                            if hasattr(e, 'is_closed') and e.is_closed:
                                is_closed = True
                            elif dxftype == 'HATCH':
                                is_closed = True # Hatches are generally closed areas
                            else:
                                # Check start/end points manually
                                try:
                                    if dxftype == 'LWPOLYLINE':
                                        pts = e.get_points()
                                        if len(pts) > 2 and pts[0] == pts[-1]: is_closed = True
                                    elif dxftype == 'POLYLINE':
                                        pts = list(e.points())
                                        if len(pts) > 2 and pts[0] == pts[-1]: is_closed = True
                                except: pass
                            
                            if not is_closed:
                                rule_geometry_valid = False
                                current_geometry_errors.append("Open Polygon detected. Area cannot be calculated.")
                            else:
                                # Valid closed polygon - Calculate Area
                                current_rule_area += calculate_entity_area(e)

                        # Text Content Validation
                        if required_type == "Text" and dxftype in ('TEXT', 'MTEXT'):
                            text_content = e.dxf.text if hasattr(e.dxf, 'text') else ""
                            is_valid_text, err_msg = validate_text_content(text_content, name)
                            if not is_valid_text:
                                rule_text_valid = False
                                current_text_errors.append(f"Invalid Text: '{text_content}' ({err_msg})")
                            current_rule_texts.append(text_content)

                    if rule_type_valid and rule_geometry_valid and rule_text_valid:
                        # Re-verify color for this specific rule
                        this_rule_color_valid = False
                        if required_color in ["Any", "NA", "N/A", "ANY"]:
                             this_rule_color_valid = True
                        elif required_color in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                            if layer.dxf.color in occupancy_colors: this_rule_color_valid = True
                            if layer.dxf.hasattr('true_color') and layer.dxf.true_color in occupancy_colors: this_rule_color_valid = True
                        else:
                             # For simplification, relying on earlier color check for candidate selection
                             pass
                        
                        if valid_match_found: 
                             fully_compliant_rule_found = True
                             
                             # Store Data for Display (Area / Text) if this rule matched
                             if required_type == "Polygon" and current_rule_area > 0:
                                 total_layer_area = current_rule_area
                             if required_type == "Text" and current_rule_texts:
                                 text_values = current_rule_texts

                    if not rule_type_valid:
                        type_errors.extend(current_type_errors)
                    if not rule_geometry_valid:
                        geometry_errors.extend(current_geometry_errors)
                    if not rule_text_valid:
                        current_text_errors = list(set(current_text_errors)) # Dedup
                        # Add to messages directly here or later? 
                        # Let's collect them
                        type_errors.extend(current_text_errors) # Treat text content errors as type/data errors

                # Summarize findings
                # If we had a color match, but Type/Geometry failed for ALL matching rules -> Error
                if valid_match_found:
                    if not fully_compliant_rule_found:
                        # Report errors from the first matching rule (or unique errors) to avoid spam
                        if type_errors:
                            final_layer_status = 'error'
                            layer_info['messages'].extend(sorted(list(set(type_errors)))[:3]) # Limit msgs
                        if geometry_errors:
                            final_layer_status = 'error'
                            layer_info['messages'].extend(sorted(list(set(geometry_errors)))[:3])
                    else:
                        # Valid Layer - Add Data Info
                        if total_layer_area > 0:
                            layer_data.append(f"Area: {total_layer_area:.2f} sq.m")
                        
                        if text_values:
                            # Single Value Constraint Check
                            unique_texts = sorted(list(set(text_values)))
                            if is_single_value_layer and len(unique_texts) > 1:
                                final_layer_status = 'error'
                                layer_info['messages'].append(f"Multiple values found for Voltage: {', '.join(unique_texts)}. Expected single unique value.")
                            else:
                                layer_data.append(f"Text: {', '.join(unique_texts[:3])}" + ("..." if len(unique_texts)>3 else ""))
                
            layer_info['status'] = final_layer_status
            layer_info['data_attributes'] = layer_data # New field for UI

            # Check if layer color matches any of the rules
            for rule in matched_rules:
                required_color = rule['Color Code']
                required_type = rule['Type']
                allowed_colors.append(required_color)
                allowed_types.append(required_type)
                
                # Check Layer Color
                if required_color in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                    if layer.dxf.color in occupancy_colors:
                        valid_match_found = True
                    # Check True Color
                    if layer.dxf.hasattr('true_color') and layer.dxf.true_color in occupancy_colors:
                        valid_match_found = True
                elif required_color.startswith("RGB"):
                    try:
                        parts = [int(x.strip()) for x in required_color.replace('RGB', '').split(',')]
                        if len(parts) == 3:
                            expected_int = colors.rgb2int((parts[0], parts[1], parts[2]))
                            if layer.dxf.hasattr('true_color') and layer.dxf.true_color == expected_int:
                                valid_match_found = True
                    except:
                        pass
                elif required_color in ["Any", "NA", "N/A", "ANY"]:
                    valid_match_found = True
                else:
                    # Handle complex color codes like "1, 2, 3", "1 (M)"
                    try:
                        allowed_list = []
                        for part in str(required_color).split(','):
                            match = re.search(r'(\d+)', part)
                            if match:
                                allowed_list.append(int(match.group(1)))
                        
                        if layer.dxf.color in allowed_list:
                            valid_match_found = True
                    except:
                        pass
                
                if valid_match_found:
                    break
            
            # If layer color is invalid, check if all entities have valid explicit colors
            if not valid_match_found and layer_info['status'] == 'error':
                # Build set of allowed color codes for validation
                allowed_code_set = set()
                for c in allowed_colors:
                    if c in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                        allowed_code_set.update(occupancy_colors)
                    elif c.startswith("RGB"):
                        try:
                            parts = [int(x.strip()) for x in c.replace('RGB', '').split(',')]
                            if len(parts) == 3:
                                expected_int = colors.rgb2int((parts[0], parts[1], parts[2]))
                                allowed_code_set.add(expected_int)
                        except: pass
                    elif c in ["Any", "NA", "N/A", "ANY"]:
                        allowed_code_set.add("Any")
                    else:
                        # Handle complex color codes like "1, 2, 3", "1 (M)"
                        try:
                            for part in str(c).split(','):
                                match = re.search(r'(\d+)', part)
                                if match:
                                    allowed_code_set.add(int(match.group(1)))
                        except: pass

                # Check entities
                msp = doc.modelspace()
                layer_entities = msp.query(f'*[layer=="{name}"]')
                
                if len(layer_entities) > 0:
                    all_entities_valid = True
                    for e in layer_entities:
                        e_color = e.dxf.color
                        e_true_color = e.dxf.true_color if e.dxf.hasattr('true_color') else None
                        
                        entity_valid = False
                        
                        # ByLayer (256) inherits invalid layer color
                        if e_color == 256:
                            entity_valid = False
                        # ByBlock (0) is not acceptable
                        elif e_color == 0:
                             entity_valid = False
                        elif "Any" in allowed_code_set:
                            entity_valid = True
                        else:
                            if e_color in allowed_code_set:
                                entity_valid = True
                            elif e_true_color is not None and e_true_color in allowed_code_set:
                                entity_valid = True
                        
                        if not entity_valid:
                            all_entities_valid = False
                            break
                    
                    if all_entities_valid:
                        # Accept layer if all entities have valid explicit colors
                        layer_info['status'] = 'valid'
                        valid_match_found = True
            
            if not valid_match_found:
                layer_info['status'] = 'error'
                # Get unique allowed colors for error message
                unique_colors = sorted(list(set(allowed_colors)))
                
                # Expand "As per Sub-Occupancy" for better error message
                expanded_colors = []
                for c in unique_colors:
                    if c in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                        if not occupancy_colors:
                            expanded_colors.append("As per Sub-Occupancy (No valid BLT_UP_AREA layers found to define colors)")
                        else:
                            occ_list = sorted([str(oc) for oc in occupancy_colors])
                            expanded_colors.append(f"As per Sub-Occupancy ({', '.join(occ_list)})")
                    else:
                        expanded_colors.append(c)
                
                msg = f"Incorrect color. Expected one of: {', '.join(expanded_colors)}, Found: {layer.dxf.color}"
                if layer.dxf.hasattr('true_color'):
                    msg += f" (True Color {layer.dxf.true_color})"
                layer_info['messages'].append(msg)
                errors.append(f"Layer '{name}': {msg}")

        validated_layers.append(layer_info)

    return {
        'success': True,
        'layers': validated_layers,  # List of validated layer dictionaries
        'count': len(dxf_layers),
        'errors': errors,
        'warnings': warnings,
        'dxf_version': doc.dxfversion
    }

@app.route('/', methods=['GET'])
def index():
    """Display the upload form"""
    return render_template('index.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin panel for updating master validation rules JSON file"""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)
            
        if file and file.filename and file.filename.endswith('.json'):
            try:
                # Verify valid JSON before saving
                content = json.load(file.stream)
                # Save to disk
                with open(app.config['MASTER_JSON'], 'w') as f:
                    json.dump(content, f, indent=4)
                flash('Master data updated successfully', 'success')
            except Exception as e:
                flash(f'Invalid JSON file: {str(e)}', 'error')
        else:
            flash('Please upload a .json file', 'error')
            
    return render_template('admin.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Process uploaded DXF/ZIP file and return validation results"""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if not file.filename:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload a .dxf or .zip file', 'error')
        return redirect(url_for('index'))
    
    filepath = None
    extract_dir = None
    
    try:
        filename = secure_filename(file.filename)
        if not filename:
            raise Exception("Invalid filename")
            
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        target_dxf = filepath
        
        # Extract DXF from ZIP if necessary
        if filename.lower().endswith('.zip'):
            extract_dir = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{os.path.splitext(filename)[0]}")
            os.makedirs(extract_dir, exist_ok=True)
            
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
                
            # Find first DXF in extracted files
            found_dxf = False
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith('.dxf'):
                        target_dxf = os.path.join(root, f)
                        found_dxf = True
                        break
                if found_dxf:
                    break
            
            if not found_dxf:
                raise Exception("No .dxf file found in the zip archive")

        # Load master validation rules based on selection
        rules_source = request.form.get('rules_source', 'odisha')
        master_rules = []
        rules_source_name = "Odisha Rules"

        if rules_source == 'odisha':
            rules_path = app.config['MASTER_JSON']
            if os.path.exists(rules_path):
                with open(rules_path, 'r') as f:
                    master_rules = json.load(f)
            rules_source_name = "Odisha Rules"
        elif rules_source == 'ppa':
            rules_path = os.path.join(os.path.dirname(__file__), 'ppa_layers.json')
            if os.path.exists(rules_path):
                with open(rules_path, 'r') as f:
                    master_rules = json.load(f)
            else:
                raise Exception("PPA Rules file not found on server")
            rules_source_name = "PPA Rules"
        elif rules_source == 'custom':
            if 'custom_rules_file' not in request.files:
                raise Exception("No custom rules file uploaded")
            
            cfile = request.files['custom_rules_file']
            if cfile.filename == '':
                raise Exception("No custom rules file selected")
                
            if cfile and cfile.filename.endswith('.json'):
                try:
                    master_rules = json.load(cfile.stream)
                    rules_source_name = f"Custom Rules ({cfile.filename})"
                except Exception as e:
                    raise Exception(f"Invalid JSON in custom rules file: {str(e)}")
            else:
                raise Exception("Custom rules file must be a .json file")

        # Read and validate DXF file
        try:
            doc = ezdxf.readfile(target_dxf)
            result = validate_dxf_content(doc, master_rules)
            result['filename'] = filename
            result['rules_source_name'] = rules_source_name
        except Exception as e:
            raise Exception(f"Error parsing DXF: {str(e)}")
        
        # Clean up temporary files
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        
        return render_template('results.html', **result)
        
    except Exception as e:
        # Clean up on error
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    flash('File is too large. Maximum size is 100 MB', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
