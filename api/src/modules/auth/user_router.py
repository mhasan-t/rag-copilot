from fastapi import APIRouter

from src.modules.auth import user_controller

router = APIRouter(prefix="/users", tags=["users"])
router.add_api_route("", user_controller.create_user, methods=["POST"], status_code=201)
router.add_api_route("", user_controller.list_users, methods=["GET"])
router.add_api_route("/{user_id}", user_controller.update_user, methods=["PATCH"])
