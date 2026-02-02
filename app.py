"""
DXF Layer Extractor & Validator

A Flask web application that uploads, extracts, and validates layer information
from DXF files against a master JSON rule set (odisha_layers.json).
Supports .dxf and .zip uploads with comprehensive validation.
"""

import os
import json
import zipfile
import io
import re
import shutil
from flask import Flask, render_template, request, flash, redirect, url_for, send_file
from werkzeug.utils import secure_filename
import ezdxf
from ezdxf import colors
from ezdxf.math import area, Vec3
from ezdxf.addons.drawing.frontend import Frontend
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.addons.drawing.svg import SVGBackend
from ezdxf.addons.drawing.properties import Properties, LayoutProperties
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
from comparison_engine import DXFComparator, ChangeType, generate_diff_svg, LayerChange

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Configuration
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload limit
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MASTER_JSON"] = os.path.join(
    os.path.dirname(__file__), "odisha_layers.json"
)

# Database configuration
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///dxf_versions.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize database
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"


# User Model for Authentication
class User(UserMixin, db.Model):
    """User model for authentication"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_active = db.Column(db.Boolean, default=True)

    # Relationship with versions
    versions = db.relationship("Version", backref="user", lazy=True)

    def set_password(self, password):
        """Hash and set user password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Verify user password"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    return User.query.get(int(user_id))


# Database Models for Version Comparison
class Version(db.Model):
    """Stores metadata about uploaded DXF versions"""

    __tablename__ = "versions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    upload_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    file_hash = db.Column(db.String(64), unique=True, nullable=False)
    file_size = db.Column(db.Integer)
    dxf_version = db.Column(db.String(10))
    total_layers = db.Column(db.Integer)
    project_name = db.Column(db.String(255))
    notes = db.Column(db.Text)

    def __repr__(self):
        return f"<Version {self.id}: {self.original_filename}>"


class LayerSnapshot(db.Model):
    """Stores extracted metrics for each layer at a point in time"""

    __tablename__ = "layer_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("versions.id"), nullable=False)
    layer_name = db.Column(db.String(255), nullable=False)
    entity_count = db.Column(db.Integer, default=0)
    total_area = db.Column(db.Float, default=0.0)
    perimeter = db.Column(db.Float, default=0.0)
    min_x = db.Column(db.Float)
    min_y = db.Column(db.Float)
    max_x = db.Column(db.Float)
    max_y = db.Column(db.Float)
    color = db.Column(db.Integer)
    linetype = db.Column(db.String(50))
    is_visible = db.Column(db.Boolean, default=True)
    geometry_hash = db.Column(db.String(64))

    def __repr__(self):
        return f"<LayerSnapshot {self.layer_name} in Version {self.version_id}>"


class ComparisonResult(db.Model):
    """Stores results of version comparisons"""

    __tablename__ = "comparison_results"

    id = db.Column(db.Integer, primary_key=True)
    base_version_id = db.Column(
        db.Integer, db.ForeignKey("versions.id"), nullable=False
    )
    new_version_id = db.Column(db.Integer, db.ForeignKey("versions.id"), nullable=False)
    comparison_date = db.Column(db.DateTime, default=db.func.current_timestamp())
    added_layers_count = db.Column(db.Integer, default=0)
    removed_layers_count = db.Column(db.Integer, default=0)
    modified_layers_count = db.Column(db.Integer, default=0)
    unchanged_layers_count = db.Column(db.Integer, default=0)
    changes_json = db.Column(db.Text)

    def __repr__(self):
        return f"<ComparisonResult {self.base_version_id} -> {self.new_version_id}>"


ALLOWED_EXTENSIONS = {"dxf", "zip"}

# Layers to ignore during validation (AutoCAD standard + user defined)
IGNORED_LAYERS = {
    "0",
    "Defpoints",
    "PLAN",
    "WALL",
    "elevation",
    "TEXT",
    "column",
    "dim",
    "HATCH",
    "IC",
    "sec-slab",
    "Chajja",
    "win",
    "BUA TOTAL",
    "FORMAT LINE",
    "SEC LINE",
    "ele-1",
    "SEC WALL",
    "SEC DIM",
    "rm text",
    "TEXT-D-W",
    "ELE-2",
    "ELE-3",
    "LANDSCAPE",
    "dw text",
    "Dim.",
    "WALL.",
    "ELE",
    "layer",
    "Layer2",
    "WINDOWS",
    "LS-Tree",
    "RM TXT",
}

# Allowed DXF entity types for each JSON rule type
ENTITY_TYPE_MAPPING = {
    "Polygon": {"LWPOLYLINE", "POLYLINE", "HATCH", "MPOLYGON"},
    "Line": {"LINE", "LWPOLYLINE", "POLYLINE"},
    "Text": {"TEXT", "MTEXT"},
    "Dimension": {"DIMENSION", "ARC_DIMENSION", "LEADER", "MLEADER"},
}

# Ensure upload folder exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def allowed_file(filename):
    """Check if the uploaded file has a valid extension (.dxf or .zip)"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_layer_pattern(pattern_name):
    """Convert JSON layer name pattern to regex, replacing 'n' placeholders with digit matchers"""
    # Replace 'n' placeholders with regex digit patterns
    escaped = re.escape(pattern_name)
    # Replace 'n' with '\d+' (one or more digits)
    # Replace 'n' placeholders in specific contexts (e.g., BLK_n, _n_, =n)
    # Avoids replacing 'n' in words like 'Green' or 'Open'
    regex_pattern = pattern_name
    regex_pattern = regex_pattern.replace("BLK_n", r"BLK_-?\d+")
    regex_pattern = regex_pattern.replace("_n_", r"_-?\d+_")
    if regex_pattern.endswith("_n"):
        regex_pattern = regex_pattern[:-2] + r"_-?\d+"
    regex_pattern = regex_pattern.replace("=n", r"=-?\d+")

    # Special case: "STAIR_n" at end or middle
    regex_pattern = regex_pattern.replace("STAIR_n", r"STAIR_-?\d+")
    regex_pattern = regex_pattern.replace("RAMP_n", r"RAMP_-?\d+")
    regex_pattern = regex_pattern.replace("LIFT_n", r"LIFT_-?\d+")
    regex_pattern = regex_pattern.replace("UNIT_n", r"UNIT_-?\d+")
    regex_pattern = regex_pattern.replace("FLIGHT_n", r"FLIGHT_-?\d+")
    regex_pattern = regex_pattern.replace("LANDING_n", r"LANDING_-?\d+")
    regex_pattern = regex_pattern.replace("ROOM_n", r"ROOM_-?\d+")
    regex_pattern = regex_pattern.replace("FACADE_n", r"FACADE_-?\d+")
    regex_pattern = regex_pattern.replace("AREA_n", r"AREA_-?\d+")
    regex_pattern = regex_pattern.replace("CTI_n", r"CTI_-?\d+")
    regex_pattern = regex_pattern.replace("OHEL_n", r"OHEL_-?\d+")

    # If no placeholders were found, use strict pattern matching
    if regex_pattern == pattern_name:
        return f"^{re.escape(pattern_name)}$"

    return f"^{regex_pattern}$"


def calculate_entity_area(entity):
    """Calculate area of a closed entity (LWPOLYLINE, POLYLINE, HATCH, MPOLYGON)"""
    try:
        dxftype = entity.dxftype()
        if dxftype == "LWPOLYLINE":
            if entity.is_closed:
                # Use ezdxf's internal area calculation if available (newer versions)
                # or manually calculate polygon area
                with entity.points("xy") as points:
                    if len(points) < 3:
                        return 0.0
                    # shoelace formula for polygon area
                    return abs(area(points))
        elif dxftype == "POLYLINE":
            if entity.is_closed:
                # 2D Polyline only
                points = [v.dxf.location[:2] for v in entity.vertices]
                if len(points) < 3:
                    return 0.0
                return abs(area(points))
        elif dxftype == "HATCH":
            # Hatch area is complex, simplified for single boundary
            return entity.area if hasattr(entity, "area") else 0.0
    except Exception:
        pass
    return 0.0


def validate_text_content(text_str, layer_name):
    """Validate text content based on layer name suffixes"""
    clean_text = text_str.strip().upper()

    # Rule 1: Capacity (CAPACITY_L=n) -> Expect Integer
    if "CAPACITY_L" in layer_name:
        # Allow "1000", "1000L", "1000 L"
        match = re.match(r"^(\d+)\s*L?$", clean_text)
        if not match:
            return False, "Expected numeric capacity (e.g. '5000' or '5000L')"

    # Rule 2: Voltage (VOLTAGE_KV=n) -> Expect Number
    elif "VOLTAGE_KV" in layer_name:
        # Allow "11", "11KV", "11 KV", "11.5"
        match = re.match(r"^(\d+(\.\d+)?)\s*(KV)?$", clean_text)
        if not match:
            return False, "Expected numeric voltage (e.g. '11' or '11KV')"

    # Rule 3: Height/Width/Slope (General number check)
    elif any(x in layer_name for x in ["_HEIGHT", "_WIDTH", "_SLOPE"]):
        # Simple number check
        match = re.match(r"^(\d+(\.\d+)?)\s*[A-Z%]*$", clean_text)
        if not match:
            return False, "Expected numeric value"

    return True, None


def get_entity_center(entity):
    """Get a representative center point for an entity for error marking"""
    try:
        dxftype = entity.dxftype()
        if dxftype in ("LWPOLYLINE", "POLYLINE"):
            # Return first point
            if hasattr(entity, "get_points"):
                pts = entity.get_points()
                if pts:
                    return pts[0]
            elif hasattr(entity, "points"):
                pts = list(entity.points())
                if pts:
                    return pts[0]
        elif dxftype == "LINE":
            return entity.dxf.start
        elif dxftype in ("TEXT", "MTEXT", "INSERT", "CIRCLE", "ARC"):
            if entity.dxf.hasattr("insert"):
                return entity.dxf.insert
            elif entity.dxf.hasattr("center"):
                return entity.dxf.center
    except:
        pass
    return (0, 0)  # Fallback


def load_allowed_layers(config_path=None):
    """Load allowed layer names from the PDF layer configuration file."""
    # If no config_path provided, try default locations
    if config_path is None:
        # Try multiple possible locations for the config file
        possible_paths = [
            "/home/pkurane/Downloads/DxfToPdfLayerConfigCat_CD_ALL.json",
            os.path.join(
                os.path.dirname(__file__), "DxfToPdfLayerConfigCat_CD_ALL.json"
            ),
            "DxfToPdfLayerConfigCat_CD_ALL.json",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                config_path = path
                break

    allowed_layers = set()

    if not config_path or not os.path.exists(config_path):
        print(f"DEBUG: Config file not found: {config_path}")
        return allowed_layers

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        # Extract layer names from all sheet configurations
        configs = config.get("DxfToPdfLayerConfigCat_CD_ALL", [])
        for sheet_config in configs:
            for layer_config in sheet_config.get("planPdfLayerConfigs", []):
                layer_name = layer_config.get("layerName", "")
                if layer_name:
                    # Handle wildcard patterns like BLK_*_FLR_*_FLOOR_PLAN
                    if "*" in layer_name:
                        # Convert pattern to regex for matching
                        # BLK_*_FLR_*_FLOOR_PLAN -> BLK_\d+_FLR_\d+_FLOOR_PLAN
                        # Escape other regex special chars
                        pattern = layer_name
                        # First escape special regex chars except *
                        for char in [
                            ".",
                            "+",
                            "?",
                            "^",
                            "$",
                            "(",
                            ")",
                            "[",
                            "]",
                            "{",
                            "}",
                            "|",
                            "\\",
                        ]:
                            pattern = pattern.replace(char, "\\" + char)
                        # Then replace * with digit pattern
                        pattern = pattern.replace("*", r"\d+")
                        allowed_layers.add(("pattern", pattern))
                    else:
                        allowed_layers.add(("exact", layer_name.upper()))

        print(f"DEBUG: Loaded {len(allowed_layers)} allowed layers from {config_path}")
        # Print first few for debugging
        sample = list(allowed_layers)[:10]
        for item in sample:
            print(f"DEBUG: {item}")
    except Exception as e:
        print(f"DEBUG: Error loading config: {e}")
        import traceback

        traceback.print_exc()

    return allowed_layers


# Global cache for allowed layers - initialize as None to force load on first use
ALLOWED_LAYERS_CACHE = None


# Force cache reload on module reload (development)
def reset_allowed_layers_cache():
    """Reset the allowed layers cache to force reload from config file."""
    global ALLOWED_LAYERS_CACHE
    ALLOWED_LAYERS_CACHE = None
    print("DEBUG: Allowed layers cache reset")


def is_layer_allowed(layer_name, allowed_layers):
    """Check if a layer name matches any of the allowed patterns or exact names."""
    layer_upper = layer_name.upper()

    for rule_type, rule_value in allowed_layers:
        if rule_type == "exact" and layer_upper == rule_value:
            return True
        elif rule_type == "pattern":
            # Convert regex pattern back to check for matching
            import re

            try:
                if re.match(rule_value + "$", layer_upper):
                    return True
            except re.error:
                continue

    return False


def generate_preview_svg(doc, error_markers, config_path=None):
    """
    Generate an SVG string of the DXF with error markers.
    Uses ezdxf's SVG output with proper viewBox that matches content bounds.
    If config_path is provided, only layers in that config are shown.
    """
    try:
        from ezdxf import bbox as ezdxf_bbox
        import re

        msp = doc.modelspace()

        # Load allowed layers from config if provided
        allowed_layers = None
        if config_path and os.path.exists(config_path):
            allowed_layers = load_allowed_layers(config_path)
            print(
                f"DEBUG: Loaded {len(allowed_layers)} allowed layers from {config_path}"
            )

        # Get entities for rendering
        target_entities = []
        if allowed_layers:
            # Only include entities on layers from the config
            for entity in msp:
                try:
                    layer_name = entity.dxf.layer
                    if is_layer_allowed(layer_name, allowed_layers):
                        target_entities.append(entity)
                except Exception:
                    pass
            print(
                f"DEBUG: Filtered to {len(target_entities)} entities on allowed layers"
            )
        else:
            # Fallback: show all non-ignored layers
            for entity in msp:
                try:
                    layer_name = entity.dxf.layer
                    if layer_name not in IGNORED_LAYERS:
                        target_entities.append(entity)
                except Exception:
                    pass

        if not target_entities:
            print("DEBUG: No target entities found for preview")
            return None

        # Calculate bounding box of filtered entities
        cache = ezdxf_bbox.Cache()
        bounds = ezdxf_bbox.extents(target_entities, cache=cache)
        if not bounds.has_data:
            return None

        min_x, max_x = bounds.extmin.x, bounds.extmax.x
        min_y, max_y = bounds.extmin.y, bounds.extmax.y
        width = max_x - min_x
        height = max_y - min_y

        # Handle case where all coordinates are the same (single point)
        if width < 0.001:
            width = 100
            min_x -= 50
            max_x += 50
        if height < 0.001:
            height = 100
            min_y -= 50
            max_y += 50

        # Add padding (5%)
        padding = max(width, height) * 0.05
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        width = max_x - min_x
        height = max_y - min_y

        # Add error markers
        marker_layer = "SYS_ERROR_MARKERS"
        if marker_layer not in doc.layers:
            doc.layers.add(marker_layer, color=1)

        marker_radius = max(width, height) * 0.01
        marker_radius = max(marker_radius, 0.5)

        for marker in error_markers:
            x, y = marker["coords"]
            msp.add_circle(
                (x, y),
                radius=marker_radius,
                dxfattribs={"layer": marker_layer, "color": 1},
            )

        # Hide layers not in the allowed list (or ignored layers)
        layers_to_show = set(e.dxf.layer for e in target_entities)
        layers_to_show.add(marker_layer)

        for layer in doc.layers:
            if layer.dxf.name not in layers_to_show:
                layer.off()

        # Render to SVG with explicit page size matching our bounds exactly
        ctx = RenderContext(doc)
        backend = SVGBackend()
        frontend = Frontend(ctx, backend)
        frontend.draw_layout(msp, finalize=True)

        from ezdxf.addons.drawing.layout import Page, Settings

        # Create a page that matches our bounds exactly
        page = Page(width, height)
        svg_string = backend.get_string(page=page, settings=Settings())

        # Restore layers
        for layer in doc.layers:
            layer.on()

        if not svg_string:
            return None

        # Calculate display size for PC browser
        max_display_width = 1400
        max_display_height = 900

        aspect = width / height if height > 0 else 1

        if aspect >= 1:
            disp_width = min(max_display_width, max(900, width * 5))
            disp_height = disp_width / aspect
        else:
            disp_height = min(max_display_height, max(700, height * 5))
            disp_width = disp_height * aspect

        # Replace the SVG dimensions but keep ezdxf's viewBox and transforms
        # ezdxf generates proper viewBox and transform to handle Y-axis flip
        svg_string = re.sub(
            r'width="[^"]*"', f'width="{disp_width:.0f}"', svg_string, count=1
        )
        svg_string = re.sub(
            r'height="[^"]*"', f'height="{disp_height:.0f}"', svg_string, count=1
        )

        # Add background style if not present
        if "style=" not in svg_string[:200]:
            svg_string = re.sub(
                r"<svg", '<svg style="background:#f5f5f5;"', svg_string, count=1
            )

        # Fix white strokes to dark color for visibility on light background
        svg_string = svg_string.replace("stroke: #ffffff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke:#ffffff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke: #fff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke:#fff", "stroke: #2d3748")

        # Fix white fills to light gray
        svg_string = svg_string.replace("fill: #ffffff", "fill: #f0f0f0")
        svg_string = svg_string.replace("fill:#ffffff", "fill: #f0f0f0")

        return svg_string

    except Exception as e:
        print(f"SVG Generation Error: {e}")
        import traceback

        traceback.print_exc()
        return None

        # Calculate bounding box of all entities
        cache = ezdxf_bbox.Cache()
        bounds = ezdxf_bbox.extents(target_entities, cache=cache)
        if not bounds.has_data:
            return None

        min_x, max_x = bounds.extmin.x, bounds.extmax.x
        min_y, max_y = bounds.extmin.y, bounds.extmax.y
        width = max_x - min_x
        height = max_y - min_y

        # Handle case where all coordinates are the same (single point)
        if width < 0.001:
            width = 100
            min_x -= 50
            max_x += 50
        if height < 0.001:
            height = 100
            min_y -= 50
            max_y += 50

        # Add padding (5%)
        padding = max(width, height) * 0.05
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        width = max_x - min_x
        height = max_y - min_y

        # Add error markers
        marker_layer = "SYS_ERROR_MARKERS"
        if marker_layer not in doc.layers:
            doc.layers.add(marker_layer, color=1)

        marker_radius = max(width, height) * 0.01
        marker_radius = max(marker_radius, 0.5)

        for marker in error_markers:
            x, y = marker["coords"]
            msp.add_circle(
                (x, y),
                radius=marker_radius,
                dxfattribs={"layer": marker_layer, "color": 1},
            )

        # Hide ignored layers for cleaner preview
        for layer in doc.layers:
            if layer.dxf.name in IGNORED_LAYERS:
                layer.off()

        # Render to SVG with explicit page size matching our bounds exactly
        ctx = RenderContext(doc)
        backend = SVGBackend()
        frontend = Frontend(ctx, backend)
        frontend.draw_layout(msp, finalize=True)

        from ezdxf.addons.drawing.layout import Page, Settings

        # Create a page that matches our bounds exactly
        page = Page(width, height)
        svg_string = backend.get_string(page=page, settings=Settings())

        # Restore layers
        for layer in doc.layers:
            layer.on()

        if not svg_string:
            return None

        # Calculate display size for PC browser
        max_display_width = 1400
        max_display_height = 900

        aspect = width / height if height > 0 else 1

        if aspect >= 1:
            disp_width = min(max_display_width, max(900, width * 5))
            disp_height = disp_width / aspect
        else:
            disp_height = min(max_display_height, max(700, height * 5))
            disp_width = disp_height * aspect

        # Replace the SVG dimensions but keep ezdxf's viewBox and transforms
        # ezdxf generates proper viewBox and transform to handle Y-axis flip
        svg_string = re.sub(
            r'width="[^"]*"', f'width="{disp_width:.0f}"', svg_string, count=1
        )
        svg_string = re.sub(
            r'height="[^"]*"', f'height="{disp_height:.0f}"', svg_string, count=1
        )

        # Add background style if not present
        if "style=" not in svg_string[:200]:
            svg_string = re.sub(
                r"<svg", '<svg style="background:#f5f5f5;"', svg_string, count=1
            )

        # Fix white strokes to dark color for visibility on light background
        svg_string = svg_string.replace("stroke: #ffffff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke:#ffffff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke: #fff", "stroke: #2d3748")
        svg_string = svg_string.replace("stroke:#fff", "stroke: #2d3748")

        # Fix white fills to light gray
        svg_string = svg_string.replace("fill: #ffffff", "fill: #f0f0f0")
        svg_string = svg_string.replace("fill:#ffffff", "fill: #f0f0f0")

        # Scale down stroke widths - they are too thick in the preview
        # Reduce all stroke widths by 60% to make lines thinner
        def scale_stroke_width(match):
            try:
                width = float(match.group(1))
                # Reduce by 60%, with minimum of 0.3 and maximum of 2.0
                new_width = max(0.3, min(width * 0.4, 2.0))
                return f"stroke-width: {new_width:.2f}"
            except:
                return match.group(0)

        svg_string = re.sub(r"stroke-width:\s*([\d.]+)", scale_stroke_width, svg_string)

        return svg_string

    except Exception as e:
        print(f"SVG Generation Error: {e}")
        import traceback

        traceback.print_exc()
        return None


def get_layer_analysis_data(doc):
    """
    Extract layer analysis data for display in the results table.
    Returns list of dicts with: layer_name, color_hex, color_swatch, line_type, visibility
    """
    layer_analysis = []

    # DXF color to RGB mapping for standard AutoCAD colors
    # Standard AutoCAD colors 1-255 mapped to RGB values
    aci_colors = {
        0: (0, 0, 0),  # ByBlock (special)
        1: (255, 0, 0),  # Red
        2: (255, 255, 0),  # Yellow
        3: (0, 255, 0),  # Green
        4: (0, 255, 255),  # Cyan
        5: (0, 0, 255),  # Blue
        6: (255, 0, 255),  # Magenta
        7: (255, 255, 255),  # White/Black
        8: (128, 128, 128),  # Dark Gray
        9: (192, 192, 192),  # Light Gray
        # Common colors
        10: (255, 0, 0),  # Red
        30: (0, 127, 0),  # Dark Green
        40: (127, 0, 0),  # Dark Red
        50: (127, 63, 0),  # Brown
        80: (127, 127, 0),  # Olive
        100: (255, 127, 0),  # Orange
        120: (127, 0, 127),  # Dark Magenta
        140: (0, 127, 127),  # Dark Cyan
        160: (192, 192, 192),  # Light Gray
        180: (128, 128, 128),  # Dark Gray
    }

    # Default for colors not in mapping
    def get_color_rgb(color_code, true_color=None):
        if true_color is not None and true_color > 0:
            # True color is stored as 24-bit RGB
            r = (true_color >> 16) & 0xFF
            g = (true_color >> 8) & 0xFF
            b = true_color & 0xFF
            return (r, g, b)
        elif color_code in aci_colors:
            return aci_colors[color_code]
        elif color_code == 256:
            # ByLayer - use layer color
            return (128, 128, 128)
        elif color_code == 0:
            # ByBlock
            return (0, 0, 0)
        else:
            # Generate a color based on the index
            # Simple algorithm for colors not in our mapping
            return (
                (color_code * 47) % 256,
                (color_code * 113) % 256,
                (color_code * 179) % 256,
            )

    for layer in doc.layers:
        layer_name = layer.dxf.name

        # Get color
        color_code = layer.dxf.color
        true_color = None
        if layer.dxf.hasattr("true_color"):
            true_color = layer.dxf.true_color

        rgb = get_color_rgb(color_code, true_color)
        color_integer = str(color_code)
        if true_color is not None and true_color > 0:
            color_integer = str(true_color)
        color_swatch = f"rgb({rgb[0]}, {rgb[1]}, {rgb[2]})"

        # Get line type
        line_type = "Continuous"
        if layer.dxf.hasattr("linetype"):
            line_type = layer.dxf.linetype

        # Get visibility
        visibility = "Visible"
        if layer.is_off():
            visibility = "Hidden"
        elif layer.dxf.hasattr("frozen") and layer.dxf.frozen:
            visibility = "Frozen"

        layer_analysis.append(
            {
                "layer_name": layer_name,
                "color_integer": color_integer,
                "color_swatch": color_swatch,
                "line_type": line_type,
                "visibility": visibility,
            }
        )

    # Sort by layer name
    layer_analysis.sort(key=lambda x: x["layer_name"])
    return layer_analysis


def validate_dxf_content(doc, master_rules, config_path=None):
    """Validate DXF content against master rules, checking units and layer specifications"""
    errors = []
    warnings = []
    fix_actions = []  # List of fixable actions for LISP script
    error_markers = []  # List of {'coords': (x,y), 'msg': str} for Visual Preview

    # Master rules passed as argument

    # 1. Validate DXF unit settings (must be Meters, Decimal, Decimal Degrees)
    units = doc.header.get("$INSUNITS", 0)
    if units != 6:
        unit_names = {
            0: "Unitless",
            1: "Inches",
            2: "Feet",
            4: "Millimeters",
            5: "Centimeters",
            6: "Meters",
        }
        found_unit = unit_names.get(units, f"Custom ({units})")
        errors.append(f"Drawing unit must be Meter ($INSUNITS=6). Found: {found_unit}")

    lunits = doc.header.get("$LUNITS", 0)
    if lunits != 2:
        lunit_names = {
            1: "Scientific",
            2: "Decimal",
            3: "Engineering",
            4: "Architectural",
            5: "Fractional",
        }
        found_lunit = lunit_names.get(lunits, str(lunits))
        errors.append(
            f"Drawing unit length type must be Decimal ($LUNITS=2). Found: {found_lunit}"
        )

    aunits = doc.header.get("$AUNITS", 0)
    if aunits != 0:
        aunit_names = {
            0: "Decimal Degrees",
            1: "Deg/Min/Sec",
            2: "Gradians",
            3: "Radians",
            4: "Surveyor",
        }
        found_aunit = aunit_names.get(aunits, str(aunits))
        errors.append(
            f"Drawing unit angle type must be Decimal Degrees ($AUNITS=0). Found: {found_aunit}"
        )

    # Check linear unit precision (warning only)
    luprec = doc.header.get("$LUPREC", 0)
    if luprec != 2:
        warnings.append(
            f"Linear unit precision should be 0.00 ($LUPREC=2). Found: {luprec}"
        )

    # 2. Perform layer analysis and validation
    dxf_layers = {layer.dxf.name: layer for layer in doc.layers}

    # Extract allowed occupancy colors from BLT_UP_AREA layers
    occupancy_colors = set()
    blt_up_pattern = re.compile(r"^BLK_-?\d+_FLR_-?\d+_BLT_UP_AREA$")

    for name, layer in dxf_layers.items():
        if blt_up_pattern.match(name):
            occupancy_colors.add(layer.dxf.color)
            # Include true color if present
            if layer.dxf.hasattr("true_color"):
                occupancy_colors.add(layer.dxf.true_color)

    # Compile regex patterns from master rules for efficient matching
    compiled_rules = []
    mandatory_rules = []

    for rule in master_rules:
        pattern = parse_layer_pattern(rule["Layer Name"])
        compiled_rule = {"regex": re.compile(pattern), "rule": rule}
        compiled_rules.append(compiled_rule)

        # Track mandatory rules
        if rule.get("Requirement", "").lower().startswith("mandatory"):
            mandatory_rules.append(compiled_rule)

    # 3. Check for Missing Mandatory Layers
    existing_layer_names = set(dxf_layers.keys())
    for mr in mandatory_rules:
        rule = mr["rule"]
        regex = mr["regex"]

        # Check if any existing layer matches this mandatory rule
        match_found = False
        for layer_name in existing_layer_names:
            if regex.match(layer_name):
                match_found = True
                break

        if not match_found:
            errors.append(
                f"Missing Mandatory Layer: {rule['Layer Name']} (Feature: {rule.get('Feature', 'Unknown')})"
            )

            # Determine correct color for fix
            fix_color = "7"  # Default white
            required_color = rule.get("Color Code", "7")

            # Try to resolve color code
            if required_color in ["Any", "NA", "N/A", "ANY"]:
                fix_color = "7"
            elif required_color in [
                "As per Sub-Occupancy",
                "As per sub-occupancy type",
            ]:
                # Can't auto-fix safely
                fix_color = None
            elif required_color.startswith("RGB"):
                fix_color = f"T {required_color.replace('RGB', '').strip()}"
            else:
                # Take first number if multiple
                try:
                    parts = str(required_color).split(",")
                    match = re.search(r"(\d+)", parts[0])
                    if match:
                        fix_color = match.group(1)
                except:
                    pass

            if fix_color:
                fix_actions.append(
                    {
                        "type": "create_layer",
                        "layer": rule["Layer Name"],
                        "color": fix_color,
                    }
                )

    # Validate each layer in the DXF
    validated_layers = []

    for name, layer in dxf_layers.items():
        # Ignore special and excluded layers
        if name in IGNORED_LAYERS:
            continue

        matched_rules = []
        for cr in compiled_rules:
            if cr["regex"].match(name):
                matched_rules.append(cr["rule"])

        layer_info = {"name": name, "status": "valid", "messages": []}

        if not matched_rules:
            layer_info["status"] = "warning"
            layer_info["messages"].append("Layer not found in master guidelines")
            warnings.append(f"Layer '{name}': Unknown layer not in guidelines")
        else:
            # Check if layer matches ANY of the allowed configurations
            # If multiple rules match, we allow the layer if it satisfies ANY of them
            # This handles cases where the same layer name pattern is used for multiple features with different colors

            valid_match_found = False
            allowed_colors = []
            allowed_types = []

            for rule in matched_rules:
                required_color = rule["Color Code"]
                required_type = rule["Type"]  # Keep track of types too
                allowed_colors.append(required_color)
                allowed_types.append(required_type)

                current_color = layer.dxf.color
                current_true_color = (
                    layer.dxf.true_color if layer.dxf.hasattr("true_color") else None
                )

                color_valid = False

                if required_color in [
                    "As per Sub-Occupancy",
                    "As per sub-occupancy type",
                ]:
                    if current_color in occupancy_colors or (
                        current_true_color is not None
                        and current_true_color in occupancy_colors
                    ):
                        color_valid = True
                    elif not occupancy_colors:
                        color_valid = False
                    else:
                        color_valid = False
                elif required_color.startswith("RGB"):
                    try:
                        parts = [
                            int(x.strip())
                            for x in required_color.replace("RGB", "").split(",")
                        ]
                        if len(parts) == 3:
                            expected_int = colors.rgb2int(
                                (parts[0], parts[1], parts[2])
                            )
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
                        for part in str(required_color).split(","):
                            match = re.search(r"(\d+)", part)
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
                    r_color = rule["Color Code"]
                    c_valid = False

                    # ... (Simple logic copy to re-confirm) ...
                    # For simplicity, if we found a valid match, we assume the first rule
                    # that matches color is the intended one.
                    # Or we just check all matched rules?
                    # Better: Check all matched rules. If ANY is fully valid (Color + Type + Geometry), it's Valid.
                    pass
                rules_to_check = matched_rules  # Check all candidate rules
            else:
                rules_to_check = matched_rules

            # Reset status to re-evaluate based on Type/Geometry
            # If valid_match_found was True (Color OK), we start as Valid, but might downgrade to Error/Warning
            # If valid_match_found was False (Color Fail), we start as Error.

            final_layer_status = "valid" if valid_match_found else "error"
            type_errors = []
            geometry_errors = []

            # Retrieve entities once
            msp = doc.modelspace()
            layer_entities = msp.query(f'*[layer=="{name}"]')

            # --- Phase 2: Data Extraction & Validation ---
            layer_data = []  # To store "Area: 50sqm" or "Text: 5000L"
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
                is_single_value_layer = any(
                    "VOLTAGE" in r["Layer Name"] for r in rules_to_check
                )

                for rule in rules_to_check:
                    required_type = rule.get("Type")
                    required_color = rule.get("Color Code")

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
                            err_msg = f"Invalid Entity: Found '{dxftype}' on layer requiring '{required_type}'"
                            current_type_errors.append(err_msg)
                            # Add Marker
                            pt = get_entity_center(e)
                            error_markers.append(
                                {"coords": (pt[0], pt[1]), "msg": err_msg}
                            )

                        # Geometry Check (Closed Polygon) & Area Calculation
                        if required_type == "Polygon" and dxftype in (
                            "LWPOLYLINE",
                            "POLYLINE",
                            "HATCH",
                        ):
                            is_closed = False
                            if hasattr(e, "is_closed") and e.is_closed:
                                is_closed = True
                            elif dxftype == "HATCH":
                                is_closed = True  # Hatches are generally closed areas
                            else:
                                # Check start/end points manually
                                try:
                                    if dxftype == "LWPOLYLINE":
                                        pts = e.get_points()
                                        if len(pts) > 2 and pts[0] == pts[-1]:
                                            is_closed = True
                                    elif dxftype == "POLYLINE":
                                        pts = list(e.points())
                                        if len(pts) > 2 and pts[0] == pts[-1]:
                                            is_closed = True
                                except:
                                    pass

                            if not is_closed:
                                rule_geometry_valid = False
                                err_msg = (
                                    "Open Polygon detected. Area cannot be calculated."
                                )
                                current_geometry_errors.append(err_msg)
                                # Add Marker
                                pt = get_entity_center(e)
                                error_markers.append(
                                    {"coords": (pt[0], pt[1]), "msg": err_msg}
                                )
                            else:
                                # Valid closed polygon - Calculate Area
                                current_rule_area += calculate_entity_area(e)

                        # Text Content Validation
                        if required_type == "Text" and dxftype in ("TEXT", "MTEXT"):
                            text_content = e.dxf.text if hasattr(e.dxf, "text") else ""
                            is_valid_text, err_msg = validate_text_content(
                                text_content, name
                            )
                            if not is_valid_text:
                                rule_text_valid = False
                                current_text_errors.append(
                                    f"Invalid Text: '{text_content}' ({err_msg})"
                                )
                            current_rule_texts.append(text_content)

                    if rule_type_valid and rule_geometry_valid and rule_text_valid:
                        # Re-verify color for this specific rule
                        this_rule_color_valid = False
                        if required_color in ["Any", "NA", "N/A", "ANY"]:
                            this_rule_color_valid = True
                        elif required_color in [
                            "As per Sub-Occupancy",
                            "As per sub-occupancy type",
                        ]:
                            if layer.dxf.color in occupancy_colors:
                                this_rule_color_valid = True
                            if (
                                layer.dxf.hasattr("true_color")
                                and layer.dxf.true_color in occupancy_colors
                            ):
                                this_rule_color_valid = True
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
                        current_text_errors = list(set(current_text_errors))  # Dedup
                        # Add to messages directly here or later?
                        # Let's collect them
                        type_errors.extend(
                            current_text_errors
                        )  # Treat text content errors as type/data errors

                # Summarize findings
                # If we had a color match, but Type/Geometry failed for ALL matching rules -> Error
                if valid_match_found:
                    if not fully_compliant_rule_found:
                        # Report errors from the first matching rule (or unique errors) to avoid spam
                        if type_errors:
                            final_layer_status = "error"
                            layer_info["messages"].extend(
                                sorted(list(set(type_errors)))[:3]
                            )  # Limit msgs
                        if geometry_errors:
                            final_layer_status = "error"
                            layer_info["messages"].extend(
                                sorted(list(set(geometry_errors)))[:3]
                            )
                    else:
                        # Valid Layer - Add Data Info
                        if total_layer_area > 0:
                            layer_data.append(f"Area: {total_layer_area:.2f} sq.m")

                        if text_values:
                            # Single Value Constraint Check
                            unique_texts = sorted(list(set(text_values)))
                            if is_single_value_layer and len(unique_texts) > 1:
                                final_layer_status = "error"
                                layer_info["messages"].append(
                                    f"Multiple values found for Voltage: {', '.join(unique_texts)}. Expected single unique value."
                                )
                            else:
                                layer_data.append(
                                    f"Text: {', '.join(unique_texts[:3])}"
                                    + ("..." if len(unique_texts) > 3 else "")
                                )

            layer_info["status"] = final_layer_status
            layer_info["data_attributes"] = layer_data  # New field for UI

            # Check if layer color matches any of the rules
            for rule in matched_rules:
                required_color = rule["Color Code"]
                required_type = rule["Type"]
                allowed_colors.append(required_color)
                allowed_types.append(required_type)

                # Check Layer Color
                if required_color in [
                    "As per Sub-Occupancy",
                    "As per sub-occupancy type",
                ]:
                    if layer.dxf.color in occupancy_colors:
                        valid_match_found = True
                    # Check True Color
                    if (
                        layer.dxf.hasattr("true_color")
                        and layer.dxf.true_color in occupancy_colors
                    ):
                        valid_match_found = True
                elif required_color.startswith("RGB"):
                    try:
                        parts = [
                            int(x.strip())
                            for x in required_color.replace("RGB", "").split(",")
                        ]
                        if len(parts) == 3:
                            expected_int = colors.rgb2int(
                                (parts[0], parts[1], parts[2])
                            )
                            if (
                                layer.dxf.hasattr("true_color")
                                and layer.dxf.true_color == expected_int
                            ):
                                valid_match_found = True
                    except:
                        pass
                elif required_color in ["Any", "NA", "N/A", "ANY"]:
                    valid_match_found = True
                else:
                    # Handle complex color codes like "1, 2, 3", "1 (M)"
                    try:
                        allowed_list = []
                        for part in str(required_color).split(","):
                            match = re.search(r"(\d+)", part)
                            if match:
                                allowed_list.append(int(match.group(1)))

                        if layer.dxf.color in allowed_list:
                            valid_match_found = True
                    except:
                        pass

                if valid_match_found:
                    break

            # If layer color is invalid, check if all entities have valid explicit colors
            if not valid_match_found and layer_info["status"] == "error":
                # Build set of allowed color codes for validation
                allowed_code_set = set()
                for c in allowed_colors:
                    if c in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                        allowed_code_set.update(occupancy_colors)
                    elif c.startswith("RGB"):
                        try:
                            parts = [
                                int(x.strip()) for x in c.replace("RGB", "").split(",")
                            ]
                            if len(parts) == 3:
                                expected_int = colors.rgb2int(
                                    (parts[0], parts[1], parts[2])
                                )
                                allowed_code_set.add(expected_int)
                        except:
                            pass
                    elif c in ["Any", "NA", "N/A", "ANY"]:
                        allowed_code_set.add("Any")
                    else:
                        # Handle complex color codes like "1, 2, 3", "1 (M)"
                        try:
                            for part in str(c).split(","):
                                match = re.search(r"(\d+)", part)
                                if match:
                                    allowed_code_set.add(int(match.group(1)))
                        except:
                            pass

                # Check entities
                msp = doc.modelspace()
                layer_entities = msp.query(f'*[layer=="{name}"]')

                if len(layer_entities) > 0:
                    all_entities_valid = True
                    for e in layer_entities:
                        e_color = e.dxf.color
                        e_true_color = (
                            e.dxf.true_color if e.dxf.hasattr("true_color") else None
                        )

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
                            elif (
                                e_true_color is not None
                                and e_true_color in allowed_code_set
                            ):
                                entity_valid = True

                        if not entity_valid:
                            all_entities_valid = False
                            break

                    if all_entities_valid:
                        # Accept layer if all entities have valid explicit colors
                        layer_info["status"] = "valid"
                        valid_match_found = True

            if not valid_match_found:
                layer_info["status"] = "error"
                # Get unique allowed colors for error message
                unique_colors = sorted(list(set(allowed_colors)))

                # Expand "As per Sub-Occupancy" for better error message
                expanded_colors = []
                fix_color_code = None

                for c in unique_colors:
                    if c in ["As per Sub-Occupancy", "As per sub-occupancy type"]:
                        if not occupancy_colors:
                            expanded_colors.append(
                                "As per Sub-Occupancy (No valid BLT_UP_AREA layers found to define colors)"
                            )
                        else:
                            occ_list = sorted([str(oc) for oc in occupancy_colors])
                            expanded_colors.append(
                                f"As per Sub-Occupancy ({', '.join(occ_list)})"
                            )
                    else:
                        expanded_colors.append(c)
                        # Pick first valid color as fix target if not yet set
                        if not fix_color_code and c not in ["Any", "NA", "N/A", "ANY"]:
                            if str(c).startswith("RGB"):
                                fix_color_code = (
                                    f"T {str(c).replace('RGB', '').strip()}"
                                )
                            else:
                                try:
                                    parts = str(c).split(",")
                                    match = re.search(r"(\d+)", parts[0])
                                    if match:
                                        fix_color_code = match.group(1)
                                except:
                                    pass

                msg = f"Incorrect color. Expected one of: {', '.join(expanded_colors)}, Found: {layer.dxf.color}"
                if layer.dxf.hasattr("true_color"):
                    msg += f" (True Color {layer.dxf.true_color})"
                layer_info["messages"].append(msg)
                errors.append(f"Layer '{name}': {msg}")

                if fix_color_code:
                    fix_actions.append(
                        {"type": "fix_color", "layer": name, "color": fix_color_code}
                    )

        validated_layers.append(layer_info)

    # Generate Preview SVG if errors found (or always?)
    # Generating always is nice for "Preview", but might be slow.
    # Let's generate it.
    # Note: config_path is passed from the caller (upload_file route)
    preview_svg = generate_preview_svg(doc, error_markers, config_path)

    # Generate layer analysis data for the table
    layer_analysis = get_layer_analysis_data(doc)

    return {
        "success": True,
        "layers": validated_layers,  # List of validated layer dictionaries
        "count": len(dxf_layers),
        "errors": errors,
        "warnings": warnings,
        "fix_actions": fix_actions,
        "dxf_version": doc.dxfversion,
        "preview_svg": preview_svg,
        "layer_analysis": layer_analysis,  # Layer analysis data for results table
    }


def store_version_metadata(
    doc, filename, original_filename, filepath, project_name=None
):
    """
    Store version metadata and layer snapshots in database.
    Called after successful DXF validation.
    """
    try:
        # Calculate file hash
        import hashlib

        with open(filepath, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Check if version already exists
        existing = Version.query.filter_by(file_hash=file_hash).first()
        if existing:
            return existing.id

        # Get file size
        file_size = os.path.getsize(filepath)

        # Create version record with user association
        version = Version(
            user_id=current_user.id,
            filename=filename,
            original_filename=original_filename,
            file_hash=file_hash,
            file_size=file_size,
            dxf_version=doc.dxfversion,
            total_layers=len(list(doc.layers)),
            project_name=project_name or os.path.splitext(original_filename)[0],
            notes="",
        )
        db.session.add(version)
        db.session.flush()  # Get version.id

        # Create layer snapshots
        for layer in doc.layers:
            layer_name = layer.dxf.name

            # Extract metrics
            msp = doc.modelspace()
            entities = msp.query(f'*[layer=="{layer_name}"]')

            # Calculate area for closed polygons
            total_area = 0.0
            for entity in entities:
                dxftype = entity.dxftype()
                if (
                    dxftype == "LWPOLYLINE"
                    and hasattr(entity, "is_closed")
                    and entity.is_closed
                ):
                    try:
                        points = list(entity.points())
                        if len(points) >= 3:
                            area = abs(calculate_entity_area(entity))
                            total_area += area
                    except:
                        pass
                elif dxftype == "HATCH" and hasattr(entity, "area"):
                    total_area += entity.area

            # Get bounding box
            min_x, min_y, max_x, max_y = None, None, None, None
            if len(entities) > 0:
                all_x, all_y = [], []
                for entity in entities:
                    try:
                        center = get_entity_center(entity)
                        all_x.append(center[0])
                        all_y.append(center[1])
                    except:
                        pass
                if all_x and all_y:
                    min_x, max_x = min(all_x), max(all_x)
                    min_y, max_y = min(all_y), max(all_y)

            snapshot = LayerSnapshot(
                version_id=version.id,
                layer_name=layer_name,
                entity_count=len(entities),
                total_area=total_area,
                min_x=min_x,
                min_y=min_y,
                max_x=max_x,
                max_y=max_y,
                color=layer.dxf.color if hasattr(layer.dxf, "color") else None,
                linetype=layer.dxf.linetype
                if hasattr(layer.dxf, "linetype")
                else "Continuous",
                is_visible=not layer.is_off(),
            )
            db.session.add(snapshot)

        db.session.commit()
        return version.id

    except Exception as e:
        db.session.rollback()
        print(f"Error storing version metadata: {e}")
        return None


# ============================================================================
# VERSION COMPARISON ROUTES
# ============================================================================


@app.route("/versions", methods=["GET"])
@login_required
def list_versions():
    """List user's stored versions with filtering by project"""
    project = request.args.get("project", None)

    # Filter versions by current user
    query = Version.query.filter_by(user_id=current_user.id)
    if project:
        query = query.filter_by(project_name=project)

    versions = query.order_by(Version.upload_date.desc()).all()

    # Get unique project names for filter dropdown (user's projects only)
    projects = (
        db.session.query(Version.project_name)
        .filter_by(user_id=current_user.id)
        .distinct()
        .all()
    )
    projects = [p[0] for p in projects if p[0]]

    return render_template(
        "versions.html", versions=versions, projects=projects, selected_project=project
    )


@app.route("/compare", methods=["GET", "POST"])
@login_required
def compare_versions():
    """Interface to select and compare two versions"""
    if request.method == "POST":
        base_version_id = request.form.get("base_version_id")
        new_version_id = request.form.get("new_version_id")

        if not base_version_id or not new_version_id:
            flash("Please select both base and new versions", "error")
            return redirect(url_for("compare_versions"))

        if base_version_id == new_version_id:
            flash("Cannot compare a version with itself", "error")
            return redirect(url_for("compare_versions"))

        return redirect(
            url_for("comparison_result", base_id=base_version_id, new_id=new_version_id)
        )

    # GET request - show version selection form (user's versions only)
    project = request.args.get("project", None)
    query = Version.query.filter_by(user_id=current_user.id)
    if project:
        query = query.filter_by(project_name=project)

    versions = query.order_by(Version.upload_date.desc()).all()
    projects = (
        db.session.query(Version.project_name)
        .filter_by(user_id=current_user.id)
        .distinct()
        .all()
    )
    projects = [p[0] for p in projects if p[0]]

    return render_template(
        "compare_select.html",
        versions=versions,
        projects=projects,
        selected_project=project,
    )


@app.route("/compare_result/<int:base_id>/<int:new_id>")
@login_required
def comparison_result(base_id, new_id):
    """Display comparison results between two versions"""
    base_version = Version.query.get_or_404(base_id)
    new_version = Version.query.get_or_404(new_id)

    # Verify user owns both versions
    if (
        base_version.user_id != current_user.id
        or new_version.user_id != current_user.id
    ):
        flash("You don't have permission to compare these versions", "error")
        return redirect(url_for("compare_versions"))

    # Check if comparison already exists
    existing = ComparisonResult.query.filter_by(
        base_version_id=base_id, new_version_id=new_id
    ).first()

    if existing:
        # Use cached results
        changes = json.loads(existing.changes_json)
        summary = {
            "total_layers_base": base_version.total_layers,
            "total_layers_new": new_version.total_layers,
            "added_count": existing.added_layers_count,
            "removed_count": existing.removed_layers_count,
            "modified_count": existing.modified_layers_count,
            "unchanged_count": existing.unchanged_layers_count,
        }
        diff_svg = None  # Diff SVG not stored, would need to regenerate
    else:
        # Perform comparison using stored LayerSnapshots

        # Helper to convert snapshots to metrics dict format expected by comparator
        def snapshots_to_dict(version_id):
            snapshots = LayerSnapshot.query.filter_by(version_id=version_id).all()
            data = {}
            for s in snapshots:
                data[s.layer_name] = {
                    "entity_count": s.entity_count,
                    "total_area": s.total_area,
                    "perimeter": s.perimeter,
                    "min_x": s.min_x,
                    "min_y": s.min_y,
                    "max_x": s.max_x,
                    "max_y": s.max_y,
                    "color": s.color,
                    "linetype": s.linetype,
                    "is_visible": s.is_visible,
                }
            return data

        try:
            base_data = snapshots_to_dict(base_id)
            new_data = snapshots_to_dict(new_id)

            comparator = DXFComparator()
            changes_objects, summary_obj = comparator.compare_snapshot_data(
                base_data, new_data
            )

            # Serialize changes for display and storage
            changes = [c.to_dict() for c in changes_objects]
            summary = summary_obj.to_dict()

            # Store result in database for caching
            result = ComparisonResult(
                base_version_id=base_id,
                new_version_id=new_id,
                added_layers_count=summary["added_count"],
                removed_layers_count=summary["removed_count"],
                modified_layers_count=summary["modified_count"],
                unchanged_layers_count=summary["unchanged_count"],
                changes_json=json.dumps(changes),
            )
            db.session.add(result)
            db.session.commit()

            diff_svg = (
                None  # SVG generation requires original DXF files which are not stored
            )

        except Exception as e:
            db.session.rollback()
            import traceback

            traceback.print_exc()
            flash(f"Error performing comparison: {str(e)}", "error")
            changes = []
            summary = {
                "total_layers_base": base_version.total_layers,
                "total_layers_new": new_version.total_layers,
                "added_count": 0,
                "removed_count": 0,
                "modified_count": 0,
                "unchanged_count": 0,
            }
            diff_svg = None

    return render_template(
        "comparison_result.html",
        base_version=base_version,
        new_version=new_version,
        changes=changes,
        summary=summary,
        diff_svg=diff_svg,
    )


@app.route("/delete_version/<int:version_id>", methods=["POST"])
@login_required
def delete_version(version_id):
    """Delete a version and its snapshots"""
    version = Version.query.get_or_404(version_id)

    # Verify user owns this version
    if version.user_id != current_user.id:
        flash("You don't have permission to delete this version", "error")
        return redirect(url_for("list_versions"))

    try:
        db.session.delete(version)
        db.session.commit()
        flash(f"Version '{version.original_filename}' deleted successfully", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting version: {str(e)}", "error")

    return redirect(url_for("list_versions"))


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================


@app.route("/register", methods=["GET", "POST"])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Validation
        if not username or not email or not password:
            flash("All fields are required", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters long", "error")
            return render_template("register.html")

        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered", "error")
            return render_template("register.html")

        # Create user
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember", False)

        if not username or not password:
            flash("Please enter both username and password", "error")
            return render_template("login.html")

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_page) if next_page else redirect(url_for("index"))
        else:
            flash("Invalid username or password", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    """User logout"""
    logout_user()
    flash("You have been logged out successfully", "success")
    return redirect(url_for("login"))


# ============================================================================
# EXISTING ROUTES
# ============================================================================


@app.route("/", methods=["GET"])
@login_required
def index():
    """Display the upload form"""
    return render_template("index.html")


@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin():
    """Admin panel for updating master validation rules JSON file"""
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected", "error")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "error")
            return redirect(request.url)

        if file and file.filename and file.filename.endswith(".json"):
            try:
                # Verify valid JSON before saving
                content = json.load(file.stream)
                # Save to disk
                with open(app.config["MASTER_JSON"], "w") as f:
                    json.dump(content, f, indent=4)
                flash("Master data updated successfully", "success")
            except Exception as e:
                flash(f"Invalid JSON file: {str(e)}", "error")
        else:
            flash("Please upload a .json file", "error")

    return render_template("admin.html")


@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    """Process uploaded DXF/ZIP file and return validation results"""
    if "file" not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("index"))

    file = request.files["file"]
    if not file.filename:
        flash("No file selected", "error")
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash("Invalid file type. Please upload a .dxf or .zip file", "error")
        return redirect(url_for("index"))

    filepath = None
    extract_dir = None

    try:
        filename = secure_filename(file.filename)
        if not filename:
            raise Exception("Invalid filename")

        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        target_dxf = filepath

        # Extract DXF from ZIP if necessary
        if filename.lower().endswith(".zip"):
            extract_dir = os.path.join(
                app.config["UPLOAD_FOLDER"], f"temp_{os.path.splitext(filename)[0]}"
            )
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(filepath, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find first DXF in extracted files
            found_dxf = False
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    if f.lower().endswith(".dxf"):
                        target_dxf = os.path.join(root, f)
                        found_dxf = True
                        break
                if found_dxf:
                    break

            if not found_dxf:
                raise Exception("No .dxf file found in the zip archive")

        # Load master validation rules based on selection
        rules_source = request.form.get("rules_source", "odisha")
        master_rules = []
        rules_source_name = "Odisha Rules"
        config_path = None  # Path to CAD to PDF config for SVG preview

        if rules_source == "odisha":
            rules_path = app.config["MASTER_JSON"]
            if os.path.exists(rules_path):
                with open(rules_path, "r") as f:
                    master_rules = json.load(f)
            rules_source_name = "Odisha Rules"
            # Use odisha_cadtopdf.json for SVG preview config
            config_path = os.path.join(
                os.path.dirname(__file__), "odisha_cadtopdf.json"
            )
        elif rules_source == "ppa":
            rules_path = os.path.join(os.path.dirname(__file__), "ppa_layers.json")
            if os.path.exists(rules_path):
                with open(rules_path, "r") as f:
                    master_rules = json.load(f)
            else:
                raise Exception("PPA Rules file not found on server")
            rules_source_name = "PPA Rules"
            # Use ppa_cadtopdf_corrected.json for SVG preview config
            config_path = os.path.join(
                os.path.dirname(__file__), "ppa_cadtopdf_corrected.json"
            )
        elif rules_source == "custom":
            if "custom_rules_file" not in request.files:
                raise Exception("No custom rules file uploaded")

            cfile = request.files["custom_rules_file"]
            if cfile.filename == "":
                raise Exception("No custom rules file selected")

            if cfile and cfile.filename.endswith(".json"):
                try:
                    master_rules = json.load(cfile.stream)
                    rules_source_name = f"Custom Rules ({cfile.filename})"
                except Exception as e:
                    raise Exception(f"Invalid JSON in custom rules file: {str(e)}")
            else:
                raise Exception("Custom rules file must be a .json file")
            # For custom rules, no specific SVG config, will show all non-ignored layers
            config_path = None

        # Read and validate DXF file
        try:
            doc = ezdxf.readfile(target_dxf)
            result = validate_dxf_content(doc, master_rules, config_path)
            result["filename"] = filename
            result["rules_source_name"] = rules_source_name

            # Store version metadata for comparison (only for DXF files, not ZIP)
            if filename.lower().endswith(".dxf"):
                try:
                    version_id = store_version_metadata(
                        doc=doc,
                        filename=filename,
                        original_filename=file.filename,
                        filepath=filepath,
                        project_name=request.form.get("project_name", None),
                    )
                    if version_id:
                        result["version_id"] = version_id
                        result["version_stored"] = True
                except Exception as e:
                    # Don't fail if version storage fails
                    print(f"Warning: Could not store version metadata: {e}")
                    result["version_stored"] = False
        except Exception as e:
            raise Exception(f"Error parsing DXF: {str(e)}")

        # Clean up temporary files
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

        return render_template("results.html", **result)

    except Exception as e:
        # Clean up on error
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        if extract_dir and os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

        flash(f"Error processing file: {str(e)}", "error")
        return redirect(url_for("index"))


@app.route("/generate_fix_script", methods=["POST"])
@login_required
def generate_fix_script():
    """Generate AutoLISP script to fix layer issues"""
    try:
        data = request.json
        if not data or "actions" not in data:
            return "No actions provided", 400

        actions = data["actions"]
        lsp_content = [
            ";; Auto-Generated Fix Script by DXF Validator",
            ";; Run this script in AutoCAD (Drag & Drop or APPLOAD)",
            "",
            "(defun c:FixLayers ()",
            '  (setvar "CMDECHO" 0)',
            '  (command "-LAYER"',
        ]

        for action in actions:
            layer = action.get("layer")
            color = action.get("color")

            if not layer or not color:
                continue

            # Handle True Color logic for LISP (simplified, mostly supports Index)
            # AutoCAD LISP for True Color is complex "c" "t" "r,g,b"
            color_cmd = ""
            if str(color).startswith("T "):
                # True Color format: "T 255,0,0"
                rgb = color.replace("T ", "").strip()
                color_cmd = f'"C" "T" "{rgb}" "{layer}"'
            else:
                # Index Color
                color_cmd = f'"C" "{color}" "{layer}"'

            if action["type"] == "create_layer":
                # Make (Create) layer and set color
                # "M" makes and sets current. "N" New.
                # Better: "N" to create, then "C" to set color.
                lsp_content.append(f'    "N" "{layer}"')
                lsp_content.append(f"    {color_cmd}")
            elif action["type"] == "fix_color":
                lsp_content.append(f"    {color_cmd}")

        lsp_content.append('    "")')  # End Layer command
        lsp_content.append('  (setvar "CMDECHO" 1)')
        lsp_content.append('  (princ "\\nLayers Updated Successfully.")')
        lsp_content.append("  (princ)")
        lsp_content.append(")")
        lsp_content.append("")
        lsp_content.append('(princ "\\nType FixLayers to run the script.")')

        # Create memory file
        proxy = io.BytesIO("\n".join(lsp_content).encode("utf-8"))
        proxy.seek(0)

        return send_file(
            proxy,
            as_attachment=True,
            download_name="fix_layers.lsp",
            mimetype="application/x-lisp",
        )

    except Exception as e:
        return str(e), 500


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    flash("File is too large. Maximum size is 100 MB", "error")
    return redirect(url_for("index"))


@app.template_filter("format_change")
def format_change_filter(value):
    """Format a number with explicit sign for positive values"""
    try:
        val = float(value)
        if val > 0:
            return f"+{val:g}"
        return f"{val:g}"
    except (ValueError, TypeError):
        return str(value)


# Database table creation
with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8080)
