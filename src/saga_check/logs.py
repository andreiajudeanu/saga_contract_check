import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, name: str) -> None:
    """Log complet in <name>, iar erorile si separat in erori.log (fisierul de urmarit de admin)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    main = RotatingFileHandler(log_dir / name, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    errors = RotatingFileHandler(log_dir / "erori.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    errors.setLevel(logging.ERROR)
    console = logging.StreamHandler()
    for h in (main, errors, console):
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[main, errors, console])
    logging.getLogger("httpx").setLevel(logging.WARNING)
