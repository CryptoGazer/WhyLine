from fastapi import FastAPI

from app.api.routes_analyze import router as analyze_router
from app.api.routes_health import router as health_router
from app.api.routes_workspace import router as workspace_router

app = FastAPI(title="WhyLine Backend", version="0.1.0")

app.include_router(health_router)
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")
