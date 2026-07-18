"""Growth analytics wrapper (Task 7 of the extraction).

Thin wrapper around the growth_scheduler module. Re-exports the public growth-scheduler
API so the rest of the app can import growth helpers from a single, stable module instead
of reaching into growth_scheduler directly.

Imports ONLY growth_scheduler (a standalone module) + app_config. MUST NOT import app.

See .hermes/plans/2026-07-16_143000-monolith-extraction.md (Task 7).
"""

from __future__ import annotations

import growth_scheduler as _sched

# Re-export the public growth-scheduler surface. (The plan referenced
# growth_scheduler.VALID_NOVELS, but the module does not define that name; we re-export
# the symbols it actually exposes so callers get a stable import point.)
NOVEL_ORDER = _sched.NOVEL_ORDER
GOALS = _sched.GOALS
GOAL_CTAS = _sched.GOAL_CTAS
HOOK_TEMPLATES = _sched.HOOK_TEMPLATES
WEEKDAYS = _sched.WEEKDAYS
DEFAULT_WEIGHTS = _sched.DEFAULT_WEIGHTS

build_weekly_growth_plan = _sched.build_weekly_growth_plan
weighted_novel_slots = _sched.weighted_novel_slots
normalize_weights = _sched.normalize_weights
monday_for = _sched.monday_for
cta_for_goal = _sched.cta_for_goal
engagement_score = _sched.engagement_score


def growth_metrics_snapshot() -> dict:
    """Lightweight snapshot used by the analytics dashboard (placeholder for Phase 2)."""
    return {
        "novels": list(NOVEL_ORDER),
        "goals": list(GOALS),
        "scheduler": "growth_scheduler",
    }
