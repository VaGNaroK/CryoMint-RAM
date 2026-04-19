import sys
import os
import subprocess
from PySide6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton,
                               QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QTabWidget)
from PySide6.QtGui import QIcon, QAction, QFont, QPixmap
from PySide6.QtCore import Qt

class CryoMintUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Localização da pasta de ativos local (usado como Fallback para desenvolvimento)
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        
        # MAGIA DO LINUX: Tenta carregar o ícone Symbolic nativo do sistema. 
        # Se falhar, usa o arquivo local da pasta assets.
        self.icon_frozen = QIcon.fromTheme("cryomint-close-symbolic", QIcon(os.path.join(self.assets_dir, "close.svg")))
        self.icon_unfrozen = QIcon.fromTheme("cryomint-open-symbolic", QIcon(os.path.join(self.assets_dir, "open.svg")))
        self.icon_main = QIcon.fromTheme("cryomint", QIcon(os.path.join(self.assets_dir, "icon.svg")))
        
        # Define o ícone da janela principal
        self.setWindowIcon(self.icon_main)
        
        self.is_frozen = self.check_real_status() 

        self.setWindowTitle("❄️ CryoMint v0.1.13")
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

        # === ABA 1: CONTROLE ===
        self.tab_controle = QWidget()
        layout_controle = QVBoxLayout(self.tab_controle)
        layout_controle.setAlignment(Qt.AlignCenter)

        self.lbl_status = QLabel()
        self.lbl_status.setFont(QFont("Arial", 18, QFont.Bold))
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

        # === ABA 2: SOBRE ===
        self.tab_sobre = QWidget()
        layout_sobre = QVBoxLayout(self.tab_sobre)
        layout_sobre.setAlignment(Qt.AlignCenter)
        
        lbl_icon = QLabel()
        lbl_icon.setPixmap(self.icon_main.pixmap(64, 64))
        lbl_icon.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel("CryoMint")
        lbl_title.setFont(QFont("Arial", 22, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        lbl_title.setStyleSheet("color: #ffffff; margin-bottom: 0px;")
        
        lbl_versao = QLabel("Versão 0.1.13")
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

        # --- Tray System ---
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("❄️ CryoMint")

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
        self.tray_icon.show()
        self.update_ui_visuals()

    def check_real_status(self):
        if os.path.ismount("/media/root-ro"):
            config_file = "/media/root-ro/etc/overlayroot.conf"
        else:
            config_file = "/etc/overlayroot.conf"
            
        if not os.path.exists(config_file): return False
            
        try:
            with open(config_file, "r") as file:
                for line in file:
                    clean = line.strip().replace(" ", "").replace("'", '"')
                    if clean.startswith('overlayroot="tmpfs'): 
                        return True
        except: return False
        return False

    def request_access(self):
        try:
            res = subprocess.run(["pkexec", "id"], capture_output=True)
            if res.returncode == 0:
                self.is_frozen = self.check_real_status()
                self.update_ui_visuals()
                self.showNormal()
        except: pass

    def update_ui_visuals(self):
        if self.is_frozen:
            self.lbl_status.setText("❄️ STATUS: CONGELADO")
            self.lbl_status.setStyleSheet("color: #3498DB;") 
            self.btn_toggle.setText("🔥 Descongelar Sistema")
            self.tray_icon.setIcon(self.icon_frozen)
        else:
            self.lbl_status.setText("🔥 STATUS: DESCONGELADO")
            self.lbl_status.setStyleSheet("color: #E74C3C;") 
            self.btn_toggle.setText("❄️ Congelar Sistema")
            self.tray_icon.setIcon(self.icon_unfrozen)

    def toggle_status(self):
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.setText("⏳ Aplicando...")
        QApplication.processEvents()

        comando_backend = "thaw" if self.is_frozen else "freeze"
        diretorio_atual = os.path.dirname(os.path.abspath(__file__))
        caminho_backend = os.path.join(diretorio_atual, "cryo_core.py")
        
        try:
            resultado = subprocess.run(
                ["pkexec", "/usr/bin/python3", caminho_backend, comando_backend],
                capture_output=True, text=True
            )
            
            if resultado.returncode == 0:
                self.is_frozen = not self.is_frozen
                self.btn_reboot.show()
                self.lbl_info.setText("⚠️ Reinicialização pendente para aplicar mudanças!")
                self.lbl_info.setStyleSheet("color: #E67E22; font-weight: bold; font-size: 12px;")
            else:
                erro_txt = resultado.stderr.strip() or resultado.stdout.strip()
                self.lbl_info.setText(f"❌ Falha interna: {erro_txt}")
                self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
        except Exception as e:
            self.lbl_info.setText(f"❌ Erro de execução: {e}")
            self.lbl_info.setStyleSheet("color: #E74C3C; font-weight: bold; font-size: 11px;")
        
        self.btn_toggle.setEnabled(True)
        self.update_ui_visuals()

    def reboot_system(self):
        subprocess.run(["pkexec", "systemctl", "reboot"])

    def closeEvent(self, event):
        event.ignore()
        self.hide()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False) 
    window = CryoMintUI()
    if "--tray-only" not in sys.argv:
        window.request_access()
    sys.exit(app.exec())