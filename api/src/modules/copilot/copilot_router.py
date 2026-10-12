from fastapi import APIRouter

from src.modules.copilot import copilot_controller

router = APIRouter(prefix="/copilot/runs", tags=["copilot"])
router.add_api_route("", copilot_controller.create_run, methods=["POST"], status_code=201)
router.add_api_route("", copilot_controller.list_runs, methods=["GET"])
router.add_api_route("/{run_id}", copilot_controller.get_run, methods=["GET"])
router.add_api_route("/{run_id}/steps", copilot_controller.list_run_steps, methods=["GET"])
