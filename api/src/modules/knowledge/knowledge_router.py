from fastapi import APIRouter

from src.modules.knowledge import knowledge_controller

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
router.add_api_route("/documents", knowledge_controller.ingest_document, methods=["POST"])
router.add_api_route("/search", knowledge_controller.search, methods=["GET"])
