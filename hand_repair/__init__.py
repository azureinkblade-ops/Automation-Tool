"""Hand / regional repair service for the Automation Tool.

Public surface for Stage-2 localized hand repair. Built on top of the
generic object_refinement engine. This package must never import app.
"""

from .service import (
    HandRepairRequest,
    HandRepairResult,
    repair_hands,
)

__all__ = [
    "HandRepairRequest",
    "HandRepairResult",
    "repair_hands",
]
