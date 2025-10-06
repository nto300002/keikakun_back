from fastapi import HTTPException, status

class AppError(Exception):
    """Base application error class."""
    pass

class DatabaseError(AppError):
    """For database related errors."""
    pass

class OfficeNotFoundError(AppError):
    """When an office is not found."""
    pass

# Common HTTP-related exceptions used across the API endpoints
class BadRequestException(HTTPException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

class InvalidStepOrderError(BadRequestException):
    def __init__(self, detail: str = "成果物をアップロードする順序が正しくありません。"):
        super().__init__(detail=detail)


class NotFoundException(HTTPException):
    def __init__(self, detail: str = "Not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

class ForbiddenException(HTTPException):
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

class InternalServerException(HTTPException):
    def __init__(self, detail: str = "Internal server error"):
        super().__init__(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
