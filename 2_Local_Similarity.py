# 2_Local_Similarity.py
import argparse
import os
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon, Point
import PlotMap

class LocalSimilarityTransformationEngine:
    def __init__(self, result_dir="RESULT"):
        self.result_dir = result_dir
        self.input_gpkg = os.path.abspath(os.path.join(result_dir, "01_parcel_conflation_sim.gpkg"))
        self.output_gpkg = os.path.abspath(os.path.join(result_dir, "02_parcel_conflation_aligned.gpkg"))
        self.vertex_col = "Vertex_Sequenc"

    def compute_similarity_matrix(self, src_pts, dst_pts):
        """
        Computes a 4-parameter similarity transformation matrix (Scale, Rotation, Translations)
        Mapping: X_target = a*X - b*Y + Tx , Y_target = b*X + a*Y + Ty
        """
        A = []
        B = []
        for (x, y), (u, v) in zip(src_pts, dst_pts):
            A.append([x, -y, 1, 0])
            A.append([y,  x, 0, 1])
            B.append(u)
            B.append(v)
        
        # Solve least squares parameters: [a, b, Tx, Ty]
        params, _, _, _ = np.linalg.lstsq(np.array(A), np.array(B), rcond=None)
        a, b, tx, ty = params
        
        M = np.array([
            [a, -b, tx],
            [b,  a, ty],
            [0,  0,  1]
        ])
        return M

    def run_alignment_pipeline(self):
        print("\n" + "="*60)
        print("  STEP 2: LOCAL SIMILARITY ALIGNMENT ENGINE (VERTEX OPTIMIZED)")
        print("="*60)

        print(f"[DATABASE IO] Opening stage 1 simulation workspace:\n  -> Path: {self.input_gpkg}")
        if not os.path.exists(self.input_gpkg):
            raise FileNotFoundError(f"[ERROR] Simulation database not found at {self.input_gpkg}. Run Step 1 first!")

        # 1. Load incoming feature layers from Step 1 Workspace
        gdf_measured = gpd.read_file(self.input_gpkg, layer="measured")
        
        # Open fix_control to pass it forward down the pipeline stream untouched
        try:
            gdf_fix_forward = gpd.read_file(self.input_gpkg, layer="fix_control")
            print(f"[DATABASE IO] Loaded fix_control tracking {len(gdf_fix_forward)} points to carry forward.")
        except Exception:
            gdf_fix_forward = None
            print("[DATABASE IO] Warning: fix_control layer not found in stage 1. Cannot forward.")

        # 2. Extract fixed baseline anchor coordinates straight from Class L1 parcels
        l1_anchors = {}
        gdf_l1 = gdf_measured[gdf_measured['Class'] == 'L1']
        for idx, row in gdf_l1.iterrows():
            labels = [lbl.strip() for lbl in str(row[self.vertex_col]).split(",")][:-1]
            coords = list(row["geometry"].exterior.coords)[:-1]
            for label, coord in zip(labels, coords):
                l1_anchors[label] = coord

        # 3. Group all L2 vertex observations to calculate unified target coordinates
        vertex_observations = {}
        for idx, row in gdf_measured.iterrows():
            if row.get('Class', 'L2') == 'L2':
                labels = [lbl.strip() for lbl in str(row[self.vertex_col]).split(",")][:-1]
                coords = list(row["geometry"].exterior.coords)[:-1]
                for label, coord in zip(labels, coords):
                    vertex_observations.setdefault(label, []).append(coord)

        # 4. Optimize target coordinates per unique vertex ID
        optimized_targets = {}
        for v_id, obs_list in vertex_observations.items():
            if v_id in l1_anchors:
                # If tied to an L1 parcel, lock it strictly to that absolute position
                optimized_targets[v_id] = l1_anchors[v_id]
            else:
                # Optimize for the target coordinate using the mean of competing L2 observations
                obs_arr = np.array(obs_list)
                optimized_targets[v_id] = (np.mean(obs_arr[:, 0]), np.mean(obs_arr[:, 1]))

        # 5. Execute Localized Similarity Transformation for each individual L2 parcel
        print("[COMPUTE] Processing individual similarity transformations against optimized targets...")
        aligned_geometries = []
        final_vertex_records = []

        for idx, row in gdf_measured.iterrows():
            p_id = row['id']
            p_class = row.get('Class', 'L2')
            labels = [lbl.strip() for lbl in str(row[self.vertex_col]).split(",")][:-1]
            src_coords = list(row["geometry"].exterior.coords)[:-1]
            
            if p_class == 'L1':
                # Preserve fixed L1 parcels exactly as they arrived
                aligned_geometries.append(row["geometry"])
                for label, s_coord in zip(labels, src_coords):
                    final_vertex_records.append({"vertex_id": label, "geometry": Point(s_coord[0], s_coord[1])})
                continue

            # Build control point pairs using the optimized targets
            control_pair_src = []
            control_pair_dst = []
            for label, s_coord in zip(labels, src_coords):
                if label in optimized_targets:
                    control_pair_src.append(s_coord)
                    control_pair_dst.append(optimized_targets[label])

            # Compute transformation matrix back down to the target space
            if len(control_pair_src) >= 2:
                M = self.compute_similarity_matrix(control_pair_src, control_pair_dst)
            else:
                M = np.identity(3)

            # Apply similarity transformation matrix directly to each adjusted measured vertex
            transformed_coords = []
            for label, (x, y) in zip(labels, src_coords):
                pt_vector = np.array([x, y, 1.0])
                trans_pt = np.dot(M, pt_vector)
                x_adj, y_adj = trans_pt[0], trans_pt[1]
                
                transformed_coords.append((x_adj, y_adj))
                
                # Store transformed vertex points for database layer tracking
                final_vertex_records.append({
                    "vertex_id": label,
                    "geometry": Point(x_adj, y_adj)
                })
            
            aligned_geometries.append(Polygon(transformed_coords))

        # Update layer collection structures
        gdf_aligned_parcels = gdf_measured.copy()
        gdf_aligned_parcels["geometry"] = aligned_geometries

        # 6. Compile and deduplicate Adjusted Vertex Point Features
        print("[COMPUTE] Compiling adjusted point features database registry...")
        gdf_vertices = gpd.GeoDataFrame(final_vertex_records, crs=gdf_measured.crs)
        gdf_vertices = gdf_vertices.drop_duplicates(subset=["vertex_id"], keep="first")
        print(f"[COMPUTE] Successfully optimized {len(gdf_vertices)} unique adjusted point records.")

        # 7. Database Packaging & Disk Exports
        if os.path.exists(self.output_gpkg):
            os.remove(self.output_gpkg)

        print(f"[EXPORT] Writing layer 'aligned_parcels' into database: {self.output_gpkg}")
        gdf_aligned_parcels.to_file(self.output_gpkg, layer="aligned_parcels", driver="GPKG")

        print(f"[EXPORT] Writing point layer 'adjusted_vertices' into database: {self.output_gpkg}")
        gdf_vertices.to_file(self.output_gpkg, layer="adjusted_vertices", driver="GPKG")

        # Export the untouched fix_control layer down the pipeline file
        if gdf_fix_forward is not None:
            print(f"[EXPORT] Forwarding point layer 'fix_control' into database: {self.output_gpkg}")
            gdf_fix_forward.to_file(self.output_gpkg, layer="fix_control", driver="GPKG")

        # 8. Render Graphical Map Sheets
        img_base_path = os.path.abspath(os.path.join(self.result_dir, "02_alignment_result"))
        print(f"[EXPORT] Rendering high-resolution inspection map: {img_base_path}.png")
        print(f"[EXPORT] Rendering lossless vector workspace sheet: {img_base_path}.svg")
        
        map_layers = {
            "Aligned Fabric Output": gdf_aligned_parcels,
            "Adjusted Vertices": gdf_vertices
        }

        if gdf_fix_forward is not None and not gdf_fix_forward.empty:
            map_layers["Fix Control"] = gdf_fix_forward

        PlotMap.render_map(
            layers=map_layers,
            title="Stage 2: Local Similarity Topology Alignment Workspace",
            filename_base=img_base_path
        )
        print(f"[STAGE 2 COMPLETED] Local similarity alignment step successful.\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Step 2: Local Similarity Transformation Engine.")
    args = parser.parse_args()

    LocalSimilarityTransformationEngine().run_alignment_pipeline()
