# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato baseia-se em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [1.0.1] - 2026-04-23
### Adicionado
- **Prevenção de Múltiplas Instâncias (Singleton):** Implementação de Sockets Unix na interface para impedir a abertura simultânea de múltiplas janelas, enviando sinal para trazer a interface existente ao topo.
- **Travas de Concorrência (Locking):** Adição do módulo `fcntl` no backend criando arquivos de trava (`/run/lock/cryomint-core.lock`) para evitar que execuções simultâneas corrompam o arquivo de configuração.
- **Sistema de Logging Profissional:** Implementação de Dual Logging. Registros agora são enviados silenciosamente para o Syslog do sistema e arquivos dedicados (`/var/log/cryomint/core.log` e `~/.local/share/cryomint/logs/cryomint_ui.log`).
- **Autostart via Systemd:** Substituição do modelo legado XDG por serviços e timers do Systemd em *user space* (`cryomint-tray.service`).
- **Ativação Inteligente de Interface:** Script `/etc/profile.d/cryomint-autostart.sh` para acionar a bandeja do sistema apenas para usuários humanos (`UID >= 1000`) em sessões gráficas.
- **Tray Health Monitor:** Um `QTimer` dedicado na interface que verifica e recarrega o ícone do sistema caso a barra de tarefas do ambiente desktop do Linux Mint sofra *crash* ou reinicie.
- **Proteção Anti-Path Traversal:** Validação rigorosa na interface (`os.path.realpath`) garantindo que apenas o backend legítimo instalado em `/opt/cryomint/src/` seja executado via `pkexec`.
- **Extração Dinâmica de Versão:** A interface e os logs agora leem a versão oficial do pacote instalado no sistema via `dpkg-query`.

### Modificado
- **Gravação Atômica de Arquivos:** Modificação drástica no backend para prevenir corrupção em quedas de energia. O arquivo `overlayroot.conf` é escrito em um temporário, sincronizado no disco (`os.fsync`) e substituído de forma atômica (`os.replace`).
- **Construção do Pacote Debian:** Script `build_deb.sh` aprimorado com tolerância a erros (fallbacks com `|| true`), criação preventiva de diretórios com permissões corretas (logs e locks) e otimização de RAM usando `exec` no atalho `/usr/bin/cryomint`.
- **Resiliência da Interface Gráfica:** Adição de *timeouts* estritos (30 a 60 segundos) para processos e chamadas `pkexec`, prevenindo que a UI congele permanentemente caso a janela de senha não responda.

### Corrigido
- **Integração com Swap e Tmpfs:** Otimização definitiva do parâmetro `overlayroot="tmpfs:swap=1"` no backend refatorado, garantindo proteção total contra o esgotamento do limite de 50% da memória em máquinas do laboratório com recursos limitados.
- **Verificação de Ponto de Montagem:** Substituição da dependência exclusiva do Python (`os.path.ismount`) pelo utilitário nativo do sistema (`mountpoint -q`) para maior precisão na leitura do estado atual (Congelado/Descongelado).

## [0.1.13] - 2026-04-18
### Adicionado
- **Arquitetura RAM/Swap:** Consolidação do motor usando `tmpfs` integrado ativamente com partições Swap (`overlayroot="tmpfs:swap=1"`), resolvendo o gargalo de memória RAM em laboratórios.
- **Interface Vetorial (SVG):** Substituição de arquivos `.png` estáticos por `.svg` no menu Iniciar e na Bandeja do Sistema, garantindo escalabilidade infinita e contraste perfeito em temas Light/Dark.
- **Aba Sobre:** Adição de créditos do desenvolvedor, versão atual e tecnologias utilizadas na interface PySide6.
- **Gestão de Empacotamento:** Adicionado script `postrm` no construtor `.deb` para garantir a remoção profunda (VENV e regras udev) ao desinstalar o programa.
- **Proteção de UI:** O botão de alternância (Toggle) agora desativa visualmente e exibe "Aplicando..." para evitar cliques duplos durante a elevação de privilégios via `pkexec`.