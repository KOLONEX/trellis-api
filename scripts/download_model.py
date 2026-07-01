"""Download TRELLIS-image-large at build time into MODEL_DIR."""
import os
import sys

from huggingface_hub import snapshot_download

REPO_ID = "microsoft/TRELLIS-image-large"
MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/models/TRELLIS-image-large")


def main() -> int:
    print(f"Downloading {REPO_ID} -> {MODEL_DIR}", flush=True)
    snapshot_download(repo_id=REPO_ID, local_dir=MODEL_DIR)
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
