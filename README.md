# services/analyzer_service.py
import os
import subprocess
import shutil
from pathlib import Path
from config import OUTPUT_DIR, INPUT_DIR

def analyze_project(migration_id: str, folder_path: str = None) -> dict:
    # Resolve folder path
    if folder_path is None:
        folder_path = os.path.join(INPUT_DIR, migration_id)

    if not os.path.isdir(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    # Analyzer script location (where it writes output)
    analyzer_dir = "/mnt/MyDocuments/new_analyzer/migration-service/migration_analysis_api_latest/tools/vbnet-project-health-analyzer-precision-classification_6738"

    # Output directory (where we want to store results)
    output_dir = os.path.join(OUTPUT_DIR, migration_id, "ir")
    os.makedirs(output_dir, exist_ok=True)

    # Run analyzer: writes to analyzer_dir/
    try:
        result = subprocess.run(
            ["python3.11", "-m", "vbnet_migration_analyzer", folder_path],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=analyzer_dir  # ensure module runs in correct dir
        )
        if result.returncode != 0:
            raise RuntimeError(f"Analyzer failed: {result.stderr}")
    except FileNotFoundError:
        raise RuntimeError("python3.11 not found")
    except Exception as e:
        raise RuntimeError(f"Analyzer execution error: {str(e)}")

    # Source files (where analyzer writes)
    src_json = os.path.join(analyzer_dir, "project-health.json")
    src_txt = os.path.join(analyzer_dir, "migration-report.txt")

    # Destination files (in output/{id}/ir/)
    dst_json = os.path.join(output_dir, "project.ir.json")
    dst_txt = os.path.join(output_dir, "report.txt")

    # Copy files
    if not os.path.exists(src_json):
        raise RuntimeError(f"Analyzer did not produce {src_json}")
    shutil.copy2(src_json, dst_json)

    if not os.path.exists(src_txt):
        raise RuntimeError(f"Analyzer did not produce {src_txt}")
    shutil.copy2(src_txt, dst_txt)

    return {
        "json_path": dst_json,
        "txt_path": dst_txt,
        "migration_id": migration_id
    }
