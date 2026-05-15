"""FastAPI application entry point.

Creates and configures the FastAPI app with CORS middleware, routers,
and global exception handlers.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.ads import router as facebook_router
from app.api.catalog import router as catalog_router
from app.api.health import router as health_router
from app.api.tasks import router as task_router
from app.core.config import settings
from app.core.response import failure
from app.dao.database import init_database


def create_app() -> FastAPI:
    """Initialize database, configure middleware and routers, return the app."""

    init_database()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(task_router)
    app.include_router(facebook_router)
    app.include_router(catalog_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """Convert HTTPException into the unified ApiResponse JSON format."""
        response = failure(str(exc.detail), exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=response.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Convert request validation errors into the unified ApiResponse JSON format."""
        response = failure("参数校验失败", 422, exc.errors())
        return JSONResponse(status_code=422, content=response.model_dump())

    return app


# Module-level app instance used by uvicorn
app = create_app()
