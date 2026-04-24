#!/usr/bin/env python3
import sys
import os
import subprocess
import fcntl
import logging
import logging.handlers
import time

# --- CONFIGURAÇÕES FIXAS ---
CONFIG_PATH_RO = "/media/root-ro/etc/overlayroot.conf"
CONFIG_PATH_RW = "/etc/overlayroot.conf"
MOUNT_POINT_RO = "/media/root-ro"
LOCK_FILE = "/run/lock/cryomint-core.lock"
LOG_TAG = "CryoMint-Core"

def setup_logging(tag: str) -> logging.Logger:
    logger = logging.getLogger(tag)
    logger.setLevel(logging.DEBUG)
    if logger.handlers: return logger
    try:
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
        syslog_handler.setFormatter(logging.Formatter(f'{tag}: %(message)s'))
        logger.addHandler(syslog_handler)
    except: pass
    log_dir = "/var/log/cryomint"
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "core.log"), encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(file_handler)
    return logger

logger = setup_logging(LOG_TAG)

def _acquire_lock(timeout: float = 15.0) -> int:
    os.makedirs("/run/lock", exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o666)
    start = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except (IOError, OSError):
            if time.monotonic() - start > timeout:
                os.close(fd)
                raise RuntimeError("Timeout ao adquirir lock")
            time.sleep(0.1)

def _get_config_path() -> tuple[str, bool]:
    is_frozen = os.path.ismount(MOUNT_POINT_RO)
    if is_frozen:
        subprocess.run(["mount", "-o", "remount,rw", MOUNT_POINT_RO], check=False)
        return CONFIG_PATH_RO, True
    return CONFIG_PATH_RW, False

def set_frozen_state(freeze: bool) -> None:
    if os.geteuid() != 0:
        logger.error("Requer root!")
        sys.exit(1)

    lock_fd = None
    try:
        lock_fd = _acquire_lock()
        config_path, was_frozen = _get_config_path()

        lines = []
        if os.path.exists(config_path):
            with open(config_path, "r") as f: lines = f.readlines()

        new_lines = []
        found = False
        
        # REINSERÇÃO DA MÁGICA: O segredo para a Swap não sumir
        target_value = 'overlayroot="tmpfs:swap=1"\n' if freeze else 'overlayroot=""\n'

        for line in lines:
            if "overlayroot=" in line:
                new_lines.append(target_value)
                found = True
            else:
                new_lines.append(line)
        if not found: new_lines.append(target_value)

        temp_path = config_path + ".tmp"
        with open(temp_path, "w") as f:
            f.writelines(new_lines)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, config_path)
        os.sync()

        if was_frozen:
            subprocess.run(["mount", "-o", "remount,ro", MOUNT_POINT_RO], check=False)

        logger.info(f"SUCESSO: Sistema {'CONGELADO' if freeze else 'DESCONGELADO'}.")
        sys.exit(0)

    except Exception as e:
        logger.error(f"ERRO: {e}")
        sys.exit(1)
    finally:
        if lock_fd: fcntl.flock(lock_fd, fcntl.LOCK_UN); os.close(lock_fd)

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in ["freeze", "thaw"]:
        set_frozen_state(freeze=(sys.argv[1] == "freeze"))