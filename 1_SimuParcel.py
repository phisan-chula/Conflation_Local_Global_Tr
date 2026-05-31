# 1_SimuParcel.py
import argparse
import os
import shutil
import hashlib
from pathlib import Path
import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, Point
import PlotMap  # Dynamic Map Rendering Engine

def parse_toml(file_path):
    """
    A lightweight custom parser to extract configurations from the new TOML setup.
    Guarantees no silent fallbacks if keys or structural blocks are missing.
    """
    config = {}
    current_section = None
    
    if not os.path.exists(file_path):
        print(f"\n[CRITICAL ERROR] Configuration file missing at: {file_path}")
        print("--> System default fallbacks are disabled. Execution halted.")
        raise FileNotFoundError(f"Mandatory configuration file not found: {file_path}")
        
    print(f"Reading configuration from: {file_path}...")   
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Parse sections: [SIMU_PARCEL], [FIX_PARCEL], [FIX_CONTROL]
            if line.startswith('['):
                end_idx = line.find(']')
                if end_idx != -1:
                    current_section = line[1:end_idx].strip()
                    if current_section not in config:
                        config[current_section] = {}
                    continue
            
            # Parse key-value pairs within sections
            if '=' in line and current_section:
                key, val = line.split('=', 1)
                key = key.strip()
                val = val.split('#')[0].strip()
                
                if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
                    key = key[1:-1]
                
                if val.startswith('[') and val.endswith(']'):
                    list_contents = val[1:-1].strip()
                    if list_contents:
                        raw_items = [x.strip() for x in list_contents.split(',')]
                        val_parsed = []
                        for item in raw_items:
                            try:
                                if '.' in item:
                                    val_parsed.append(float(item))
                                else:
                                    val_parsed.append(int(item))
                            except ValueError:
                                if (item.startswith('"') and item.endswith('"')) or (item.startswith("'") and item.endswith("'")):
                                    item = item[1:-1]
                                val_parsed.append(item)
                    else:
                        val_parsed = []
                else:
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val_parsed = val[1:-1]
                    else:
                        try:
                            if '.' in val:
                                val_parsed = float(val)
                            else:
                                val_parsed = int(val)
                        except ValueError:
                            val_parsed = val
                            
                config[current_section][key] = val_parsed
                
    return config


class Base32TokenGenerator:
    """
    An iterator-based generator object that yields unique, sequential 3-digit 
    Base32 tracking tokens without zero prefixes on demand.
    """
    def __init__(self):
        self.alphabet = "0123456789bcdefghjkmnpqrstuvwxyz"

    def yield_tokens(self, limit=None):
        """
        A generator method that yields unique tokens one-by-one.
        d1 starts at index 1 to guarantee no leading '0' prefix.
        """
        count = 0
        for d1 in self.alphabet[1:]:
            for d2 in self.alphabet:
                for d3 in self.alphabet:
                    token = f"{d1}{d2}{d3}"
                    yield token
                    
                    count += 1
                    if limit is not None and count >= limit:
                        return


def main():
    parser = argparse.ArgumentParser(
        description="Simulate spatial layouts assigning shared topologies BEFORE parcel displacement vectors."
    )
    parser.add_argument(
        "config_file", 
        type=str, 
        help="Path to the custom TOML configuration file (e.g., CONFIG/L1x3_CTx1.toml)"
    )
    args = parser.parse_args()
    
    config = parse_toml(args.config_file)
    
    if 'SIMU_PARCEL' not in config:
        raise KeyError("Missing mandatory [SIMU_PARCEL] configuration block in TOML profile.")
        
    parcel_cfg = config['SIMU_PARCEL']
    default_parcel_class = parcel_cfg['class']
    width = float(parcel_cfg['width'])
    height = float(parcel_cfg['height'])
    space = float(parcel_cfg['space'])
    cols = int(parcel_cfg['cols'])
    rows = int(parcel_cfg['rows'])
    
    fix_parcels = config.get('FIX_PARCEL', {})
    fix_controls = config.get('FIX_CONTROL', {})
    
    result_dir = Path('./RESULT')
    if result_dir.exists():
        shutil.rmtree(result_dir)
    result_dir.mkdir(parents=True, exist_ok=True)

    # Temporary storage blocks for the generation layers
    raw_records = []
    unique_ideal_coords = set()
    current_id = 1

    # =========================================================================
    # PASS 1: GENERATE PERFECTLY CONTIGUOUS IDEAL GEOMETRIES & TRACK COORDS
    # =========================================================================
    print("[PROCESS] Pass 1: Constructing contiguous structural grid layout baseline...")
    for r in range(rows):
        space_multiplier = r // 2
        for c in range(cols):
            # X coordinate is contiguous within the horizontal row
            x_min = c * width
            # Y coordinate groups blocks of 2 tight, stepping vertically by space factor
            y_min = (r * height) + (space_multiplier * space)
            
            x_max = x_min + width
            y_max = y_min + height
            
            poly_ideal = Polygon([(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)])
            
            # Extract and round pure ideal coordinates to pre-map shared vertices
            ideal_coords = list(poly_ideal.exterior.coords)[:-1]
            for cx, cy in ideal_coords:
                unique_ideal_coords.add((round(cx, 3), round(cy, 3)))
            
            raw_records.append({
                "id": current_id,
                "poly_ideal": poly_ideal,
                "ideal_coords_list": ideal_coords
            })
            current_id += 1

    # =========================================================================
    # PASS 2: ASSIGN IDENTICAL VERTEX TOKENS TO TRUE SHARED CORNERS FIRST
    # =========================================================================
    print("[PROCESS] Pass 2: Tokenizing shared node topology database rules...")
    token_engine = Base32TokenGenerator()
    coord_to_node_id = {}
    sorted_ideal_coords = sorted(list(unique_ideal_coords))
    
    token_stream = token_engine.yield_tokens(limit=len(sorted_ideal_coords))
    for coord, token in zip(sorted_ideal_coords, token_stream):
        coord_to_node_id[coord] = token

    # Map the generated token lists back to each parcel record before any adjustments take place
    for record in raw_records:
        tokens = [coord_to_node_id[(round(x, 3), round(y, 3))] for x, y in record["ideal_coords_list"]]
        # Standard trailing comma loop format
        record["Vertex_Sequenc"] = f"{tokens[0]},{tokens[1]},{tokens[2]},{tokens[3]},{tokens[0]}"

    # =========================================================================
    # PASS 3: EXECUTE INDEPENDENT SHIFTS & ASSIGN LAYER CLASSES
    # =========================================================================
    print("[PROCESS] Pass 3: Applying custom [FIX_PARCEL] spatial shifts and class updates...")
    ideal_parcels = []
    measured_parcels = []
    ids = []
    classes = []
    vertex_sequences = []

    for record in raw_records:
        p_id_str = str(record["id"])
        poly_ideal = record["poly_ideal"]
        ideal_parcels.append(poly_ideal)
        
        # Check if this specific ID requires spatial modification rules
        if p_id_str in fix_parcels:
            active_class = "L1"  # Automatically promote listed IDs to anchor reference layer
            shift_x = float(fix_parcels[p_id_str][0])
            shift_y = float(fix_parcels[p_id_str][1])
            print(f"          ID {p_id_str} matched -> Class OVERRIDE to L1 | Applying Shift: [{shift_x}, {shift_y}]")
            
            # Pull apart the contiguous borders into displaced coordinates
            coords = np.array(poly_ideal.exterior.coords)
            shifted_coords = [(x + shift_x, y + shift_y) for x, y in coords]
            poly_measured = Polygon(shifted_coords)
        else:
            active_class = default_parcel_class
            poly_measured = poly_ideal
            
        measured_parcels.append(poly_measured)
        ids.append(record["id"])
        classes.append(active_class)
        vertex_sequences.append(record["Vertex_Sequenc"]) # Topology stays locked!

    # =========================================================================
    # PASS 4: GLOBAL COORDINATE TRANSLATION PASS (SNAP BOUNDARY TO ORIGIN 0,0)
    # =========================================================================
    print("[PROCESS] Pass 4: Running origin boundary snapping verification matrix pass...")
    all_x, all_y = [], []
    for poly in measured_parcels:
        coords = np.array(poly.exterior.coords)
        all_x.extend(coords[:, 0])
        all_y.extend(coords[:, 1])
        
    global_min_x = min(all_x)
    global_min_y = min(all_y)
    
    print(f"          Detected structural workspace minimum boundary corner: ({global_min_x:.3f}, {global_min_y:.3f})")
    print(f"          Translating fabric layouts by vector: [{-global_min_x:.3f}, {-global_min_y:.3f}] to baseline at (0,0)")

    snapped_ideal = []
    for poly in ideal_parcels:
        coords = np.array(poly.exterior.coords)
        adjusted_coords = [(x - global_min_x, y - global_min_y) for x, y in coords]
        snapped_ideal.append(Polygon(adjusted_coords))

    snapped_measured = []
    for poly in measured_parcels:
        coords = np.array(poly.exterior.coords)
        adjusted_coords = [(x - global_min_x, y - global_min_y) for x, y in coords]
        snapped_measured.append(Polygon(adjusted_coords))

    # Extract target control markers defined in the [FIX_CONTROL] block
    fix_control_points = []
    fix_control_ids = []
    plotmap_targets = {}  # Object to handle on-map typography text rendering

    for ctrl_id, coords in fix_controls.items():
        fix_control_ids.append(ctrl_id)
        
        # Apply origin offset adjustment shifts to targets
        shifted_x = float(coords[0]) - global_min_x
        shifted_y = float(coords[1]) - global_min_y
        
        fix_control_points.append(Point(shifted_x, shifted_y))
        
        # Explicit RED color prefix assigned to label key to force a bright red text render
        plotmap_targets[f"RED:{ctrl_id}"] = (shifted_x, shifted_y)

    # Package structures cleanly into GeoDataFrames
    gdf_ideal = gpd.GeoDataFrame(
        {'id': ids, 'Class': classes, 'geometry': snapped_ideal}, 
        crs="EPSG:32647"
    )
    gdf_measured = gpd.GeoDataFrame(
        {'id': ids, 'Class': classes, 'Vertex_Sequenc': vertex_sequences, 'geometry': snapped_measured}, 
        crs="EPSG:32647"
    )
    gdf_fix_control = gpd.GeoDataFrame(
        {'id': fix_control_ids, 'geometry': fix_control_points},
        crs="EPSG:32647"
    )

    gpkg_path = result_dir / "01_parcel_conflation_sim.gpkg"
    gdf_ideal.to_file(str(gpkg_path), layer="ideal", driver="GPKG")
    gdf_measured.to_file(str(gpkg_path), layer="measured", driver="GPKG")
    gdf_fix_control.to_file(str(gpkg_path), layer="fix_control", driver="GPKG")

    print("[EXPORT] Rendering high-resolution layout map graphics via PlotMap...")
    map_layers = {
        "Aligned Fabric Output": gdf_measured
    }
    
    if not gdf_fix_control.empty:
        map_layers["Fix Control"] = gdf_fix_control
        print(f"          [PLOT] Active tie stations identified. Passing {len(plotmap_targets)} RED labels into rendering dictionary.")
    else:
        plotmap_targets = None

    PlotMap.render_map(
        layers=map_layers,
        title="Simulation Workspace Input (Shared Nodes Locked BEFORE Displacement Shift)",
        filename_base=str(result_dir / "01_simulation_input"),
        targets=plotmap_targets
    )
    print("[STAGE 1 COMPLETED] Process terminated successfully. Lower-bottom vertex is locked at (0,0).\n")

if __name__ == "__main__":
    main()
