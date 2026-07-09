# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

O formato baseia-se em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [1.0.5] - 2026-07-08

### Adicionado
- **Aba Status Expandida:** Barra de progresso (`QProgressBar` estilizado) que calcula dinamicamente o espaço livre/usado na RAM e no Swap do overlay (`/media/root-rw`), com alerta automático via bandeja ao ultrapassar 85% de uso.
- **Modo de Manutenção:** Novo botão na aba Status que guia o administrador por um fluxo de boot único para alterações persistentes, com caixas de diálogo explicativas e banner de alerta permanente enquanto o modo estiver ativo.
- **Aba Logs (Nova):** Terminal estilizado (verde/preto) exibindo as últimas 80 linhas dos logs do núcleo (`core.log`) e da interface (`ui.log`), com botões de recarga sob demanda, limpeza do log do usuário e exportação para `.txt`.
- **Aba Sistema (Nova):** Painel de diagnósticos rápidos do hardware listando Hostname, Endereço IP, versão do SO, modelo do CPU, RAM total, Swap configurado e Uptime da máquina.
- **Aba Sobre (Reorganizada):** Créditos e informações de empacotamento movidos para aba dedicada, limpando a tela principal.
- **Backend — Comando `status`:** Retorna JSON estruturado contendo estado do congelamento, marcadores ativos e uso de armazenamento do overlay.
- **Backend — Comando `maintenance`:** Desativa a imutabilidade gravando `overlayroot=""` no arquivo de configuração e gera o marcador persistente `/etc/cryomint_maintenance_pending`.
- **Backend — Comando `boot-check`:** Executa durante a inicialização para limpar o marcador de manutenção, reconfigurar o congelamento (`overlayroot="tmpfs:swap=1"`) e criar a flag em RAM `/run/cryomint_in_maintenance` para sinalizar sessão volátil à GUI.
- **Resiliência Mock:** Interface e backend continuam operando normalmente em ambientes sem Polkit/Linux Mint para facilitar desenvolvimento e testes.
- **Redimensionamento Dinâmico:** Janela principal ajustada para `500×420` para acomodar as novas abas.

### Corrigido
- Correção do aviso `QSystemTrayIcon::setVisible: No Icon set` ao iniciar a interface gráfica, atribuindo o ícone antes de exibir a bandeja.
- Correção do salto de rolagem na aba de Logs ("scroll jumping"), substituindo o `QTextEdit` por `QPlainTextEdit` e desativando a quebra de linha.
- Tratamento adequado de `PermissionError` ao criar diretórios de log (`/var/log/cryomint`) no módulo `cryo_core.py`, viabilizando a execução de testes locais.

### Alterado
- Serviço systemd `cryomint-maintenance.service` agora dispara o comando `boot-check` durante a inicialização do sistema (`After=local-fs.target`, `Before=display-manager.service`).
- `build_deb.sh` atualizado para copiar e configurar permissões (`644`) do serviço systemd e habilitar automaticamente o serviço no `postinst` (`systemctl enable`).
- Arquivo `org.cryomint.policy` movido para `services/` (local canônico); `build_deb.sh` atualizado para referenciar o novo caminho.

## [1.0.4] - 2026-05-05

### Adicionado
- Implementação de Thread Pool (`QThreadPool`) no frontend para execução assíncrona, evitando travamentos da interface (GUI) durante as transições de congelamento/descongelamento.
- Variável `__version__` adicionada ao topo do `main.py` para sincronização unificada com o construtor do pacote Debian.

### Corrigido
- Fixação permanente do tema "Dark Mode" blindado, contornando falhas de detecção nativa do ambiente desktop (Cinnamon/Linux Mint) e garantindo a consistência visual.
- Correção do Tooltip no menu da bandeja (System Tray) que estava ocultando o nome do aplicativo.
- Resolução do erro de importação da biblioteca `PySide6.QtCore` que impedia a inicialização silenciosa (`--tray-only`) com o sistema.
- Correção do script `build_deb.sh` que não estava lendo corretamente a versão do Python devido a um conflito de escape de aspas simples no Bash.

### Alterado
- O script construtor (`build_deb.sh`) agora varre todos os arquivos dentro do diretório `src/` em busca da versão do software.
- Refatoração do `cryo_core.py` (backend) para retornar mensagens de status em string (stdout) formatadas, substituindo a finalização abrupta com `sys.exit()` e melhorando o feedback visual de falhas.

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