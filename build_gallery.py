# build_gallery.py
import os
import glob

# Define the explicit 8 matrix folders in alphabetical order for predictable grouping
TARGET_FOLDERS = [
    "RESULT_L1x3_affine_1",
    "RESULT_L1x3_affine_10000",
    "RESULT_L1x3_tps_1",
    "RESULT_L1x3_tps_10000",
    "RESULT_L1x3_CTx1_affine_1",
    "RESULT_L1x3_CTx1_affine_10000",
    "RESULT_L1x3_CTx1_tps_1",
    "RESULT_L1x3_CTx1_tps_10000"
]

def main():
    html_filename = "conflation_matrix_gallery.html"
    
    # HTML Layout Header with modern styling and a responsive 2-column CSS Grid framework
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
        
        /* Strict 2-Column Responsive Matrix Grid Configuration */
        .grid-container {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 25px;
            max-width: 1600px;
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
        
        /* Clean SVG frame view encapsulation allowing smooth zooming */
        .vector-frame {
            width: 100%;
            height: auto;
            min-height: 450px;
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
    
    # Iterate through specified targets to build the sheet pairs
    for folder in TARGET_FOLDERS:
        # Search specifically for Stage 4 SVG outputs inside the explicit folder targets
        search_pattern = os.path.join(".", folder, "04*.svg")
        matching_files = glob.glob(search_pattern)
        
        if matching_files:
            # Use relative file path targeting to guarantee working browser loads
            relative_svg_path = matching_files[0]
            found_count += 1
            
            # Format display labels cleanly for the header asset cards
            display_title = folder.replace("RESULT_", "").replace("_", " | ")
            
            html_content += f"""
    <div class="card">
        <div class="card-header">📊 Configuration: {display_title}</div>
        <div class="card-body">
            <object class="vector-frame" data="{relative_svg_path}" type="image/svg+xml"></object>
        </div>
    </div>
"""
        else:
            print(f"[WARNING] No '04*.svg' target map found inside folder: ./{folder}/")

    html_content += """
</div>

</body>
</html>
"""

    # Save to disk container
    with open(html_filename, "w", encoding="utf-8") as html_file:
        html_file.write(html_content)
        
    print("\n" + "="*80)
    print(f"🎉 DASHBOARD GENERATED SUCCESSFULLY: {html_filename}")
    print(f" Embedded and verified {found_count} vector output sheets into a 2-column mesh dashboard.")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
