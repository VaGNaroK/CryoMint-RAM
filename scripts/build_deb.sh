#!/bin/bash
set -euo pipefail

echo "============================================"
echo "            CryoMint Build Script (v2)      "
echo "============================================"

# =============================================================
# PASSO 1: DETECÇÃO DE VERSÃO
# =============================================================
VERSION=""
# Agora o 'if' também procura em todos os arquivos .py da pasta src
if grep -q '__version__' src/*.py 2>/dev/null; then
    VERSION=$(grep -h -oP "__version__\s*=\s*[\"']\K[^\"']+" src/*.py | head -n 1)
fi

[ -z "$VERSION" ] && VERSION="1.0.1"

echo "📦 Versão Detectada (via __version__): $VERSION"
PKG_NAME="cryomint_${VERSION}_amd64"
echo "📦 Pacote de saída: ${PKG_NAME}.deb"

# Limpeza anterior
rm -rf "${PKG_NAME}"

# =============================================================
# PASSO 2: ESTRUTURA DE DIRETÓRIOS
# =============================================================
mkdir -p "${PKG_NAME}/DEBIAN"
mkdir -p "${PKG_NAME}/opt/cryomint/src"
mkdir -p "${PKG_NAME}/opt/cryomint/assets"
mkdir -p "${PKG_NAME}/usr/share/applications"
mkdir -p "${PKG_NAME}/usr/bin"
mkdir -p "${PKG_NAME}/etc/xdg/autostart"
mkdir -p "${PKG_NAME}/usr/share/polkit-1/actions"
mkdir -p "${PKG_NAME}/lib/systemd/system"
mkdir -p "${PKG_NAME}/var/log/cryomint"

# =============================================================
# PASSO 3: COPIAR ARQUIVOS E CONFIGURAR PERMISSÕES
# =============================================================
cp src/main.py "${PKG_NAME}/opt/cryomint/src/"
cp src/cryo_core.py "${PKG_NAME}/opt/cryomint/src/"
cp src/version.py "${PKG_NAME}/opt/cryomint/src/"
cp services/org.cryomint.policy "${PKG_NAME}/usr/share/polkit-1/actions/"
cp services/cryomint-maintenance.service "${PKG_NAME}/lib/systemd/system/"

[ -d "assets" ] && cp -a assets/* "${PKG_NAME}/opt/cryomint/assets/" 2>/dev/null || true

chmod 755 "${PKG_NAME}/opt/cryomint/src"
chmod 755 "${PKG_NAME}/opt/cryomint/src/cryo_core.py"
chmod 644 "${PKG_NAME}/opt/cryomint/src/main.py"
chmod 644 "${PKG_NAME}/opt/cryomint/src/version.py"
chmod 644 "${PKG_NAME}/usr/share/polkit-1/actions/org.cryomint.policy"
chmod 644 "${PKG_NAME}/lib/systemd/system/cryomint-maintenance.service"

echo "✅ Arquivos copiados e permissões definidas."

# =============================================================
# PASSO 4: DEBIAN CONTROL FILE
# =============================================================
cat <<EOF > "${PKG_NAME}/DEBIAN/control"
Package: cryomint
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, policykit-1, overlayroot, libxcb-cursor0, mount
Maintainer: VaGNaroK
Description: CryoMint RAM Edition - Congelamento de estado usando tmpfs e Swap dedicada.
 Sistema imutável para proteção de estado de laboratórios.
EOF

echo "✅ Control file criado."

# =============================================================
# PASSO 5: POSTINST SCRIPT (CRÍTICO)
# =============================================================
cat <<'EOF' > "${PKG_NAME}/DEBIAN/postinst"
#!/bin/bash
set -e

echo "⚙️ Configurando CryoMint..."
INSTALL_DIR="/opt/cryomint"
VENV_PATH="$INSTALL_DIR/venv"

# 1. Setup do Ambiente Virtual (Venv)
if [ ! -d "$VENV_PATH" ]; then
    echo "-> Criando ambiente virtual Python em $VENV_PATH..."
    python3 -m venv "$VENV_PATH" || { echo "ERRO: Falha ao criar Venv. Verifique o python3."; exit 1; }
fi

# 2. Instalação de Dependências
echo "-> Instalando dependências Python (PySide6 e outras)..."
pip_cmd="$VENV_PATH/bin/pip"

DEPENDENCIES="PySide6" 

if ! $pip_cmd install --no-cache-dir $DEPENDENCIES; then
    echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    echo "ERRO FATAL DE DEPENDÊNCIA PYTHON:" >&2
    echo "Falha ao instalar um ou mais pacotes Python necessários." >&2
    echo "Por favor, verifique os pacotes listados em 'DEPENDENCIES' no script build_deb.sh." >&2
    exit 1
fi

# 3. Permissões de Código
chmod 755 /opt/cryomint/src/cryo_core.py
chmod 644 /opt/cryomint/src/main.py
chmod 644 /opt/cryomint/src/version.py

# 4. Diretórios do Sistema e Locks
echo "-> Configurando diretórios de lock e log..."
mkdir -p /run/lock
chown root:root /run/lock
chmod 1777 /run/lock

mkdir -p /var/log/cryomint
chmod 755 /var/log/cryomint

# 5. Udev Rules
echo "-> Verificando regras Udev..."
ROOT_UUID=$(findmnt / -n -o UUID 2>/dev/null || true)
if [ -n "$ROOT_UUID" ]; then
    mkdir -p /etc/udev/rules.d/
    cat <<UDEV > /etc/udev/rules.d/99-hide-cryomint.rules
ACTION=="add|change", ENV{ID_FS_UUID}=="$ROOT_UUID", ENV{UDISKS_IGNORE}="1"
UDEV
    udevadm control --reload-rules 2>/dev/null || true
fi

# 6. Habilitar o Serviço Systemd de Manutenção
echo "-> Configurando serviço systemd de boot..."
systemctl daemon-reload 2>/dev/null || true
systemctl enable cryomint-maintenance.service 2>/dev/null || true

echo "✅ CryoMint v$(dpkg-query -W -f='${Version}' cryomint) instalado com sucesso."
EOF
chmod 755 "${PKG_NAME}/DEBIAN/postinst"

# =============================================================
# PASSO 6: POSTRM SCRIPT (Limpeza)
# =============================================================
cat <<'EOF' > "${PKG_NAME}/DEBIAN/postrm"
#!/bin/bash
set -e

if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    echo "🧹 Removendo CryoMint..."
    systemctl disable cryomint-maintenance.service 2>/dev/null || true
    rm -f /lib/systemd/system/cryomint-maintenance.service 2>/dev/null || true
    systemctl daemon-reload 2>/dev/null || true
    rm -rf /opt/cryomint 2>/dev/null || true
    rm -f /etc/udev/rules.d/99-hide-cryomint.rules 2>/dev/null || true
    rm -f /etc/profile.d/cryomint-autostart.sh 2>/dev/null || true
    rm -f /etc/xdg/autostart/cryomint.desktop 2>/dev/null || true
    udevadm control --reload-rules 2>/dev/null || true
    echo "✅ Limpeza concluída."
fi
exit 0
EOF
chmod 755 "${PKG_NAME}/DEBIAN/postrm"

# =============================================================
# PASSO 7: EXECUTÁVEL E SCRIPTS DE ENTORNE
# =============================================================
cat <<'EOF' > "${PKG_NAME}/usr/bin/cryomint"
#!/bin/bash
set -e

# Tentativa de ajuste de tema do Nemo
gsettings set org.nemo.desktop volumes-visible false 2>/dev/null || true

exec /opt/cryomint/venv/bin/python /opt/cryomint/src/main.py "$@"
EOF
chmod 755 "${PKG_NAME}/usr/bin/cryomint"

# Desktop entry
cat <<EOF > "${PKG_NAME}/usr/share/applications/cryomint.desktop"
[Desktop Entry]
Name=CryoMint
Exec=cryomint
Icon=/opt/cryomint/assets/icon.svg
Type=Application
Categories=System;Security;
StartupNotify=true
StartupWMClass=CryoMint
EOF

# Autostart Desktop entry (inicia oculto na bandeja)
cat <<EOF > "${PKG_NAME}/etc/xdg/autostart/cryomint.desktop"
[Desktop Entry]
Name=CryoMint Tray
Comment=Iniciar o CryoMint na bandeja do sistema
Exec=cryomint --tray-only
Icon=/opt/cryomint/assets/icon.svg
Type=Application
Categories=System;Security;
StartupNotify=false
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

# =============================================================
# PASSO FINAL: BUILD E OUTPUT
# =============================================================
echo ""
echo "--------------------------------------------"
echo "🛠️ Iniciando a construção do pacote DEB..."
dpkg-deb --build "${PKG_NAME}"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ SUCESSO: ${PKG_NAME}.deb gerado!"
else
    echo ""
    echo "❌ FALHA FATAL na criação do pacote DEB. Verifique os logs acima."
fi