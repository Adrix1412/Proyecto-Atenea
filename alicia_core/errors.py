"""Public errors carry safe messages, never provider responses or secrets."""


class AliciaError(Exception):
    """Recoverable application failure."""


class ConfigurationError(AliciaError):
    """Invalid or missing trusted configuration."""


class ProviderError(AliciaError):
    """Unavailable provider or invalid remote response."""


class StorageError(AliciaError):
    """Persistence operation failed."""


class ConversationConflict(StorageError):
    """Another turn modified the conversation; caller must not retry blindly."""


class ToolError(AliciaError):
    """Denied or failed tool invocation."""
