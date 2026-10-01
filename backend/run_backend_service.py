import logging
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

BACKEND_ROOT = Path(r"C:\warehouse\backend")
LOG_FILE = Path(r"C:\warehouse\logs\backend.log")

MAX_LOG_SIZE = 10 * 1024 * 1024
BACKUP_COUNT = 20

command = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
]

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("warehouse-backend")
logger.setLevel(logging.INFO)
logger.propagate = False

handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=MAX_LOG_SIZE,
    backupCount=BACKUP_COUNT,
    encoding="utf-8",
)

handler.setFormatter(
    logging.Formatter("%(asctime)s | %(message)s")
)

logger.addHandler(handler)

while True:
    logger.info("Supervisor starting backend")

    process = subprocess.Popen(
        command,
        cwd=str(BACKEND_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    if process.stdout is not None:
        for line in process.stdout:
            line = line.rstrip()

            if line:
                logger.info(line)

    exit_code = process.wait()

    logger.warning(
        "Backend exited with code %s; restarting in 5 seconds",
        exit_code,
    )

    time.sleep(5)
