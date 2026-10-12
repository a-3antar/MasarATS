

class SmartATSError(Exception):
    pass


class ValidationError(SmartATSError):
    pass


class DatabaseError(SmartATSError):
    pass


class ConfigurationError(SmartATSError):
    pass



class AuthenticationError(SmartATSError):
    pass


class UserAlreadyExistsError(SmartATSError):
    pass


class InactiveUserError(SmartATSError):
    pass



class UnsupportedFileTypeError(SmartATSError):
    pass


class DocumentParsingError(SmartATSError):
    pass


class AIServiceError(SmartATSError):
    pass


class DuplicateCandidateError(SmartATSError):
    pass

class PermissionDeniedError(SmartATSError):
    pass
