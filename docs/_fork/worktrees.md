# Worktrees do fork mms (DNBSCDC289)

> Registro canônico. Worktree é área de trabalho **de uma sessão por vez** — trabalhar no
> worktree de outra sessão causa colisão de branch e perda de estado. Antes de criar um novo,
> verifique esta lista; ao criar, **adicione a linha aqui no mesmo commit**.
> Atualizado: 21/out/2026.

## Lista medida

| caminho | branch | para quê | estado |
|---|---|---|---|
| `~/git/mms/mms` | `main` | **LINHA VIVA** — o serviço systemd roda daqui (venv editable ONNX) | ativo, serviço |
| `~/git/mms/mms-dev` | — | removida 21/out (trabalho de tracker já entregue na main) | suprimida |
| `~/git/mms/opencode-first-class` | `feat/opencode-installer` | bancada do embarque OpenCode 1ª classe: instalador no pacote, CLI `memory install opencode`, specs F001–F010, E2E clean-room | ativa, 12 commits (28/out) |

Rastreio: `git -C ~/git/mms/mms worktree list --porcelain` é a fonte de verdade; esta tabela
explica **para quê** cada um existe, o que o comando não diz.

## Regras

1. **Um worktree, uma sessão.** Se o worktree estiver em branch diferente da esperada ou com
   arquivos modificados que você não fez, não trabalhe nele.
2. **Bancada é nova, não a de outra sessão:** `git worktree add ~/git/mms/lab-<tema> -b lab/<tema> main`.
3. **Remoção exige commit ou descarte explícito:** `git worktree remove <path>` recusa com
   trabalho sujo — isso é proteção, não erro.
4. **Documentação anda junto:** worktree criado, linha nesta tabela. Worktree removido, linha
   removida. A regra do LEDGER vale aqui também — rastro ou não existiu.
5. Worktrees não compartilham `venv`: para rodar testes num worktree sem criar venv,
   `PYTHONPATH=$PWD/src <venv-do-repo-principal>/bin/python -m pytest ...` e confirme com
   `python -c "import mcp_memory_service; print(m.__file__)"` que importa do worktree.

## Histórico

- **21/out/2026** — reorganização do workspace (pedida pelo Claudio): repo principal movido
  de `~/git/mcp-memory-service` para `~/git/mms/mms`; 15 worktrees de PR removidas, branches
  fully merged deletados local + remoto; unit systemd (`~/.config/systemd/user/memory-service.service`)
  atualizada para o novo caminho (WorkingDirectory + ExecStart). Health 200 na 8000 após restart.
- **19/out/2026** — criado `~/git/mms/lab-recall` a partir de `github/lab/precisao-recall`
  (branch local `lab/precisao-recall-t'pol`), porque o laboratório de recall vivia apenas no
  remoto e o diretório de bancada anterior (`~/local-data/mcp/lab/`) não existe mais neste host.
  Os artefatos estão versionados na branch: `eval/`, `scripts/lab/onnx_embeddings_api.py`,
  `scripts/maintenance/migrate_embeddings.py`, `scripts/deep_search.py`.
