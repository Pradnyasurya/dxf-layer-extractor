#!/usr/bin/env python3
"""
Script to correct layer names in ppa_cadtopdf.json based on ppa_layers.json
and remove layers that don't match any pattern.
"""

import json
import re
import copy

# Load both files
with open("ppa_layers.json", "r") as f:
    ppa_layers = json.load(f)

with open("/home/pkurane/projects/layerslist/ppa_cadtopdf.json", "r") as f:
    cadtopdf = json.load(f)

# Extract valid layer name patterns from ppa_layers.json
valid_patterns = set()
for layer in ppa_layers:
    layer_name = layer.get("Layer Name", "")
    if layer_name:
        valid_patterns.add(layer_name)

# Layers to always keep even if they don't match ppa_layers.json patterns
ALWAYS_KEEP_LAYERS = {
    "ELEVATION_PLAN_*",
    "SECTION_PLAN_*",
    "SERVICE_PLAN",
}


# Function to convert any layer name to a normalized pattern
def normalize_to_pattern(layer_name):
    """
    Convert a layer name to a normalized pattern by replacing:
    - Actual numbers (_1, _2, etc.) with _n
    - Wildcards (_*) with _n
    """
    result = layer_name
    # Replace _* with _n (wildcard from cadtopdf)
    result = result.replace("_*", "_n")
    # Replace _\d+ with _n (actual numbers)
    result = re.sub(r"_\d+", "_n", result)
    return result


# Function to check if normalized name matches a valid pattern
def find_matching_pattern(layer_name):
    """Find the best matching pattern for a layer name"""
    normalized = normalize_to_pattern(layer_name)

    # First try exact match with normalized name
    if normalized in valid_patterns:
        return normalized

    # Then try to match by converting pattern to regex and matching
    for pattern in valid_patterns:
        # Convert pattern to regex
        # _n should match _\d+
        regex_pattern = pattern.replace("_n", r"_\d+")
        # n at end should match \d+
        regex_pattern = regex_pattern.replace("n_", r"\d+_")
        regex_pattern = f"^{regex_pattern}$"

        try:
            if re.match(regex_pattern, layer_name):
                return pattern
        except:
            pass

    return None


# Create a deep copy of the cadtopdf data for the cleaned version
cleaned_cadtopdf = copy.deepcopy(cadtopdf)

# Process each sheet and filter out unmatched layers
total_removed = 0
total_kept = 0

for sheet in cleaned_cadtopdf.get("DxfToPdfLayerConfigCat_CD_ALL", []):
    original_configs = sheet.get("planPdfLayerConfigs", [])
    cleaned_configs = []

    for config in original_configs:
        layer_name = config.get("layerName", "")
        matched_pattern = find_matching_pattern(layer_name)

        # Check if layer should be kept (matches pattern or is in always-keep list)
        should_keep = matched_pattern is not None or layer_name in ALWAYS_KEEP_LAYERS

        if should_keep:
            # Keep this layer, optionally update the name to the pattern
            # But let's keep the original concrete name since that's what's in the DXF
            cleaned_configs.append(config)
            total_kept += 1
        else:
            # Remove this layer (don't add to cleaned_configs)
            total_removed += 1

    # Update the sheet with cleaned configs
    sheet["planPdfLayerConfigs"] = cleaned_configs

# Save the cleaned file
output_path = "/home/pkurane/projects/layerslist/ppa_cadtopdf_corrected.json"
with open(output_path, "w") as f:
    json.dump(cleaned_cadtopdf, f, indent=3)

print(f"✓ Cleaned file saved to: {output_path}")
print(f"\nSummary:")
print(f"  Total layer configs processed: {total_kept + total_removed}")
print(f"  Kept (matched): {total_kept}")
print(f"  Removed (unmatched): {total_removed}")

# Print some examples of what was kept vs removed
print("\n\nExamples of KEPT layers (first 10):")
kept_examples = []
for sheet in cleaned_cadtopdf.get("DxfToPdfLayerConfigCat_CD_ALL", []):
    for config in sheet.get("planPdfLayerConfigs", []):
        layer_name = config.get("layerName", "")
        if layer_name not in kept_examples:
            kept_examples.append(layer_name)
            if len(kept_examples) >= 10:
                break
    if len(kept_examples) >= 10:
        break

for layer in kept_examples:
    matched = find_matching_pattern(layer)
    print(f"  ✓ {layer} -> {matched}")
