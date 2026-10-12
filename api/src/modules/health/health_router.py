from fastapi import APIRouter

from src.modules.health import health_controller

router = APIRouter(tags=["health"])
router.add_api_route("/health", health_controller.get_health, methods=["GET"])
