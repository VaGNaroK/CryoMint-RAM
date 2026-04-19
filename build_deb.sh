#!/bin/bash
set -e

echo "🔍 Analisando código fonte para descobrir a versão..."
VERSION=$(grep -oP 'CryoMint v\K[0-9\.]+' src/main.py | head -n 1)
[ -z "$VERSION" ] && VERSION="1.0"

PKG_NAME="cryomint_${VERSION}_amd64"
echo "📦 Preparando para criar o pacote: ${PKG_NAME}.deb"

rm -rf ${PKG_NAME}

# 1. Estrutura
mkdir -p ${PKG_NAME}/DEBIAN
mkdir -p ${PKG_NAME}/opt/cryomint/src
mkdir -p ${PKG_NAME}/usr/share/applications
mkdir -p ${PKG_NAME}/usr/bin
mkdir -p ${PKG_NAME}/etc/xdg/autostart

# 2. Copiar fontes e Ativos SVG
echo "📋 Copiando arquivos fonte..."
cp src/main.py ${PKG_NAME}/opt/cryomint/src/
cp src/cryo_core.py ${PKG_NAME}/opt/cryomint/src/

if [ -d "assets" ]; then
    echo "🎨 Incluindo ativos SVG..."
    cp -a assets ${PKG_NAME}/opt/cryomint/
fi

# 3. Control
cat <<EOF > ${PKG_NAME}/DEBIAN/control
Package: cryomint
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: amd64
Depends: python3, python3-venv, policykit-1, overlayroot, libxcb-cursor0
Maintainer: VaGNaroK
Description: CryoMint RAM Edition - Congelamento de estado usando tmpfs e Swap dedicada.
EOF

# 4. Postinst (Instalação Limpa)
cat <<EOF > ${PKG_NAME}/DEBIAN/postinst
#!/bin/bash
set -e
echo "⚙️ Configurando CryoMint RAM Edition..."

python3 -m venv --system-site-packages /opt/cryomint/venv
/opt/cryomint/venv/bin/pip install --no-cache-dir PySide6
chmod +x /opt/cryomint/src/cryo_core.py

# Camuflagem Segura do Nemo (Udev Rules)
ROOT_UUID=\$(findmnt / -n -o UUID)
if [ -n "\$ROOT_UUID" ]; then
    mkdir -p /etc/udev/rules.d/
    cat <<UDEV > /etc/udev/rules.d/99-hide-cryomint.rules
ACTION=="add|change", ENV{ID_FS_UUID}=="\$ROOT_UUID", ENV{UDISKS_IGNORE}="1"
UDEV
    udevadm control --reload-rules 2>/dev/null || true
fi

exit 0
EOF
chmod 755 ${PKG_NAME}/DEBIAN/postinst

# 5. POSTRM (Limpeza total na desinstalação)
cat <<EOF > ${PKG_NAME}/DEBIAN/postrm
#!/bin/bash
set -e

if [ "\$1" = "remove" ] || [ "\$1" = "purge" ]; then
    echo "🧹 Removendo arquivos dinâmicos do CryoMint..."
    
    if [ -d /opt/cryomint ]; then
        rm -rf /opt/cryomint
    fi
    
    if [ -f /etc/udev/rules.d/99-hide-cryomint.rules ]; then
        rm -f /etc/udev/rules.d/99-hide-cryomint.rules
        udevadm control --reload-rules 2>/dev/null || true
    fi
    
    echo "✅ Limpeza profunda concluída com sucesso."
fi

exit 0
EOF
chmod 755 ${PKG_NAME}/DEBIAN/postrm

# 6. Executável Global
cat <<EOF > ${PKG_NAME}/usr/bin/cryomint
#!/bin/bash
gsettings set org.nemo.desktop volumes-visible false 2>/dev/null || true
/opt/cryomint/venv/bin/python /opt/cryomint/src/main.py "\$@"
EOF
chmod 755 ${PKG_NAME}/usr/bin/cryomint

# 7. Desktop e Autostart
cat <<EOF > ${PKG_NAME}/usr/share/applications/cryomint.desktop
[Desktop Entry]
Name=CryoMint
Exec=cryomint
Icon=/opt/cryomint/assets/icon.svg
Type=Application
Categories=System;Security;
EOF

cat <<EOF > ${PKG_NAME}/etc/xdg/autostart/cryomint.desktop
[Desktop Entry]
Type=Application
Exec=cryomint --tray-only
X-GNOME-Autostart-Delay=10
Icon=/opt/cryomint/assets/icon.svg
EOF

echo "🛠️ Construindo pacote..."
dpkg-deb --build ${PKG_NAME}
echo "✅ Sucesso! Pacote ${PKG_NAME}.deb gerado (Edição RAM)."