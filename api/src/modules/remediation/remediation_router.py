from fastapi import APIRouter

from src.modules.remediation import remediation_controller

router = APIRouter(prefix="/remediations", tags=["remediations"])
router.add_api_route("", remediation_controller.list_remediations, methods=["GET"])
router.add_api_route("/{proposal_id}", remediation_controller.get_remediation, methods=["GET"])
# 202: the action and its verification continue after the response; poll the remediation for the outcome.
router.add_api_route("/{proposal_id}/approve", remediation_controller.approve, methods=["POST"], status_code=202)
router.add_api_route("/{proposal_id}/reject", remediation_controller.reject, methods=["POST"])
