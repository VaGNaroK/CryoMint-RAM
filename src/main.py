#!/usr/bin/env python3
"""
CryoMint UI - Versão 1.0.4
Thread Pool Assíncrono + Tema Dark Fixo + UX
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

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QTabWidget,
    QMessageBox
)
from PySide6.QtGui import QIcon, QAction, QFont, QFontDatabase
from PySide6.QtCore import Qt, QTimer, Signal, QRunnable, Slot, QObject, QThreadPool

# ===============================================
# VERSÃO DO SISTEMA
__version__ = "1.0.4"
# ===============================================

# --- CONSTANTES ---
BACKEND_PATH = "/opt/cryomint/src/cryo_core.py"
ASSETS_DIR = "/opt/cryomint/assets"
LOG_TAG = "CryoMint-UI"
SINGLETON_SOCKET = os.path.join(tempfile.gettempdir(), f"cryomint_{os.getuid()}.sock")

# ===============================================
# 1. WORKER ASSÍNCRONO PARA PYSIDE6
# ===============================================
class WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)

class BackendWorker(QRunnable):
    def __init__(self, action: str):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            logger.info(f"Executando operação backend async: {self.action}")
            cmd = ["pkexec", "/usr/bin/python3", BACKEND_PATH, self.action]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                self.signals.finished.emit(result.stdout.strip())
            else:
                self.signals.error.emit(f"Falha de privilégio ou backend ({result.returncode}):\n{result.stderr.strip()}")

        except subprocess.TimeoutExpired:
            self.signals.error.emit("TIMEOUT: O sistema demorou mais de 60 segundos para responder.")
        except Exception as e:
            self.signals.error.emit(f"ERRO CRÍTICO no processamento em background: {e}")

# ===============================================
# 2. SISTEMA DE LOG E SINGLETON (Proteções)
# ===============================================
def setup_logging(tag: str) -> logging.Logger:
    logger = logging.getLogger(tag)
    logger.setLevel(logging.DEBUG)
    if logger.handlers: return logger
    try:
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
        syslog_handler.setFormatter(logging.Formatter(f'{tag}: %(message)s'))
        logger.addHandler(syslog_handler)
    except: pass
    log_dir = os.path.expanduser("~/.local/share/cryomint/logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "ui.log"), encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    logger.addHandler(file_handler)
    return logger

logger = setup_logging(LOG_TAG)

def ensure_single_instance() -> bool:
    test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        test_sock.connect(SINGLETON_SOCKET)
        test_sock.sendall(b"SHOW")
        test_sock.close()
        return False
    except: pass
    if os.path.exists(SINGLETON_SOCKET): os.unlink(SINGLETON_SOCKET)
    try:
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(SINGLETON_SOCKET); server_sock.listen(1); server_sock.setblocking(False)
        global _singleton_socket; _singleton_socket = server_sock
        atexit.register(lambda: server_sock.close() or (os.path.exists(SINGLETON_SOCKET) and os.unlink(SINGLETON_SOCKET)))
        return True
    except: return False

def handle_singleton_signal(window) -> QTimer:
    def check_socket():
        sock = globals().get('_singleton_socket')
        if not sock: return
        try:
            ready, _, _ = select.select([sock], [], [], 0)
            if ready:
                conn, _ = sock.accept(); data = conn.recv(1024)
                if data == b"SHOW" and window:
                    window.showNormal(); window.raise_(); window.activateWindow()
                conn.close()
        except: pass
    timer = QTimer(window)
    timer.timeout.connect(check_socket)
    timer.start(500)
    return timer

# ===============================================
# 3. INTERFACE DE USUÁRIO
# ===============================================
class CryoMintUI(QMainWindow):
    def __init__(self):
        super().__init__()

        # ASSETS E ÍCONES
        self.assets_dir = ASSETS_DIR if os.path.isdir(ASSETS_DIR) else "assets"
        self.icon_frozen = QIcon.fromTheme("cryomint-close-symbolic", QIcon(os.path.join(self.assets_dir, "close.svg")))
        self.icon_unfrozen = QIcon.fromTheme("cryomint-open-symbolic", QIcon(os.path.join(self.assets_dir, "open.svg")))
        self.icon_main = QIcon.fromTheme("cryomint", QIcon(os.path.join(self.assets_dir, "icon.svg")))
        if self.icon_main.isNull(): self.icon_main = QIcon.fromTheme("system-run")
        self.setWindowIcon(self.icon_main)

        # FONTES E JANELA
        sys_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        self.is_frozen = self._check_real_status()
        self.setWindowTitle(f"❄️ CryoMint {__version__}")
        self.setFixedSize(450, 350)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ABA 1: CONTROLE
        self.tab_controle = QWidget()
        layout_controle = QVBoxLayout(self.tab_controle); layout_controle.setAlignment(Qt.AlignCenter)
        self.lbl_status = QLabel(); self.lbl_status.setFont(QFont(sys_font.family(), 18, QFont.Bold)); self.lbl_status.setAlignment(Qt.AlignCenter)
        
        self.btn_toggle = QPushButton()
        self.btn_toggle.setFixedSize(280, 50)
        self.btn_toggle.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.btn_toggle.clicked.connect(self.start_async_toggle)

        self.btn_reboot = QPushButton("🔄 Reiniciar Agora")
        self.btn_reboot.setFixedSize(280, 40)
        self.btn_reboot.setStyleSheet("background-color: #d35400; color: white; font-size: 14px; border: none; font-weight: bold;")
        self.btn_reboot.hide()
        self.btn_reboot.clicked.connect(self.reboot_system)

        self.lbl_info = QLabel("✅ Sistema operacional normal."); self.lbl_info.setAlignment(Qt.AlignCenter)
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        
        layout_controle.addSpacing(15); layout_controle.addWidget(self.lbl_status)
        layout_controle.addSpacing(25); layout_controle.addWidget(self.btn_toggle, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(10); layout_controle.addWidget(self.btn_reboot, alignment=Qt.AlignCenter)
        layout_controle.addWidget(self.lbl_info)

        # ABA 2: SOBRE
        self.tab_sobre = QWidget()
        layout_sobre = QVBoxLayout(self.tab_sobre); layout_sobre.setAlignment(Qt.AlignCenter)
        self.lbl_icon_sobre = QLabel(); self.lbl_icon_sobre.setAlignment(Qt.AlignCenter)
        self.lbl_icon_sobre.setPixmap(self.icon_main.pixmap(64, 64))
        lbl_title = QLabel("CryoMint"); lbl_title.setFont(QFont(sys_font.family(), 22, QFont.Bold)); lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_desc = QLabel("Sistema imutável para laboratórios.<br><b>Desenvolvedor:</b> VaGNaroK")
        self.lbl_desc.setAlignment(Qt.AlignCenter)
        self.lbl_desc.setStyleSheet("color: #aaaaaa; font-size: 13px; line-height: 1.5;")
        layout_sobre.addWidget(self.lbl_icon_sobre); layout_sobre.addWidget(lbl_title); layout_sobre.addSpacing(15); layout_sobre.addWidget(self.lbl_desc)

        self.tabs.addTab(self.tab_controle, "🛡️ Status"); self.tabs.addTab(self.tab_sobre, "ℹ️ Sobre")

        # TRAY
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip(f"❄️ CryoMint {__version__}")
        self._setup_tray_menu()
        self.tray_icon.show()

        # APLICAÇÃO DE TEMA DARK FIXO
        self.apply_dark_theme()
        self.update_ui_visuals()

        # Thread Pool
        self.threadpool = QThreadPool.globalInstance()

    def _setup_tray_menu(self):
        self.tray_menu = QMenu(self)
        self.tray_menu.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.tray_menu.setAttribute(Qt.WA_TranslucentBackground)
        act_show = QAction("🖥️ Abrir Painel", self); act_show.triggered.connect(self.request_access)
        act_exit = QAction("❌ Sair", self); act_exit.triggered.connect(QApplication.instance().quit)
        self.tray_menu.addAction(act_show); self.tray_menu.addSeparator(); self.tray_menu.addAction(act_exit)
        self.tray_icon.setContextMenu(self.tray_menu)

    def apply_dark_theme(self):
        """Fixa o tema Escuro para garantir a identidade visual em qualquer SO"""
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QTabWidget::pane { border: 1px solid #333333; background-color: #2b2b2b; border-radius: 5px; }
            QTabBar::tab { background-color: #333333; color: #aaaaaa; padding: 10px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #2b2b2b; color: #ffffff; }
            QLabel { color: #dddddd; }
            QPushButton { background-color: #3a3a3a; color: #ffffff; border: 1px solid #555555; border-radius: 5px; padding: 10px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:disabled { background-color: #222222; color: #555555; }
        """)
        self.tray_menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; border-radius: 12px; padding: 5px; }
            QMenu::item { padding: 8px 20px; border-radius: 6px; margin: 2px 0px; }
            QMenu::item:selected { background-color: #4a4a4a; color: #ffffff; }
            QMenu::separator { height: 1px; background-color: #444444; margin: 4px 10px; }
        """)

    def _check_real_status(self) -> bool:
        config = "/media/root-ro/etc/overlayroot.conf" if os.path.ismount("/media/root-ro") else "/etc/overlayroot.conf"
        try:
            with open(config, "r") as f: return any('overlayroot="tmpfs' in line for line in f)
        except: return False

    def request_access(self):
        if subprocess.run(["pkexec", "id"], capture_output=True).returncode == 0:
            self.is_frozen = self._check_real_status()
            self.update_ui_visuals(); self.showNormal(); self.raise_(); self.activateWindow()

    def update_ui_visuals(self):
        color = "#3498DB" if self.is_frozen else "#E74C3C"
        status = "CONGELADO" if self.is_frozen else "DESCONGELADO"
        self.lbl_status.setText(f"❄️ STATUS: {status}"); self.lbl_status.setStyleSheet(f"color: {color};")
        self.btn_toggle.setText("🔥 Descongelar" if self.is_frozen else "❄️ Congelar")
        self.tray_icon.setIcon(self.icon_frozen if self.is_frozen else self.icon_unfrozen)

    # --- FLUXO ASSÍNCRONO INTEGRADO ---
    def start_async_toggle(self):
        if not os.path.isfile(BACKEND_PATH):
            QMessageBox.critical(self, "Erro", f"Backend não encontrado: {BACKEND_PATH}")
            return
            
        self.btn_toggle.setEnabled(False)
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
        if "ERRO" in msg.upper():
            self._handle_failure(msg)
        else:
            self.is_frozen = not self.is_frozen
            self.update_ui_visuals()
            self.btn_toggle.setEnabled(True)
            self.btn_reboot.show()
            self.lbl_info.setText("⚠️ Reinicialização pendente para aplicar mudanças!")
            self.lbl_info.setStyleSheet("color: #E67E22; font-weight: bold; font-size: 12px;")

    @Slot(str)
    def _handle_failure(self, err: str):
        self.lbl_info.setStyleSheet("color: #888888; font-size: 11px;")
        self.lbl_info.setText("❌ A operação foi cancelada ou falhou.")
        QMessageBox.critical(self, "Falha na Operação", err)
        self.btn_toggle.setEnabled(True)

    def reboot_system(self): subprocess.run(["pkexec", "systemctl", "reboot"])
    
    def closeEvent(self, event): event.ignore(); self.hide()
    
    def _cleanup_tray(self):
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide(); self.tray_icon.deleteLater()

if __name__ == "__main__":
    if not ensure_single_instance(): sys.exit(0)
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    window = CryoMintUI(); timer = handle_singleton_signal(window)
    if "--tray-only" not in sys.argv: window.request_access()
    exit_code = app.exec()
    window._cleanup_tray()
    sys.exit(exit_code)