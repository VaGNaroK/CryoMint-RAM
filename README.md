# ❄️ CryoMint - RAM Edition

CryoMint é um sistema imutável de proteção de estado para Linux Mint, desenvolvido com interface gráfica em **PySide6** e motor baseado em **OverlayFS**. 

Projetado especificamente para laboratórios de informática e ambientes educacionais, o CryoMint congela a partição raiz (`/`) do sistema operacional. Qualquer alteração feita pelo usuário (instalação de programas, download de arquivos, exclusão de pastas) é registrada em uma camada temporária na memória RAM (`tmpfs`) e descartada automaticamente assim que o computador é reiniciado.

## 🚀 Funcionalidades

### 📌 Descrição do Projeto
CryoMint é um sistema imutável de proteção de estado para Linux Mint, desenvolvido com interface gráfica em **PySide6** e motor baseado em **OverlayFS**. Projetado especificamente para laboratórios de informática e ambientes educacionais, o CryoMint congela a partição raiz (`/`) do sistema operacional. Qualquer alteração feita pelo usuário (instalação de programas, download de arquivos, exclusão de pastas) é registrada em uma camada temporária na memória RAM (`tmpfs`) e descartada automaticamente assim que o computador é reiniciado.
* **Proteção Absoluta:** O HD/SSD principal fica em modo Somente Leitura (Read-Only).
* **RAM + Swap Architecture:** Utiliza a memória RAM para máxima velocidade nas sessões dos alunos, com suporte a transbordo inteligente para partições Swap (`swap=1`), evitando travamentos por falta de memória.
* **Interface Intuitiva:** Painel de controle amigável com System Tray para ligar/desligar a proteção e exigir reinicialização.
* **Camuflagem de Sistema:** Oculta automaticamente os discos virtuais do OverlayFS no gerenciador de arquivos (Nemo) via regras `udev`.
* **Pacote Autolimpante:** Geração de arquivo `.deb` com scripts de pré/pós instalação e remoção limpa.

### ✨ Novidades da v1.0.5
* **🛡️ Aba Status Expandida:** Barra de progresso dinâmica mostrando uso de RAM e Swap do overlay (`/media/root-rw`), com alerta automático na bandeja ao ultrapassar 85% de uso.
* **🛠️ Modo de Manutenção:** Novo botão que guia o administrador por um fluxo de boot único para realizar alterações persistentes no sistema, com diálogos explicativos e banner de alerta enquanto ativo.
* **📄 Aba Logs (Nova):** Terminal estilizado (verde/preto) exibindo as últimas 80 linhas dos logs do núcleo (`core.log`) e da interface (`ui.log`), com botões de recarga, limpeza e exportação `.txt`.
* **🖥️ Aba Sistema (Nova):** Painel de diagnósticos rápidos do hardware: Hostname, IP, versão do SO, modelo do CPU, RAM total, Swap configurado e Uptime da máquina.
* **ℹ️ Aba Sobre (Reorganizada):** Créditos e informações de empacotamento movidos para aba dedicada, limpando a tela principal.
* **Backend — Comando `status`:** Retorna JSON estruturado com estado do congelamento, marcadores ativos e uso de armazenamento do overlay.
* **Backend — Comando `maintenance`:** Desativa a imutabilidade gravando `overlayroot=""` e cria o marcador persistente `/etc/cryomint_maintenance_pending`.
* **Backend — Comando `boot-check`:** Executa no boot para limpar o marcador de manutenção, reconfigurar o congelamento (`overlayroot="tmpfs:swap=1"`) e sinalizar a sessão volátil via `/run/cryomint_in_maintenance`.
* **Resiliência Mock:** Interface e backend continuam operando normalmente em ambientes sem Polkit/Linux Mint para facilitar desenvolvimento.

## 🛠️ Tecnologias Utilizadas
* **Python 3** e **PySide6** (Interface Gráfica)
* **Bash Scripting** (Automação de Build e Empacotamento Debian)
* **Overlayroot / OverlayFS** (Motor do Kernel Linux)
* **Polkit (`pkexec`)** (Escalonamento de Privilégios seguro)

## 📦 Como Compilar

### 📌 Compilação e Instalação
1. Clone este repositório: `git clone https://github.com/VaGNaroK/CryoMint-RAM`
2. Instale as dependências Python: `pip install -r requirements.txt`
3. Dê permissão de execução ao script de build: `chmod +x scripts/build_deb.sh`
4. Execute o script de build a partir da raiz do projeto: `./scripts/build_deb.sh`
5. Instale o pacote gerado: `sudo apt install ./cryomint_1.0.5_amd64.deb`

## 👨‍💻 Autor
Desenvolvido por **VaGNaroK** com ajudinha de IA.