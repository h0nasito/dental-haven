"""Clinic & lab overview for owners/admins: today / this week / this month / this year, each compared with the same stretch before,
money owed, the lab's workload, and two small charts (collections and new vs returning patients).
Everything is scoped to the branches the user can see (or the one picked in the branch switcher)."""
from __future__ import annotations

from datetime import date, timedelta

from .billing import CREDIT_METHOD
from .lab_status import LATE, OPEN, sql_list


def _in(ids):
    return ",".join("?" * len(ids)) or "NULL"


def _change(now_v, before_v):
    """Percent change, or None when there is nothing to compare with."""
    if not before_v:
        return None
    return round(100 * (now_v - before_v) / before_v)


def _collected(conn, ids, start: str, end: str) -> int:
    """Money received between two dates (inclusive): payments (not account credit) + deposits - refunds."""
    if not ids:
        return 0
    m = _in(ids)
    p = conn.one(f"SELECT COALESCE(SUM(CASE WHEN kind='payment' THEN amount_cents ELSE -amount_cents END), 0) AS n FROM payments "
                 f"WHERE status='valid' AND method != ? AND branch_id IN ({m}) AND substr(received_at, 1, 10) BETWEEN ? AND ?",
                 [CREDIT_METHOD, *ids, start, end])["n"]
    d = conn.one(f"SELECT COALESCE(SUM(CASE WHEN kind='deposit' THEN amount_cents WHEN kind='refund' THEN -amount_cents ELSE 0 END), 0) AS n "
                 f"FROM patient_credits WHERE status='valid' AND branch_id IN ({m}) AND entry_date BETWEEN ? AND ?", [*ids, start, end])["n"]
    return int(p or 0) + int(d or 0)


def _appt_counts(conn, ids, start: str, end: str) -> dict:
    m = _in(ids)
    rows = conn.all(f"SELECT status, COUNT(*) AS n FROM appointments WHERE branch_id IN ({m}) AND substr(start_at, 1, 10) BETWEEN ? AND ? "
                    "GROUP BY status", [*ids, start, end]) if ids else []
    c = {r["status"]: r["n"] for r in rows}
    return {"all": sum(c.values()) - c.get("cancelled", 0), "waiting": c.get("checked_in", 0), "completed": c.get("completed", 0),
            "cancelled": c.get("cancelled", 0) + c.get("no_show", 0), "upcoming": c.get("requested", 0) + c.get("confirmed", 0)}


PERIODS = {"day": "Today", "week": "This week", "month": "This month", "year": "This year"}


def _back(d: date, months: int) -> date:
    """The same day-of-month some months earlier (clamped to the month's last day)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, min(d.day, day))
        except ValueError:
            continue
    return date(y, m, 28)


def ranges(period: str, t: date) -> dict:
    """The period so far and the same stretch of the period before, for comparisons."""
    if period == "day":
        s, ps = t, t - timedelta(days=7)
        return {"start": s, "end": t, "pstart": ps, "pend": ps, "vs": f"last {t.strftime('%a')}"}
    if period == "week":
        s = t - timedelta(days=t.weekday())
        return {"start": s, "end": t, "pstart": s - timedelta(days=7), "pend": t - timedelta(days=7), "vs": "same days last week"}
    if period == "month":
        s = t.replace(day=1)
        return {"start": s, "end": t, "pstart": _back(s, 1), "pend": _back(t, 1), "vs": "same days last month"}
    s = t.replace(month=1, day=1)
    return {"start": s, "end": t, "pstart": s.replace(year=s.year - 1), "pend": _back(t, 12), "vs": "same time last year"}


def buckets(period: str, t: date) -> list[dict]:
    """Chart points: days (today -> the last 14 days; week; month) or months (year), each with the matching earlier bucket."""
    out = []
    if period == "year":
        for mth in range(1, 13):
            s = date(t.year, mth, 1)
            e = _back(date(t.year + (mth == 12), mth % 12 + 1, 1), 0) - timedelta(days=1)
            out.append({"label": s.strftime("%b"), "start": s, "end": min(e, t), "future": s > t,
                        "pstart": s.replace(year=s.year - 1), "pend": e.replace(year=e.year - 1) if not (e.month == 2 and e.day == 29) else e.replace(year=e.year - 1, day=28)})
        return out
    if period == "day":
        days = [t - timedelta(days=i) for i in range(13, -1, -1)]
        shift = lambda d: d - timedelta(days=7)  # noqa: E731
    elif period == "week":
        s = t - timedelta(days=t.weekday())
        days = [s + timedelta(days=i) for i in range(7)]
        shift = lambda d: d - timedelta(days=7)  # noqa: E731
    else:
        s = t.replace(day=1)
        nxt = _back(date(t.year + (t.month == 12), t.month % 12 + 1, 1), 0)
        days = [s + timedelta(days=i) for i in range((nxt - s).days)]
        shift = lambda d: _back(d, 1)  # noqa: E731
    for d in days:
        lab = d.strftime("%a") if period == "week" else (str(d.day) if period == "month" else d.strftime("%-d %b"))
        out.append({"label": lab, "start": d, "end": d, "future": d > t, "pstart": shift(d), "pend": shift(d)})
    return out


def build(conn, ids: list[int], t: date, period: str = "day") -> dict:
    period = period if period in PERIODS else "day"
    r = ranges(period, t)
    s0, s1, p0, p1 = r["start"].isoformat(), r["end"].isoformat(), r["pstart"].isoformat(), r["pend"].isoformat()
    day = t.isoformat()
    m = _in(ids)
    out: dict = {"today": t, "period": period, "range": r}
    a, ap = _appt_counts(conn, ids, s0, s1), _appt_counts(conn, ids, p0, p1)
    out["appts"] = {k: (a[k], _change(a[k], ap[k])) for k in a}
    out["waiting_now"] = _appt_counts(conn, ids, day, day)["waiting"]
    out["bookings"] = conn.scalar(f"SELECT COUNT(*) FROM booking_requests WHERE status = 'pending' AND branch_id IN ({m})", ids) if ids else 0
    c_now, c_prev = _collected(conn, ids, s0, s1), _collected(conn, ids, p0, p1)
    out["collected"] = (c_now, _change(c_now, c_prev))
    month0 = t.replace(day=1).isoformat()
    out["collected_month"] = _collected(conn, ids, month0, day)
    # money owed on issued bills
    owed = conn.all(f"SELECT i.total_cents - COALESCE((SELECT SUM(CASE WHEN p.kind='payment' THEN p.amount_cents ELSE -p.amount_cents END) "
                    f"FROM payments p WHERE p.invoice_id = i.id AND p.status = 'valid'), 0) AS due FROM invoices i "
                    f"WHERE i.status = 'issued' AND i.branch_id IN ({m})", ids) if ids else []
    owed = [r["due"] for r in owed if r["due"] > 0]
    out["unpaid"] = (len(owed), sum(owed))
    out["drafts"] = conn.scalar(f"SELECT COUNT(*) FROM invoices WHERE status = 'draft' AND branch_id IN ({m})", ids) if ids else 0
    # patients registered in the period
    np_now = conn.scalar(f"SELECT COUNT(*) FROM patients WHERE substr(created_at, 1, 10) BETWEEN ? AND ? AND preferred_branch_id IN ({m})",
                         [s0, s1, *ids]) if ids else 0
    np_prev = conn.scalar(f"SELECT COUNT(*) FROM patients WHERE substr(created_at, 1, 10) BETWEEN ? AND ? AND preferred_branch_id IN ({m})",
                          [p0, p1, *ids]) if ids else 0
    out["new_patients"] = (np_now, _change(np_now, np_prev))
    out["recalls_due"] = conn.scalar(f"SELECT COUNT(*) FROM follow_ups WHERE status = 'open' AND kind = 'recall' AND substr(due_at, 1, 10) <= ? "
                                     f"AND branch_id IN ({m})", [day, *ids]) if ids else 0
    # lab (all labs: branch cases from these branches + outside works)
    lab: dict = {}
    lab["open_cases"] = conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE status IN {sql_list(OPEN)} AND branch_id IN ({m})", ids) if ids else 0
    lab["open_works"] = conn.scalar(f"SELECT COUNT(*) FROM lab_works WHERE status IN {sql_list(OPEN)}") or 0
    lab["overdue"] = (conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE status IN {sql_list(LATE)} AND due_on IS NOT NULL AND due_on < ? "
                                  f"AND branch_id IN ({m})", [day, *ids]) if ids else 0) \
        + (conn.scalar(f"SELECT COUNT(*) FROM lab_works WHERE status IN {sql_list(LATE)} AND due_on IS NOT NULL AND due_on < ?", [day]) or 0)
    lab["due_today"] = (conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE status IN {sql_list(LATE)} AND due_on = ? AND branch_id IN ({m})", [day, *ids]) if ids else 0) \
        + (conn.scalar(f"SELECT COUNT(*) FROM lab_works WHERE status IN {sql_list(LATE)} AND due_on = ?", [day]) or 0)
    lab["ready"] = (conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE status = 'ready' AND branch_id IN ({m})", ids) if ids else 0) \
        + (conn.scalar("SELECT COUNT(*) FROM lab_works WHERE status = 'ready'") or 0)
    lab["to_bill"] = conn.scalar("SELECT COUNT(*) FROM lab_works WHERE status = 'delivered' AND invoice_id IS NULL") or 0
    lab["received"] = (conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE sent_on BETWEEN ? AND ? AND branch_id IN ({m})", [s0, s1, *ids]) if ids else 0) \
        + (conn.scalar("SELECT COUNT(*) FROM lab_works WHERE received_on BETWEEN ? AND ?", [s0, s1]) or 0)
    lab["delivered"] = (conn.scalar(f"SELECT COUNT(*) FROM lab_cases WHERE status = 'delivered' AND completed_on BETWEEN ? AND ? AND branch_id IN ({m})",
                                    [s0, s1, *ids]) if ids else 0) \
        + (conn.scalar("SELECT COUNT(*) FROM lab_works WHERE status = 'delivered' AND delivered_on BETWEEN ? AND ?", [s0, s1]) or 0)
    lab["collected"] = conn.scalar("SELECT COALESCE(SUM(amount_cents), 0) FROM lab_payments WHERE status = 'ok' AND received_on BETWEEN ? AND ?",
                                   [s0, s1]) or 0
    lab["unpaid"] = conn.scalar("SELECT COALESCE(SUM(total_cents - paid_cents), 0) FROM lab_invoices WHERE status = 'issued' AND total_cents > paid_cents") or 0
    lab["soon"] = [dict(r, kind="case") for r in conn.all(
        f"SELECT c.id, c.case_type, c.units, c.status, c.due_on, b.name AS place FROM lab_cases c JOIN branches b ON b.id = c.branch_id "
        f"WHERE c.status IN {sql_list(LATE)} AND c.due_on IS NOT NULL AND c.due_on <= ? AND c.branch_id IN ({m}) ORDER BY c.due_on LIMIT 8",
        [(t + timedelta(days=2)).isoformat(), *ids])] if ids else []
    lab["soon"] += [dict(r, kind="work") for r in conn.all(
        f"SELECT w.id, w.number, w.case_type, w.units, w.status, w.due_on, w.clinic_name AS place FROM lab_works w "
        f"WHERE w.status IN {sql_list(LATE)} AND w.due_on IS NOT NULL AND w.due_on <= ? ORDER BY w.due_on LIMIT 8",
        [(t + timedelta(days=2)).isoformat()])]
    lab["soon"].sort(key=lambda r: r["due_on"])
    lab["soon"] = lab["soon"][:8]
    out["lab"] = lab
    # charts: collections per bucket (with the earlier period dashed) and new vs returning patients
    bk = buckets(period, t)
    out["chart_labels"] = [x["label"] for x in bk]
    out["chart_coll"] = [None if x["future"] else _collected(conn, ids, x["start"].isoformat(), x["end"].isoformat()) for x in bk]
    out["chart_prev"] = [_collected(conn, ids, x["pstart"].isoformat(), x["pend"].isoformat()) for x in bk]
    lo, hi = bk[0]["start"].isoformat(), bk[-1]["end"].isoformat()
    visits = conn.all(f"SELECT substr(a.start_at, 1, 10) AS d, "
                      f"(SELECT MIN(substr(a2.start_at, 1, 10)) FROM appointments a2 WHERE a2.patient_id = a.patient_id AND a2.status = 'completed') AS first "
                      f"FROM appointments a WHERE a.status = 'completed' AND a.branch_id IN ({m}) AND substr(a.start_at, 1, 10) BETWEEN ? AND ?",
                      [*ids, lo, hi]) if ids else []
    newc, retc = [0] * len(bk), [0] * len(bk)
    for v in visits:
        for i, x in enumerate(bk):
            if x["start"].isoformat() <= v["d"] <= x["end"].isoformat():
                (newc if v["first"] == v["d"] else retc)[i] += 1
                break
    out["chart_new"], out["chart_ret"] = newc, retc
    # today's appointments
    out["today_appts"] = conn.all(
        "SELECT a.id, a.start_at, a.status, p.first_name, p.last_name, s.name AS service, u.name AS dentist, b.name AS branch "
        "FROM appointments a JOIN patients p ON p.id = a.patient_id JOIN services s ON s.id = a.service_id "
        f"LEFT JOIN users u ON u.id = a.dentist_id JOIN branches b ON b.id = a.branch_id WHERE a.branch_id IN ({m}) "
        "AND substr(a.start_at, 1, 10) = ? ORDER BY a.start_at LIMIT 60", [*ids, day]) if ids else []
    return out


def nice_top(v: float) -> float:
    """A round axis maximum (in cents) above v: 1, 2 or 5 x a power of ten pesos, at least P1,000."""
    v = max(v, 100000)
    mag = 10 ** (len(str(int(v))) - 1)
    for m in (1, 2, 5, 10):
        if v <= m * mag:
            return m * mag
    return 10 * mag


def money_short(cents: float) -> str:
    p = cents / 100
    if p >= 1_000_000:
        return f"₱{p / 1_000_000:g}M"
    if p >= 1000:
        return f"₱{p / 1000:g}k"
    return f"₱{p:,.0f}"


def line_chart(values: list, prev: list, labels: list[str], w: int = 560, h: int = 200) -> dict:
    """SVG geometry for a small line chart: the period (with a filled area) and the previous period (dashed)."""
    pad_l, pad_b, pad_t = 52, 26, 10
    vals = [v for v in values + prev if v is not None]
    top = nice_top(max(vals + [0]))
    n = max(1, len(labels) - 1)
    x = lambda i: pad_l + (w - pad_l - 8) * i / n  # noqa: E731
    y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - v / top)  # noqa: E731
    pts = [(x(i), y(v)) for i, v in enumerate(values) if v is not None]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"{pts[0][0]:.1f},{y(0):.1f} " + line + f" {pts[-1][0]:.1f},{y(0):.1f}") if pts else ""
    pline = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(prev))
    ticks = [{"y": y(top * k / 4), "label": money_short(top * k / 4)} for k in range(5)]
    every = 1 if len(labels) <= 14 else 5
    xl = [{"x": x(i), "label": lb} for i, lb in enumerate(labels) if i % every == 0 or i == len(labels) - 1]
    return {"w": w, "h": h, "line": line, "area": area, "prev": pline, "ticks": ticks, "xl": xl,
            "dots": [{"x": px, "y": py} for px, py in pts]}


def bar_chart(a: list[int], b: list[int], labels: list[str], w: int = 560, h: int = 180) -> dict:
    pad_l, pad_b, pad_t = 30, 26, 10
    top = max([x + y for x, y in zip(a, b)] + [4])
    top = -(-top // 4) * 4                                           # a multiple of 4, so the 5 grid lines are whole numbers
    n = max(1, len(labels))
    slot = (w - pad_l - 8) / n
    bw = max(4, min(28, slot * 0.6))
    y = lambda v: pad_t + (h - pad_t - pad_b) * (1 - v / top)  # noqa: E731
    bars = []
    for i, (na, nb) in enumerate(zip(a, b)):
        cx = pad_l + slot * i + slot / 2 - bw / 2
        bars.append({"x": cx, "w": bw, "new_y": y(na), "new_h": y(0) - y(na), "ret_y": y(na + nb), "ret_h": y(na) - y(na + nb), "new": na, "ret": nb})
    every = 1 if len(labels) <= 14 else 5
    xl = [{"x": pad_l + slot * i + slot / 2, "label": lb} for i, lb in enumerate(labels) if i % every == 0 or i == len(labels) - 1]
    ticks = [{"y": y(top * k / 4), "label": round(top * k / 4)} for k in range(5)]
    return {"w": w, "h": h, "bars": bars, "xl": xl, "ticks": ticks, "base": y(0)}
