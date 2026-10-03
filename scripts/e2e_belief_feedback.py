"""E2E real — feedback negativo recalibra confiança de belief (L4 learning-loop).
Prova com NÚMEROS: mesma lista de observações, confiança COM vs SEM feedback.
Usa o derive_confidence real do serviço (não mock)."""
import os
from datetime import datetime, timezone

from mcp_memory_service.consolidation.belief import (
    derive_confidence,
    derive_confidence_with_feedback,
    get_feedback_flag_value,
)

now = datetime.now(timezone.utc)
ts = now.timestamp()

def obs(h, rating=None, otype="automated"):
    m = {"observation_type": otype}
    if rating is not None:
        m["user_rating"] = rating
    return {"content_hash": h, "created_at": ts, "metadata": m}

# 3 observações que sustentam um belief
supporting = [obs("h1"), obs("h2"), obs("h3")]
contradicting = []

print("=== E2E: feedback negativo em belief (serviço real) ===")

# Baseline (flag OFF)
os.environ.pop("MCP_BELIEF_USE_FEEDBACK", None)
print(f"flag OFF -> get_feedback_flag_value()={get_feedback_flag_value()}")
conf_baseline = derive_confidence(supporting, contradicting, now)
conf_fb_off = derive_confidence_with_feedback(supporting, contradicting, supporting, now)
print(f"confiança baseline (derive_confidence)      = {conf_baseline:.6f}")
print(f"confiança feedback-aware, flag OFF          = {conf_fb_off:.6f}")
assert abs(conf_baseline - conf_fb_off) < 1e-9, "FALHA R3: flag OFF deve ser idêntico ao baseline"
print("  [R3 OK] flag OFF == baseline (identidade)")

# Flag ON, uma obs-fonte com rating -1 (humano marcou thumbs-down)
os.environ["MCP_BELIEF_USE_FEEDBACK"] = "true"
print(f"\nflag ON -> get_feedback_flag_value()={get_feedback_flag_value()}")
supporting_dr = [obs("h1", rating=-1), obs("h2"), obs("h3")]
conf_fb_on = derive_confidence_with_feedback(supporting_dr, contradicting, supporting_dr, now)
print(f"confiança COM 1 down-rated (flag ON)        = {conf_fb_on:.6f}")
delta = conf_fb_on - conf_baseline
print(f"delta vs baseline                           = {delta:+.6f}")
assert conf_fb_on < conf_baseline, "FALHA R2: down-rated deve BAIXAR a confiança"
print(f"  [R2 OK] confiança caiu {abs(delta):.4f} ({abs(delta)/conf_baseline*100:.1f}%)")

# rating string '-1' também funciona (P3)
supporting_str = [obs("h1", rating="-1"), obs("h2"), obs("h3")]
conf_str = derive_confidence_with_feedback(supporting_str, contradicting, supporting_str, now)
print(f"\nconfiança com rating STRING '-1'            = {conf_str:.6f}")
assert abs(conf_str - conf_fb_on) < 1e-9, "FALHA P3: string '-1' deve == int -1"
print("  [P3 OK] rating '-1' (string) == -1 (int)")

# rating positivo/neutro não penaliza (R5)
supporting_pos = [obs("h1", rating=1), obs("h2"), obs("h3")]
conf_pos = derive_confidence_with_feedback(supporting_pos, contradicting, supporting_pos, now)
print(f"\nconfiança com rating +1 (flag ON)          = {conf_pos:.6f}")
assert abs(conf_pos - conf_baseline) < 1e-9, "FALHA R5: rating +1/neutro não deve mudar"
print("  [R5 OK] rating +1 == baseline (sem penalidade)")

print("\n=== E2E PASSOU: todos os invariantes provados com números ===")
