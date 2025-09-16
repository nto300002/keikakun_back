class AppError(Exception):
    """Base application error class."""
    pass

class DatabaseError(AppError):
    """For database related errors."""
    pass

class OfficeNotFoundError(AppError):
    """When an office is not found."""
    pass
