#!/usr/bin/env python3
"""
Script to correct layer names in ppa_cadtopdf.json based on ppa_layers.json
"""

import json
import re

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

print("Valid patterns from ppa_layers.json:")
for pattern in sorted(valid_patterns):
    print(f"  {pattern}")


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


# Analyze all layer names in cadtopdf
print("\n\nAnalyzing ppa_cadtopdf.json layers:")
print("=" * 80)

all_layer_names = []
for sheet in cadtopdf.get("DxfToPdfLayerConfigCat_CD_ALL", []):
    for config in sheet.get("planPdfLayerConfigs", []):
        layer_name = config.get("layerName", "")
        if layer_name and layer_name not in all_layer_names:
            all_layer_names.append(layer_name)

# Categorize layers
matched_layers = []
unmatched_layers = []
layer_mappings = {}  # Maps old name to new (corrected) name

for layer_name in sorted(all_layer_names):
    matched_pattern = find_matching_pattern(layer_name)
    if matched_pattern:
        matched_layers.append((layer_name, matched_pattern))
        layer_mappings[layer_name] = matched_pattern
        print(f"✓ MATCH: {layer_name:50s} -> {matched_pattern}")
    else:
        unmatched_layers.append(layer_name)
        print(f"✗ UNMATCHED: {layer_name}")

print(f"\n\nSummary:")
print(f"  Total unique layers: {len(all_layer_names)}")
print(f"  Matched: {len(matched_layers)}")
print(f"  Unmatched: {len(unmatched_layers)}")

print("\n\nUnmatched layers that will be REMOVED:")
for layer in unmatched_layers:
    print(f"  - {layer}")
