"""Tests for per-store domain NER entity extraction."""
import pytest
from mcp_memory_service.reasoning.entities import EntityExtractor


class TestDomainNerPerStore:
    """Entity extraction respects per-store vocabulary."""

    def test_mir_term_extracted_in_mir_store(self):
        """'floresta tipo B' is extracted when store=mir."""
        ext = EntityExtractor()
        entities = ext.extract_entities(
            "Sobreposição com floresta tipo B detectada no imóvel",
            store="mir"
        )
        names = [e.name.lower() for e in entities]
        assert "floresta tipo b" in names

    def test_mir_term_not_extracted_in_rer_store(self):
        """'floresta tipo B' is NOT extracted when store=rer."""
        ext = EntityExtractor()
        entities = ext.extract_entities(
            "Sobreposição com floresta tipo B detectada no imóvel",
            store="rer"
        )
        names = [e.name.lower() for e in entities]
        assert "floresta tipo b" not in names

    def test_rer_term_extracted_in_rer_store(self):
        """'geoserver' is extracted when store=rer."""
        ext = EntityExtractor()
        entities = ext.extract_entities(
            "Deploy geoserver no Kubernetes cluster",
            store="rer"
        )
        names = [e.name.lower() for e in entities]
        assert "geoserver" in names

    def test_rer_term_not_extracted_in_mir_store(self):
        """'geoserver' is NOT extracted when store=mir (not in mir vocab)."""
        ext = EntityExtractor()
        entities = ext.extract_entities(
            "Deploy geoserver no Kubernetes cluster",
            store="mir"
        )
        names = [e.name.lower() for e in entities]
        assert "geoserver" not in names

    def test_global_custom_terms_still_work(self):
        """MCP_ENTITY_CUSTOM_TERMS env var still works (backward compat)."""
        import mcp_memory_service.config as cfg
        original = cfg.MCP_ENTITY_CUSTOM_TERMS
        cfg.MCP_ENTITY_CUSTOM_TERMS = 'TestGlobalTerm'
        EntityExtractor._store_terms_cache = None
        try:
            ext = EntityExtractor()
            entities = ext.extract_entities("This has TestGlobalTerm in it", store="default")
            names = [e.name.lower() for e in entities]
            assert "testglobalterm" in names
        finally:
            cfg.MCP_ENTITY_CUSTOM_TERMS = original
            EntityExtractor._store_terms_cache = None

    def test_unknown_store_uses_default(self):
        """Unknown store falls back to default (no crash)."""
        ext = EntityExtractor()
        entities = ext.extract_entities("Some random content", store="nonexistent")
        # Should not crash, returns whatever default gives
        assert isinstance(entities, list)

    def test_multi_word_term_matched(self):
        """Multi-word terms like 'terra indígena' are matched correctly."""
        ext = EntityExtractor()
        entities = ext.extract_entities(
            "Imóvel sobrepõe terra indígena demarcada",
            store="mir"
        )
        names = [e.name.lower() for e in entities]
        assert "terra indígena" in names

    def test_entity_type_is_domain(self):
        """Per-store terms get entity_type='domain'."""
        ext = EntityExtractor()
        entities = ext.extract_entities("Verificar PRODES nesta área", store="mir")
        domain_ents = [e for e in entities if e.entity_type == 'domain']
        assert len(domain_ents) > 0
        assert any(e.name == 'PRODES' for e in domain_ents)
