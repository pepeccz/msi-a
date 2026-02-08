"""
Phase 5: Validation Metrics API

Exposes validation metrics for monitoring dashboards.

Endpoints:
- GET /api/validation-metrics - Get current metrics
- POST /api/validation-metrics/reset - Reset metrics (admin only)
"""

from fastapi import APIRouter, Depends
from database.models import AdminUser
from api.routes.admin import require_role

router = APIRouter(prefix="/api/validation-metrics", tags=["validation-metrics"])


@router.get("")
async def get_validation_metrics(
    current_user: AdminUser = Depends(require_role("admin")),
):
    """
    Get current validation metrics.
    
    Returns aggregated statistics for:
    - Validation attempts and failures
    - Retry success rate
    - Escalation rate
    - Failures by tool and layer
    
    Requires admin role.
    """
    from agent.utils.validation_metrics import get_validation_metrics
    
    metrics = get_validation_metrics()
    return metrics.export_dict()


@router.post("/reset")
async def reset_validation_metrics(
    current_user: AdminUser = Depends(require_role("admin")),
):
    """
    Reset validation metrics.
    
    Useful for starting a new measurement window.
    Requires admin role.
    """
    from agent.utils.validation_metrics import get_validation_metrics
    
    metrics = get_validation_metrics()
    metrics.reset()
    
    return {
        "message": "Validation metrics reset successfully",
        "reset_at": metrics.window_start.isoformat(),
    }
