#!/usr/bin/env python3
import sys
import os
import subprocess
try:
    import fcntl
except ImportError:
    fcntl = None
import logging
import logging.handlers
import time
import json
from typing import Tuple, Optional

# ===============================================
# VERSÃO DO SISTEMA (centralizada em version.py)
# ===============================================
try:
    from version import __version__
except ImportError:
    __version__ = "1.0.5"  # fallback de desenvolvimento

# --- CONFIGURAÇÕES FIXAS ---
CONFIG_PATH_RO = "/media/root-ro/etc/overlayroot.conf"
CONFIG_PATH_RW = "/etc/overlayroot.conf"
MOUNT_POINT_RO = "/media/root-ro"
LOCK_FILE = "/run/lock/cryomint-core.lock"
LOG_TAG = "CryoMint-Core"
# Constantes de marcadores — fonte canônica única
MAINTENANCE_MARKER = "/etc/cryomint_maintenance_pending"
MAINTENANCE_RUN_FLAG = "/run/cryomint_in_maintenance"


def setup_logging(tag: str) -> logging.Logger:
    logger = logging.getLogger(tag)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    try:
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
        syslog_handler.setFormatter(logging.Formatter(f'{tag}: %(message)s'))
        logger.addHandler(syslog_handler)
    except Exception:
        # Captura falha de /dev/log, que é comum em containers sem syslog
        pass

    log_dir = "/var/log/cryomint"
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "core.log"), maxBytes=1024 * 1024, backupCount=3, encoding='utf-8'
        )
    except Exception:
        try:
            file_handler = logging.FileHandler(os.path.join(log_dir, "core.log"), encoding='utf-8')
        except Exception:
            file_handler = logging.StreamHandler()
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(file_handler)
    return logger


logger = setup_logging(LOG_TAG)


def _acquire_lock(timeout: float = 15.0) -> int:
    os.makedirs("/run/lock", exist_ok=True)
    fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o666)
    if not fcntl:
        logger.info("Mock Lock adquirido (sem fcntl).")
        return fd
    start = time.monotonic()
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.info("Lock adquirido com sucesso.")
            return fd
        except (IOError, OSError):
            if time.monotonic() - start > timeout:
                os.close(fd)
                raise RuntimeError("Timeout ao adquirir lock") from None
            time.sleep(0.1)


def _get_config_path() -> Tuple[str, bool]:
    """Determina o caminho do config e se o sistema está congelado.
    NÃO executa remount — apenas lê o estado via ismount."""
    is_frozen = os.path.ismount(MOUNT_POINT_RO)
    if is_frozen:
        return CONFIG_PATH_RO, True
    return CONFIG_PATH_RW, False


def _remount(path: str, mode: str) -> Optional[str]:
    """Remonta `path` como `mode` ('rw' ou 'ro').

    Returns:
        None em sucesso, ou string de erro.
    """
    try:
        subprocess.run(
            ["mount", "-o", f"remount,{mode}", path],
            check=True,
            capture_output=True,
        )
        logger.info(f"Remontagem de {path} em modo {mode} concluída.")
        return None
    except subprocess.CalledProcessError as e:
        msg = (
            f"AVISO CRÍTICO: Falha ao remountar {path} para {mode}. "
            f"Código: {e.returncode}. Stderr: {e.stderr.decode(errors='replace')}"
        )
        logger.error(msg)
        return msg


def _write_overlayroot(config_path: str, overlay_value: str) -> Optional[str]:
    """Atualiza atomicamente a linha overlayroot= em config_path.

    Elimina a duplicação de código que existia em set_frozen_state,
    set_maintenance_mode e run_boot_check.

    Args:
        config_path:   Caminho completo para overlayroot.conf.
        overlay_value: Valor interno, ex: 'tmpfs:swap=1' ou '' (vazio).

    Returns:
        None em sucesso, ou string de erro.
    """
    if not os.path.exists(config_path):
        return f"ERRO: Arquivo de configuração não encontrado em {config_path}"

    try:
        with open(config_path, "r") as f:
            lines = f.readlines()
    except OSError as e:
        return f"ERRO ao ler arquivo de configuração: {e}"

    target_value = f'overlayroot="{overlay_value}"\n'
    new_lines: list = []
    found = False

    # 1ª passagem: busca linha ativa
    for line in lines:
        if line.strip().startswith("overlayroot=") and not found:
            new_lines.append(target_value)
            found = True
        else:
            new_lines.append(line)

    # 2ª passagem: busca linha comentada
    if not found:
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if (
                stripped.startswith("#overlayroot=")
                or stripped.startswith("# overlayroot=")
            ) and not found:
                new_lines.append(target_value)
                found = True
            else:
                new_lines.append(line)

    # Append ao final se não encontrado
    if not found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(target_value)

    temp_path = config_path + ".tmp"
    try:
        with open(temp_path, "w") as f:
            f.writelines(new_lines)
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        if e.errno == 30:
            return "ERRO: Sistema de arquivos Somente Leitura — falhou ao gravar configuração."
        return f"ERRO ao gravar arquivo de configuração temporário: {e}"

    try:
        os.replace(temp_path, config_path)
    except OSError as e:
        if e.errno == 30:
            return "ERRO: Sistema de arquivos Somente Leitura — falhou ao substituir configuração."
        return f"ERRO ao aplicar arquivo de configuração de forma atômica: {e}"

    return None  # sucesso


def set_frozen_state(freeze: bool) -> str:
    """Congela (freeze=True) ou descongela (freeze=False) o sistema.
    Retorna mensagem de status para o frontend.
    """
    if os.geteuid() != 0:
        return "ERRO: Requer root! Execute com sudo."

    lock_fd = None
    try:
        lock_fd = _acquire_lock()
        config_path, was_frozen = _get_config_path()

        # Remonta para rw antes de escrever (somente se necessário)
        if was_frozen:
            err = _remount(MOUNT_POINT_RO, "rw")
            if err:
                return f"AVISO CRÍTICO: Falha ao preparar sistema de arquivos para escrita. {err}"

        overlay_value = "tmpfs:swap=1" if freeze else ""
        err = _write_overlayroot(config_path, overlay_value)
        if err:
            return err

        os.sync()
        logger.info("Configuração do sistema atualizada com sucesso.")

        # Remonta de volta para ro após a escrita
        if was_frozen:
            err = _remount(MOUNT_POINT_RO, "ro")
            if err:
                return err

        return "SUCESSO: Sistema CONGELADO." if freeze else "SUCESSO: Sistema DESCONGELADO."

    except Exception as e:
        error_msg = f"ERRO CRÍTICO AO PROCESSAR O ESTADO: {e}"
        logger.critical(error_msg, exc_info=True)
        return error_msg
    finally:
        if lock_fd:
            if fcntl:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def get_overlay_usage() -> dict:
    """Calcula o uso do overlay em /media/root-rw."""
    path = "/media/root-rw"
    if not os.path.exists(path) or not os.path.ismount(path):
        return {"active": False}
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        percent = (used / total) * 100 if total > 0 else 0
        return {
            "active": True,
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        }
    except Exception as e:
        logger.error(f"Erro ao calcular uso do overlay: {e}")
        return {"active": False, "error": str(e)}


def set_maintenance_mode() -> str:
    """Configura o próximo boot como modo manutenção (overlayroot="").
    Cria marcador persistente canônico no disco real.
    """
    if os.geteuid() != 0:
        return "ERRO: Requer root! Execute com sudo."

    lock_fd = None
    try:
        lock_fd = _acquire_lock()
        config_path, was_frozen = _get_config_path()

        # Remonta para rw antes de escrever
        if was_frozen:
            err = _remount(MOUNT_POINT_RO, "rw")
            if err:
                return f"AVISO CRÍTICO: Falha ao preparar sistema de arquivos para escrita. {err}"

        # O marcador DEVE ficar no disco real:
        #   - Congelado:     disco real está em MOUNT_POINT_RO/etc/
        #   - Descongelado:  disco real é /etc/ diretamente
        # No próximo boot de manutenção (sem overlay), /etc/ == disco real → paths alinham.
        real_etc = os.path.join(MOUNT_POINT_RO, "etc") if was_frozen else "/etc"
        marker_path = os.path.join(real_etc, "cryomint_maintenance_pending")

        try:
            with open(marker_path, "w") as f:
                f.write("1\n")
                f.flush()
                os.fsync(f.fileno())
            logger.info(f"Marcador de manutenção criado em: {marker_path}")
        except OSError as e:
            if e.errno == 30:
                return "ERRO: Sistema Somente Leitura — falhou ao criar marcador de manutenção."
            return f"ERRO ao criar marcador de manutenção: {e}"

        err = _write_overlayroot(config_path, "")
        if err:
            return err

        os.sync()
        logger.info("Modo de manutenção configurado com sucesso.")

        # Remonta de volta para ro
        if was_frozen:
            err = _remount(MOUNT_POINT_RO, "ro")
            if err:
                return err

        return "SUCESSO: Modo de manutenção configurado para o próximo boot."

    except Exception as e:
        error_msg = f"ERRO CRÍTICO AO PROCESSAR MODO MANUTENÇÃO: {e}"
        logger.critical(error_msg, exc_info=True)
        return error_msg
    finally:
        if lock_fd:
            if fcntl:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def run_boot_check() -> str:
    """Executa durante o boot para detectar e processar o modo de manutenção.
    Remove o marcador e reativa o congelamento para o próximo boot.
    """
    if os.geteuid() != 0:
        return "ERRO: Requer root! Execute com sudo."

    if not os.path.exists(MAINTENANCE_MARKER):
        return "INFO: Sem pendência de manutenção detectada no boot."

    lock_fd = None
    try:
        lock_fd = _acquire_lock()

        # Remove o marcador do disco real
        try:
            os.remove(MAINTENANCE_MARKER)
            logger.info("Marcador de manutenção removido do disco.")
        except Exception as e:
            logger.error(f"Falha ao remover marcador: {e}")

        # No boot de manutenção, o overlay NÃO está ativo — escreve direto em /etc/
        err = _write_overlayroot(CONFIG_PATH_RW, "tmpfs:swap=1")
        if err:
            logger.error(f"Falha ao reativar congelamento no boot-check: {err}")
            return err

        os.sync()
        logger.info("Auto-congelamento configurado para o próximo boot pós-manutenção.")

        # Cria sinalizador em /run (RAM) para a GUI detectar a sessão de manutenção
        try:
            with open(MAINTENANCE_RUN_FLAG, "w") as f:
                f.write("1\n")
            logger.info("Sinalizador de manutenção ativo criado em /run.")
        except Exception as e:
            logger.error(f"Falha ao criar sinalizador em /run: {e}")

        return "SUCESSO: Auto-congelamento reativado."

    except Exception as e:
        error_msg = f"ERRO CRÍTICO NO BOOT CHECK: {e}"
        logger.critical(error_msg, exc_info=True)
        return error_msg
    finally:
        if lock_fd:
            if fcntl:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)


def get_status_json() -> str:
    """Retorna o estado completo do sistema em formato JSON."""
    is_currently_frozen = os.path.ismount(MOUNT_POINT_RO)
    config_path = CONFIG_PATH_RO if is_currently_frozen else CONFIG_PATH_RW

    configured_frozen = False
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                configured_frozen = any('overlayroot="tmpfs' in line for line in f)
        except Exception:
            pass

    status_data = {
        "version": __version__,
        "is_frozen": is_currently_frozen,
        "configured_frozen": configured_frozen,
        "maintenance_pending": os.path.exists(MAINTENANCE_MARKER),
        "maintenance_active": os.path.exists(MAINTENANCE_RUN_FLAG),
        "overlay": get_overlay_usage(),
    }
    return json.dumps(status_data)


if __name__ == "__main__":
    valid_commands = ["freeze", "thaw", "maintenance", "boot-check", "status"]
    if len(sys.argv) != 2 or sys.argv[1] not in valid_commands:
        print(f"Uso: python cryo_core.py [{'|'.join(valid_commands)}]")
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd in ["freeze", "thaw"]:
            print(set_frozen_state(cmd == "freeze"))
        elif cmd == "maintenance":
            print(set_maintenance_mode())
        elif cmd == "boot-check":
            print(run_boot_check())
        elif cmd == "status":
            print(get_status_json())
    except Exception as e:
        print(f"Falha não tratada no core para o comando {cmd}: {e}", file=sys.stderr)
        sys.exit(1)
