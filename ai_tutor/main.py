from fastapi import FastAPI

from app.ai_tutor.router import router
from app.services.licensing.api import router as license_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="CBT AI Tutor",
    version="1.0.0",
)

app.include_router(router)
app.include_router(license_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():

    return {
        "success": True,
        "service": "Mock CBT AI Tutor API",
    }
