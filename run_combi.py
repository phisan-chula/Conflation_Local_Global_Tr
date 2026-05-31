# run_combi.py
import os
import shutil
import subprocess
import sys
import time
import glob

# =========================================================================
# HARDCODED CONFIGURATION COMBINATION MATRIX
# =========================================================================
CONFIG_FILES = ["CONFIG/L1x3.toml", "CONFIG/L1x3_CTx1.toml", "CONFIG/CTx4.toml"]
GLOBAL_MODES = ["affine", "tps"]
WEIGHTS = [1, 10000]

def run_command(cmd, dry_run=False):
    """Prints and executes a system shell command block."""
    cmd_string = " ".join(cmd)
    print(f"    Executing: {cmd_string}")
    
    if dry_run:
        return True
        
    try:
        # Stream script logs straight to the terminal window
        subprocess.run(cmd, check=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[CRITICAL FAILURE] Pipeline crashed at command: {cmd_string}")
        print(f"Halting entire matrix execution loop. Exit Code: {e.returncode}")
        sys.exit(e.returncode)

def execute_pipeline_combination(config, mode, weight, dry_run=False):
    """Runs the 4 sequential processing steps for a specific parameter mix."""
    config_base = os.path.splitext(os.path.basename(config))[0]
    target_rename = f"./RESULT_{config_base}_{mode}_{weight}"
    
    print(f"▶ MATRIX STEP: Profile={config} | Mode={mode.upper()} | Weight={weight}")
    print(f"  Expected Output Archive: {target_rename}")
    
    # --- SAFE CLEANUP ACTIVE & DESTINATION WORKSPACES ---
    if not dry_run:
        if os.path.exists("./RESULT"):
            shutil.rmtree("./RESULT")
        if os.path.exists(target_rename):
            shutil.rmtree(target_rename)
            
    # --- SEQUENTIAL PIPELINE INVOCATIONS ---
    # Step 1: Cadaster Fabric Grid Generation
    cmd_1 = ["python", "1_SimuParcel.py", config]
    run_command(cmd_1, dry_run=dry_run)
    
    # Step 2: Local Similarity Topological Pre-Alignment
    cmd_2 = ["python", "2_Local_Similarity.py"]
    run_command(cmd_2, dry_run=dry_run)
    
    # Step 3: Global Core Transformation (Weighted Affine or Spline Non-Linear Warp)
    cmd_3 = ["python", "3_global_aff_tps.py", "-g", mode, "-w", str(weight), "-v"]
    run_command(cmd_3, dry_run=dry_run)
    
    # Step 4: Final Topological Edge Snapping / Closure
    cmd_4 = ["python", "4_vertex_conflation.py"]
    run_command(cmd_4, dry_run=dry_run)
    
    # --- WORKSPACE ARCHIVE SYSTEM REALLOCATION ---
    if not dry_run:
        if os.path.exists("./RESULT"):
            os.rename("./RESULT", target_rename)
            print(f"✅ Success. Output compiled cleanly at {target_rename}\n")
        else:
            print(f"[ERROR] Directory './RESULT' missing at loop completion. Pipeline aborted.")
            sys.exit(1)
    else:
        print(f"  [DRY RUN] Would execute directory storage reallocation: mv ./RESULT -> {target_rename}\n")
    print("-" * 90)

def build_html_gallery(combinations):
    """Dynamically generates a 2-column HTML dashboard for all compiled 04*.svg maps."""
    html_filename = "conflation_matrix_gallery.html"
    print("\n>>> [POST-PROCESSING] Compiling Lossless Vector Inspection Dashboard...")
    
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stage 4: Topological Vertex Conflation Matrix Dashboard</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f6f9;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        header {
            margin-bottom: 30px;
            border-bottom: 2px solid #e1e4e8;
            padding-bottom: 15px;
        }
        h1 { margin: 0 0 5px 0; font-size: 24px; color: #1a202c; }
        p { margin: 0; color: #4a5568; font-size: 14px; }
        
        .grid-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 25px;
            max-width: 1800px;
            margin: 0 auto;
        }
        
        .card {
            background-color: #ffffff;
            border: 1px solid #e1e4e8;
            border-radius: 8px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .card-header {
            background-color: #f8fafc;
            padding: 12px 15px;
            border-bottom: 1px solid #e1e4e8;
            font-weight: 600;
            font-size: 14px;
            color: #2d3748;
        }
        .card-body {
            padding: 15px;
            background-color: #ffffff;
            display: flex;
            justify-content: center;
            align-items: center;
            flex-grow: 1;
        }
        .vector-frame {
            width: 100%;
            height: auto;
            min-height: 500px;
            border: none;
        }
    </style>
</head>
<body>

<header>
    <h1>Stage 4 Final Vertex Conflation Inspection Dashboard</h1>
    <p>Lossless vector verification matrix comparisons: Grid configs vs Warping Strategies vs Weights</p>
</header>

<div class="grid-container">
"""
    
    found_count = 0
    for config, mode, weight in combinations:
        config_base = os.path.splitext(os.path.basename(config))[0]
        folder_name = f"RESULT_{config_base}_{mode}_{weight}"
        
        search_pattern = os.path.join(".", folder_name, "04*.svg")
        matching_files = glob.glob(search_pattern)
        
        if matching_files:
            relative_svg_path = matching_files[0]
            display_title = folder_name.replace("RESULT_", "").replace("_", " | ")
            found_count += 1
            
            html_content += f"""
    <div class="card">
        <div class="card-header">📊 Configuration: {display_title}</div>
        <div class="card-body">
            <object class="vector-frame" data="{relative_svg_path}" type="image/svg+xml"></object>
        </div>
    </div>
"""
        else:
            print(f"          [HTML WARNING] Skipping card: No '04*.svg' found in ./{folder_name}/")

    html_content += """
</div>
</body>
</html>
"""

    with open(html_filename, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"🎉 DASHBOARD FILE GENERATED: ./{html_filename} ({found_count} layers embedded into a 2-column matrix layout).")


def main():
    # Build out all 12 absolute parameter matrix variations (3 configs * 2 modes * 2 weights)
    combinations = []
    for config in CONFIG_FILES:
        for mode in GLOBAL_MODES:
            for weight in WEIGHTS:
                combinations.append((config, mode, weight))
                
    print("=" * 90)
    print("      CADASTER CONFLATION PIPELINE: MATRIX MATURATION SUITE")
    print("=" * 90)
    print(f" Total Hardcoded Combinations Discovered: {len(combinations)}")
    print(" Engine will complete a dry run profile overview before live processing loops begin.")
    print("=" * 90 + "\n")
    
    # =========================================================================
    # PHASE 1: SYSTEM DRY RUN DISPLAY
    # =========================================================================
    print(" [PHASE 1/2] DISPLAYING PIPELINE COMBINATION MATRIX DRY RUN PREVIEW")
    print("=" * 90)
    for idx, (cfg, mod, wt) in enumerate(combinations, start=1):
        print(f"Combination {idx}/{len(combinations)}")
        execute_pipeline_combination(cfg, mod, wt, dry_run=True)
        
    print("\n [DRY RUN VERIFIED CLEAR] Matrix initialization starting in 5 seconds...")
    print(" Press Ctrl+C right now if you need to abort the run sequence.")
    print("=" * 90)
    time.sleep(5)
    
    # =========================================================================
    # PHASE 2: LIVE SCRIPT MATRIX EXECUTION LOOP
    # =========================================================================
    print("\n [PHASE 2/2] STARTING LIVE WORKSPACE COMPILATION PROCESSING RUNS")
    print("=" * 90)
    start_time = time.time()
    
    for idx, (cfg, mod, wt) in enumerate(combinations, start=1):
        print(f"\n[RUNNING BLOCK {idx}/{len(combinations)}]")
        execute_pipeline_combination(cfg, mod, wt, dry_run=False)
        
    # Generate the dashboard after live run completion
    build_html_gallery(combinations)
        
    total_elapsed = time.time() - start_time
    print("\n" + "=" * 90)
    print(f" 🎉 ALL {len(combinations)} PIPELINE MATRIX JOBS EXECUTED SUCCESSFULLY")
    print(f" Total Compiling Time Elapsed: {total_elapsed:.2f} seconds")
    print(f" Open 'conflation_matrix_gallery.html' in your web browser to check outputs.")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    main()
