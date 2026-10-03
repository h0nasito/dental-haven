"""Laboratory work stages, shared by branch lab cases (lab_cases) and outside-clinic works (lab_works)."""
from __future__ import annotations

# key: (label, what it means). Order is the order shown in the status menu.
STAGES: dict[str, tuple[str, str]] = {
    "sent": ("Sent to lab", "The branch sent the case; the lab hasn't accepted it yet."),
    "accepted": ("Accepted", "The case, prescription or materials were received, inspected and logged by the lab."),
    "setting": ("Setting", "Initial arrangement or alignment, such as setting teeth in wax or letting materials cure and set."),
    "designing": ("Designing", "Digital CAD modeling, drawing or structural layout of the piece."),
    "fabricating": ("Fabricating / production", "Core manufacturing: 3D printing, milling, casting or building the piece."),
    "trimming": ("Trimming", "Removing excess material, flash or rough edges."),
    "polishing": ("Polishing", "Smoothing, removing scratches and buffing to the final finish."),
    "quality_control": ("Quality control", "Final inspection against the prescription and quality standards."),
    "try_in": ("Out for trial fitting", "Sent to the clinic for a try-in; comes back to the lab with the dentist's notes."),
    "on_hold": ("On hold", "Waiting for the clinic: missing information, impression, shade, approval or payment."),
    "ready": ("Ready / packed", "Passed inspection, packed and waiting for pick-up or dispatch."),
    "delivered": ("Delivered", "Handed over to the clinic or client."),
    "remake": ("Remake needed", "Has to be made again (e.g. poor fit or wrong shade)."),
    "cancelled": ("Cancelled", "Stopped; no further work."),
}
STATUSES = {k: v[0] for k, v in STAGES.items()}
HELP = {k: v[1] for k, v in STAGES.items()}
# Outside-clinic works start when the lab receives them, so they don't use "sent".
WORK_STATUSES = {k: v for k, v in STATUSES.items() if k != "sent"}

PRODUCTION = ("accepted", "setting", "designing", "fabricating", "trimming", "polishing", "quality_control")
OPEN = ("sent", *PRODUCTION, "try_in", "on_hold", "ready", "remake")
# Still the lab's job to finish by the due date (ready, try-in and delivered pieces are not "late").
LATE = ("sent", *PRODUCTION, "on_hold", "remake")
CLOSED = ("delivered", "cancelled")

# Old status keys (before October 2026) → new ones.
OLD = {"received": "accepted", "in_progress": "fabricating"}


def sql_list(keys) -> str:
    """('a','b') for SQL IN (...); keys are fixed constants, never user input."""
    return "(" + ",".join(f"'{k}'" for k in keys) + ")"


def badge(status: str) -> str:
    return {"ready": "badge-green", "delivered": "badge-teal", "remake": "badge-red", "cancelled": "",
            "on_hold": "badge-amber", "try_in": "badge-amber", "sent": "badge-blue"}.get(status, "badge-blue")


def label(status: str) -> str:
    status = OLD.get(status, status)
    return STATUSES.get(status, status)
