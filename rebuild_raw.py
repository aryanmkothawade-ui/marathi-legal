import os
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(BASE_DIR, "corpus", "raw_text")
LOG_PATH = os.path.join(BASE_DIR, "logs", "extract_log.json")
EXTRACT_SCRIPT = os.path.join(BASE_DIR, "pipeline", "01_extract.py")

def rebuild():
    print("=" * 65)
    print("  MLDC -- Rebuilding Raw Data")
    print("=" * 65)

    # 1. Clear raw_text directory
    if os.path.exists(RAW_DIR):
        print(f"[*] Clearing directory: {RAW_DIR}")
        for filename in os.listdir(RAW_DIR):
            file_path = os.path.join(RAW_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"[!] Failed to delete {file_path}. Reason: {e}")
    else:
        print(f"[*] Creating directory: {RAW_DIR}")
        os.makedirs(RAW_DIR, exist_ok=True)

    # 2. Delete extraction log
    if os.path.exists(LOG_PATH):
        print(f"[*] Deleting old log: {LOG_PATH}")
        os.remove(LOG_PATH)

    print("[*] Starting extraction process...")
    
    # 3. Run the extraction script
    try:
        subprocess.run([sys.executable, EXTRACT_SCRIPT], check=True)
        print("[+] Rebuild completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"[!] Extraction failed with error code {e.returncode}")
    except KeyboardInterrupt:
        print("\n[!] Extraction cancelled by user.")

if __name__ == "__main__":
    rebuild()
