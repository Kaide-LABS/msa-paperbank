class AppError(Exception):
    pass

class WhatsAppError(AppError):
    pass

class RouterError(AppError):
    pass

class DuplicateMessage(AppError):
    pass

class PreprocessError(AppError):
    pass

class OcrError(AppError):
    pass

class EmbeddingError(AppError):
    pass