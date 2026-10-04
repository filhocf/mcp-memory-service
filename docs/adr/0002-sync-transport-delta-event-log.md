# ADR-0002: Multi-agent sync transport — adopt delta event-log, retire OneDrive file-sync

- **Date:** 2026-10-04
- **Status:** Accepted
- **Deciders:** Claudio (owner), Zero (agent)

## Context

Memory is shared across 3 machines + a VPS. Three transports were proposed across RFCs
and never arbitrated:
- `rfc-hub-memoria-centralizada` **rejects** an event-log ("~70KB/day doesn't justify it")
  and keeps a star-topology **file-sync script**.
- `rfc-delta-sync` proposes a **bidirectional delta event-log** (HLC ordering, optional
  crypto, per-agent sharing; acceptance invariants reviewed by @ducanhnguyen223, #1345).
- Upstream #1304 proposes a hybrid-native remote storage (third path).

**Verified fact that settles it (4/out):** the *actual* transport in use today is neither
the hub script nor delta-sync — it is **OneDrive/Insync syncing whole ~500MB SQLite
`.hot.db` files** between machines (`backup-and-sync.sh` → Insync `SYNC_DIR` → OneDrive →
`sync-memories-incremental.sh` imports missing memories via `memory_store`). The hub's
"70KB/day → script is enough" argument is moot because the real transport ships the whole
database, not deltas. The DB only grows; cloud-drive file-sync of a live SQLite DB is
fragile and does not scale.

## Decision

We will build the **delta event-log sync** (`rfc-delta-sync`) as the robust transport, and
**retire the OneDrive/Insync whole-DB sync**. The event-log ships only new events
(~70KB/day of real deltas), not 500MB snapshots. The acceptance invariants from #1345
(idempotency, HLC ordering + stable tie-break, embedding-pending, authorship scope) are
adopted as RED fixtures before code.

The hub RFC is reclassified to historical context (the prior attempt). Upstream #1304,
when it lands, is **reused** as the native transport layer rather than competed with.

## Alternatives Considered

### Keep OneDrive whole-DB sync (status quo)
- **Pros:** works today; zero build.
- **Cons:** ships 500MB files; fragile (SQLite over cloud-drive = corruption/conflict risk);
  does not scale as the DB grows (owner's stated pain). Must die.
- **Reversibility:** easy to keep, but it's the problem.

### Hub star-topology file-sync script (rfc-hub)
- **Pros:** simple; low volume argument.
- **Cons:** not actually the transport in use; N×N; doesn't propagate deletes; replicates
  consolidation noise. The "low volume" premise assumed deltas, but it ships whole DBs.

### Delta event-log (rfc-delta-sync) — CHOSEN
- **Pros:** ships only deltas; correct (deletes, idempotency, HLC); per-agent scope;
  scales with DB growth.
- **Cons:** more machinery (may look like over-engineering at today's volume) — accepted,
  because the current transport must be replaced regardless.
- **Reversibility:** medium (new subsystem), but the hot-backup remains as a safety net.

## Consequences

- **Positive:** OneDrive stops carrying the live DB; sync scales; correctness invariants.
- **Negative / cost:** build effort; a real subsystem to design/test (not trivial).
- **Neutral / follow-up:** concrete goal = **stop syncing the DB via OneDrive**; hot-backup
  stays as disaster recovery; #1304 reuse to be confirmed when it lands.

## References

- `docs/rfc/planned/rfc-delta-sync.md` (§8 invariants ported, @ef2555ac)
- `docs/rfc/planned/rfc-hub-memoria-centralizada.md` (superseded as transport)
- scripts: `backup-and-sync.sh`, `sync-memories-incremental.sh` (the OneDrive path to retire)
- upstream #1304 (hybrid native), #1345 (delta-sync review)
