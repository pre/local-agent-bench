"""Exceptions of stockd."""


class StockdError(Exception):
    """Base class of all errors of stockd."""


class ConfigError(StockdError):
    """The configuration file or an option has a bad value."""


class CommandError(StockdError):
    """A command is not valid in the current state. The service rejects it."""


class StoreError(StockdError):
    """The event log is damaged or not continuous."""


class RecoveryError(StockdError):
    """The service cannot build its state from the data directory."""
