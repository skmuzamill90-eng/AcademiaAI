"""Tenant-selected CSV services. No client input or legacy-data fallback."""
import threading
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from .config import DATASET_FILES, DATASET_SCHEMAS
from .data_service import DataService, DataValidationError


class TenantRegistry:
    def __init__(self, data_root):
        self.root = Path(data_root) / "tenants"
        self.services = {}
        self.lock = threading.RLock()

    def path(self, institution_id):
        # Prevent path traversal even if the control store is misconfigured.
        identifier = str(UUID(institution_id))
        return self.root / identifier

    def initialize(self, institution_id):
        path = self.path(institution_id)
        path.mkdir(parents=True, exist_ok=False)
        for name, filename in DATASET_FILES.items():
            (path / filename).write_text(",".join(DATASET_SCHEMAS[name]["required"]) + "\n", encoding="utf-8")
        return self.get(institution_id)

    def get(self, institution_id):
        with self.lock:
            if institution_id not in self.services:
                try:
                    self.services[institution_id] = DataService(self.path(institution_id)).load()
                except (DataValidationError, OSError, ValueError):
                    raise HTTPException(503, "Institution datasets are unavailable. Contact your administrator.")
            return self.services[institution_id]


def acquire_process_lock(path):
    """CSV caches and JSON transactions require exactly one running writer process."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("r+b")
    except FileNotFoundError:
        handle = path.open("w+b")
    if handle.seek(0, 2) == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        import os
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Another process owns this store. Use one worker; stop the API before CLI migrations.")
    return handle
