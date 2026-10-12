from fastapi import APIRouter

from src.modules.incidents import incident_controller

router = APIRouter(prefix="/incidents", tags=["incidents"])
router.add_api_route("", incident_controller.list_incidents, methods=["GET"])
