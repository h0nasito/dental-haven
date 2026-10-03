"""Google reviews and ratings for each branch, through the Google Places API (New).

Only runs when GOOGLE_PLACES_API_KEY is set on the server and a branch has its Google Place ID. Each refresh makes one
Place Details request per branch (rating, number of reviews, the reviews Google returns, the Google Maps link). By
default a branch is refreshed every 12 hours, so 4 branches use about 240 requests a month.

Reviews are shown as Google gives them (author name, photo and link, star rating, text, "2 weeks ago"), with
"Reviews from Google" attribution. They're kept only until the next refresh, and hidden when older than 2 days.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from .util import now, now_str, today

DETAILS_URL = "https://places.googleapis.com/v1/places/{id}"
FIELDS = "id,rating,userRatingCount,googleMapsUri,reviews"
REFRESH_HOURS = 12
STALE_HOURS = 48
PLACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,300}$")


def api_key() -> str:
    return os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()


def enabled() -> bool:
    return bool(api_key())


def valid_place_id(pid: str) -> bool:
    return bool(PLACE_ID_RE.match(pid or ""))


def fetch(place_id: str, opener=None) -> dict:
    """One Place Details request. Raises RuntimeError with a short, safe message."""
    if not valid_place_id(place_id):
        raise RuntimeError("The Place ID doesn't look right.")
    url = DETAILS_URL.format(id=urllib.parse.quote(place_id, safe="")) + "?languageCode=en"
    req = urllib.request.Request(url, headers={"X-Goog-Api-Key": api_key(), "X-Goog-FieldMask": FIELDS, "accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode() or "{}").get("error", {}).get("message", "")
        except ValueError:
            pass
        raise RuntimeError(f"Google answered {exc.code}{': ' + detail[:160] if detail else ''}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Couldn't reach Google ({getattr(exc, 'reason', exc)})") from None


def _review_rows(data: dict) -> list[dict]:
    rows = []
    for i, r in enumerate(data.get("reviews") or []):
        a = r.get("authorAttribution") or {}
        text = (r.get("originalText") or r.get("text") or {}).get("text", "")
        photo = a.get("photoUri", "")
        rows.append({"author_name": (a.get("displayName") or "Google user")[:120], "author_uri": _https(a.get("uri")),
                     "author_photo": photo if photo.startswith("https://") and "googleusercontent.com" in photo else "",
                     "rating": int(r["rating"]) if r.get("rating") else None, "text": text[:3000],
                     "relative_time": (r.get("relativePublishTimeDescription") or "")[:60],
                     "publish_time": (r.get("publishTime") or "")[:40], "review_uri": _https(r.get("googleMapsUri")), "sort_order": i})
    return rows


def _https(u) -> str:
    return u if isinstance(u, str) and u.startswith("https://") else ""


def sync_branch(conn, b, opener=None) -> int:
    """Refresh one branch. Returns the number of reviews stored. Errors are saved on the branch and re-raised."""
    try:
        data = fetch(b["google_place_id"], opener)
    except RuntimeError as exc:
        conn.execute("UPDATE branches SET google_sync_error = ? WHERE id = ?", (str(exc)[:300], b["id"]))
        raise
    rows = _review_rows(data)
    with conn.transaction():
        upd = {"google_synced_at": now_str(), "google_sync_error": ""}
        if data.get("rating") is not None and data.get("userRatingCount"):
            upd.update(google_rating=round(float(data["rating"]), 1), google_review_count=int(data["userRatingCount"]),
                       google_rating_as_of=today().isoformat())
        if not b["google_reviews_url"] and _https(data.get("googleMapsUri")):
            upd["google_reviews_url"] = data["googleMapsUri"]
        conn.update("branches", b["id"], upd)
        conn.execute("DELETE FROM google_reviews WHERE branch_id = ?", (b["id"],))
        for r in rows:
            conn.insert("google_reviews", {**r, "branch_id": b["id"], "fetched_at": now_str()})
    return len(rows)


def run(conn, force=False, opener=None) -> int:
    """Refresh branches that are due. Safe to call often. Returns how many branches were refreshed."""
    if not enabled():
        return 0
    cutoff = (now() - timedelta(hours=REFRESH_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    done = 0
    for b in conn.all("SELECT * FROM branches WHERE active = 1 AND google_place_id != ''"):
        if not force and b["google_synced_at"] and b["google_synced_at"] > cutoff:
            continue  # refreshed (or tried) recently
        try:
            sync_branch(conn, b, opener)
            done += 1
        except RuntimeError:
            conn.execute("UPDATE branches SET google_synced_at = ? WHERE id = ?", (now_str(), b["id"]))
    return done


def reviews_for_site(conn, limit=None):
    """Fetched reviews that are still fresh, newest first, with the branch name."""
    cutoff = (now() - timedelta(hours=STALE_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    q = ("SELECT r.*, b.name AS branch FROM google_reviews r JOIN branches b ON b.id = r.branch_id "
         "WHERE b.active = 1 AND r.fetched_at >= ? AND r.text != '' ORDER BY r.publish_time DESC, r.id")
    return conn.all(q + (f" LIMIT {int(limit)}" if limit else ""), (cutoff,))
