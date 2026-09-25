from fastapi import HTTPException


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, retry_after: int | None = None):
        self.code = code
        self.message = message
        headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
        super().__init__(status_code=status_code, detail=message, headers=headers)
