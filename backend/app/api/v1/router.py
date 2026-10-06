from fastapi import APIRouter

from app.api.v1 import admin, auth, concerns, health, insights

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(concerns.router)
api_router.include_router(insights.router)
