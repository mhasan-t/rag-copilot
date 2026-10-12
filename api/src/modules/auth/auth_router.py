from fastapi import APIRouter

from src.modules.auth import auth_controller

router = APIRouter(prefix="/auth", tags=["auth"])
router.add_api_route("/token", auth_controller.login, methods=["POST"])
router.add_api_route("/me", auth_controller.get_me, methods=["GET"])
