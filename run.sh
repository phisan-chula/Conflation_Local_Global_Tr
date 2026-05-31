#!/bin/bash

# Exit immediately if any command exits with a non-zero status
set -e

# --- Default Configurations ---
#CONFIG_FILE="CONFIG/L1x3_CTx1.toml"
CONFIG_FILE="CONFIG/L1x3.toml"
MODE="affine"
WEIGHT="10000.0"
VERBOSE_FLAG="-v" # FIXED: Default verbose telemetry log table is now ON
TARGET_DIR="./RESULT"

# --- Usage Help Menu ---
usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -c, --config PATH    Path to the configuration TOML file (Default: $CONFIG_FILE)"
    echo "  -g, --mode MODE      Warping mode: 'affine' or 'tps' (Default: $MODE)"
    echo "  -w, --weight VAL     Fix control target variable weight (Default: $WEIGHT)"
    echo "  -q, --quiet          Disable verbose telemetry table logs in Step 3"
    echo "  -h, --help           Show this help menu"
    echo ""
    echo "Example:"
    echo "  $0 -c CONFIG/L1x3_CTx1.toml -g tps -w 5000 -q"
    exit 1
}

# --- Parse Command Line Arguments ---
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -g|--mode)
            MODE=$(echo "$2" | tr '[:upper:]' '[:lower:]')
            if [[ "$MODE" != "affine" && "$MODE" != "tps" ]]; then
                echo "Error: Invalid mode '$2'. Choose 'affine' or 'tps'."
                exit 1
            fi
            shift 2
            ;;
        -w|--weight)
            WEIGHT="$2"
            shift 2
            ;;
        -q|--quiet)
            VERBOSE_FLAG="" # Disables the verbose flag for step 3
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            ;;
    esac
done

echo "========================================================================="
echo " STARTING CADASTER CONFLATION PIPELINE ROUTINE"
echo "========================================================================="
echo " Profile Target : $CONFIG_FILE"
echo " Warping Strategy: $(echo $MODE | tr '[:lower:]' '[:upper:]')"
echo " Anchors Weight  : $WEIGHT"
echo " Verbose Output  : $([ -n "$VERBOSE_FLAG" ] && echo "ENABLED (DEFAULT)" || echo "DISABLED")"
echo "========================================================================="
echo ""

# --- SAFE WORKSPACE CLEANUP PASS ---
if [ -d "$TARGET_DIR" ]; then
    if [[ "$TARGET_DIR" == "./RESULT" || "$TARGET_DIR" == "RESULT" ]]; then
        echo ">>> [CLEANUP] Safely clearing previous workspace data at $TARGET_DIR..."
        echo "rm -rf $TARGET_DIR"
        rm -rf "$TARGET_DIR"
    else
        echo ">>> [SAFETY WARNING] Aborting cleanup: Directory path '$TARGET_DIR' looks unsafe."
        exit 1
    fi
else
    echo ">>> [CLEANUP] No previous workspace detected. Starting fresh."
fi
echo ""

# --- STEP 1: Synthetic Fabric Generation ---
echo ">>> [STAGE 1/4] Running Grid Simulation..."
echo "python 1_SimuParcel.py \"$CONFIG_FILE\""
python 1_SimuParcel.py "$CONFIG_FILE"
echo ""

# --- STEP 2: Local Similarity Pre-Alignment ---
echo ">>> [STAGE 2/4] Running Localized Vertex Pre-Alignment..."
echo "python 2_Local_Similarity.py"
python 2_Local_Similarity.py
echo ""

# --- STEP 3: Global Transformation (Unified Strategy Engine) ---
echo ">>> [STAGE 3/4] Executing Global Matrix Hybrid Warp Engine..."
echo "python 3_global_aff_tps.py -g \"$MODE\" -w \"$WEIGHT\" $VERBOSE_FLAG"
python 3_global_aff_tps.py -g "$MODE" -w "$WEIGHT" $VERBOSE_FLAG
echo ""

# --- STEP 4: Topological Vertex Closure ---
echo ">>> [STAGE 4/4] Executing Final Mesh Vertex Conflation Snap..."
echo "python 4_vertex_conflation.py"
python 4_vertex_conflation.py

echo ""
echo "========================================================================="
echo " 🎉 PIPELINE EXECUTION COMPLETED SUCCESSFULLY"
echo " Workspace assets compiled inside: ./RESULT/"
echo "========================================================================="
