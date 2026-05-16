from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class GemaException(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def gema_exception_handler(request: Request, exc: GemaException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )
