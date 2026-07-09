# 🔍 Sugestões de Melhoria — CryoMint

Análise feita com base em `cryo_core.py` (445 linhas), `main.py` (903 linhas), `build_deb.sh` e arquivos de configuração.

---

## 🔴 Alta Prioridade (Bugs / Riscos reais)

### 1. `__version__` desincronizada entre os dois arquivos

`cryo_core.py` linha 17 e `main.py` linha 30 declaram `__version__ = "1.0.4"` de forma independente, e o `build_deb.sh` lê apenas de `src/*.py`. Qualquer atualização pode esquecer um dos dois.

**Sugestão:** Centralizar a versão em um único arquivo (ex: `src/version.py`) e importar nos dois módulos:
```python
# src/version.py
__version__ = "1.0.5"

# em cryo_core.py e main.py
from version import __version__
```

---

### 2. `_get_config_path()` força `remount,rw` silenciosamente

```python
# cryo_core.py — linha 77
subprocess.run(["mount", "-o", "remount,rw", MOUNT_POINT_RO], ...)
```
Esta chamada tenta remount como `rw` **toda vez** que o sistema está congelado — inclusive nas leituras de status. Se falhar, o aviso é apenas um `logger.warning` e a função continua com o caminho `root-ro` sem garantia de poder escrever nele.

**Sugestão:** Separar a lógica: `_get_config_path()` só lê, e o remount deve ocorrer **exclusivamente** dentro de `set_frozen_state()` e `set_maintenance_mode()`, que são as únicas funções que de fato precisam escrever.

---

### 3. Duplicação de código: lógica de edição do `overlayroot.conf`

O bloco de busca e substituição da linha `overlayroot=...` (busca ativa → busca comentada → append) aparece **3 vezes** idênticas: em `set_frozen_state()`, `set_maintenance_mode()` e `run_boot_check()`.

**Sugestão:** Extrair para uma função utilitária:
```python
def _write_overlayroot(config_path: str, value: str) -> str:
    """Atualiza a linha overlayroot= de forma atômica. Retorna erro ou ''."""
    ...
```

---

### 4. `reboot_system()` sem confirmação de privilégio

```python
# main.py — linha 883
def reboot_system(self): subprocess.run(["pkexec", "systemctl", "reboot"])
```
Chamada sem `check=True`, sem tratamento de erro e sem timeout. Se `pkexec` falhar silenciosamente, o sistema não reinicia e o usuário não recebe feedback.

**Sugestão:**
```python
def reboot_system(self):
    try:
        result = subprocess.run(["pkexec", "systemctl", "reboot"],
                                capture_output=True, timeout=15)
        if result.returncode != 0:
            QMessageBox.critical(self, "Erro", f"Falha ao reiniciar:\n{result.stderr.decode()}")
    except Exception as e:
        QMessageBox.critical(self, "Erro", str(e))
```

---

## 🟡 Média Prioridade (Qualidade / Manutenibilidade)

### 5. `get_system_info()` bloqueia a UI thread

`reload_system_info()` chama `get_system_info()` diretamente no main thread. Em redes lentas ou `/proc` travado, isso congela a interface por segundos.

**Sugestão:** Mover `get_system_info()` para um `BackendWorker` ou `QRunnable` dedicado, igual ao padrão já adotado para as operações de freeze/thaw.

---

### 6. `clear_logs()` usando `open(...).close()` sem contexto

```python
# main.py — linha 856
open(ui_log_path, 'w').close()
```
Abre o arquivo sem `with`, o que pode deixar o file descriptor sem garantia de fechamento em exceções.

**Sugestão:**
```python
with open(ui_log_path, 'w'): pass
```

---

### 7. `except: pass` nu em vários locais

`ensure_single_instance()` tem múltiplos `except: pass` sem captura específica nem log, silenciando potenciais falhas críticas de socket.

**Sugestão:** Capturar ao menos `OSError` e logar com `logger.warning(...)`, para não esconder problemas de permissão de socket no `tmp`.

---

### 8. `requirements.txt` com versões fixas demais

```
PySide6==6.11.0
```
Versões exatas (`==`) podem causar falha de instalação caso o usuário tenha uma versão compatível mas diferente, ou caso o pacote não esteja disponível para a arquitetura exata.

**Sugestão:** Usar `>=` com floor de compatibilidade conhecida:
```
PySide6>=6.6.0
```

---

### 9. `marker_path` em `set_maintenance_mode()` depende do diretório do `config_path`

```python
# cryo_core.py — linha 226–227
marker_dir = os.path.dirname(config_path)
marker_path = os.path.join(marker_dir, "cryomint_maintenance_pending")
```
Se o sistema estiver congelado, `config_path` seria `/media/root-ro/etc/overlayroot.conf`, então o marcador seria gravado em `/media/root-ro/etc/` — que é a partição real somente leitura. Em `run_boot_check()` (linha 318), o marcador é sempre lido de `/etc/cryomint_maintenance_pending`. **Caminhos inconsistentes.**

**Sugestão:** Fixar `marker_path = "/etc/cryomint_maintenance_pending"` em `set_maintenance_mode()`, sem depender do diretório do `config_path`.

---

## 🟢 Baixa Prioridade (Melhorias de UX / Robustez)

### 10. README com instruções de instalação duplicadas e conflitantes

O README tem **dois blocos** de instruções de instalação (linhas 36–40 e 41–45) com conteúdo sobreposto. A segunda lista começa sem título de seção, misturada com a primeira.

**Sugestão:** Unificar em um único bloco com título `### Compilação e Instalação`.

---

### 11. Polling de status a cada 10s sem back-off

```python
# main.py — linha 470
self.status_timer.start(10000)
```
O timer de status dispara um novo `BackendWorker` a cada 10 segundos independentemente de estado. Se uma operação de freeze estiver em andamento, pode haver execuções concorrentes de `status`.

**Sugestão:** Parar o timer durante operações longas e retomá-lo no `_handle_success` / `_handle_failure`.

---

### 12. Ausência de testes automatizados

Nenhum arquivo de testes existe no projeto. Para um sistema que manipula partições root e overlayfs, bugs podem ser catastróficos.

**Sugestão:** Adicionar `tests/` com testes unitários para as funções puras do `cryo_core.py` (ex: lógica de edição do `overlayroot.conf`, `get_overlay_usage()`, `get_status_json()`) usando `unittest` e mocks de filesystem (`unittest.mock.patch`).

---

## 📊 Resumo e Status de Implementação

| # | Categoria | Impacto | Esforço | Status | Nota de Implementação |
|---|---|---|---|---|---|
| 1 | `__version__` duplicada | 🔴 Alto | Baixo | ✅ Implementado | Centralizado em `version.py`, importado nos módulos e incluído no `build_deb.sh`. |
| 2 | remount indevido no `_get_config_path` | 🔴 Alto | Médio | ✅ Implementado | `_get_config_path` foi limpo; o remount ocorre estritamente antes e depois das escritas. |
| 3 | Código duplicado de edição de config | 🔴 Alto | Médio | ✅ Implementado | Lógica de escrita atômica unificada na função utilitária `_write_overlayroot` de `cryo_core.py`. |
| 4 | `reboot_system` sem tratamento de erro | 🔴 Alto | Baixo | ✅ Implementado | Adicionado bloco `try/except` com tratamento de timeout (15s) e diálogos UI de erro em `main.py`. |
| 5 | `get_system_info` bloqueia UI thread | 🟡 Médio | Médio | ✅ Implementado | Informações de sistema coletadas via `SystemInfoWorker` (executado no `QThreadPool`). |
| 6 | `open(...).close()` sem contexto | 🟡 Médio | Baixo | ✅ Implementado | Utilização do bloco seguro `with open(...)` para truncar o arquivo de logs. |
| 7 | `except: pass` silencioso | 🟡 Médio | Baixo | ✅ Implementado | Captura explícita de `OSError` e log de aviso no singleton de instância única em `main.py`. |
| 8 | `requirements.txt` com versões rígidas | 🟡 Médio | Baixo | ✅ Implementado | Alterado para operadores `>=6.6.0` em vez de versões fixas. |
| 9 | Caminho do marcador de manutenção inconsistente | 🔴 Alto | Baixo | ✅ Implementado | Caminho do marcador gerenciado dinamicamente com base no estado do congelamento (`MOUNT_POINT_RO`). |
| 10 | README com instruções duplicadas | 🟢 Baixo | Baixo | ✅ Implementado | Seções de instalação unificadas de forma coerente sob o título `### Compilação e Instalação`. |
| 11 | Timer de status sem back-off | 🟢 Baixo | Médio | ✅ Implementado | Timer de status é parado durante ações críticas e retomado após o sucesso ou falha da operação. |
| 12 | Ausência de testes automatizados | 🟢 Baixo | Alto | ✅ Implementado | Criada suite de testes em `tests/test_cryo_core.py` usando `unittest` e mocks multiplataforma. |
