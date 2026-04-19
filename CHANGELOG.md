# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

## [0.1.13] - 2026-04-18
### Adicionado
- **Arquitetura RAM/Swap:** Consolidação do motor usando `tmpfs` integrado ativamente com partições Swap (`overlayroot="tmpfs:swap=1"`), resolvendo o gargalo de memória RAM em laboratórios.
- **Interface Vetorial (SVG):** Substituição de arquivos `.png` estáticos por `.svg` no menu Iniciar e na Bandeja do Sistema, garantindo escalabilidade infinita e contraste perfeito em temas Light/Dark.
- **Aba Sobre:** Adição de créditos do desenvolvedor, versão atual e tecnologias utilizadas na interface PySide6.
- **Gestão de Empacotamento:** Adicionado script `postrm` no construtor `.deb` para garantir a remoção profunda (VENV e regras udev) ao desinstalar o programa.
- **Proteção de UI:** O botão de alternância (Toggle) agora desativa visualmente e exibe "Aplicando..." para evitar cliques duplos durante a elevação de privilégios via `pkexec`.