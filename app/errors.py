class AppError(Exception):
    pass

class WhatsAppError(AppError):
    pass

class RouterError(AppError):
    pass

class DuplicateMessage(AppError):
    pass