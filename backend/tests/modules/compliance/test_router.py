"""Compliance modülü — fail-closed davranışının testleri.

Bu kapının tek bir yönü var: her belirsizlik BLOCK'a çözülür. Testlerin
çoğu, "PASS dönmemesi gereken durumda PASS dönmüyor mu?" sorusunu soruyor.
"""

from __future__ import annotations

from app.modules.compliance import rules, service

URL = "/api/compliance/validate"

CLEAN_DRAFT = (
    "THYAO pozisyonunuz 120 adet ve son kapanışa göre 35.460 TRY değerinde.\n\n"
    + rules.DISCLOSURES["DISC-GENERAL"]["text"]
)


def body(draft: str, **overrides):
    payload = {"draft_response": draft, "user_query": "portföyüm nasıl?"}
    payload.update(overrides)
    return payload


class TestPass:
    def test_clean_draft_with_its_disclosure_passes(self, client):
        result = client.post(URL, json=body(CLEAN_DRAFT)).json()
        assert result["verdict"] == "PASS"
        assert result["violations"] == []
        assert result["remediated_response"] is None
        assert result["blocked_reason_user_facing"] is None

    def test_audit_id_is_always_present(self, client):
        assert client.post(URL, json=body(CLEAN_DRAFT)).json()["audit_id"]

    def test_rule_pack_version_is_reported(self, client):
        result = client.post(URL, json=body(CLEAN_DRAFT)).json()
        assert result["rule_pack_version"] == rules.RULE_PACK_VERSION


class TestCriticalBlocks:
    def test_imperative_advice_is_blocked(self, client):
        result = client.post(URL, json=body("Bence THYAO almalısınız.")).json()
        assert result["verdict"] == "BLOCK"
        assert result["blocked_reason_user_facing"]
        assert result["remediated_response"] is None

    def test_explicit_recommendation_verb_is_blocked(self, client):
        result = client.post(URL, json=body("Size ASELS tavsiye ediyorum.")).json()
        assert result["verdict"] == "BLOCK"

    def test_return_guarantee_is_blocked(self, client):
        result = client.post(URL, json=body("Bu fon garantili getiri sağlar.")).json()
        assert result["verdict"] == "BLOCK"
        assert any(v["rule_id"] == "GUA-001" for v in result["violations"])

    def test_claiming_execution_of_a_staged_proposal_is_blocked(self, client):
        """Öneri aşamasındaki işlem gerçekleşmiş gibi sunulamaz."""
        result = client.post(
            URL, json=body("Emriniz iletildi, 10 adet THYAO satın alındı.")
        ).json()
        assert result["verdict"] == "BLOCK"
        assert any(v["rule_id"] == "EXE-001" for v in result["violations"])

    def test_violation_entries_carry_the_documented_shape(self, client):
        result = client.post(URL, json=body("Bence THYAO almalısınız.")).json()
        violation = result["violations"][0]
        assert set(violation) == {
            "rule_id", "rule_name", "severity", "offending_span", "rationale", "remediation",
        }
        assert set(violation["offending_span"]) == {"start", "end", "text"}

    def test_offending_span_offsets_point_at_the_real_text(self, client):
        draft = "Bence THYAO almalısınız."
        result = client.post(URL, json=body(draft)).json()
        span = result["violations"][0]["offending_span"]
        assert draft[span["start"] : span["end"]] == span["text"]


class TestRevise:
    def test_softenable_finding_is_rewritten_not_blocked(self, client):
        result = client.post(URL, json=body("Yerinizde olsam beklerdim.")).json()
        assert result["verdict"] == "REVISE"
        assert result["remediated_response"]
        assert "Yerinizde olsam" not in result["remediated_response"]

    def test_missing_disclosure_alone_triggers_a_revise(self, client):
        result = client.post(URL, json=body("THYAO pozisyonunuz 120 adet.")).json()
        assert result["verdict"] == "REVISE"
        assert any(d["disclosure_id"] == "DISC-GENERAL" for d in result["required_disclosures"])

    def test_disclosures_appear_verbatim_in_the_remediated_draft(self, client):
        """Sözleşme bunların birebir yazılmasını, kısaltılmamasını,
        çevrilmemesini ve birleştirilmemesini şart koşuyor."""
        result = client.post(URL, json=body("THYAO pozisyonunuz 120 adet.")).json()
        for disclosure in result["required_disclosures"]:
            assert disclosure["text"] in result["remediated_response"]

    def test_a_draft_that_already_has_a_disclosure_is_not_asked_to_repeat_it(self, client):
        result = client.post(URL, json=body(CLEAN_DRAFT)).json()
        assert result["required_disclosures"] == []

    def test_multiple_spans_are_all_rewritten(self, client):
        """Sağdan sola düzeltme: soldan sağa gidilseydi ilk değişiklik
        sonraki span'ların offset'lerini kaydırır ve metni bozardı."""
        draft = "Yerinizde olsam alırdım, kaçırmayın, şimdi tam zamanı."
        result = client.post(URL, json=body(draft)).json()
        assert result["verdict"] == "REVISE"
        for fragment in ("Yerinizde olsam", "kaçırmayın", "şimdi tam zamanı"):
            assert fragment not in result["remediated_response"]

    def test_remediation_preserves_the_surrounding_text(self, client):
        result = client.post(
            URL, json=body("THYAO 120 adet. Yerinizde olsam beklerdim. Toplam 35.460 TRY.")
        ).json()
        assert "THYAO 120 adet." in result["remediated_response"]
        assert "Toplam 35.460 TRY." in result["remediated_response"]


class TestContextSensitiveRules:
    def test_suitability_claim_only_fires_on_personal_data(self, client):
        neutral = client.post(URL, json=body("Bu ürün size uygun olabilir." )).json()
        personal = client.post(
            URL, json=body("Bu ürün size uygun olabilir.", contains_personal_data=True)
        ).json()
        assert not any(v["rule_id"] == "SUI-001" for v in neutral["violations"])
        assert any(v["rule_id"] == "SUI-001" for v in personal["violations"])

    def test_strict_mode_flags_borderline_tone(self, client):
        draft = "THYAO güçlü duruyor."
        standard = client.post(URL, json=body(draft)).json()
        strict = client.post(URL, json=body(draft, strictness="STRICT")).json()
        assert not any(v["rule_id"] == "TON-001" for v in standard["violations"])
        assert any(v["rule_id"] == "TON-001" for v in strict["violations"])

    def test_transaction_proposals_require_the_proposal_disclosure(self, client):
        result = client.post(
            URL, json=body("Öneri hazırlandı.", contains_transaction_proposal=True)
        ).json()
        assert any(d["disclosure_id"] == "DISC-PROPOSAL" for d in result["required_disclosures"])

    def test_personal_data_requires_the_personal_disclosure(self, client):
        result = client.post(
            URL, json=body("Portföyünüz 100 TRY.", contains_personal_data=True)
        ).json()
        assert any(d["disclosure_id"] == "DISC-PERSONAL" for d in result["required_disclosures"])

    def test_a_data_tool_requires_the_delay_disclosure(self, client):
        result = client.post(
            URL, json=body("THYAO 295 TRY.", tools_used=["get_portfolio_positions"])
        ).json()
        assert any(d["disclosure_id"] == "DISC-DELAYED" for d in result["required_disclosures"])

    def test_a_routing_only_tool_does_not(self, client):
        result = client.post(
            URL, json=body("Merhaba.", tools_used=["classify_and_route_intent"])
        ).json()
        assert not any(d["disclosure_id"] == "DISC-DELAYED" for d in result["required_disclosures"])


class TestJurisdiction:
    def test_unknown_jurisdiction_is_rejected_not_defaulted(self, client):
        """Bilinmeyen bir yetki alanı, kural olmadığı anlamına gelmez;
        kuralların bilinmediği anlamına gelir."""
        response = client.post(URL, json=body(CLEAN_DRAFT, jurisdiction="XX"))
        assert response.status_code == 400
        assert "XX" in response.json()["detail"]

    def test_tr_is_accepted_case_insensitively(self, client):
        assert client.post(URL, json=body(CLEAN_DRAFT, jurisdiction="tr")).status_code == 200


class TestUnremediableFindingFailsClosed:
    def test_a_non_critical_rule_without_a_safe_rewrite_blocks(self, client, monkeypatch):
        """Bir kural `replacement` tanımlamadan eklenirse, kısmen temizlenmiş
        bir taslak yayımlanmamalı. Bugün kural paketindeki her non-CRITICAL
        kuralın düzeltmesi var; bu test, biri düzeltmesiz eklendiğinde
        davranışın BLOCK olarak kaldığını garanti eder."""
        unsafe = rules.Rule(
            "TST-001",
            "Rule with no safe rewrite",
            "HIGH",
            r"belirsiz ifade",
            "Test amaçlı kural.",
            "Elle yeniden yazın.",
            replacement=None,
        )
        monkeypatch.setattr(rules, "RULES", rules.RULES + [unsafe])

        result = client.post(URL, json=body("Burada belirsiz ifade var.")).json()
        assert result["verdict"] == "BLOCK"
        assert result["remediated_response"] is None
        assert result["blocked_reason_user_facing"]


class TestRemediationInternals:
    def test_a_finding_with_no_safe_rewrite_falls_through_to_block(self):
        """HIGH bulgular arasında replacement'ı olmayan biri varsa, kısmen
        temizlenmiş taslak yayımlanmaz.

        Kural GUA-001 (getiri garantisi): bir garanti vaadinin güvenli bir
        yeniden yazımı YOK -- cümleden çıkarılabilecek bir parça değil, iddia
        cümlenin kendisi."""
        violations = [
            {
                "rule_id": "GUA-001",
                "offending_span": {"start": 0, "end": 5, "text": "dummy"},
            }
        ]
        assert service._remediate("dummy metin", violations) is None

    def test_an_unknown_rule_id_also_blocks(self):
        violations = [{"rule_id": "NOPE-999", "offending_span": {"start": 0, "end": 1, "text": "x"}}]
        assert service._remediate("x", violations) is None

    def test_prepend_disclosures_go_before_the_draft(self):
        text = service._append_disclosures(
            "gövde", [{"text": "önce", "placement": "PREPEND"}, {"text": "sonra", "placement": "APPEND"}]
        )
        assert text == "önce\n\ngövde\n\nsonra"

    def test_rule_lookup_returns_none_for_an_unknown_id(self):
        assert rules.rule_by_id("NOPE-999") is None


class TestHealth:
    def test_health_reports_the_module(self, client):
        assert client.get("/api/compliance/health").json() == {
            "status": "ok", "module": "compliance",
        }


class TestRebalanceContext:
    """ADV-001 ve ADV-002 yeniden dengeleme bağlamında koşullu.

    Kural KALKMIYOR, şiddeti düşüyor. Fark ölçülebilir: engellenen bir cevap
    kullanıcıya hiç ulaşmıyor, düzeltilen bir cevap uygunluk katmanının kendi
    yeniden yazımıyla ulaşıyor ve denetim kaydında iz bırakıyor.
    """

    DRAFT = "Dengeleme listesine göre THYAO satmalısınız."

    def test_outside_the_context_it_still_blocks(self):
        result = service.validate(
            {"draft_response": self.DRAFT, "jurisdiction": "TR", "tools_used": []}
        )
        assert result["verdict"] == "BLOCK"

    def test_inside_the_context_it_is_revised_not_blocked(self):
        result = service.validate({
            "draft_response": self.DRAFT, "jurisdiction": "TR",
            "tools_used": ["get_rebalance_plan"],
        })
        assert result["verdict"] == "REVISE"
        assert "[emir kipi kaldırıldı]" in result["remediated_response"]

    def test_the_finding_is_still_reported(self):
        """Gevşeyen şey şiddet; bulgu kaybolmuyor. Kaybolsaydı denetim kaydı
        gevşemenin ne sıklıkta işlediğini söyleyemezdi."""
        result = service.validate({
            "draft_response": self.DRAFT, "jurisdiction": "TR",
            "tools_used": ["get_rebalance_plan"],
        })
        assert [v["rule_id"] for v in result["violations"]] == ["ADV-001"]
        assert result["violations"][0]["severity"] == "MEDIUM"

    def test_a_guarantee_is_not_relaxed_by_the_context(self):
        """Gevşeme yalnızca `relaxed_in` yazan iki kuralda. Bir getiri
        garantisi hiçbir bağlamda kabul edilebilir değil."""
        result = service.validate({
            "draft_response": "Bu liste ile garantili getiri elde edersiniz.",
            "jurisdiction": "TR", "tools_used": ["get_rebalance_plan"],
        })
        assert result["verdict"] == "BLOCK"

    def test_another_tool_does_not_open_the_context(self):
        result = service.validate({
            "draft_response": self.DRAFT, "jurisdiction": "TR",
            "tools_used": ["get_portfolio_positions", "calculate_portfolio_risk_metrics"],
        })
        assert result["verdict"] == "BLOCK"

    def test_an_unknown_context_name_changes_nothing(self):
        """Yazım hatasıyla gevşeyen bir kural paketi, gevşemeyi ölçülemez
        yapardı."""
        found = rules.find_violations(
            self.DRAFT, "STANDARD", False, frozenset({"REBALANC"})
        )
        assert found[0]["severity"] == "CRITICAL"

    def test_the_rule_pack_version_moved_with_the_change(self):
        """Denetim kaydı hangi kural paketinin uygulandığını söylüyor; paket
        değişip sürüm kalsaydı iki farklı davranış aynı sürümle kaydedilirdi."""
        assert rules.RULE_PACK_VERSION == "TR_RETAIL_2026.09"
