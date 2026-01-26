import os
from flask import Flask, render_template, request, flash, redirect, url_for
from werkzeug.utils import secure_filename
import ezdxf

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB limit
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'dxf'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    """Check if the uploaded file has a .dxf extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_layers(dxf_path):
    """
    Extract layer information from a DXF file
    
    Args:
        dxf_path: Path to the DXF file
        
    Returns:
        dict: Contains layers list, count, and file info
        
    Raises:
        Exception: If DXF parsing fails
    """
    try:
        # Read the DXF file
        doc = ezdxf.readfile(dxf_path)
        
        # Get all layers from the layer table
        layers = []
        layer_table = doc.layers
        
        for layer in layer_table:
            layers.append(layer.dxf.name)
        
        # Sort layers alphabetically
        layers.sort()
        
        # Get DXF version info
        dxf_version = doc.dxfversion
        
        return {
            'layers': layers,
            'count': len(layers),
            'dxf_version': dxf_version,
            'success': True
        }
        
    except ezdxf.DXFStructureError as e:
        raise Exception(f"Invalid DXF file structure: {str(e)}")
    except ezdxf.DXFVersionError as e:
        raise Exception(f"Unsupported DXF version: {str(e)}")
    except Exception as e:
        raise Exception(f"Error parsing DXF file: {str(e)}")


@app.route('/', methods=['GET'])
def index():
    """Display the upload form"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and display layer information"""
    
    # Check if file was uploaded
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    # Check if filename is empty
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    # Validate file extension
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload a .dxf file', 'error')
        return redirect(url_for('index'))
    
    filepath = None
    try:
        # Secure the filename and save
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract layer information
        result = extract_layers(filepath)
        
        # Clean up the uploaded file
        os.remove(filepath)
        
        # Render results
        return render_template('results.html', 
                             layers=result['layers'],
                             count=result['count'],
                             filename=filename,
                             dxf_version=result['dxf_version'])
        
    except Exception as e:
        # Clean up file if it exists
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        
        flash(f'Error processing file: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    flash('File is too large. Maximum size is 100 MB', 'error')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
