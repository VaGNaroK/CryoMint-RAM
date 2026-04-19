# ❄️ CryoMint - RAM Edition

CryoMint é um sistema imutável de proteção de estado para Linux Mint, desenvolvido com interface gráfica em **PySide6** e motor baseado em **OverlayFS**. 

Projetado especificamente para laboratórios de informática e ambientes educacionais, o CryoMint congela a partição raiz (`/`) do sistema operacional. Qualquer alteração feita pelo usuário (instalação de programas, download de arquivos, exclusão de pastas) é registrada em uma camada temporária na memória RAM (`tmpfs`) e descartada automaticamente assim que o computador é reiniciado.

## 🚀 Funcionalidades
* **Proteção Absoluta:** O HD/SSD principal fica em modo Somente Leitura (Read-Only).
* **RAM + Swap Architecture:** Utiliza a memória RAM para máxima velocidade nas sessões dos alunos, com suporte a transbordo inteligente para partições Swap (`swap=1`), evitando travamentos por falta de memória.
* **Interface Intuitiva:** Painel de controle amigável com System Tray para ligar/desligar a proteção e exigir reinicialização.
* **Camuflagem de Sistema:** Oculta automaticamente os discos virtuais do OverlayFS no gerenciador de arquivos (Nemo) via regras `udev`.
* **Pacote Autolimpante:** Geração de arquivo `.deb` com scripts de pré/pós instalação e remoção limpa.

## 🛠️ Tecnologias Utilizadas
* **Python 3** e **PySide6** (Interface Gráfica)
* **Bash Scripting** (Automação de Build e Empacotamento Debian)
* **Overlayroot / OverlayFS** (Motor do Kernel Linux)
* **Polkit (`pkexec`)** (Escalonamento de Privilégios seguro)

## 📦 Como Compilar
Para compilar o pacote `.deb` instalável:
1. Clone este repositório.
2. Dê permissão de execução ao script de build: `chmod +x build_deb.sh`
3. Execute o script: `./build_deb.sh`
4. Instale o pacote gerado: `sudo apt install ./cryomint_X.X.X_amd64.deb`

## 👨‍💻 Autor
Desenvolvido por **VaGNaroK** com ajudinha de IA.