# utils/logging_ex.py
import logging, os, sys
from logging.handlers import RotatingFileHandler

def get_logger(name="bibit", level=None, log_dir="logs"):
    os.makedirs(log_dir, exist_ok=True)
    level = level or os.getenv("LOG_LEVEL", "INFO").upper()

    fmt = ("%(asctime)s [%(levelname)s] %(name)s: "
           "%(message)s  —  (%(module)s.py:%(lineno)d %(funcName)s)")
    datefmt = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Console
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter(fmt, datefmt))
        ch.setLevel(level)
        logger.addHandler(ch)

        # Archivo rotativo
        fh = RotatingFileHandler(
            os.path.join(log_dir, "bibit.log"),
            maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(fmt, datefmt))
        fh.setLevel(level)
        logger.addHandler(fh)

    return logger

class Section:
    """Context manager para agrupar pasos de una operación en el log."""
    def __init__(self, logger, title, **kv):
        self.logger = logger
        self.title = title
        self.kv = kv
    def __enter__(self):
        self.logger.info("▶ %s %s", self.title, self.kv if self.kv else "")
    def __exit__(self, exc_type, exc, tb):
        if exc:
            self.logger.exception("✖ %s FAILED: %s", self.title, exc)
        else:
            self.logger.info("✔ %s OK", self.title)
