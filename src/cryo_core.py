#!/usr/bin/env python3
import sys
import os
import subprocess
import fcntl
import logging
import logging.handlers
import time
from typing import Tuple, Optional

# ===============================================
# VERSÃO DO SISTEMA (Melhoria: Metadados)
__version__ = "1.0.4" 
# ===============================================

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
    except Exception as e: 
        # Captura falha de /dev/log, que é comum em containers sem syslog
        pass

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
            logger.info("Lock adquirido com sucesso.")
            return fd
        except (IOError, OSError):
            if time.monotonic() - start > timeout:
                os.close(fd)
                raise RuntimeError("Timeout ao adquirir lock") from None # Adiciona 'from None' para limpar o stack trace de I/O
            time.sleep(0.1)

def _get_config_path() -> Tuple[str, bool]:
    """Determina se estamos em um ambiente congelado (ro)."""
    is_frozen = os.path.ismount(MOUNT_POINT_RO)
    if is_frozen:
        try:
            # Melhora a verificação do mount
            subprocess.run(["mount", "-o", "remount,rw", MOUNT_POINT_RO], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
             logger.warning(f"Falha ao remountar {MOUNT_POINT_RO} para RW. Possível motivo: permissões.")
             # Não forçamos a falha, mas registramos o aviso.
        return CONFIG_PATH_RO, True
    else:
        return CONFIG_PATH_RW, False

def set_frozen_state(freeze: bool) -> str:
    """
    Tenta congelar (freeze=True) ou descongelar (freeze=False) o sistema.
    Retorna uma mensagem de status para o frontend.
    """
    if os.geteuid() != 0:
        return "ERRO: Requer root! Execute com sudo." # Retornando string em vez de sys.exit
    
    lock_fd = None
    try:
        # Tenta adquirir lock e obter caminhos
        lock_fd = _acquire_lock()
        config_path, was_frozen = _get_config_path()

        lines = []
        if not os.path.exists(config_path):
            return f"ERRO: Arquivo de configuração não encontrado em {config_path}"
        
        with open(config_path, "r") as f: 
             lines = f.readlines()

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
        if not found: 
             # Se não encontrar, adiciona a linha no final (mantendo o comportamento antigo como fallback)
            new_lines.append(f"\n{target_value}")

        temp_path = config_path + ".tmp"
        with open(temp_path, "w") as f:
            f.writelines(new_lines)
            f.flush()
            os.fsync(f.fileno())

        # Operação ATÔMICA de substituição
        os.replace(temp_path, config_path)
        os.sync()
        logger.info("Configuração do sistema atualizada com sucesso.")


        if was_frozen:
            try:
                # Melhora o tratamento de falhas aqui
                subprocess.run(["mount", "-o", "remount,ro", MOUNT_POINT_RO], check=True, capture_output=True)
                logger.info("Remontagem em modo somente leitura (ro) concluída.")
            except subprocess.CalledProcessError as e:
                return f"AVISO CRÍTICO: Falha ao remountar o sistema para RO. Código de retorno: {e.returncode}. Mensagem: {e.stderr.decode()}"


        if freeze:
            message = "SUCESSO: Sistema CONGELADO."
        else:
            message = "SUCESSO: Sistema DESCONGELADO."
        
        return message

    except Exception as e:
        # Captura qualquer falha do processo de arquivo/lock
        error_msg = f"ERRO CRÍTICO AO PROCESSAR O ESTADO: {e}"
        logger.critical(error_msg, exc_info=True) # Loga o stack trace completo
        return error_msg

    finally:
        if lock_fd: 
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

if __name__ == "__main__":
    # O backend agora deve retornar um resultado em vez de chamar sys.exit() diretamente.
    if len(sys.argv) != 2 or sys.argv[1] not in ["freeze", "thaw"]:
        print("Uso: python cryo_core.py [freeze|thaw]")
        sys.exit(1)

    try:
        state = (sys.argv[1] == "freeze")
        result = set_frozen_state(state)
        # O código principal agora simplesmente imprime o resultado, que será capturado pelo subprocess do frontend.
        print(result) 
    except Exception as e:
        print(f"Falha não tratada no core: {e}", file=sys.stderr)
        sys.exit(1)

