"""Help center: searchable how-to guides, showing only the guides that fit the user's role."""
from __future__ import annotations

from flask import Blueprint, abort, g, render_template, request

from .. import help as guides
from ..auth import login_required

bp = Blueprint("help", __name__, url_prefix="/staff/help")


@bp.route("/")
@login_required
def index():
    items = guides.visible(g.user)
    q = (request.args.get("q") or "").strip()[:100]
    found = guides.search(items, q) if q else None
    by_cat = [(c, [a for a in items if a["cat"] == c]) for c in guides.CATEGORIES]
    return render_template("staff/help/index.html", q=q, found=found, by_cat=[x for x in by_cat if x[1]],
                           plain=guides.plain)


@bp.route("/<slug>")
@login_required
def article(slug):
    items = guides.visible(g.user)
    a = next((x for x in items if x["slug"] == slug), None)
    if not a:
        abort(404)
    related = [x for x in items if x["cat"] == a["cat"] and x["slug"] != slug][:5]
    return render_template("staff/help/article.html", a=a, related=related, bold=guides.bold)
