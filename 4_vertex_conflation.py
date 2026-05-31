# 4_vertex_conflation.py
import os
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon
import PlotMap  # Centralized Dynamic Map Rendering Engine

class TopologicalVertexConflation:
    def __init__(self, result_dir="RESULT", input_filename="03_global_aligned.gpkg"):
        self.result_dir = result_dir
        self.input_gpkg = os.path.join(result_dir, input_filename)
        
        # Output workspace configurations
        self.output_gpkg = os.path.join(result_dir, "04_vertex_conflation_final.gpkg")
        self.output_layer_name = "aligned_parcels"
        
        # Schema tracking attributes
        self.layer_name = "global_aligned"
        self.vertex_col = "Vertex_Sequenc"
        
        self.gdf_all = None
        self.gdf_transformed = None
        self.gdf_fix = None  # Holds stationary control anchors carried through pipeline layers
        self.vertex_targets = {}  # Holds final target coordinates (L1 Constants or L2 Centroids)

    def run_vertex_conflation(self):
        """Executes the fixed constraint node collapse, centroid fallback, and edge adjustment."""
        self._load_data()
        self._calculate_vertex_targets_with_l1_priority()
        self._reconstruct_polygons_with_targets()
        self._generate_and_save_plots()
        self._export_to_structured_geopackage()

    def _load_data(self):
        """Loads the spatial dataset from the previous pipeline execution stage."""
        if not os.path.exists(self.input_gpkg):
            raise FileNotFoundError(f"[ERROR] Cannot find the input database at: {self.input_gpkg}")
            
        print(f"Reading compilation layer '{self.layer_name}' from: {self.input_gpkg}...")
        self.gdf_all = gpd.read_file(self.input_gpkg, layer=self.layer_name)
        
        # Pull fix_control layer to make sure point locations propagate onto your visual map plots
        try:
            self.gdf_fix = gpd.read_file(self.input_gpkg, layer="fix_control")
            print(f"Isolated 'fix_control' anchor layer tracking {len(self.gdf_fix)} stations.")
        except Exception:
            self.gdf_fix = None
            print("Warning: Standalone 'fix_control' point layer not found in input database.")

    def _calculate_vertex_targets_with_l1_priority(self):
        """
        Groups vertices by name. If a vertex name belongs to an L1 anchor polygon, 
        its true coordinate is enforced as a constant framework benchmark.
        For internal L2 vertices, it falls back to a cluster centroid mean.
        """
        print("Grouping vertex nodes and isolating Class L1 constant constraints...")
        l1_constants = {}
        l2_vertex_groups = {}
        
        # Pass 1: Scan and lock down absolute L1 positions
        for idx, row in self.gdf_all.iterrows():
            val = str(row[self.vertex_col]).strip() if row[self.vertex_col] is not None else ""
            if not val or val.lower() == 'nan': 
                continue
            
            labels = [lbl.strip() for lbl in val.split(",")]
            coords = list(row["geometry"].exterior.coords)
            
            if row["Class"] == "L1":
                for label, coord in zip(labels[:-1], coords[:-1]):
                    # Set absolute constant framework lock from L1 boundary
                    l1_constants[label] = coord
            else:
                for label, coord in zip(labels[:-1], coords[:-1]):
                    if label not in l2_vertex_groups:
                        l2_vertex_groups[label] = []
                    l2_vertex_groups[label].append(coord)

        print(f"-> Locked {len(l1_constants)} immutable anchor nodes from Class L1 data rows.")
        print("Resolving final target coordinates with fallback centroid calculations...")
        
        # Combine parameters into primary target index map
        all_unique_labels = set(list(l1_constants.keys()) + list(l2_vertex_groups.keys()))
        
        for label in all_unique_labels:
            if label in l1_constants:
                # Rule: Prioritize absolute fixed constraint from reference layer
                self.vertex_targets[label] = l1_constants[label]
            else:
                # Fallback rule: Cluster centroid for floating internal layout corners
                if label in l2_vertex_groups and l2_vertex_groups[label]:
                    pts_arr = np.array(l2_vertex_groups[label])
                    mean_x = np.mean(pts_arr[:, 0])
                    mean_y = np.mean(pts_arr[:, 1])
                    self.vertex_targets[label] = (mean_x, mean_y)
                
        print("-> Target node mapping index successfully optimized.")

    def _reconstruct_polygons_with_targets(self):
        """
        Modifies all edges across all polygons by re-mapping their raw boundary 
        paths directly to the newly computed target coordinates.
        """
        print("Modifying polygon edges and snaps... Reconstructing network geometries...")
        conflated_geometries = []
        
        for idx, row in self.gdf_all.iterrows():
            val = str(row[self.vertex_col]).strip() if row[self.vertex_col] is not None else ""
            if not val or val.lower() == 'nan':
                conflated_geometries.append(row["geometry"])
                continue
                
            labels = [lbl.strip() for lbl in val.split(",")]
            
            # Reconstruct boundary loop from the optimized target dictionary index
            new_coords = []
            for label in labels[:-1]:
                if label in self.vertex_targets:
                    new_coords.append(self.vertex_targets[label])
            
            if new_coords:
                new_coords.append(new_coords[0])  # Close ring geometry structure
                conflated_geometries.append(Polygon(new_coords))
            else:
                conflated_geometries.append(row["geometry"])
                
        # Commit updated geometries back to the active dataframe fabric
        self.gdf_transformed = self.gdf_all.copy()
        self.gdf_transformed["geometry"] = conflated_geometries
        print("-> Geometry reconstruction and edge modification completed successfully.")

    def _generate_and_save_plots(self):
        """Delegates visualization work exclusively to PlotMap to export PNG and SVG formats."""
        print("Echoing graphics layout parameters... Sending data elements to PlotMap module...")
        
        # FIXED: Label your primary dictionary payload as 'Aligned Fabric Output' so PlotMap.py 
        # triggers the dynamic split filtering and colors L1=Red, L2=Grey automatically.
        layers = {
            "Aligned Fabric Output": self.gdf_transformed
        }
        
        # Inject fix_control if it exists to preserve your red triangles layout layer
        if self.gdf_fix is not None and not self.gdf_fix.empty:
            layers["Fix Control"] = self.gdf_fix
        
        # FIXED: Removed 'show_scale_bar=True' to resolve signature parameter TypeError crash
        PlotMap.render_map(
            layers=layers,
            title="Topological Vertex Conflation: Perfect Edge Alignment via L1 Constant Snap",
            filename_base=os.path.join(self.result_dir, "04_vertex_conflation_result"),
            targets=self.vertex_targets
        )

    def _export_to_structured_geopackage(self):
        """Writes out the final structured topology layer into a clean version 4 GeoPackage file."""
        print(f"Preparing output data tables... Packaging structured attributes and geometries...")
        output_gdf = gpd.GeoDataFrame(self.gdf_transformed, geometry='geometry', crs=self.gdf_all.crs)
        
        if os.path.exists(self.output_gpkg):
            os.remove(self.output_gpkg)
            
        print(f"Echoing file system call... Writing layer '{self.output_layer_name}' to database file: {self.output_gpkg}...")
        output_gdf.to_file(self.output_gpkg, layer=self.output_layer_name, driver="GPKG")
        
        # Carry fix_control forward into the final GeoPackage output file too to maintain file structural integrity
        if self.gdf_fix is not None:
            print(f"Forwarding layer 'fix_control' into database file: {self.output_gpkg}...")
            self.gdf_fix.to_file(self.output_gpkg, layer="fix_control", driver="GPKG")
            
        print(f"-> Production layer completely exported. Process terminated successfully.")

if __name__ == "__main__":
    conflator = TopologicalVertexConflation()
    conflator.run_vertex_conflation()
