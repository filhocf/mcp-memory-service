# Inter-agent inbox — o que falta antes de implementar

Registrado em 18/out, depois de o Claudio apontar que a implementação foi prematura.
`inbox-mms` existe como **experimento de transporte** e não deve ser tratado como
mecanismo de coordenação até as três camadas abaixo existirem.

## Fatos verificados

- **delta-sync ativo e cego a store.** Cron de 30 min (`sync-memories-incremental.sh`),
  sirdata como spoke do hub. Chama `memory_store` **sem `store`**, então importa tudo
  no `default`. Mensagem gravada no store `inbox` não propaga; se propagasse, perderia
  o endereço. Não há caminho funcional de mensagem entre hosts hoje.
- **presença não existe.** O `session-registry` (registro/heartbeat/claims) foi removido
  do boot em 18/out a pedido do Claudio. O orc, nesta versão, não tem tabela de presença
  nem de claims; `work_items` não tem coluna de dono. Presença só se descobre por `ps`.
- **A3 v3 inalcançável do sirdata.** Redis Streams na VPS; API `127.0.0.1:3333` responde
  `000` e `cfnarede.dev` falha no certificado.

## Camadas que faltam na RFC

1. **Presença** — `agente@host@sessão` + `started_at` + `last_seen` + `working_on`,
   TTL de 2× o intervalo de heartbeat. Responde "estou sozinho?" e "quem existe?".
2. **Claim de trabalho** — "sessão X com o item Y até T", renovável. Sem isso, mensagem
   entregue não gera coordenação: falta o vínculo entre mensagem e trabalho.
3. **Roteamento** — mesmo host: entrega direta; outro host: delta-sync store-aware (ou
   A3 quando houver rota); destino ausente: mensagem retida com aviso ao remetente;
   sem delta-sync ativo: declarar explicitamente que o problema é local.

## Perguntas em aberto

1. Presença volta como **tabela no mms** ou como **serviço próprio** (session-registry
   reerguido)? Preferência da T'Pol: tabela no mms, desde que o delta-sync passe a ser
   store-aware — correção pequena e mensurável.
2. Este trabalho pertence ao arco do **mms** ou ao arco do **orc**? Claudio também não
   sabe; decidir quando o orc voltar da atualização.
3. Com 3 sessões locais (mms, orc, mir), como uma fala com a outra e sincroniza esforço?
4. Mesmo problema, multiplicado, para outra máquina com múltiplas sessões.

## Regra

Não escrever mais código de comunicação antes do aval do Claudio sobre a camada de
presença. Transporte sem presença é demo.
