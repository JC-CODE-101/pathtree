class RepositoryError(Exception):
    """Base exception for repository-level errors."""


class RepositoryIntegrityError(RepositoryError):
    """Raised when repository operations violate database integrity constraints."""
