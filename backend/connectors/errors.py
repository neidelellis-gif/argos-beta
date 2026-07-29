"""Typed errors shared by portfolio connectors."""


class ConnectorError(ValueError):
    """Base error raised by portfolio connector infrastructure."""


class UnsupportedExtensionError(ConnectorError):
    """The connector does not support the supplied file extension."""


class ConnectorFileNotFoundError(ConnectorError):
    """The requested source file does not exist."""


class UnrecognizedFileError(ConnectorError):
    """The file does not contain the connector's expected structure."""


class EmptyPortfolioError(ConnectorError):
    """A recognized file contains no portfolio positions."""


class MissingDependencyError(ConnectorError):
    """An optional dependency required to read a format is unavailable."""


class DuplicateConnectorIdError(ConnectorError):
    """A registry already contains the connector identifier."""
