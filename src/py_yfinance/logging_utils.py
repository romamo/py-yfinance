import logging
import sys


def setup_logging(v: bool, vv: bool, silence_loggers: list[str] | None = None):
    """
    Set up logging based on v (INFO) and vv (DEBUG) flags.

    :param v: Verbose output (INFO level).
    :param vv: Debug output (DEBUG level).
    :param silence_loggers: Optional list of logger names to set to WARNING level
                            when vv is False. If None, uses a default noisy list.
                            Pass an empty list [] to disable silencing entirely.
    """
    if vv:
        level = logging.DEBUG
        verbosity = 2
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    elif v:
        level = logging.INFO
        verbosity = 1
        fmt = "[%(levelname)s] %(name)s: %(message)s"
    else:
        level = logging.WARNING
        verbosity = 0
        fmt = "%(message)s"

    # 1. Configure root logger
    logging.basicConfig(
        level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stderr, force=True
    )

    # 2. Apply level to all existing loggers to ensure consistency
    for logger_name in logging.root.manager.loggerDict:
        logging.getLogger(logger_name).setLevel(level)

    # 3. Specifically silence noisy third-party libraries if not in deep debug
    if verbosity < 2:
        if silence_loggers is None:
            silence_loggers = [
                "urllib3",
                "requests",
                "yfinance",
                "peewee",
                "urllib3.connectionpool",
                "charset_normalizer",
            ]

        for name in silence_loggers:
            logging.getLogger(name).setLevel(logging.WARNING)
