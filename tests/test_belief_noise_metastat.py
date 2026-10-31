"""RED tests: _is_noise must reject META-STATISTICS beliefs (#belief-corpus-metastat).

Investigation (31/out) measured ~230 active/candidate beliefs in the live DB that are
META-NOISE escaping `_is_noise`: automatic tag statistics and decision gaps, NOT
actionable knowledge — they occupy top-k slots in search.

These tests call the REAL `_is_noise` imported from
`mcp_memory_service.consolidation.belief_service` (NO mocks, NO stubs of internals),
so they exercise the real filter contract. They FAIL today (RED) because the four
meta-noise shapes below currently return False, and go GREEN when the filter learns to
reject them. The three legit cases guard against over-reach (must stay False).
"""

from mcp_memory_service.consolidation.belief_service import _is_noise


# ── Real cases measured in the live corpus that MUST be rejected (True) ──

# [GAP]: automatic "decision gap" statistic — meta, not a claim.
GAP_CASE = (
    "[GAP] Decision gap: 'shared_tags'\n\n"
    "Tag 'shared_tags' has 189 memories but no decisions recorded. "
    "Consider documenting key decisions for this area."
)

# [PATTERN]: automatic "recurring theme" tag co-occurrence statistic.
PATTERN_CASE = (
    "[PATTERN] Recurring pattern: daia + sa3\n\n"
    "6 memories share tags ['daia', 'sa3'], indicating a recurring theme."
)

# [TREND]: any belief opening with the [TREND] marker is an auto trend statistic.
TREND_CASE = "[TREND] Growing focus on consolidation over the last 30 days."

# Bracket-less variant: the "N memories share tags ... indicating a recurring theme"
# sentence is meta-statistics even without the [PATTERN] bracket.
NOBRACKET_CASE = (
    "6 memories share tags ['injecao', 'learning-loop'], indicating a recurring theme."
)


# ── Legit knowledge that MUST keep passing the filter (False = not noise) ──

LEGIT_PR_COLLISION = (
    "Antes de implementar um fix, verificar se já existe PR aberto para o mesmo "
    "problema (colisão de PRs)."
)

LEGIT_ONTOLOGY = (
    'Filtrar memory_type="observation" literal ignora a hierarquia da ontologia '
    "(models/ontology.py); decisões, aprendizados e erros nunca entram."
)

# Merely MENTIONS "padrão" (pattern) in a legit sentence — must not be caught by mistake.
LEGIT_MENTIONS_PATTERN = "O padrão de retry deve usar backoff exponencial."


class TestMetaStatNoiseRejected:
    """The four meta-statistics shapes must be rejected as noise (True)."""

    def test_gap_decision_statistic_is_noise(self):
        # [GAP] auto decision-gap statistic. FAILS today: returns False.
        assert _is_noise(GAP_CASE) is True

    def test_pattern_recurring_theme_is_noise(self):
        # [PATTERN] auto tag co-occurrence statistic. FAILS today: returns False.
        assert _is_noise(PATTERN_CASE) is True

    def test_trend_marker_is_noise(self):
        # [TREND] auto trend statistic. FAILS today: returns False.
        assert _is_noise(TREND_CASE) is True

    def test_bracketless_share_tags_is_noise(self):
        # "N memories share tags ... recurring theme" sans bracket. FAILS today: False.
        assert _is_noise(NOBRACKET_CASE) is True


class TestLegitBeliefsNotNoise:
    """Anti-regression: legitimate, actionable beliefs stay un-filtered (False)."""

    def test_pr_collision_lesson_not_noise(self):
        assert _is_noise(LEGIT_PR_COLLISION) is False

    def test_ontology_filter_lesson_not_noise(self):
        assert _is_noise(LEGIT_ONTOLOGY) is False

    def test_sentence_mentioning_pattern_not_noise(self):
        assert _is_noise(LEGIT_MENTIONS_PATTERN) is False
