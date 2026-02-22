from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class NoCacheMiddleware(BaseHTTPMiddleware):
    """
    Prevents browser caching of API responses and SPA HTML pages.
    Sets Cache-Control headers on all /api/ routes and SPA catch-all
    responses (index.html) to ensure clients always receive fresh data.
    Hashed static assets under /assets/ are left untouched.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        if path.startswith("/api/") or not path.startswith("/assets"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response
