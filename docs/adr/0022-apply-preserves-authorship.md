# ADR-0022: APPLY preserves original authorship; never re-stamps agent_id (§8.4)

- **Date:** 2026-10-07
- **Status:** Accepted
- **Deciders:** Claudio (owner/client), Zero (agent). Arch input: seven (Gate 1).
- **Scope:** delta-sync (#1345) Phase 4a. Satisfies RFC §8.4.

## Context

§8.4: `agent_id` is the authorship carried by the event; a peer must not publish on behalf
of another agent. When a pulled event is applied locally, the APPLY must not overwrite the
original authorship with the local `MCP_AGENT_ID`.

## Decision

The APPLY **preserves `agent_id`, `event_id` and the HLC** of the remote event exactly as
received, inserting them into the local `sync_events` unchanged (idempotent via
`UNIQUE(agent_id, event_id)`). It NEVER re-stamps authorship with the local identity. The
authenticated transport (bearer/api-key/basic) identifies the *peer* it pulled from; the
`agent_id` inside each event is the *original author*.

## Alternatives Considered

### Re-stamp agent_id with local MCP_AGENT_ID on apply — rejected
- Erases authorship; makes "who wrote this" meaningless across the mesh; violates §8.4.

### Preserve authorship as received — CHOSEN
- Replay keeps original authorship; the UNIQUE(agent_id,event_id) key stays stable across
  peers, so re-sync is idempotent and convergent.

## Consequences

- **Positive:** authorship survives replay; idempotency key is cross-peer stable.
- **Negative / limitation (pull-only):** strong anti-impersonation (peer X cannot inject an
  event claiming agent Y) is a SERVER-SIDE validation deferred to Phase 4b/push. In pull,
  the client trusts the hub it authenticated to. Documented explicitly as a 4a limitation.

## References
- `docs/rfc/planned/rfc-delta-sync.md` §8.4
- ADR-0007 (UNIQUE(agent_id,event_id)), ADR-0018 (pull-only scope)
