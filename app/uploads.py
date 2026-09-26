"""Secure file upload handling.

- Allow-listed types, verified by file signature (magic bytes), not by the name the browser sends.
- Stored under random names; original names are kept only as metadata.
- Patient documents live outside the web root (UPLOAD_DIR) and are served only through an
  authorised route. Website gallery images are public by design and stored in PUBLIC_UPLOAD_DIR
  (served at /static/uploads/...).
"""
from __future__ import annotations

import secrets
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

SIGNATURES = {
    "pdf": (b"%PDF-", "application/pdf"),
    "png": (b"\x89PNG\r\n\x1a\n", "image/png"),
    "jpg": (b"\xff\xd8\xff", "image/jpeg"),
    "webp": (b"RIFF", "image/webp"),  # plus 'WEBP' at offset 8
}
DOC_TYPES = {"pdf", "png", "jpg", "webp"}
IMAGE_TYPES = {"png", "jpg", "webp"}


def sniff(head: bytes) -> str | None:
    for kind, (sig, _mime) in SIGNATURES.items():
        if head.startswith(sig):
            if kind == "webp" and head[8:12] != b"WEBP":
                continue
            return kind
    return None


def _read_checked(file_storage, allowed: set[str]):
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    kind = sniff(head)
    if kind not in allowed:
        return None, None, "Unsupported file type. Allowed: " + ", ".join(sorted(t.upper() for t in allowed)) + "."
    data = file_storage.stream.read()
    if not data:
        return None, None, "The file is empty."
    limit = current_app.config.get("MAX_DOCUMENT_MB", 10)
    if len(data) > limit * 1024 * 1024:
        return None, None, f"The file is larger than {limit} MB."
    return kind, data, None


def save_document(file_storage):
    """Returns (stored_name, mime, size, original_name, error)."""
    kind, data, err = _read_checked(file_storage, DOC_TYPES)
    if err:
        return None, None, 0, None, err
    stored = f"{secrets.token_hex(16)}.{kind}"
    folder = Path(current_app.config["UPLOAD_DIR"])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored).write_bytes(data)
    original = secure_filename(file_storage.filename or "") or f"document.{kind}"
    return stored, SIGNATURES[kind][1], len(data), original[:150], None


def document_path(stored_name: str) -> Path:
    folder = Path(current_app.config["UPLOAD_DIR"]).resolve()
    path = (folder / stored_name).resolve()
    if folder not in path.parents:
        raise ValueError("invalid path")
    return path


def save_public_image(file_storage):
    """Returns (relative static path, error)."""
    kind, data, err = _read_checked(file_storage, IMAGE_TYPES)
    if err:
        return None, err
    folder = Path(current_app.config["PUBLIC_UPLOAD_DIR"]) / "gallery"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(12)}.{kind}"
    (folder / name).write_bytes(data)
    return f"uploads/gallery/{name}", None
