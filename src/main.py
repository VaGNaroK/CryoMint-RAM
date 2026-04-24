#!/usr/bin/env python3
"""
CryoMint UI - Interface Qt6 para controle de estado do sistema
Edição RAM com tmpfs + swap dedicada
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

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QTabWidget,
    QMessageBox
)
from PySide6.QtGui import QIcon, QAction, QFont, QFontDatabase
from PySide6.QtCore import Qt, QTimer

# --- CONSTANTES ---
BACKEND_PATH = "/opt/cryomint/src/cryo_core.py"
ASSETS_DIR = "/opt/cryomint/assets"
LOG_TAG = "CryoMint-UI"
SINGLETON_SOCKET = os.path.join(tempfile.gettempdir(), f"cryomint_{os.getuid()}.sock")


def setup_logging(tag: str) -> logging.Logger:
    """Logging dual: arquivo local + syslog."""
    logger = logging.getLogger(tag)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        return logger
    
    try:
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log')
        syslog_handler.setLevel(logging.INFO)
        syslog_handler.setFormatter(logging.Formatter(f'{tag}: %(message)s'))
        logger.addHandler(syslog_handler)
    except Exception:
        pass
    
    log_dir = os.path.expanduser("~/.local/share/cryomint/logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(log_dir, f"{tag.lower().replace('-', '_')}.log"),
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    ))
    logger.addHandler(file_handler)
    
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    logger.addHandler(console)
    
    return logger


logger = setup_logging(LOG_TAG)


def ensure_single_instance() -> bool:
    """Garante singleton via socket Unix."""
    test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        test_sock.settimeout(1.0)
        test_sock.connect(SINGLETON_SOCKET)
        test_sock.sendall(b"SHOW")
        test_sock.close()
        logger.info("Outra instância detectada. Enviando sinal SHOW.")
        return False
    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
        pass
    finally:
        test_sock.close()
    
    if os.path.exists(SINGLETON_SOCKET):
        try:
            os.unlink(SINGLETON_SOCKET)
        except OSError:
            pass
    
    try:
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(SINGLETON_SOCKET)
        server_sock.listen(1)
        server_sock.setblocking(False)
        
        global _singleton_socket
        _singleton_socket = server_sock
        atexit.register(lambda: cleanup_singleton(server_sock))
        logger.info("Singleton lock adquirido.")
        return True
    except OSError as e:
        logger.error(f"Falha ao criar socket singleton: {e}")
        return False


def cleanup_singleton(sock: socket.socket) -> None:
    try:
        sock.close()
    except Exception:
        pass
    try:
        if os.path.exists(SINGLETON_SOCKET):
            os.unlink(SINGLETON_SOCKET)
    except Exception:
        pass


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
                    logger.info("Sinal SHOW recebido.")
                conn.close()
        except (BlockingIOError, OSError):
            pass
        except Exception as e:
            logger.warning(f"Erro no singleton listener: {e}")
    
    timer = QTimer(window)
    timer.timeout.connect(check_socket)
    timer.start(500)
    return timer


class CryoMintUI(QMainWindow):
    def __init__(self):
        super().__init__()

        # Assets
        dev_assets = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets"
        )
        self.assets_dir = ASSETS_DIR if os.path.isdir(ASSETS_DIR) else dev_assets

        # Ícones (Fallbacks simples se não existirem)
        close_path = os.path.join(self.assets_dir, "close.svg")
        open_path = os.path.join(self.assets_dir, "open.svg")
        main_path = os.path.join(self.assets_dir, "icon.svg")

        self.icon_frozen = QIcon.fromTheme(
            "cryomint-close-symbolic",
            QIcon(close_path) if os.path.exists(close_path) else QIcon()
        )
        self.icon_unfrozen = QIcon.fromTheme(
            "cryomint-open-symbolic",
            QIcon(open_path) if os.path.exists(open_path) else QIcon()
        )
        self.icon_main = QIcon.fromTheme(
            "cryomint",
            QIcon(main_path) if os.path.exists(main_path) else QIcon()
        )
        
        # Se nenhum ícone customizado existir, usa um padrão do sistema
        if self.icon_main.isNull():
            self.icon_main = QIcon.fromTheme("system-run")

        self.setWindowIcon(self.icon_main)

        # Fonte do sistema
        system_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        self.title_font = QFont(system_font.family(), 22, QFont.Bold)
        self.status_font = QFont(system_font.family(), 18, QFont.Bold)

        # Estado
        self.is_frozen = self._check_real_status()

        self.setWindowTitle("❄️ CryoMint 1.0.1")
        self.setFixedSize(450, 350)

        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QTabWidget::pane { border: 1px solid #333333; background-color: #2b2b2b; border-radius: 5px; }
            QTabBar::tab { background-color: #333333; color: #aaaaaa; padding: 10px 20px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-weight: bold; }
            QTabBar::tab:selected { background-color: #2b2b2b; color: #ffffff; }
            QLabel { color: #dddddd; }
            QPushButton { background-color: #3a3a3a; color: #ffffff; border: 1px solid #555555; border-radius: 5px; padding: 10px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a3a; }
            QPushButton:disabled { background-color: #222222; color: #555555; }
        """)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ABA 1: CONTROLE
        self.tab_controle = QWidget()
        layout_controle = QVBoxLayout(self.tab_controle)
        layout_controle.setAlignment(Qt.AlignCenter)

        self.lbl_status = QLabel()
        self.lbl_status.setFont(self.status_font)
        self.lbl_status.setAlignment(Qt.AlignCenter)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setFixedSize(280, 50)
        self.btn_toggle.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.btn_toggle.clicked.connect(self.toggle_status)

        self.btn_reboot = QPushButton("🔄 Reiniciar Computador Agora")
        self.btn_reboot.setFixedSize(280, 40)
        self.btn_reboot.setStyleSheet("background-color: #d35400; color: white; font-size: 14px; border: none;")
        self.btn_reboot.clicked.connect(self.reboot_system)
        self.btn_reboot.hide()

        self.lbl_info = QLabel("✅ O sistema está operando normalmente.")
        self.lbl_info.setStyleSheet("color: #888888; font-size: 12px;")
        self.lbl_info.setAlignment(Qt.AlignCenter)

        layout_controle.addSpacing(15)
        layout_controle.addWidget(self.lbl_status)
        layout_controle.addSpacing(25)
        layout_controle.addWidget(self.btn_toggle, alignment=Qt.AlignCenter)
        layout_controle.addSpacing(10)
        layout_controle.addWidget(self.btn_reboot, alignment=Qt.AlignCenter)
        layout_controle.addWidget(self.lbl_info)

        # ABA 2: SOBRE
        self.tab_sobre = QWidget()
        layout_sobre = QVBoxLayout(self.tab_sobre)
        layout_sobre.setAlignment(Qt.AlignCenter)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(self.icon_main.pixmap(64, 64))
        lbl_icon.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel("CryoMint")
        lbl_title.setFont(self.title_font)
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #ffffff; margin-bottom: 0px;")

        self.version_str = self._detect_version()
        lbl_versao = QLabel(f"Versão {self.version_str}")
        lbl_versao.setAlignment(Qt.AlignCenter)
        lbl_versao.setStyleSheet("color: #3498DB; font-weight: bold; font-size: 14px; margin-top: 0px;")

        lbl_desc = QLabel(
            "Sistema imutável de proteção de estado.<br>"
            "Projetado para garantir a integridade dos<br>"
            "computadores do laboratório.<br><br>"
            "<b>Desenvolvedor:</b> VaGNaroK<br>"
            "<b>Tecnologias:</b> Python, PySide6 e OverlayFS"
        )
        lbl_desc.setAlignment(Qt.AlignCenter)
        lbl_desc.setStyleSheet("color: #aaaaaa; font-size: 13px; line-height: 1.5;")

        layout_sobre.addWidget(lbl_icon)
        layout_sobre.addWidget(lbl_title)
        layout_sobre.addWidget(lbl_versao)
        layout_sobre.addSpacing(15)
        layout_sobre.addWidget(lbl_desc)

        self.tabs.addTab(self.tab_controle, "🛡️ Status")
        self.tabs.addTab(self.tab_sobre, "ℹ️ Sobre")

        # Tray
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip(f"❄️ CryoMint v{self.version_str}")
        self._setup_tray_menu()
        
        if not self.tray_icon.isVisible():
            self.tray_icon.show()
            logger.info("Tray icon inicializado.")

        self._tray_health_timer = QTimer(self)
        self._tray_health_timer.timeout.connect(self._ensure_tray_visible)
        self._tray_health_timer.start(10000)

        atexit.register(self._cleanup_tray)
        self.update_ui_visuals()

    def _detect_version(self) -> str:
        try:
            result = subprocess.run(
                ["dpkg-query", "-W", "-f=${Version}", "cryomint"],
                capture_output=True, text=True, check=False, timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return "1.0.1-dev"

    def _setup_tray_menu(self) -> None:
        tray_menu = QMenu(self)
        tray_menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        tray_menu.setStyleSheet("""
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #444444; border-radius: 12px; padding: 5px; }
            QMenu::item { padding: 8px 20px; border-radius: 6px; margin: 2px 0px; }
            QMenu::item:selected { background-color: #3a3a3a; color: #ffffff; }
            QMenu::separator { height: 1px; background-color: #444444; margin: 4px 10px; }
        """)

        action_show = QAction("🖥️ Abrir Painel", self)
        action_show.triggered.connect(self.request_access)

        action_exit = QAction("❌ Sair", self)
        action_exit.triggered.connect(QApplication.instance().quit)

        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        tray_menu.addAction(action_exit)

        self.tray_icon.setContextMenu(tray_menu)

    def _ensure_tray_visible(self) -> None:
        if not self.tray_icon.isVisible():
            logger.warning("Tray icon não visível, recuperando...")
            self.tray_icon.hide()
            self.tray_icon.show()

    def _cleanup_tray(self) -> None:
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.hide()
            self.tray_icon.deleteLater()

    def _check_real_status(self) -> bool:
        if os.path.ismount("/media/root-ro"):
            config_file = "/media/root-ro/etc/overlayroot.conf"
        else:
            config_file = "/etc/overlayroot.conf"

        if not os.path.exists(config_file):
            return False

        try:
            with open(config_file, "r") as file:
                for line in file:
                    clean = line.strip().replace(" ", "").replace("'", '"')
                    if clean.startswith('overlayroot="tmpfs'):
                        return True
        except Exception as e:
            logger.error(f"Erro lendo status: {e}")
            return False
        return False

    def request_access(self):
        try:
            res = subprocess.run(
                ["pkexec", "id"],
                capture_output=True, text=True, timeout=30
            )

            if res.returncode == 0:
                logger.info("Autenticação pkexec bem-sucedida")
                self.is_frozen = self._check_real_status()
                self.update_ui_visuals()
                self.showNormal()
                self.raise_()
                self.activateWindow()
            else:
                stderr_msg = res.stderr.strip() if res.stderr else "Autenticação cancelada"
                logger.warning(f"pkexec falhou: {stderr_msg}")
                if "not authorized" in stderr_msg.lower():
                    QMessageBox.warning(self, "Acesso Negado", "Privilégios administrativos negados.")
        except subprocess.TimeoutExpired:
            logger.error("pkexec timeout")
            QMessageBox.critical(self, "Timeout", "Autenticação excedeu o tempo limite.")
        except Exception as e:
            logger.error(f"Erro no pkexec: {e}")
            QMessageBox.critical(self, "Erro", f"Falha: {e}")

    def update_ui_visuals(self):
        if self.is_frozen:
            self.lbl_status.setText("❄️ STATUS: CONGELADO")
            self.lbl_status.setStyleSheet("color: #3498DB;")
            self.btn_toggle.setText("🔥 Descongelar Sistema")
            self.tray_icon.setIcon(self.icon_frozen)
            self.tray_icon.setToolTip(f"❄️ CryoMint v{self.version_str} [CONGELADO]")
        else:
            self.lbl_status.setText("🔥 STATUS: DESCONGELADO")
            self.lbl_status.setStyleSheet("color: #E74C3C;")
            self.btn_toggle.setText("❄️ Congelar Sistema")
            self.tray_icon.setIcon(self.icon_unfrozen)
            self.tray_icon.setToolTip(f"❄️ CryoMint v{self.version_str} [DESCONGELADO]")

    def toggle_status(self):
        if not os.path.isfile(BACKEND_PATH):
            self.lbl_info.setText(f"❌ Backend não encontrado: {BACKEND_PATH}")
            self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
            logger.error(f"Backend ausente: {BACKEND_PATH}")
            return

        backend_real = os.path.realpath(BACKEND_PATH)
        if not backend_real.startswith("/opt/cryomint/"):
            self.lbl_info.setText("❌ Backend em local não autorizado!")
            self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
            logger.error(f"Path traversal: {backend_real}")
            return

        self.btn_toggle.setEnabled(False)
        self.btn_toggle.setText("⏳ Aplicando...")
        QApplication.processEvents()

        comando_backend = "thaw" if self.is_frozen else "freeze"

        try:
            resultado = subprocess.run(
                ["pkexec", "/usr/bin/python3", BACKEND_PATH, comando_backend],
                capture_output=True, text=True, timeout=60
            )

            if resultado.returncode == 0:
                self.is_frozen = not self.is_frozen
                self.btn_reboot.show()
                self.lbl_info.setText("⚠️ Reinicialização pendente!")
                self.lbl_info.setStyleSheet("color: #E67E22; font-weight: bold; font-size: 12px;")
                logger.info(f"Toggle OK: {'FREEZE' if self.is_frozen else 'THAW'}")
            else:
                erro_txt = resultado.stderr.strip() or resultado.stdout.strip() or "Erro desconhecido"
                self.lbl_info.setText(f"❌ Falha: {erro_txt[:80]}")
                self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
                logger.error(f"Backend falhou: {erro_txt}")

        except subprocess.TimeoutExpired:
            self.lbl_info.setText("❌ Timeout")
            self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
            logger.error("Timeout no backend")
        except Exception as e:
            self.lbl_info.setText(f"❌ Erro: {e}")
            self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
            logger.error(f"Exceção no toggle: {e}")

        self.btn_toggle.setEnabled(True)
        self.update_ui_visuals()

    def reboot_system(self):
        try:
            res = subprocess.run(
                ["pkexec", "systemctl", "reboot"],
                capture_output=True, text=True, timeout=15
            )
            if res.returncode != 0:
                erro = res.stderr.strip() or "Falha ao reiniciar"
                QMessageBox.critical(self, "Erro", erro)
                logger.error(f"Reboot falhou: {erro}")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha: {e}")
            logger.error(f"Exceção no reboot: {e}")

    def closeEvent(self, event):
        event.ignore()
        self.hide()


if __name__ == "__main__":
    if not ensure_single_instance():
        print("CryoMint já está rodando.")
        sys.exit(0)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    system_font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
    app.setFont(system_font)

    window = CryoMintUI()
    singleton_timer = handle_singleton_signal(window)

    if "--tray-only" not in sys.argv:
        window.request_access()

    exit_code = app.exec()
    cleanup_singleton(globals().get('_singleton_socket'))
    window._cleanup_tray()
    sys.exit(exit_code)