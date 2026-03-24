from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from ..config import settings


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only guard /api/ routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Allow docs in debug mode
        if settings.debug and path in ("/api/docs", "/api/openapi.json", "/api/redoc"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if api_key != settings.api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
            )

        return await call_next(request)
