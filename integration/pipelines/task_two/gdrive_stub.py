"""
gdrive_stub.py — Minimal stub for Google Drive upload.

This is a placeholder so that auto_extinguish.py can import and call the
uploader without crashing.  Replace with a full implementation (or point
the import at the real gdrive_upload.py) once that module is rebuilt.
"""

from __future__ import annotations

import os
import shutil


from .config import TEAM_NAME


class DriveUploader:
    """Stub uploader — saves photos locally and logs a warning."""

    def __init__(self, config_path: str = ""):
        self._config_path = config_path
        if config_path and os.path.isfile(config_path):
            print(f"[GDRIVE STUB] Config found at {config_path} — "
                  "but real upload is NOT implemented in this stub.")
        else:
            print("[GDRIVE STUB] No gdrive_config.json — uploads will be skipped.")

    def upload_task2_photo(self, local_path: str, target_number: int) -> bool:
        """'Upload' a photo by copying it to a well-known directory.

        In the real implementation this would push to Google Drive.
        Returns True so the state machine considers it successful.
        """
        dest_name = f"Task_2_{TEAM_NAME}_target_{target_number}.jpg"
        dest_dir = os.path.join(os.path.dirname(local_path) or ".", "uploaded")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, dest_name)
        shutil.copy2(local_path, dest_path)
        print(f"[GDRIVE STUB] Copied → {dest_path} (real upload not implemented)")
        return True
