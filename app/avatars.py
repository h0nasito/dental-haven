"""Profile pictures: cropped to a square and made small (256 x 256 px JPEG, about 10-25 KB), with no photo metadata."""
from __future__ import annotations

import io
import secrets
from pathlib import Path

from flask import current_app, url_for

from .uploads import IMAGE_TYPES, _read_checked

SIDE = 256
QUALITY = 78
SUBFOLDER = "avatars"


def make_square(data: bytes) -> bytes | None:
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            elif im.mode != "RGB":
                im = im.convert("RGB")
            im = ImageOps.fit(im, (SIDE, SIDE), Image.LANCZOS, centering=(0.5, 0.4))   # a little above centre: faces
            out = io.BytesIO()
            im.save(out, "JPEG", quality=QUALITY, optimize=True, progressive=True)   # saved fresh: no EXIF / GPS
            return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def folder() -> Path:
    f = Path(current_app.config["UPLOAD_DIR"]) / SUBFOLDER
    f.mkdir(parents=True, exist_ok=True)
    return f


def save(file_storage):
    """Returns (stored file name, error)."""
    kind, data, err = _read_checked(file_storage, IMAGE_TYPES, limit_mb=30)
    if err:
        return None, err
    small = make_square(data)
    if small is None:
        return None, "That picture couldn't be read. Try a JPG or PNG photo."
    name = f"{secrets.token_hex(12)}.jpg"
    (folder() / name).write_bytes(small)
    return name, None


def delete(name: str | None):
    if not name or "/" in name or "\\" in name:
        return
    try:
        (folder() / name).unlink(missing_ok=True)
    except OSError:
        pass


def path(name: str) -> Path | None:
    if not name or "/" in name or "\\" in name or not name.endswith(".jpg"):
        return None
    p = folder() / name
    return p if p.is_file() else None


def url(user_id: int, name: str | None) -> str | None:
    return url_for("profile.avatar_img", user_id=user_id, name=name[:-4]) if name else None


def initials(full_name: str) -> str:
    words = [w for w in (full_name or "").replace("(", " ").replace(")", " ").split() if w[:1].isalpha() and w.lower() not in ("dr.", "dra.", "dr", "dra")]
    if not words:
        return "?"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper()


COLORS = ["#0f766e", "#1d4ed8", "#9333ea", "#be123c", "#b45309", "#15803d", "#0e7490", "#4338ca"]


def color(user_id: int) -> str:
    return COLORS[(user_id or 0) % len(COLORS)]
