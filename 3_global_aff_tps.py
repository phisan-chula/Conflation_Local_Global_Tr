# 3_global_aff_tps.py
import argparse
import os
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon
import PlotMap

class TransformationStrategy:
    """
    Abstract Base Class establishing the contract for spatial transformation strategies.
    Inherit from this class to implement new mathematical warping models.
    """
    def fit(self, src_pts, dst_pts, weights):
        """Fits the transformation model parameters using control point vectors."""
        raise NotImplementedError("Transformation strategies must implement a fit method.")
        
    def transform(self, coords):
        """Applies the calculated transformation model to an array of coordinates."""
        raise NotImplementedError("Transformation strategies must implement a transform method.")


class WeightedAffineStrategy(TransformationStrategy):
    """Computes a 6-parameter Weighted Least-Squares Affine transformation matrix."""
    def __init__(self):
        self.affine_matrix = None

    def fit(self, src_pts, dst_pts, weights):
        X = np.hstack([np.array(src_pts), np.ones((len(src_pts), 1))])
        Y = np.array(dst_pts)
        W = np.diag(weights)
        
        # Weighted Least Squares Formula: (X^T * W * X)^-1 * X^T * W * Y
        Xt_W = np.dot(X.T, W)
        self.affine_matrix = np.linalg.solve(np.dot(Xt_W, X), np.dot(Xt_W, Y))

    def transform(self, coords):
        padded_coords = np.hstack([coords, np.ones((len(coords), 1))])
        return np.dot(padded_coords, self.affine_matrix)


class ThinPlateSplineStrategy(TransformationStrategy):
    """
    Computes a non-linear Thin Plate Spline (TPS) coordinate transformation mapping.
    Acts as an exact local interpolator where point weights have no directional scaling effect.
    """
    def __init__(self, regularization=1e-6):
        self.regularization = regularization
        self.src_pts = None
        self.W = None  # Non-linear radial basis coefficient weights
        self.A = None  # Global affine polynomial component coefficients

    def _u_func(self, r):
        """Radial Basis Kernel Function: U(r) = r^2 * log(r^2)"""
        mask = r > 1e-9
        u = np.zeros_like(r)
        u[mask] = (r[mask] ** 2) * np.log(r[mask] ** 2)
        return u

    def fit(self, src_pts, dst_pts, weights):
        self.src_pts = np.array(src_pts)
        Y = np.array(dst_pts)
        num_pts = len(self.src_pts)
        
        # 1. Compute radial distances between all control point combinations (K matrix)
        diff = self.src_pts[:, np.newaxis, :] - self.src_pts[np.newaxis, :, :]
        r = np.linalg.norm(diff, axis=2)
        K = self._u_func(r)
        
        # Bending regularization parameters
        weight_factor = np.diag(1.0 / (np.array(weights) + 1e-6)) * self.regularization
        K += weight_factor
        
        # 2. Build global polynomial linear parameter plane (P matrix)
        P = np.hstack([np.ones((num_pts, 1)), self.src_pts])
        
        # 3. Assemble full TPS system block matrix L
        L = np.block([
            [K, P],
            [P.T, np.zeros((3, 3))]
        ])
        
        # 4. Target matrix padded with zero-moment condition vectors
        Y_padded = np.vstack([Y, np.zeros((3, 2))])
        
        # 5. Solve system parameters simultaneously
        coefficients = np.linalg.solve(L, Y_padded)
        self.W = coefficients[:num_pts]
        self.A = coefficients[num_pts:]

    def transform(self, coords):
        coords_arr = np.array(coords)
        num_target_pts = len(coords_arr)
        
        if self.src_pts is None:
            return coords_arr
            
        # Distance calculation matrices mapping target geometry back to source roots
        diff = coords_arr[:, np.newaxis, :] - self.src_pts[np.newaxis, :, :]
        r = np.linalg.norm(diff, axis=2)
        K = self._u_func(r)
        
        # Polynomial projection components evaluation
        P = np.hstack([np.ones((num_target_pts, 1)), coords_arr])
        
        # Map transformed values: Z = K*W + P*A
        return np.dot(K, self.W) + np.dot(P, self.A)


class PiecewiseControlWarpPipeline:
    def __init__(self, result_dir="RESULT", weight=10000.0, verbose=False, mode="affine"):
        self.result_dir = result_dir
        self.input_gpkg = os.path.abspath(os.path.join(result_dir, "02_parcel_conflation_aligned.gpkg"))
        self.output_gpkg = os.path.abspath(os.path.join(result_dir, "03_global_aligned.gpkg"))
        self.vertex_col = "Vertex_Sequenc"
        self.control_targets = {}
        self.fix_control_weight = weight
        self.verbose = verbose
        
        # Dynamic Strategy Selection based on requested mode option flag
        if mode.lower() == "tps":
            self.strategy = ThinPlateSplineStrategy()
            self.mode_label = "THIN PLATE SPLINE (TPS) NON-LINEAR WARP"
        else:
            self.strategy = WeightedAffineStrategy()
            self.mode_label = "GLOBAL WEIGHTED AFFINE REGRESSION"

    def run_transform_pipeline(self):
        print("\n" + "="*60)
        print(f"  STEP 3: HYBRID WARP ENGINE - {self.mode_label}")
        print(f"  [CONFIGURATION] Fix Control Variable Weight: {self.fix_control_weight}")
        
        # Explicit echo warning for the Thin Plate Spline strategy
        if "TPS" in self.mode_label:
            print("  [ALERT] Thin Plate Spline acts as an exact local interpolator.")
            print("          --> Individual control weights have NO EFFECT in TPS mode!")
            
        print(f"  [CONFIGURATION] Verbose Reporting Mode: {self.verbose}")
        print("="*60)

        print(f"[DATABASE IO] Opening input alignment workspace:\n  -> Path: {self.input_gpkg}")
        self.gdf_all = gpd.read_file(self.input_gpkg, layer="aligned_parcels")
        
        # Load the clean point layer generated by Step 2
        try:
            gdf_adj_vertices = gpd.read_file(self.input_gpkg, layer="adjusted_vertices")
            print(f"[DATABASE IO] Opened adjusted vertices layer tracking {len(gdf_adj_vertices)} node locations.")
        except Exception:
            raise FileNotFoundError(f"[ERROR] Required 'adjusted_vertices' layer missing from {self.input_gpkg}!")

        try:
            self.gdf_fix = gpd.read_file(self.input_gpkg, layer="fix_control")
            print(f"[DATABASE IO] Isolated FIX_CONTROL layer tracking {len(self.gdf_fix)} absolute anchor points.")
        except Exception:
            self.gdf_fix = None
            print("[DATABASE IO] Warning: fix_control layer not detected in database.")

        # Build lookups for the L1 framework boundary shapes (Priority 1 Target)
        l1_targets = {}
        gdf_l1 = self.gdf_all[self.gdf_all['Class'] == 'L1']
        for idx, row in gdf_l1.iterrows():
            labels = [lbl.strip() for lbl in str(row[self.vertex_col]).split(",")][:-1]
            coords = list(row["geometry"].exterior.coords)[:-1]
            for label, coord in zip(labels, coords):
                l1_targets[label] = (float(coord[0]), float(coord[1]))

        # Map fix_control anchor coordinates strictly by string identifier matching (Priority 2 Target)
        fix_lookup = {}
        if self.gdf_fix is not None and not self.gdf_fix.empty:
            for idx, row in self.gdf_fix.iterrows():
                fix_lookup[str(row['id']).strip()] = (float(row['geometry'].x), float(row['geometry'].y))

        # Compile optimization tie-point pairs by reading the adjusted points layer
        pair_records = []
        src_pts = []
        dst_pts = []
        weights = []
        
        # Loop over unique vertex points from L2 adjusted layer
        for idx, pt_row in gdf_adj_vertices.iterrows():
            v_id = str(pt_row["vertex_id"]).strip()
            l2_x = float(pt_row["geometry"].x)
            l2_y = float(pt_row["geometry"].y)
            l2_coord = (l2_x, l2_y)

            # Exact text element matching inside split list
            sharing_l2_parcels = []
            for _, p_row in self.gdf_all[self.gdf_all['Class'] == 'L2'].iterrows():
                p_labels = [lbl.strip() for lbl in str(p_row[self.vertex_col]).split(",") if lbl.strip()]
                if v_id in p_labels:
                    sharing_l2_parcels.append(p_row)

            # If NO adjustable L2 parcels actually own this vertex, skip it!
            if not sharing_l2_parcels:
                continue

            p_id_list = ", ".join([f"P{int(p['id'])}" for p in sharing_l2_parcels])

            # Hierarchical engine lookup matching rules
            target_coord = None
            tag_label = ""
            c_weight = 1.0

            if v_id in l1_targets:
                target_coord = l1_targets[v_id]
                tag_label = "L1 MATCH"
                c_weight = 1.0
            elif v_id in fix_lookup:
                target_coord = fix_lookup[v_id]
                tag_label = "FIX_CONTROL"
                c_weight = self.fix_control_weight

            if target_coord is not None:
                self.control_targets[v_id] = target_coord
                for _ in range(len(sharing_l2_parcels)):
                    src_pts.append(l2_coord)
                    dst_pts.append(target_coord)
                    weights.append(c_weight)
                
                # Keep tracking metadata fields for diagnostic logging outputs
                pair_records.append({
                    "id": v_id, "parcels": p_id_list, "src": l2_coord, "dst": target_coord,
                    "weight": c_weight, "tag": tag_label
                })

        # Global/Local Transformation Model Execution
        if len(src_pts) < 3:
            print(f"[SAFE MODE] Only {len(src_pts)} text-matched pairs found (minimum 3 required). Skipping warp matrix operation.")
        else:
            print(f"[COMPUTE] Fitting selected transformation strategy parameters over {len(src_pts)} coordinates...")
            self.strategy.fit(src_pts, dst_pts, weights)
            print("[COMPUTE] Mathematical model fitted successfully.")

            # Residual table logging output if verbose flag is set
            if self.verbose:
                print("\n" + "-" * 145)
                print(f"{'VERTEX_ID':<12} | {'SHARING PARCELS':<16} | {'SOURCE COORD (ADJUSTED)':<26} | {'TARGET COORD (ANCHOR)':<26} | {'WEIGHT':<10} | {'vx (m)':<10} | {'vy (m)':<10} | {'LAYER CONTEXT'}")
                print("-" * 145)
                
                for rec in pair_records:
                    computed_coord = self.strategy.transform(np.array([rec["src"]]))[0]
                    vx = rec["dst"][0] - computed_coord[0]
                    vy = rec["dst"][1] - computed_coord[1]
                    
                    src_str = f"({rec['src'][0]:.3f}, {rec['src'][1]:.3f})"
                    dst_str = f"({rec['dst'][0]:.3f}, {rec['dst'][1]:.3f})"
                    
                    print(f"{rec['id']:<12} | {rec['parcels']:<16} | {src_str:<26} | {dst_str:<26} | {rec['weight']:<10.1f} | {vx:<10.4f} | {vy:<10.4f} | [{rec['tag']}]")
                print("-" * 145 + "\n")

            # COORDS TRANSFORMED FOR L2 ONLY; L1 REMAINS CONSTANT
            warped_geometries = []
            for idx, row in self.gdf_all.iterrows():
                if row.get("Class") == "L1":
                    # Keep absolute L1 boundary data completely constant
                    warped_geometries.append(row["geometry"])
                    continue
                
                # Apply strategy parameters exclusively to adjustable L2 fabrics
                coords = np.array(row["geometry"].exterior.coords)
                warped_coords = self.strategy.transform(coords)
                warped_geometries.append(Polygon(warped_coords))
                
            self.gdf_all["geometry"] = warped_geometries
            print("[COMPUTE] L2 fabrics warped successfully. Class L1 protected completely.")

        # Data Layer Exports and Disk IO (Both L1 and L2 transferred inside self.gdf_all)
        if os.path.exists(self.output_gpkg): 
            os.remove(self.output_gpkg)
            
        print(f"[EXPORT] Writing combined layer 'global_aligned' into database: {self.output_gpkg}")
        self.gdf_all.to_file(self.output_gpkg, layer="global_aligned", driver="GPKG")
        if self.gdf_fix is not None:
            print(f"[EXPORT] Writing layer 'fix_control' into database: {self.output_gpkg}")
            self.gdf_fix.to_file(self.output_gpkg, layer="fix_control", driver="GPKG")

        img_base_path = os.path.abspath(os.path.join(self.result_dir, "03_conflation_result"))
        print(f"[EXPORT] Rendering high-resolution inspection map: {img_base_path}.png")
        print(f"[EXPORT] Rendering lossless vector workspace sheet: {img_base_path}.svg")
        
        PlotMap.render_map(
            layers={"Aligned Fabric Output": self.gdf_all, "Fix Control": self.gdf_fix}, 
            title=f"Global Fabric Warp Framework ({self.mode_label})", 
            filename_base=img_base_path, 
            targets=self.control_targets
        )
        print(f"[STAGE 3 COMPLETED] Workspace database exported cleanly to {self.output_gpkg}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-w", "--weight", type=float, default=10000.0)
    parser.add_argument("-v", "--verbose", action="store_true", 
                        help="Print verbose matching diagnostics and residual error logs table")
    parser.add_argument("-g", "--global_mode", type=str, choices=["affine", "tps"], default="affine",
                        help="Choose spatial mapping algorithm structure: 'affine' (default) or 'tps'")
    args = parser.parse_args()

    PiecewiseControlWarpPipeline(
        weight=args.weight, 
        verbose=args.verbose,
        mode=args.global_mode
    ).run_transform_pipeline()
