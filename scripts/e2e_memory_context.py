"""E2E real — injeção proativa por tema (memory_context) + evento injection na telemetria.
Prova com NÚMEROS: belief relevante ao tema (conf menor) vence o top-conf cego;
evento injection é gravado; os dois loops se conectam (injeção alimenta telemetria)."""
import asyncio, os, json, tempfile

async def main():
    from mcp_memory_service.storage.sqlite_vec import SqliteVecMemoryStorage
    from mcp_memory_service.storage.context_injection import memory_context
    from mcp_memory_service.consolidation.belief_service import BeliefService

    d = tempfile.mkdtemp(); p = os.path.join(d, "e2e.db")
    os.environ["MCP_CONTEXT_INJECTION_ENABLED"] = "true"
    os.environ["MCP_USAGE_TELEMETRY"] = "true"
    s = SqliteVecMemoryStorage(p); await s.initialize()

    # 3 beliefs: o relevante ao tema tem confiança MENOR que o irrelevante
    svc = BeliefService(s)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    beliefs = [
        ("bh_pool", "Usar connection pool com tamanho 20 para o banco PostgreSQL", 0.65),
        ("bh_async", "Sempre preferir funcoes async em todo o codigo Python", 0.95),
        ("bh_log",  "Logs em formato JSON estruturado para o Logstash", 0.80),
    ]
    for h, c, conf in beliefs:
        s.conn.execute(
            "INSERT INTO beliefs (belief_hash, content, confidence, status, created_at, updated_at, derived_from, contradicted_by, metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (h, c, conf, "active", now, now, "[]", "[]", "{}"),
        )
    s.conn.commit()

    print("=== E2E: injeção proativa por tema (serviço real) ===")
    print("beliefs: pool(conf 0.65, RELEVANTE) | async(0.95, irrelevante) | log(0.80)")

    res = await memory_context(s, task="configurar connection pool do banco de dados", budget_tokens=2048)
    items = res.get("items", [])
    print(f"\ninjected={res.get('injected')} count={res.get('count')} truncated={res.get('truncated')}")
    print("ordem injetada (top->):")
    for it in items[:3]:
        print(f"  conf={it.get('confidence')} rel={it.get('relevance'):.2f} :: {it.get('content')[:50]}")

    top = items[0]
    assert "pool" in top.get("content", "").lower() or top.get("belief_hash") == "bh_pool", \
        "FALHA: belief relevante ao tema (menor conf) devia liderar"
    print("  [REQ-1/3 OK] belief relevante (conf 0.65) venceu o top-conf cego (async 0.95)")

    # evento injection gravado (os 2 loops conectados)
    cur = s.conn.execute("SELECT n_results, metadata FROM usage_events WHERE event_type='injection'")
    rows = cur.fetchall()
    print(f"\neventos 'injection' na telemetria        = {len(rows)}")
    assert len(rows) == 1, "injeção devia gravar 1 evento"
    meta = json.loads(rows[0]["metadata"] or "{}")
    print(f"  belief_hashes no evento                = {meta.get('belief_hashes')}")
    assert "belief_hashes" in meta
    print("  [REQ-5 OK] evento injection grava — LOOP 2 alimenta LOOP 1 (telemetria)")

    # kill-switch
    os.environ["MCP_CONTEXT_INJECTION_ENABLED"] = "false"
    res_off = await memory_context(s, task="qualquer tema", budget_tokens=512)
    print(f"\nkill-switch OFF: injected={res_off.get('injected')} items={len(res_off.get('items', []))}")
    assert res_off.get("injected") is False and len(res_off.get("items", [])) == 0
    print("  [REQ-6 OK] kill-switch desliga injeção")

    print("\n=== E2E PASSOU: injeção por tema + telemetria conectada, provado com números ===")

asyncio.run(main())
