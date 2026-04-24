#!/bin/bash
set -euo pipefail

echo "🔍 Detectando versão..."

VERSION=""
if grep -q '__version__' src/main.py 2>/dev/null; then
    VERSION=$(grep -oP '__version__\s*=\s*["'\'']\K[0-9]+\.[0-9]+\.[0-9]+' src/main.py | head -n 1)
fi
if [ -z "$VERSION" ]; then
    VERSION=$(perl -CSD -ne 'print $1 if /CryoMint\s+v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)/' src/main.py | head -n 1)
fi
[ -z "$VERSION" ] && VERSION="1.0.1"
VERSION=$(echo "$VERSION" | sed 's/[^0-9.]//g')

echo "📦 Versão: $VERSION"
PKG_NAME="cryomint_${VERSION}_amd64"
echo "📦 Pacote: ${PKG_NAME}.deb"

rm -rf "${PKG_NAME}"

# Estrutura
mkdir -p "${PKG_NAME}/DEBIAN"
mkdir -p "${PKG_NAME}/opt/cryomint/src"
mkdir -p "${PKG_NAME}/opt/cryomint/assets"
mkdir -p "${PKG_NAME}/usr/share/applications"
mkdir -p "${PKG_NAME}/usr/bin"
mkdir -p "${PKG_NAME}/etc/profile.d"
mkdir -p "${PKG_NAME}/etc/systemd/user"
mkdir -p "${PKG_NAME}/var/log/cryomint"

# Fontes e assets
cp src/main.py "${PKG_NAME}/opt/cryomint/src/"
cp src/cryo_core.py "${PKG_NAME}/opt/cryomint/src/"
[ -d "assets" ] && cp -a assets/* "${PKG_NAME}/opt/cryomint/assets/" 2>/dev/null || true

chmod 755 "${PKG_NAME}/opt/cryomint/src"
chmod 644 "${PKG_NAME}/opt/cryomint/src/"*.py

# Control
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

# Postinst
cat <<'EOF' > "${PKG_NAME}/DEBIAN/postinst"
#!/bin/bash
set -e

echo "⚙️ Configurando CryoMint..."

# Venv isolado
python3 -m venv --system-site-packages /opt/cryomint/venv
/opt/cryomint/venv/bin/pip install --no-cache-dir PySide6

# Permissões
chmod 755 /opt/cryomint/src/cryo_core.py
chmod 644 /opt/cryomint/src/main.py

# Diretórios de lock e log
mkdir -p /run/lock
chmod 1777 /run/lock
mkdir -p /var/log/cryomint
chmod 755 /var/log/cryomint

# Udev rules
ROOT_UUID=$(findmnt / -n -o UUID 2>/dev/null || true)
if [ -n "$ROOT_UUID" ]; then
    mkdir -p /etc/udev/rules.d/
    cat <<UDEV > /etc/udev/rules.d/99-hide-cryomint.rules
ACTION=="add|change", ENV{ID_FS_UUID}=="$ROOT_UUID", ENV{UDISKS_IGNORE}="1"
UDEV
    udevadm control --reload-rules 2>/dev/null || true
fi

echo "✅ CryoMint v$(dpkg-query -W -f='${Version}' cryomint) instalado."
EOF
chmod 755 "${PKG_NAME}/DEBIAN/postinst"

# Postrm
cat <<'EOF' > "${PKG_NAME}/DEBIAN/postrm"
#!/bin/bash
set -e

if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    echo "🧹 Removendo CryoMint..."
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

# Executável
cat <<'EOF' > "${PKG_NAME}/usr/bin/cryomint"
#!/bin/bash
set -e
gsettings set org.nemo.desktop volumes-visible false 2>/dev/null || true
exec /opt/cryomint/venv/bin/python /opt/cryomint/src/main.py "$@"
EOF
chmod 755 "${PKG_NAME}/usr/bin/cryomint"

# Desktop entry (apenas menu, NÃO autostart)
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

# Systemd user service e timer
cat <<EOF > "${PKG_NAME}/etc/systemd/user/cryomint-tray.service"
[Unit]
Description=CryoMint System Tray
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/cryomint --tray-only
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

cat <<EOF > "${PKG_NAME}/etc/systemd/user/cryomint-tray.timer"
[Unit]
Description=Delay seguro para CryoMint

[Timer]
OnBootSec=30
OnUnitActiveSec=0
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF

# --- ATIVAÇÃO AUTOMÁTICA PARA TODOS OS USUÁRIOS ---
cat <<'EOF' > "${PKG_NAME}/etc/profile.d/cryomint-autostart.sh"
#!/bin/bash
# Ativa timer CryoMint para todo usuário humano no login gráfico

if [ "$(id -u)" -ge 1000 ] && [ -n "${DISPLAY:-}" ]; then
    TIMER_LINK="$HOME/.config/systemd/user/default.target.wants/cryomint-tray.timer"
    TIMER_SRC="/etc/systemd/user/cryomint-tray.timer"
    
    if [ ! -L "$TIMER_LINK" ] && [ -f "$TIMER_SRC" ]; then
        mkdir -p "$(dirname "$TIMER_LINK")"
        ln -sf "$TIMER_SRC" "$TIMER_LINK"
        systemctl --user daemon-reload >/dev/null 2>&1 || true
        systemctl --user start cryomint-tray.timer >/dev/null 2>&1 || true
    fi
fi
EOF
chmod 644 "${PKG_NAME}/etc/profile.d/cryomint-autostart.sh"

# Build
echo "🛠️ Construindo..."
dpkg-deb --build "${PKG_NAME}"
echo "✅ ${PKG_NAME}.deb gerado!"
echo ""
echo "📖 LOGS:"
echo "   UI:  cat ~/.local/share/cryomint/logs/cryomint_ui.log"
echo "   Core: sudo cat /var/log/cryomint/core.log"
echo "   Ou:  sudo journalctl -t CryoMint-UI -t CryoMint-Core -f"