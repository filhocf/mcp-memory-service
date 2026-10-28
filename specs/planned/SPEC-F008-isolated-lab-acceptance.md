# SPEC-F008 — Isolated lab and acceptance suite

| Field | Value |
|-------|-------|
| Status | planned |
| Impact | High — proves the installation without touching the developer's setup |
| Depends on | F001, F002 |
| Blocks | F009 |
| Branch | `feat/opencode-installer` |
| Date | 2026-10-23 |

## 1. Context

The previous session already hit the failure mode this spec prevents: running an
installer's uninstall without flags removed the developer's real
`codebase-memory-mcp`. The harness installer has a `--root` sandbox, but the
OpenCode side has more surfaces (config, plugin, `AGENTS.md`, skill, plugin
config, state file) and a real client binary that reads `HOME`.

Acceptance for "first-class OpenCode client" cannot be a unit test of the
installer alone: OpenCode itself must see the registration, and the service must
accept a memory through that path with authorship.

## 2. Objective

Provide a reusable lab that boots MMS and OpenCode into a temporary `HOME`,
installs the client, and asserts the effects end to end, with a guard proving
the real configuration was not touched.

## 3. Non-goals

- Running a model or a full agent session (needs credentials and is
  non-deterministic).
- Browser/TUI rendering.
- Testing every harness.

## 4. Requirements

**R1 — HOME isolation.**
Every lab test runs with `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and
`XDG_STATE_HOME` pointing inside `tmp_path`.

EARS: WHEN a lab test starts, THE test process SHALL resolve every user path
under `tmp_path`.

**R2 — Service isolation.**
MMS runs on a free loopback port with its database and logs under `tmp_path`,
and the test waits for `/api/health` before installing.

EARS: WHEN the lab starts the service, THE lab SHALL wait until
`http://127.0.0.1:<port>/api/health` returns 200.

**R3 — Real client check.**
When the `opencode` binary is available, the lab asserts that
`opencode mcp list` reports `mms` from the sandbox configuration.

EARS: WHERE the `opencode` binary is on `PATH`, THE lab SHALL assert that
`opencode mcp list` lists `mms`.

**R4 — Plugin validity.**
The lab asserts that the deposited plugin imports in Node and exposes `setup`
and `server`; when Node is absent the check is skipped with a reported reason.

EARS: WHERE Node is available, THE lab SHALL import the deposited plugin and
assert both entry points.

**R5 — Service round-trip with authorship.**
After install, the lab sends an MCP `initialize` + `tools/call memory_store`
with the configured `X-Agent-ID`, then searches by tag `agent:<id>` and finds
the memory.

EARS: WHEN a memory is stored through the lab MCP endpoint, THE search by
`agent:<id>` SHALL return it.

> **Emenda (28/out/2026, laboratório executado).** No build 12.3.1 o header
> `X-Agent-ID` é inerte (SPEC-F005) — a autoria determinística é o argumento
> explícito `agent_id` (precedência máxima) mais a tag `agent:<id>` no
> metadata. O caminho por header continua desenhado na RFC D4 (transform do
> plugin) e volta a valer quando o transform existir.

**R6 — No real-config mutation.**
The lab records the SHA-256 of the developer's real OpenCode config (when it
exists) before and after the test and asserts equality.

EARS: THE lab SHALL assert that the real configuration file hash is unchanged.

**R7 — No writes outside the sandbox.**
After a test, every path in the install manifest and every file the plugin
writes resolve under `tmp_path`.

EARS: WHEN the lab test finishes, THE test SHALL assert that all manifest paths
start with `tmp_path`.

**R8 — Deterministic port.**
The lab asks the OS for a free port and passes it to both the service and the
installer; no test hardcodes 8000 or 3202.

EARS: THE lab SHALL obtain the port from a bound socket with port 0.

## 5. Technical contract

### 5.1 Fixtures

`tests/harness/lab.py`:

```python
@dataclass
class Lab:
    home: Path
    config_home: Path
    state_home: Path
    data_home: Path
    port: int
    endpoint: str
    env: dict[str, str]

@pytest.fixture
def lab(tmp_path, monkeypatch) -> Iterator[Lab]:
    ...  # bind free port, export env, start service, wait for health
```

Service command:

```bash
python -m mcp_memory_service.cli.main server --http --port <port>
```

with:

```
MCP_ALLOW_ANONYMOUS_ACCESS=true
MCP_MEMORY_DB_PATH=<home>/memory.db
HOME=<home>
XDG_CONFIG_HOME=<config_home>
XDG_STATE_HOME=<state_home>
XDG_DATA_HOME=<data_home>
```

If the module entry point differs, the fixture uses the same command the
project documents (`memory server --http`) and records it in the test.

> **Emenda medida (28/out/2026).** Três correções do rascunho, descobertas ao
> executar o lab: (1) a variável que isola o banco é `MCP_MEMORY_SQLITE_PATH`
> — `MCP_MEMORY_DB_PATH` é o typo que o serviço agora rejeita
> (config/storage.py avisa explicitamente); (2) o comando `server` recebe
> `--http-host/--http-port`, não `--port`; (3) o pacote não tem `__main__.py`,
> então o serviço nasce via `cli.main:main` com `-c` e `PYTHONPATH` fixado na
> árvore de trabalho. Logs do serviço não têm variável de redirecionamento —
> ficam no HOME real (resíduo documentado, não é superfície do instalador).

### 5.2 Tests

`tests/harness/test_opencode_lab.py`:

1. `test_install_is_visible_to_opencode` — install, then `opencode mcp list`.
2. `test_plugin_imports` — Node import smoke test.
3. `test_mcp_round_trip_stamps_agent` — store/search with `X-Agent-ID`.
4. `test_real_config_untouched` — hash guard.
5. `test_all_writes_stay_in_sandbox` — manifest prefix guard.
6. `test_uninstall_leaves_clean_tree` — expected files removed.

`tests/harness/conftest.py` registers the fixtures for the harness suite.

### 5.3 Markers

`@pytest.mark.integration` for service-backed tests; the suite runs when the
service imports successfully. `@pytest.mark.skipif` for missing `opencode` or
`node`, with the reason printed.

## 6. Edge cases

| Case | Behaviour |
|------|-----------|
| Port race between free-port probe and bind | Retry up to 3 times |
| Service slow to start (model load) | 60s timeout with `/api/health` polling |
| `opencode` present but v1 | `mcp list` output parsed tolerantly; failure reported with the raw output |
| Developer has no real config | Hash guard skipped, noted |
| Node absent | Plugin check skipped, noted in the test report |
| Test killed mid-run | `tmp_path` is disposable; the service is stopped in fixture teardown |
| OpenCode's managed service binds a default port (49374 on 2.1.3) that collides with a running daemon | the lab sets its own port first: `opencode service set port <free>` (R8) |
| Cold daemon answers "No MCP servers configured" to an immediate `mcp list` (async boot) | retry up to 5× with 2s sleeps; raw output reported on failure |
| OpenCode resolves its config from `$HOME/.config/opencode` and ignores `XDG_CONFIG_HOME` (measured, 2.1.3) | the sandbox keeps the XDG vars coherent under `HOME`; the installer's default root follows the same resolution |

## 7. Acceptance criteria (measurable)

| AC | Command | Expected |
|----|---------|----------|
| AC1 | `pytest tests/harness/test_opencode_lab.py -q` | all pass (or documented skips) |
| AC2 | `opencode mcp list` under the lab env | contains `mms` |
| AC3 | MCP store + tag search | one hit with `agent:<id>` |
| AC4 | real config hash before/after | equal |
| AC5 | manifest paths | all under `tmp_path` |
| AC6 | uninstall | no MMS files remain under the sandbox root |

## 8. Test plan (RED-on-main)

The suite is itself the deliverable, so RED is demonstrated by running it on the
current branch before F001/F002 exist:

- `test_install_is_visible_to_opencode` fails with `KeyError: 'opencode'`;
- `test_plugin_imports` fails because no plugin was deposited;
- `test_mcp_round_trip_stamps_agent` passes only after F005.

Record the failure count grouped by cause.

## 9. Risks and rollback

| Risk | Mitigation |
|------|------------|
| Lab leaks into the real `HOME` | Explicit env override in every fixture; hash guard |
| Flaky service startup | Health polling with timeout and retry |
| Slow suite | Integration marker; unit tests stay fast |
| Real config touched by a mistake | Test fails loudly on hash mismatch |

Rollback: delete `tests/harness/lab.py`; no production code depends on it.

## 10. Out of scope

- Model-backed session e2e.
- TUI sidebar.
- Docker-based lab.
