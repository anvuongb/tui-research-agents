import logging

from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> logging.Logger:
    FORMAT = "%(message)s"
    logging.basicConfig(
        level=level.upper(),
        format=FORMAT,
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )

    logger = logging.getLogger("tui_agents")
    logger.setLevel(level.upper())
    return logger


def get_logger(name: str = "tui_agents") -> logging.Logger:
    return logging.getLogger(name)
