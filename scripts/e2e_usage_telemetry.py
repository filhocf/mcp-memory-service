"""E2E real — instrumentação de proveito (usage_events) no serviço.
Prova com NÚMEROS: retrieve gera evento, feedback gera evento, agregador calcula,
kill-switch desliga, query crua nunca gravada."""
import asyncio, os, tempfile

async def main():
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
    from mcp_memory_service.storage.usage_telemetry import get_usage_metrics
    from mcp_memory_service.models.memory import Memory
    from mcp_memory_service.utils.hashing import generate_content_hash

    d = tempfile.mkdtemp(); p = os.path.join(d, "e2e.db")
    os.environ["MCP_USAGE_TELEMETRY"] = "true"
    s = SqliteVecMemoryStorage(p); await s.initialize()

    # semear memórias
    for i in range(5):
        c = f"fato tecnico numero {i} sobre jenkins e credenciais"
        await s.store(Memory(content=c, content_hash=generate_content_hash(c), tags=["e2e"]))

    print("=== E2E: instrumentação de proveito (serviço real) ===")

    # 3 buscas
    for q in ["jenkins credenciais", "fato tecnico", "numero sobre"]:
        await s.retrieve(query=q, n_results=3)

    def count_events(etype):
        cur = s.conn.execute("SELECT COUNT(*) c FROM usage_events WHERE event_type=?", (etype,))
        return cur.fetchone()["c"]

    n_retr = count_events("retrieval")
    print(f"eventos 'retrieval' após 3 buscas       = {n_retr}")
    assert n_retr >= 3, "retrieve deveria gerar evento"
    print("  [REQ-1 OK] retrieval instrumentado")

    # privacidade: query crua nunca gravada
    cur = s.conn.execute("SELECT query_hash, metadata FROM usage_events WHERE event_type='retrieval'")
    rows = cur.fetchall()
    raw_leaked = any("jenkins" in str(r["query_hash"] or "") + str(r["metadata"] or "") for r in rows)
    print(f"query crua vazou?                        = {raw_leaked}")
    assert not raw_leaked, "FALHA PRIVACIDADE: query crua gravada"
    print("  [REQ-7 OK] só query_hash, nunca texto cru")

    # feedback event
    h = generate_content_hash("fato tecnico numero 0 sobre jenkins e credenciais")
    await s.record_feedback_event(content_hash=h, rating=-1, source="user_explicit")
    n_fb = count_events("feedback")
    print(f"eventos 'feedback' após 1 rating         = {n_fb}")
    assert n_fb == 1, "feedback deveria gerar evento"
    print("  [REQ-4 OK] feedback instrumentado")

    # agregador calcula de verdade
    m = await get_usage_metrics(s)
    print(f"métricas agregadas                       = total_retrievals={m.get('total_retrievals')}, "
          f"total_feedback={m.get('total_feedback')}, feedback_coverage={m.get('feedback_coverage'):.3f}")
    assert m["total_retrievals"] >= 3 and m["total_feedback"] == 1
    assert "never_reaccessed_rate" not in m, "placeholder mentiroso não pode voltar"
    print("  [REQ-5 OK] agregador calcula real, sem placeholder")

    # kill-switch
    os.environ["MCP_USAGE_TELEMETRY"] = "false"
    before = count_events("retrieval")
    await s.retrieve(query="mais uma busca", n_results=2)
    after = count_events("retrieval")
    print(f"kill-switch OFF: eventos {before}->{after} (sem incremento)")
    assert after == before, "FALHA kill-switch: gravou com flag off"
    print("  [REQ-6 OK] kill-switch desliga coleta")

    print("\n=== E2E PASSOU: instrumentação prova proveito com números ===")

asyncio.run(main())
