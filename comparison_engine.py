"""
DXF Version Comparison Engine

Provides comprehensive comparison between two DXF file versions,
detecting added, removed, and modified layers with detailed metrics.
"""

import hashlib
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class ChangeType(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class LayerChange:
    """Represents a single layer change between versions"""

    layer_name: str
    change_type: ChangeType
    significance: str  # 'critical', 'high', 'medium', 'low'

    # Metrics
    base_entity_count: int = 0
    new_entity_count: int = 0
    entity_count_diff: int = 0

    base_area: float = 0.0
    new_area: float = 0.0
    area_diff: float = 0.0
    area_diff_percent: float = 0.0

    base_perimeter: float = 0.0
    new_perimeter: float = 0.0
    perimeter_diff: float = 0.0

    # Position changes
    centroid_shift_x: float = 0.0
    centroid_shift_y: float = 0.0
    centroid_shift_distance: float = 0.0

    # Property changes
    color_changed: bool = False
    base_color: Optional[int] = None
    new_color: Optional[int] = None

    linetype_changed: bool = False
    base_linetype: Optional[str] = None
    new_linetype: Optional[str] = None

    visibility_changed: bool = False
    base_visible: bool = True
    new_visible: bool = True

    # Description
    description: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["change_type"] = self.change_type.value
        return data


@dataclass
class ComparisonSummary:
    """Summary of comparison results"""

    total_layers_base: int = 0
    total_layers_new: int = 0
    added_count: int = 0
    removed_count: int = 0
    modified_count: int = 0
    unchanged_count: int = 0
    critical_changes: int = 0
    high_changes: int = 0
    medium_changes: int = 0
    low_changes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class DXFComparator:
    """
    Main comparison engine for DXF files.
    Detects and categorizes changes between two DXF versions.
    """

    # Critical layer patterns for architectural scrutiny
    CRITICAL_LAYERS = [
        "BLT_UP_AREA",
        "COVERED_AREA",
        "PLOT_BOUNDARY",
        "FRONT_SETBACK",
        "REAR_SETBACK",
        "SIDE_SETBACK",
        "SETBACK",
        "FLOOR_AREA",
    ]

    HIGH_PRIORITY_LAYERS = [
        "STAIR",
        "LIFT",
        "HT_OF_BLDG",
        "PLINTH_HEIGHT",
        "PARAPET_HT",
        "BLDG_FOOT_PRINT",
    ]

    MEDIUM_PRIORITY_LAYERS = ["UNITFA", "ROOM", "PARKING", "DWELLING"]

    def __init__(self, tolerance: float = 0.01):
        """
        Initialize comparator.

        Args:
            tolerance: Minimum difference to consider a change (in sq.m or meters)
        """
        self.tolerance = tolerance

    def compare_documents(
        self, base_doc, new_doc
    ) -> Tuple[List[LayerChange], ComparisonSummary]:
        """
        Compare two DXF documents and return detailed changes.

        Args:
            base_doc: ezdxf document (base version)
            new_doc: ezdxf document (new version)

        Returns:
            Tuple of (list of LayerChange objects, ComparisonSummary)
        """
        changes = []

        # Get all layers from both documents
        base_layers = {layer.dxf.name: layer for layer in base_doc.layers}
        new_layers = {layer.dxf.name: layer for layer in new_doc.layers}

        base_layer_names = set(base_layers.keys())
        new_layer_names = set(new_layers.keys())

        # Find added layers (in new but not in base)
        added_names = new_layer_names - base_layer_names
        for name in added_names:
            change = self._analyze_added_layer(name, new_layers[name], new_doc)
            changes.append(change)

        # Find removed layers (in base but not in new)
        removed_names = base_layer_names - new_layer_names
        for name in removed_names:
            change = self._analyze_removed_layer(name, base_layers[name], base_doc)
            changes.append(change)

        # Find common layers and check for modifications
        common_names = base_layer_names & new_layer_names
        for name in common_names:
            change = self._compare_layer(
                name, base_layers[name], new_layers[name], base_doc, new_doc
            )
            if change:
                changes.append(change)

        # Generate summary
        summary = self._generate_summary(changes, base_layer_names, new_layer_names)

        return changes, summary

    def _analyze_added_layer(self, name: str, layer, doc) -> LayerChange:
        """Analyze a newly added layer"""
        metrics = self._extract_layer_metrics(name, doc)

        significance = self._classify_significance(name, "added")

        change = LayerChange(
            layer_name=name,
            change_type=ChangeType.ADDED,
            significance=significance,
            new_entity_count=metrics["entity_count"],
            new_area=metrics["total_area"],
            new_perimeter=metrics["perimeter"],
            new_color=layer.dxf.color if hasattr(layer.dxf, "color") else None,
            new_linetype=layer.dxf.linetype
            if hasattr(layer.dxf, "linetype")
            else "Continuous",
            new_visible=not layer.is_off(),
            description=f"New layer added with {metrics['entity_count']} entities",
        )

        if metrics["total_area"] > 0:
            change.description += f", area {metrics['total_area']:.2f} sq.m"

        return change

    def _analyze_removed_layer(self, name: str, layer, doc) -> LayerChange:
        """Analyze a removed layer"""
        metrics = self._extract_layer_metrics(name, doc)

        significance = self._classify_significance(name, "removed")

        change = LayerChange(
            layer_name=name,
            change_type=ChangeType.REMOVED,
            significance=significance,
            base_entity_count=metrics["entity_count"],
            base_area=metrics["total_area"],
            base_perimeter=metrics["perimeter"],
            base_color=layer.dxf.color if hasattr(layer.dxf, "color") else None,
            base_linetype=layer.dxf.linetype
            if hasattr(layer.dxf, "linetype")
            else "Continuous",
            base_visible=not layer.is_off(),
            description=f"Layer removed (had {metrics['entity_count']} entities",
        )

        if metrics["total_area"] > 0:
            change.description += f", {metrics['total_area']:.2f} sq.m"
        change.description += ")"

        return change

    def _compare_layer(
        self, name: str, base_layer, new_layer, base_doc, new_doc
    ) -> Optional[LayerChange]:
        """Compare a layer that exists in both versions"""
        base_metrics = self._extract_layer_metrics(name, base_doc)
        new_metrics = self._extract_layer_metrics(name, new_doc)

        # Check for changes
        has_changes = False
        change = LayerChange(
            layer_name=name,
            change_type=ChangeType.MODIFIED,
            significance="low",
            base_entity_count=base_metrics["entity_count"],
            new_entity_count=new_metrics["entity_count"],
            entity_count_diff=new_metrics["entity_count"]
            - base_metrics["entity_count"],
            base_area=base_metrics["total_area"],
            new_area=new_metrics["total_area"],
            base_perimeter=base_metrics["perimeter"],
            new_perimeter=new_metrics["perimeter"],
            base_color=base_layer.dxf.color
            if hasattr(base_layer.dxf, "color")
            else None,
            new_color=new_layer.dxf.color if hasattr(new_layer.dxf, "color") else None,
            base_linetype=base_layer.dxf.linetype
            if hasattr(base_layer.dxf, "linetype")
            else "Continuous",
            new_linetype=new_layer.dxf.linetype
            if hasattr(new_layer.dxf, "linetype")
            else "Continuous",
            base_visible=not base_layer.is_off(),
            new_visible=not new_layer.is_off(),
        )

        # Check entity count change
        if abs(change.entity_count_diff) > 0:
            has_changes = True
            if change.entity_count_diff > 0:
                change.description += f"+{change.entity_count_diff} entities added. "
            else:
                change.description += f"{change.entity_count_diff} entities removed. "

        # Check area change (for polygon layers)
        if base_metrics["total_area"] > 0 or new_metrics["total_area"] > 0:
            change.area_diff = new_metrics["total_area"] - base_metrics["total_area"]
            if base_metrics["total_area"] > 0:
                change.area_diff_percent = (
                    change.area_diff / base_metrics["total_area"]
                ) * 100

            if abs(change.area_diff) > self.tolerance:
                has_changes = True
                change.description += f"Area changed by {change.area_diff:+.2f} sq.m ({change.area_diff_percent:+.1f}%). "

        # Check perimeter change
        change.perimeter_diff = new_metrics["perimeter"] - base_metrics["perimeter"]
        if abs(change.perimeter_diff) > self.tolerance:
            has_changes = True
            change.description += (
                f"Perimeter changed by {change.perimeter_diff:+.2f}m. "
            )

        # Check centroid shift
        if base_metrics["centroid"] and new_metrics["centroid"]:
            dx = new_metrics["centroid"][0] - base_metrics["centroid"][0]
            dy = new_metrics["centroid"][1] - base_metrics["centroid"][1]
            distance = (dx**2 + dy**2) ** 0.5

            change.centroid_shift_x = dx
            change.centroid_shift_y = dy
            change.centroid_shift_distance = distance

            if distance > self.tolerance:
                has_changes = True
                change.description += f"Shifted by {distance:.2f}m. "

        # Check property changes
        if change.base_color != change.new_color:
            change.color_changed = True
            has_changes = True
            change.description += (
                f"Color changed from {change.base_color} to {change.new_color}. "
            )

        if change.base_linetype != change.new_linetype:
            change.linetype_changed = True
            has_changes = True
            change.description += f"Line type changed from {change.base_linetype} to {change.new_linetype}. "

        if change.base_visible != change.new_visible:
            change.visibility_changed = True
            has_changes = True
            change.description += f"Visibility changed to {'visible' if change.new_visible else 'hidden'}. "

        # If no significant changes, return None
        if not has_changes:
            return None

        # Classify significance based on layer type and change magnitude
        change.significance = self._classify_modification_significance(change)

        return change

    def _extract_layer_metrics(self, layer_name: str, doc) -> dict:
        """Extract metrics for a specific layer from a document"""
        msp = doc.modelspace()
        entities = msp.query(f'*[layer=="{layer_name}"]')

        metrics = {
            "entity_count": len(entities),
            "total_area": 0.0,
            "perimeter": 0.0,
            "centroid": None,
            "bounds": None,
        }

        if len(entities) == 0:
            return metrics

        # Calculate area for polygon entities
        total_area = 0.0
        all_points = []

        for entity in entities:
            dxftype = entity.dxftype()

            # Extract points and calculate area for closed shapes
            if dxftype == "LWPOLYLINE":
                if hasattr(entity, "is_closed") and entity.is_closed:
                    try:
                        points = list(entity.points())
                        if len(points) >= 3:
                            area_val = self._calculate_polygon_area(points)
                            total_area += abs(area_val)
                            all_points.extend(points)
                    except:
                        pass
            elif dxftype == "POLYLINE":
                if hasattr(entity, "is_closed") and entity.is_closed:
                    try:
                        points = [v.dxf.location[:2] for v in entity.vertices]
                        if len(points) >= 3:
                            area_val = self._calculate_polygon_area(points)
                            total_area += abs(area_val)
                            all_points.extend(points)
                    except:
                        pass
            elif dxftype == "HATCH":
                if hasattr(entity, "area"):
                    total_area += entity.area
            elif dxftype in ("LINE", "LWPOLYLINE"):
                # Collect points for centroid calculation
                try:
                    if hasattr(entity, "get_points"):
                        all_points.extend(entity.get_points())
                except:
                    pass

        metrics["total_area"] = total_area

        # Calculate centroid from all points
        if all_points:
            x_coords = [p[0] for p in all_points]
            y_coords = [p[1] for p in all_points]
            metrics["centroid"] = (
                sum(x_coords) / len(x_coords),
                sum(y_coords) / len(y_coords),
            )

        return metrics

    def _calculate_polygon_area(self, points: List[Tuple[float, float]]) -> float:
        """Calculate polygon area using shoelace formula"""
        if len(points) < 3:
            return 0.0

        area = 0.0
        n = len(points)
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]

        return abs(area) / 2.0

    def _classify_significance(self, layer_name: str, change_type: str) -> str:
        """Classify the significance of a layer addition or removal"""
        layer_upper = layer_name.upper()

        # Check critical patterns
        for pattern in self.CRITICAL_LAYERS:
            if pattern in layer_upper:
                return "critical"

        # Check high priority patterns
        for pattern in self.HIGH_PRIORITY_LAYERS:
            if pattern in layer_upper:
                return "high"

        # Check medium priority patterns
        for pattern in self.MEDIUM_PRIORITY_LAYERS:
            if pattern in layer_upper:
                return "medium"

        return "low"

    def _classify_modification_significance(self, change: LayerChange) -> str:
        """Classify the significance of a layer modification"""
        layer_upper = change.layer_name.upper()

        # Check if it's a critical layer
        is_critical = any(pattern in layer_upper for pattern in self.CRITICAL_LAYERS)
        is_high = any(pattern in layer_upper for pattern in self.HIGH_PRIORITY_LAYERS)

        # For critical layers, area changes > 5% are critical
        if is_critical:
            if abs(change.area_diff_percent) > 5:
                return "critical"
            elif abs(change.area_diff_percent) > 1:
                return "high"
            elif change.area_diff != 0:
                return "medium"

        # For high priority layers
        if is_high:
            if abs(change.area_diff_percent) > 10:
                return "high"
            elif change.area_diff != 0:
                return "medium"

        # Centroid shift on setbacks is critical
        if "SETBACK" in layer_upper and change.centroid_shift_distance > 0.5:
            return "critical"

        # Entity count changes
        if abs(change.entity_count_diff) > 10:
            return "medium"

        return "low"

    def _generate_summary(
        self, changes: List[LayerChange], base_names: set, new_names: set
    ) -> ComparisonSummary:
        """Generate summary statistics from changes"""
        summary = ComparisonSummary(
            total_layers_base=len(base_names), total_layers_new=len(new_names)
        )

        for change in changes:
            if change.change_type == ChangeType.ADDED:
                summary.added_count += 1
            elif change.change_type == ChangeType.REMOVED:
                summary.removed_count += 1
            elif change.change_type == ChangeType.MODIFIED:
                summary.modified_count += 1

            # Count by significance
            if change.significance == "critical":
                summary.critical_changes += 1
            elif change.significance == "high":
                summary.high_changes += 1
            elif change.significance == "medium":
                summary.medium_changes += 1
            else:
                summary.low_changes += 1

        # Calculate unchanged count
        common_layers = base_names & new_names
        summary.unchanged_count = len(common_layers) - summary.modified_count

        return summary

    def generate_insights(
        self, changes: List[LayerChange], summary: ComparisonSummary
    ) -> List[str]:
        """Generate human-readable insights from comparison results"""
        insights = []

        # Area change insights
        total_area_change = sum(c.area_diff for c in changes if c.area_diff > 0)
        if total_area_change > 10:
            insights.append(
                f"⚠️ Total built-up area increased by {total_area_change:.2f} sq.m - verify against permissible limits"
            )
        elif total_area_change < -10:
            insights.append(
                f"✓ Total built-up area decreased by {abs(total_area_change):.2f} sq.m"
            )

        # Coverage insights
        coverage_changes = [
            c for c in changes if "COVERED_AREA" in c.layer_name.upper()
        ]
        if coverage_changes:
            for change in coverage_changes:
                if abs(change.area_diff_percent) > 5:
                    insights.append(
                        f"⚠️ Ground coverage changed by {change.area_diff_percent:+.1f}% - may affect compliance"
                    )

        # Setback insights
        setback_changes = [c for c in changes if "SETBACK" in c.layer_name.upper()]
        if setback_changes:
            shift_changes = [
                c for c in setback_changes if c.centroid_shift_distance > 0.1
            ]
            if shift_changes:
                insights.append(
                    f"⚠️ {len(shift_changes)} setback(s) have shifted position - verify minimum distances"
                )

        # New structures
        new_structures = [
            c
            for c in changes
            if c.change_type == ChangeType.ADDED
            and any(x in c.layer_name.upper() for x in ["STAIR", "LIFT", "ROOM"])
        ]
        if new_structures:
            insights.append(
                f"ℹ️ {len(new_structures)} new structural element(s) added - check fire safety and accessibility compliance"
            )

        # Critical layer insights
        if summary.critical_changes > 0:
            insights.append(
                f"🚨 {summary.critical_changes} critical change(s) detected - review before submission"
            )

        # General summary
        if (
            summary.added_count == 0
            and summary.removed_count == 0
            and summary.modified_count == 0
        ):
            insights.append("✓ No changes detected between versions")
        elif summary.critical_changes == 0 and summary.high_changes == 0:
            insights.append("✓ Changes are minor - likely safe for revision submission")

        return insights
