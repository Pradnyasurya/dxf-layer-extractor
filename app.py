import os
import json
import zipfile
import re
import shutil
from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename
import ezdxf
from ezdxf import colors

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit
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

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    """Check if the uploaded file has a valid extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_layer_pattern(pattern_name):
    """Convert JSON layer name pattern to regex"""
    # Escape special characters but preserve 'n' for replacement
    escaped = re.escape(pattern_name)
    # Replace 'n' with '\d+' (one or more digits)
    # We need to be careful not to replace 'n' in words like 'Green', but the patterns seem to use 'n' as a standalone or specific marker
    # Looking at "BLK_n_COVERED_AREA", "RWH_CAPACITY_L=n".
    # It seems safe to replace "_n_" with "_\d+_" or "_n$" with "_\d+$" or "=n" with "=\d+".
    # A simpler approach: split by underscores and other delimiters?
    # Let's try replacing specific 'n' occurrences.
    
    # Actually, looking at the JSON, 'n' appears in:
    # BLK_n_...
    # ..._LVL_n_...
    # ..._FLR_n_...
    # ..._UNIT_n...
    # ...=n
    # ..._STAIR_n...
    
    regex = escaped.replace(r'\ n', r'\d+') # If re.escape escapes space (it usually doesn't for alphanumeric)
    # re.escape('BLK_n_COVERED_AREA') -> 'BLK_n_COVERED_AREA' (in python 3.7+ some chars aren't escaped)
    # Let's just do string replacement on the raw pattern before regex compile, assuming 'n' is the variable.
    # To avoid replacing 'n' in "Green", we should check context.
    # Most 'n's are preceded by underscore or equals or space, or valid separators.
    
    # Strategy: Replace 'n' with '\d+' or '-?\d+' (negative supported)
    # But wait, "Green" has 'n'. "Open" has 'n'.
    # We only want to replace 'n' that stands for a number.
    # In the JSON examples: "BLK_n_", "L=n", "FLR_n_".
    # It seems 'n' is always a standalone component separated by `_` or `=`.
    
    # pattern = pattern_name.replace('n', r'-?\d+')
    # Fix: "Green" -> "Gree\d+". Bad.
    
    # Better strategy: match specific placeholders
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
    
    # Handle "BLK_1_LVL_0_SIDE_SETBACK1" vs "BLK_n_LVL_n_SIDE_SETBACKn"? 
    # The JSON has specific numbers sometimes (e.g. SIDE_SETBACK1).
    
    # If the layer name in JSON has no 'n' placeholders but is just text (e.g. "PLOT BOUNDARY"), strict match.
    if regex_pattern == pattern_name:
        return f"^{re.escape(pattern_name)}$"
    
    return f"^{regex_pattern}$"

def get_master_rules():
    """Load and parse master rules from JSON"""
    if not os.path.exists(app.config['MASTER_JSON']):
        return []
    with open(app.config['MASTER_JSON'], 'r') as f:
        return json.load(f)

def validate_dxf_content(doc):
    """Validate DXF content against master rules"""
    errors = []
    warnings = []
    
    # Load rules
    master_rules = get_master_rules()
    
    # 1. Unit Settings Validation
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
        
    # Check Precision (Warning)
    luprec = doc.header.get('$LUPREC', 0)
    if luprec != 2:
        warnings.append(f"Linear unit precision should be 0.00 ($LUPREC=2). Found: {luprec}")

    # 2. Layer Analysis
    dxf_layers = {layer.dxf.name: layer for layer in doc.layers}
    
    # Find allowed occupancy colors from BLT_UP_AREA layers
    occupancy_colors = set()
    blt_up_pattern = re.compile(r'^BLK_-?\d+_FLR_-?\d+_BLT_UP_AREA$')
    
    for name, layer in dxf_layers.items():
        if blt_up_pattern.match(name):
            occupancy_colors.add(layer.dxf.color)
            # If layer has true color, add that too (as int)
            if layer.dxf.hasattr('true_color'):
                occupancy_colors.add(layer.dxf.true_color)

    # Compile rules for matching
    # Map regex pattern -> rule object
    compiled_rules = []
    for rule in master_rules:
        pattern = parse_layer_pattern(rule['Layer Name'])
        compiled_rules.append({
            'regex': re.compile(pattern),
            'rule': rule
        })

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
                
                if required_color == "As per Sub-Occupancy":
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
                elif required_color in ["Any", "NA", "N/A"]:
                    color_valid = True
                else:
                    try:
                        if int(required_color) == current_color:
                            color_valid = True
                    except ValueError:
                        pass
                
                if color_valid:
                    valid_match_found = True
                    break
            
            # Check if layer color matches any of the rules
            for rule in matched_rules:
                required_color = rule['Color Code']
                required_type = rule['Type']
                allowed_colors.append(required_color)
                allowed_types.append(required_type)
                
                # Check Layer Color
                if required_color == "As per Sub-Occupancy":
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
                elif required_color in ["Any", "NA", "N/A"]:
                    valid_match_found = True
                else:
                    try:
                        if int(required_color) == layer.dxf.color:
                            valid_match_found = True
                    except ValueError:
                        pass
                
                if valid_match_found:
                    break
            
            # If layer color is invalid, check entities
            if not valid_match_found:
                # Prepare allowed color set for efficient checking
                allowed_code_set = set()
                for c in allowed_colors:
                    if c == "As per Sub-Occupancy":
                        allowed_code_set.update(occupancy_colors)
                    elif c.startswith("RGB"):
                        try:
                            parts = [int(x.strip()) for x in c.replace('RGB', '').split(',')]
                            if len(parts) == 3:
                                expected_int = colors.rgb2int((parts[0], parts[1], parts[2]))
                                allowed_code_set.add(expected_int)
                        except: pass
                    elif c in ["Any", "NA", "N/A"]:
                        allowed_code_set.add("Any")
                    else:
                        try:
                            allowed_code_set.add(int(c))
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
                        
                        if e_color == 256: # ByLayer -> Inherits bad layer color
                            entity_valid = False
                        elif e_color == 0: # ByBlock -> Assume bad
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
                        layer_info['status'] = 'valid' # Accepted because all entities are compliant
                        valid_match_found = True # Override failure
            
            if not valid_match_found:
                layer_info['status'] = 'error'
                # Remove duplicates from allowed list
                unique_colors = sorted(list(set(allowed_colors)))
                
                # Expand "As per Sub-Occupancy" for better error message
                expanded_colors = []
                for c in unique_colors:
                    if c == "As per Sub-Occupancy":
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
        'layers': validated_layers, # List of dicts with validation info
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
    """Handle master JSON upload"""
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
    """Handle file upload and display validation results"""
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
        
        # Handle ZIP
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

        # Process DXF
        try:
            doc = ezdxf.readfile(target_dxf)
            result = validate_dxf_content(doc)
            result['filename'] = filename
        except Exception as e:
            raise Exception(f"Error parsing DXF: {str(e)}")
        
        # Clean up
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
