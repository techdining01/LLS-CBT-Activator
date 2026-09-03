from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database.database import init_database
from ai_tutor.router import router
from licensing.api import router as license_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables and seed records exist on startup
    init_database()
    yield


app = FastAPI(
    title="LLS-CBT AI Tutor & Licensing API",
    version="1.0.0",
    lifespan=lifespan,
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
        "service": "LLS-CBT AI Tutor & Licensing API",
    }
