#!/usr/bin/env python3
"""
CryoMint UI - Versão 1.0.5
Thread Pool Assíncrono + Tema Dark Fixo + UX melhorada
"""

import sys
import os
import subprocess
import socket
import tempfile
import select
import logging
import logging.handlers
import atexit
import json
import platform
import time

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QSystemTrayIcon, QMenu, QTabWidget,
    QMessageBox, QProgressBar, QPlainTextEdit, QFileDialog, QGridLayout
)
from PySide6.QtGui import QIcon, QAction, QFont, QFontDatabase, QTextCursor
from PySide6.QtCore import Qt, QTimer, Signal, QRunnable, Slot, QObject, QThreadPool

# ===============================================
# VERSÃO DO SISTEMA (centralizada em version.py)
# ===============================================
try:
    from version import __version__
except ImportError:
    __version__ = "1.0.5"  # fallback de desenvolvimento

# --- CONSTANTES ---
BACKEND_PATH = "/opt/cryomint/src/cryo_core.py"
# Fallback local se não estiver instalado (facilita desenvolvimento)
if not os.path.exists(BACKEND_PATH):
    _local_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cryo_core.py")
    if os.path.exists(_local_backend):
        BACKEND_PATH = _local_backend

ASSETS_DIR = "/opt/cryomint/assets"
LOG_TAG = "CryoMint-UI"

try:
    _uid = os.getuid()
except AttributeError:
    _uid = 1000  # Fallback para Windows sem getuid
SINGLETON_SOCKET = os.path.join(tempfile.gettempdir(), f"cryomint_{_uid}.sock")


# ===============================================
# 1. WORKERS ASSÍNCRONOS PARA PYSIDE6
# ===============================================
class WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


class BackendWorker(QRunnable):
    """Worker para operações de freeze/thaw/maintenance/status via pkexec."""

    def __init__(self, action: str):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            logger.info(f"Executando operação backend async: {self.action}")

            # Operação de status não exige root, roda sem pkexec
            if self.action == "status":
                if platform.system() == "Windows":
                    cmd = [sys.executable, BACKEND_PATH, "status"]
                else:
                    cmd = ["/usr/bin/python3", BACKEND_PATH, "status"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    self.signals.finished.emit(result.stdout.strip())
                else:
                    self.signals.error.emit(f"Erro ao consultar status: {result.stderr.strip()}")
                return

            # Se pkexec não existir (desenvolvimento local / outros SOs) — modo mock
            import shutil
            if not shutil.which("pkexec"):
                time.sleep(1.5)
                if self.action == "maintenance":
                    self.signals.finished.emit("SUCESSO: [MOCK] Modo de manutenção ativado.")
                else:
                    status_msg = "CONGELADO" if self.action == "freeze" else "DESCONGELADO"
                    self.signals.finished.emit(f"SUCESSO: [MOCK] Sistema {status_msg}.")
                return

            if (
                os.path.exists(BACKEND_PATH)
                and os.access(BACKEND_PATH, os.X_OK)
                and BACKEND_PATH == "/opt/cryomint/src/cryo_core.py"
            ):
                cmd = ["pkexec", BACKEND_PATH, self.action]
            else:
                cmd = ["pkexec", "/usr/bin/python3", BACKEND_PATH, self.action]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                self.signals.finished.emit(result.stdout.strip())
            else:
                self.signals.error.emit(
                    f"Falha de privilégio ou backend ({result.returncode}):\n{result.stderr.strip()}"
                )

        except subprocess.TimeoutExpired:
            self.signals.error.emit("TIMEOUT: O sistema demorou mais de 60 segundos para responder.")
        except Exception as e:
            self.signals.error.emit(f"ERRO CRÍTICO no processamento em background: {e}")


class SystemInfoSignals(QObject):
    finished = Signal(dict)


class SystemInfoWorker(QRunnable):
    """Worker para coleta de informações de sistema sem bloquear a UI thread."""

    def __init__(self):
        super().__init__()
        self.signals = SystemInfoSignals()

    @Slot()
    def run(self):
        info = get_system_info()
        self.signals.finished.emit(info)


# ===============================================
# 2. SISTEMA DE LOG E SINGLETON (Proteções)
# ===============================================
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
        pass
    log_dir = os.path.expanduser("~/.local/share/cryomint/logs")
    os.makedirs(log_dir, exist_ok=True)
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "ui.log"), maxBytes=1024 * 1024, backupCount=3, encoding='utf-8'
        )
    except Exception:
        file_handler = logging.FileHandler(os.path.join(log_dir, "ui.log"), encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(file_handler)
    return logger


logger = setup_logging(LOG_TAG)


def ensure_single_instance() -> bool:
    if not hasattr(socket, "AF_UNIX"):
        return True

    test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        test_sock.connect(SINGLETON_SOCKET)
        test_sock.sendall(b"SHOW")
        test_sock.close()
        return False  # já existe uma instância ativa
    except OSError:
        # Não há instância ativa — prosseguir com criação do servidor
        pass

    if os.path.exists(SINGLETON_SOCKET):
        try:
            os.unlink(SINGLETON_SOCKET)
        except OSError as e:
            logger.warning(f"Não foi possível remover socket antigo: {e}")

    try:
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(SINGLETON_SOCKET)
        server_sock.listen(1)
        server_sock.setblocking(False)
        global _singleton_socket
        _singleton_socket = server_sock
        atexit.register(
            lambda: server_sock.close() or (
                os.path.exists(SINGLETON_SOCKET) and os.unlink(SINGLETON_SOCKET)
            )
        )
        return True
    except OSError as e:
        logger.warning(f"Não foi possível criar socket singleton: {e}")
        return False


def handle_singleton_signal(window) -> QTimer:
    def check_socket():
        sock = globals().get('_singleton_socket')
        if not sock:
            return
        try:
            ready, _, _ = select.select([sock], [], [], 0)
            if ready:
                conn, _ = sock.accept()
                data = conn.recv(1024)
                if data == b"SHOW" and window:
                    window.showNormal()
                    window.raise_()
                    window.activateWindow()
                conn.close()
        except OSError as e:
            logger.debug(f"Erro no socket singleton: {e}")

    timer = QTimer(window)
    timer.timeout.connect(check_socket)
    timer.start(500)
    return timer


def get_system_info() -> dict:
    info = {
        "hostname": socket.gethostname(),
        "ip": "Desconectado",
        "os": f"{platform.system()} {platform.release()}",
        "cpu": "Desconhecido",
        "ram": "Desconhecido",
        "swap": "Desconhecido",
        "uptime": "Desconhecido",
    }
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["ip"] = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        info["cpu"] = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
        try:
            mem_total = 0
            swap_total = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1]) // 1024
                    elif line.startswith("SwapTotal:"):
                        swap_total = int(line.split()[1]) // 1024
            if mem_total:
                info["ram"] = f"{mem_total / 1024:.2f} GB" if mem_total >= 1024 else f"{mem_total} MB"
            info["swap"] = (
                f"{swap_total / 1024:.2f} GB" if swap_total >= 1024 else f"{swap_total} MB"
            ) if swap_total else "Nenhuma"
        except Exception:
            pass
        try:
            with open("/proc/uptime", "r") as f:
                uptime_seconds = float(f.readline().split()[0])
                uptime_hours = uptime_seconds / 3600
                if uptime_hours < 1:
                    info["uptime"] = f"{int(uptime_seconds / 60)} min"
                elif uptime_hours < 24:
                    info["uptime"] = f"{int(uptime_hours)}h {int((uptime_seconds % 3600) / 60)}min"
                else:
                    info["uptime"] = f"{int(uptime_hours / 24)}d {int(uptime_hours % 24)}h"
        except Exception:
            pass
    else:
        info["cpu"] = platform.processor() or "CPU Genérica"
        info["ram"] = "8.00 GB (Simulado)"
        info["swap"] = "2.00 GB (Simulado)"
        info["uptime"] = "1h 15m (Simulado)"

    return info


def read_log_tail(file_path: str, max_lines: int = 150) -> str:
    if not os.path.exists(file_path):
        return f"Arquivo de log não encontrado: {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-max_lines:])
    except PermissionError:
        return f"ERRO DE PERMISSÃO: Sem permissão de leitura para {file_path}.\n"
    except Exception as e:
        return f"Erro ao ler log: {e}"


# ===============================================
# 3. INTERFACE DE USUÁRIO
# ===============================================
class CryoMintUI(QMainWindow):
    def __init__(self):
        super().__init__()

        # ASSETS E ÍCONES
        self.assets_dir = ASSETS_DIR if os.path.isdir(ASSETS_DIR) else "assets"
        self.icon_frozen = QIcon.fromTheme(
            "cryomint-close-symbolic", QIcon(os.path.join(self.assets_dir, "close.svg"))
        )
        self.icon_unfrozen = QIcon.fromTheme(
            "cryomint-open-symbolic", QIcon(os.path.join(self.assets_dir, "open.svg"))
        )
        self.icon_main = QIcon.fromTheme(
            "cryomint", QIcon(os.path.join(self.assets_dir, "icon.svg"))
        )
        if self.icon_main.isNull():
            self.icon_main = QIcon.fromTheme("system-run")
        self.setWindowIcon(self.icon_main)

        # FONTES E JANELA
        sys_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        self.is_frozen = self._check_real_status()
        self.is_maintenance_pending = False
        self.is_maintenance_active = os.path.exists("/run/cryomint_in_maintenance")
        self.setWindowTitle(f"❄️ CryoMint {__version__}")
        self.setFixedSize(500, 420)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ── ABA 1: STATUS / CONTROLE ──────────────────────────────────
        self.tab_controle = QWidget()
        layout_controle = QVBoxLayout(self.tab_controle)
        layout_controle.setAlignment(Qt.AlignCenter)

        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont(sys_font.family(), 18, QFont.Bold))
        self.lbl_status.setAlignment(Qt.AlignCenter)

        self.lbl_maintenance_warning = QLabel(
            "⚠️ MODO DE MANUTENÇÃO ATIVO\n"
            "Alterações feitas nesta sessão serão salvas.\n"
            "O sistema voltará a congelar no próximo boot."
        )
        self.lbl_maintenance_warning.setAlignment(Qt.AlignCenter)
        self.lbl_maintenance_warning.setStyleSheet("""
            background-color: #78350f;
            color: #fef3c7;
            border: 1px solid #d97706;
            border-radius: 6px;
            padding: 8px;
            font-weight: bold;
            font-size: 11px;
        """)
        self.lbl_maintenance_warning.hide()

        self.lbl_overlay = QLabel("Espaço do Overlay: Calculando...")
        self.lbl_overlay.setAlignment(Qt.AlignCenter)
        self.lbl_overlay.setStyleSheet("font-size: 11px; color: #e4e4e7;")
        self.lbl_overlay.hide()

        self.progress_overlay = QProgressBar()
        self.progress_overlay.setObjectName("progressOverlay")
        self.progress_overlay.setFixedSize(280, 16)
        self.progress_overlay.setTextVisible(True)
        self.progress_overlay.hide()

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("btnToggle")
        self.btn_toggle.setFixedSize(280, 42)
        self.btn_toggle.clicked.connect(self.start_async_toggle)

        self.btn_maintenance = QPushButton("🛠️ Modo de Manutenção")
        self.btn_maintenance.setObjectName("btnMaintenance")
        self.btn_maintenance.setFixedSize(280, 38)
        self.btn_maintenance.clicked.connect(self.start_async_maintenance)
        self.btn_maintenance.setStyleSheet("""
            QPushButton#btnMaintenance {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1e1b4b, stop:1 #312e81);
                color: #c7d2fe;
                border: 1px solid #4338ca;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton#btnMaintenance:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #312e81, stop:1 #3730a3);
            }
            QPushButton#btnMaintenance:pressed {
                background: #1e1b4b;
            }
        """)

        self.btn_reboot = QPushButton("🔄 Reiniciar Agora")
        self.btn_reboot.setObjectName("btnReboot")
        self.btn_reboot.setFixedSize(280, 38)
        self.btn_reboot.hide()
        self.btn_reboot.clicked.connect(self.reboot_system)

        self.lbl_info = QLabel("✅ Sistema operacional normal.")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")

        layout_controle.addSpacing(5)
        layout_controle.addWidget(self.lbl_status)
        layout_controle.addWidget(self.lbl_maintenance_warning)
        layout_controle.addSpacing(5)
        layout_controle.addWidget(self.lbl_overlay, alignment=Qt.AlignCenter)
        layout_controle.addWidget(self.progress_overlay, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(5)
        layout_controle.addWidget(self.btn_toggle, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(3)
        layout_controle.addWidget(self.btn_maintenance, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(3)
        layout_controle.addWidget(self.btn_reboot, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(5)
        layout_controle.addWidget(self.lbl_info)

        # ── ABA 2: LOGS ───────────────────────────────────────────────
        self.tab_logs = QWidget()
        layout_logs = QVBoxLayout(self.tab_logs)

        self.txt_logs = QPlainTextEdit()
        self.txt_logs.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setFont(QFont("Monospace", 9))
        self.txt_logs.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0b0b0d;
                color: #a7f3d0;
                border: 1px solid #2d2d34;
                border-radius: 6px;
            }
        """)

        layout_btns_logs = QHBoxLayout()
        btn_reload_logs = QPushButton("🔄 Atualizar")
        btn_reload_logs.clicked.connect(self.reload_logs_view)
        btn_clear_logs = QPushButton("🧹 Limpar")
        btn_clear_logs.clicked.connect(self.clear_logs)
        btn_export_logs = QPushButton("💾 Exportar")
        btn_export_logs.clicked.connect(self.export_logs)
        layout_btns_logs.addWidget(btn_reload_logs)
        layout_btns_logs.addWidget(btn_clear_logs)
        layout_btns_logs.addWidget(btn_export_logs)

        layout_logs.addWidget(self.txt_logs)
        layout_logs.addLayout(layout_btns_logs)

        # ── ABA 3: SISTEMA ────────────────────────────────────────────
        self.tab_sistema = QWidget()
        layout_sistema = QVBoxLayout(self.tab_sistema)
        layout_sistema.setAlignment(Qt.AlignTop)

        grid_sys = QGridLayout()
        grid_sys.setSpacing(8)

        def _sys_title(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold; color: #3b82f6;")
            return lbl

        self.lbl_host_val = QLabel("Carregando...")
        self.lbl_ip_val = QLabel("Carregando...")
        self.lbl_os_val = QLabel("Carregando...")
        self.lbl_cpu_val = QLabel("Carregando...")
        self.lbl_cpu_val.setWordWrap(True)
        self.lbl_ram_val = QLabel("Carregando...")
        self.lbl_swap_val = QLabel("Carregando...")
        self.lbl_uptime_val = QLabel("Carregando...")

        rows = [
            ("💻 Hostname:", self.lbl_host_val),
            ("🌐 IP da Rede:", self.lbl_ip_val),
            ("💿 Sistema:", self.lbl_os_val),
            ("⚙️ Processador:", self.lbl_cpu_val),
            ("🧠 RAM Total:", self.lbl_ram_val),
            ("💾 Swap:", self.lbl_swap_val),
            ("⏱️ Tempo Ativo:", self.lbl_uptime_val),
        ]
        for row_idx, (title, val_lbl) in enumerate(rows):
            grid_sys.addWidget(_sys_title(title), row_idx, 0)
            grid_sys.addWidget(val_lbl, row_idx, 1)

        btn_refresh_sys = QPushButton("🔄 Atualizar Informações")
        btn_refresh_sys.clicked.connect(self.reload_system_info)

        layout_sistema.addSpacing(10)
        layout_sistema.addLayout(grid_sys)
        layout_sistema.addSpacing(10)
        layout_sistema.addWidget(btn_refresh_sys, alignment=Qt.AlignCenter)

        # ── ABA 4: SOBRE ──────────────────────────────────────────────
        self.tab_sobre = QWidget()
        layout_sobre = QVBoxLayout(self.tab_sobre)
        layout_sobre.setAlignment(Qt.AlignCenter)

        self.lbl_icon_sobre = QLabel()
        self.lbl_icon_sobre.setAlignment(Qt.AlignCenter)
        self.lbl_icon_sobre.setPixmap(self.icon_main.pixmap(64, 64))
        lbl_title = QLabel("CryoMint")
        lbl_title.setFont(QFont(sys_font.family(), 22, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_desc = QLabel(
            "Sistema imutável para laboratórios.<br><b>Desenvolvedor:</b> VaGNaroK"
        )
        self.lbl_desc.setAlignment(Qt.AlignCenter)
        self.lbl_desc.setStyleSheet("color: #aaaaaa; font-size: 13px; line-height: 1.5;")

        layout_sobre.addWidget(self.lbl_icon_sobre)
        layout_sobre.addWidget(lbl_title)
        layout_sobre.addSpacing(15)
        layout_sobre.addWidget(self.lbl_desc)

        # Adicionar abas
        self.tabs.addTab(self.tab_controle, "🛡️ Status")
        self.tabs.addTab(self.tab_logs, "📄 Logs")
        self.tabs.addTab(self.tab_sistema, "🖥️ Sistema")
        self.tabs.addTab(self.tab_sobre, "ℹ️ Sobre")
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # TRAY
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.icon_frozen)  # Define um ícone inicial para evitar aviso
        self.tray_icon.setToolTip(f"❄️ CryoMint {__version__}")
        self._setup_tray_menu()
        self.tray_icon.show()

        # TEMA DARK FIXO
        self.apply_dark_theme()

        # Thread Pool
        self.threadpool = QThreadPool.globalInstance()

        # Timer de polling periódico de status (com back-off durante operações)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.start_periodic_status_check)
        self.status_timer.start(10000)
        self.start_periodic_status_check()

    # ── TRAY ──────────────────────────────────────────────────────────
    def _setup_tray_menu(self):
        self.tray_menu = QMenu(self)
        self.tray_menu.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.tray_menu.setAttribute(Qt.WA_TranslucentBackground)
        act_show = QAction("🖥️ Abrir Painel", self)
        act_show.triggered.connect(self.request_access)
        act_exit = QAction("❌ Sair", self)
        act_exit.triggered.connect(QApplication.instance().quit)
        self.tray_menu.addAction(act_show)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(act_exit)
        self.tray_icon.setContextMenu(self.tray_menu)

    # ── TEMA ──────────────────────────────────────────────────────────
    def apply_dark_theme(self):
        """Aplica identidade visual escura moderna e premium (QSS)."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121214;
            }
            QTabWidget::pane {
                border: 1px solid #2d2d34;
                background-color: #18181c;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #1d1d22;
                color: #8a8a93;
                padding: 10px 20px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                border: 1px solid #2d2d34;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #18181c;
                color: #ffffff;
                border-color: #2d2d34;
                border-bottom: 2px solid #3b82f6;
            }
            QTabBar::tab:hover {
                background-color: #23232a;
                color: #ffffff;
            }
            QLabel {
                color: #e4e4e7;
                font-family: 'Segoe UI', 'Ubuntu', 'Helvetica Neue', sans-serif;
            }
            QPushButton {
                background-color: #27272a;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 10px;
                font-family: 'Segoe UI', 'Ubuntu', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                border-color: #52525b;
            }
            QPushButton:pressed {
                background-color: #18181b;
            }
            QPushButton:disabled {
                background-color: #18181b;
                color: #52525b;
                border-color: #27272a;
            }
            QPushButton#btnReboot {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d97706, stop:1 #b45309);
                color: white;
                font-size: 14px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton#btnReboot:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f59e0b, stop:1 #d97706);
            }
            QPushButton#btnReboot:pressed {
                background: #b45309;
            }
            QProgressBar {
                border: 1px solid #3f3f46;
                border-radius: 4px;
                text-align: center;
                background-color: #18181b;
                color: #ffffff;
                font-weight: bold;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #06b6d4);
                border-radius: 3px;
            }
        """)
        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #18181c;
                color: #e4e4e7;
                border: 1px solid #2d2d34;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
                margin: 2px 0px;
                font-weight: 500;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2d2d34;
                margin: 4px 10px;
            }
        """)

    # ── HELPERS DE ESTADO ─────────────────────────────────────────────
    def _check_real_status(self) -> bool:
        config = (
            "/media/root-ro/etc/overlayroot.conf"
            if os.path.ismount("/media/root-ro")
            else "/etc/overlayroot.conf"
        )
        try:
            with open(config, "r") as f:
                return any('overlayroot="tmpfs' in line for line in f)
        except Exception:
            return False

    def request_access(self):
        self.start_periodic_status_check()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def update_ui_visuals(self):
        """Fallback básico caso o status JSON falhe."""
        status = "CONGELADO" if self.is_frozen else "DESCONGELADO"
        self.lbl_status.setText(f"STATUS: {status}")
        self.tray_icon.setIcon(self.icon_frozen if self.is_frozen else self.icon_unfrozen)

    # ── FLUXO ASSÍNCRONO — TOGGLE ─────────────────────────────────────
    def start_async_toggle(self):
        if not os.path.isfile(BACKEND_PATH):
            QMessageBox.critical(self, "Erro", f"Backend não encontrado: {BACKEND_PATH}")
            return

        self.status_timer.stop()  # Pausa polling durante operação
        self.btn_toggle.setEnabled(False)
        self.btn_maintenance.setEnabled(False)
        self.btn_reboot.hide()
        self.lbl_info.setText("⏳ Processando estado do sistema, por favor aguarde...")
        self.lbl_info.setStyleSheet("color: #E67E22; font-weight: bold; font-size: 12px;")

        cmd = "thaw" if self.is_frozen else "freeze"
        worker = BackendWorker(cmd)
        worker.signals.finished.connect(self._handle_success)
        worker.signals.error.connect(self._handle_failure)
        self.threadpool.start(worker)

    @Slot(str)
    def _handle_success(self, msg: str):
        self.status_timer.start(10000)  # Retoma polling
        self.btn_toggle.setEnabled(True)
        self.btn_maintenance.setEnabled(True)
        if "ERRO" in msg.upper():
            self._handle_failure(msg)
        else:
            self.start_periodic_status_check()

    @Slot(str)
    def _handle_failure(self, err: str):
        self.status_timer.start(10000)  # Retoma polling
        self.btn_toggle.setEnabled(True)
        self.btn_maintenance.setEnabled(True)
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        self.lbl_info.setText("❌ A operação foi cancelada ou falhou.")
        QMessageBox.critical(self, "Falha na Operação", err)

    # ── FLUXO ASSÍNCRONO — MANUTENÇÃO ────────────────────────────────
    def start_async_maintenance(self):
        reply = QMessageBox.question(
            self,
            "Descongelar para Manutenção",
            "Deseja descongelar o sistema temporariamente?\n\n"
            "O sistema estará DESCONGELADO no próximo boot para que você possa "
            "realizar atualizações ou instalar programas.\n"
            "Após isso, ele voltará a congelar AUTOMATICAMENTE no boot seguinte.\n\n"
            "Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.status_timer.stop()  # Pausa polling durante operação
        self.btn_toggle.setEnabled(False)
        self.btn_maintenance.setEnabled(False)
        self.btn_reboot.hide()
        self.lbl_info.setText("⏳ Configurando modo de manutenção, por favor aguarde...")
        self.lbl_info.setStyleSheet("color: #E67E22; font-weight: bold; font-size: 12px;")

        worker = BackendWorker("maintenance")
        worker.signals.finished.connect(self._handle_maintenance_success)
        worker.signals.error.connect(self._handle_maintenance_failure)
        self.threadpool.start(worker)

    @Slot(str)
    def _handle_maintenance_success(self, msg: str):
        self.status_timer.start(10000)  # Retoma polling
        self.btn_toggle.setEnabled(True)
        self.btn_maintenance.setEnabled(True)
        if "ERRO" in msg.upper():
            self._handle_maintenance_failure(msg)
        else:
            self.is_maintenance_pending = True
            self.start_periodic_status_check()
            QMessageBox.information(
                self,
                "Modo Manutenção Configurado",
                "O modo de manutenção foi ativado com sucesso!\n\n"
                "Por favor, REINICIE o computador para iniciar a manutenção.",
            )

    @Slot(str)
    def _handle_maintenance_failure(self, err: str):
        self.status_timer.start(10000)  # Retoma polling
        self.btn_toggle.setEnabled(True)
        self.btn_maintenance.setEnabled(True)
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        self.lbl_info.setText("❌ Falha ao ativar modo de manutenção.")
        QMessageBox.critical(self, "Falha na Operação", err)

    # ── POLLING DE STATUS ─────────────────────────────────────────────
    def start_periodic_status_check(self):
        worker = BackendWorker("status")
        worker.signals.finished.connect(self._handle_status_success)
        worker.signals.error.connect(self._handle_status_error)
        self.threadpool.start(worker)

    @Slot(str)
    def _handle_status_success(self, json_str: str):
        try:
            data = json.loads(json_str)
            self.is_frozen = data.get("is_frozen", False)
            self.is_maintenance_pending = data.get("maintenance_pending", False)
            self.is_maintenance_active = data.get("maintenance_active", False)
            self.update_ui_state(data)
        except Exception as e:
            logger.error(f"Erro ao processar status: {e}. Entrada: {json_str}")
            self.is_frozen = self._check_real_status()
            self.update_ui_visuals()

    @Slot(str)
    def _handle_status_error(self, err: str):
        logger.error(f"Falha na consulta periódica de status: {err}")
        self.is_frozen = self._check_real_status()
        self.update_ui_visuals()

    def update_ui_state(self, data: dict):
        status_text = "CONGELADO" if self.is_frozen else "DESCONGELADO"

        # 1. Indicador do Status Principal
        if self.is_maintenance_active:
            self.lbl_status.setText("STATUS: MODO MANUTENÇÃO")
            self.lbl_status.setStyleSheet(
                "color: #fbbf24; font-size: 20px; font-weight: bold; padding: 5px; border-radius: 4px;"
            )
            self.lbl_maintenance_warning.show()
        else:
            self.lbl_status.setText(f"STATUS: {status_text}")
            color = "#38bdf8" if self.is_frozen else "#ef4444"
            self.lbl_status.setStyleSheet(
                f"color: {color}; font-size: 20px; font-weight: bold; padding: 5px; border-radius: 4px;"
            )
            self.lbl_maintenance_warning.hide()

        # 2. Botões e estilos
        if self.is_frozen:
            btn_text = "🔥 Descongelar Sistema"
            button_style = """
                QPushButton#btnToggle {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ea580c, stop:1 #c2410c);
                    color: white; border: none; border-radius: 6px;
                    font-size: 14px; font-weight: bold;
                }
                QPushButton#btnToggle:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f97316, stop:1 #ea580c);
                }
                QPushButton#btnToggle:pressed { background: #9a3412; }
            """
            self.btn_maintenance.show()
        else:
            btn_text = "❄️ Congelar Sistema"
            button_style = """
                QPushButton#btnToggle {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06b6d4, stop:1 #2563eb);
                    color: white; border: none; border-radius: 6px;
                    font-size: 14px; font-weight: bold;
                }
                QPushButton#btnToggle:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #22d3ee, stop:1 #3b82f6);
                }
                QPushButton#btnToggle:pressed { background: #1d4ed8; }
            """
            self.btn_maintenance.hide()

        self.btn_toggle.setText(btn_text)
        self.btn_toggle.setStyleSheet(button_style)
        self.tray_icon.setIcon(self.icon_frozen if self.is_frozen else self.icon_unfrozen)

        # 3. Monitoramento do Overlay
        overlay = data.get("overlay", {})
        if overlay.get("active", False):
            total_mb = overlay.get("total", 0) / (1024 * 1024)
            used_mb = overlay.get("used", 0) / (1024 * 1024)
            percent = overlay.get("percent", 0.0)

            self.lbl_overlay.setText(
                f"Overlay em uso: {used_mb:.1f} MB / {total_mb:.1f} MB ({percent:.1f}%)"
            )
            self.progress_overlay.setValue(int(percent))
            self.lbl_overlay.show()
            self.progress_overlay.show()

            if percent > 85.0:
                self.lbl_overlay.setStyleSheet("color: #ef4444; font-weight: bold;")
                last_warn = getattr(self, '_last_warn_time', 0)
                if time.time() - last_warn > 300:
                    self.tray_icon.showMessage(
                        "⚠️ Espaço do CryoMint esgotando",
                        f"O overlay temporário atingiu {percent:.1f}% de uso. "
                        "Salve seus dados e reinicie.",
                        QSystemTrayIcon.Warning,
                        10000,
                    )
                    self._last_warn_time = time.time()
            else:
                self.lbl_overlay.setStyleSheet("color: #e4e4e7;")
        else:
            self.lbl_overlay.hide()
            self.progress_overlay.hide()

        # 4. Reinicialização pendente
        active_frozen = data.get("is_frozen", False)
        target_frozen = data.get("configured_frozen", False)

        if active_frozen != target_frozen or self.is_maintenance_pending:
            self.btn_reboot.show()
            if self.is_maintenance_pending:
                self.lbl_info.setText("⚠️ Reinicie para entrar no Modo de Manutenção!")
            else:
                status_futuro = "Congelado" if target_frozen else "Descongelado"
                self.lbl_info.setText(f"⚠️ Reinicie para aplicar: {status_futuro}!")
            self.lbl_info.setStyleSheet("color: #fbbf24; font-weight: bold; font-size: 11px;")
        else:
            if self.btn_toggle.isEnabled():
                self.btn_reboot.hide()
                if self.is_maintenance_active:
                    self.lbl_info.setText("🛠️ Modo de manutenção ativo (alterações persistentes).")
                    self.lbl_info.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px;")
                else:
                    self.lbl_info.setText("✅ Sistema operacional normal.")
                    self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")

    # ── ABAS — CALLBACKS ──────────────────────────────────────────────
    def on_tab_changed(self, index: int):
        if index == 1:
            self.reload_logs_view()
        elif index == 2:
            self.reload_system_info()

    def reload_logs_view(self):
        ui_log_path = os.path.expanduser("~/.local/share/cryomint/logs/ui.log")
        core_log_path = "/var/log/cryomint/core.log"
        ui_log_content = read_log_tail(ui_log_path, 80)
        core_log_content = read_log_tail(core_log_path, 80)
        log_text = (
            f"=== UI LOG ({ui_log_path}) ===\n{ui_log_content}\n\n"
            f"=== CORE LOG ({core_log_path}) ===\n{core_log_content}"
        )
        self.txt_logs.setPlainText(log_text)
        self.txt_logs.moveCursor(QTextCursor.End)

    def clear_logs(self):
        ui_log_path = os.path.expanduser("~/.local/share/cryomint/logs/ui.log")
        try:
            if os.path.exists(ui_log_path):
                with open(ui_log_path, 'w'):
                    pass  # trunca o arquivo com contexto seguro
        except Exception as e:
            logger.error(f"Erro ao limpar log: {e}")
        self.reload_logs_view()

    def export_logs(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Logs", os.path.expanduser("~/cryomint_logs.txt"),
            "Arquivos de Texto (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.txt_logs.toPlainText())
                QMessageBox.information(self, "Sucesso", f"Logs salvos com sucesso em:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Erro ao Exportar", f"Não foi possível salvar os logs: {e}")

    def reload_system_info(self):
        """Coleta informações de sistema em thread separada para não bloquear a UI."""
        worker = SystemInfoWorker()
        worker.signals.finished.connect(self._apply_system_info)
        self.threadpool.start(worker)

    @Slot(dict)
    def _apply_system_info(self, info: dict):
        self.lbl_host_val.setText(info["hostname"])
        self.lbl_ip_val.setText(info["ip"])
        self.lbl_os_val.setText(info["os"])
        self.lbl_cpu_val.setText(info["cpu"])
        self.lbl_ram_val.setText(info["ram"])
        self.lbl_swap_val.setText(info["swap"])
        self.lbl_uptime_val.setText(info["uptime"])

    def reboot_system(self):
        """Reinicia o sistema com tratamento completo de erros."""
        try:
            result = subprocess.run(
                ["pkexec", "systemctl", "reboot"],
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0:
                QMessageBox.critical(
                    self, "Erro ao Reiniciar",
                    f"O sistema não pôde ser reiniciado:\n"
                    f"{result.stderr.decode(errors='replace')}",
                )
        except subprocess.TimeoutExpired:
            QMessageBox.critical(self, "Timeout", "O comando de reinicialização não respondeu a tempo.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def closeEvent(self, event):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
        else:
            event.ignore()
            self.hide()

    def _cleanup_tray(self):
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()


if __name__ == "__main__":
    if not ensure_single_instance():
        sys.exit(0)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = CryoMintUI()
    timer = handle_singleton_signal(window)
    if "--tray-only" not in sys.argv:
        window.request_access()
    exit_code = app.exec()
    window._cleanup_tray()
    sys.exit(exit_code)