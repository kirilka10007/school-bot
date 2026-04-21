import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(app_name: str, log_level: str = "INFO", log_dir: str = "logs") -> Path:
    level = getattr(logging, log_level.upper(), logging.INFO)
    logs_path = Path(log_dir).resolve()
    logs_path.mkdir(parents=True, exist_ok=True)

    log_file = logs_path / f"{app_name}.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("aiogram").setLevel(level)
    logging.getLogger("aiohttp").setLevel(max(level, logging.WARNING))

    return log_file


def get_log_settings(default_level: str = "INFO", default_dir: str = "logs") -> tuple[str, str]:
    return (
        os.getenv("SCHOOL_LOG_LEVEL", default_level),
        os.getenv("SCHOOL_LOG_DIR", default_dir),
    )
