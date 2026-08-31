"""TR retail rule pack.

Deterministic pattern matching, deliberately not an LLM. This gate exists to
catch what the language model produced, so making it depend on a language
model — the same provider, in the same failure domain — would mean a Groq
outage silently disables the control rather than blocking output. Regexes are
auditable, reproducible, and cost nothing to run on every turn.

Severity drives the verdict:
  CRITICAL -> BLOCK  (a single one is enough)
  HIGH     -> REVISE if the span can be softened, otherwise BLOCK
  MEDIUM   -> REVISE
  LOW      -> noted, does not by itself change the verdict

Turkish is agglutinative, so the patterns match stems with suffix wildcards
(`al` + `malısın(ız)`) rather than whole words. Word boundaries use explicit
character classes because `\\b` mishandles the dotted/dotless i pair.
"""

import re
from typing import Any, Dict, List, Optional

RULE_PACK_VERSION = "TR_RETAIL_2026.08"

SUPPORTED_JURISDICTIONS = frozenset({"TR"})


class Rule:
    def __init__(
        self,
        rule_id: str,
        name: str,
        severity: str,
        pattern: str,
        rationale: str,
        remediation: str,
        replacement: Optional[str] = None,
        strict_only: bool = False,
        requires_personal_data: bool = False,
    ) -> None:
        self.rule_id = rule_id
        self.name = name
        self.severity = severity
        self.regex = re.compile(pattern, re.IGNORECASE | re.UNICODE)
        self.rationale = rationale
        self.remediation = remediation
        #: When present, the remediator can rewrite the span in place and the
        #: finding becomes REVISE-able. When absent, there is no safe edit and
        #: the draft is blocked.
        self.replacement = replacement
        self.strict_only = strict_only
        self.requires_personal_data = requires_personal_data


RULES: List[Rule] = [
    Rule(
        "ADV-001",
        "Personalized investment recommendation",
        "CRITICAL",
        r"\b(al|sat)(malısın|malısınız|manı öneririm|manızı öneririm)\b",
        "Doğrudan alım/satım talimatı, kişiye özel yatırım tavsiyesi sayılır.",
        "Emir kipini kaldırın; yalnızca geçmiş veriyi ve maliyetleri tarafsız biçimde aktarın.",
    ),
    Rule(
        "ADV-002",
        "Explicit recommendation verb",
        "CRITICAL",
        r"(tavsiye ediyorum|tavsiyem|öneriyorum|önerim şu|portföyünüze ekleyin)",
        "Tavsiye fiili, yatırım danışmanlığı yetkisi gerektirir.",
        "Tavsiye ifadesini kaldırın ve bilgilendirici bir çerçeveye geçin.",
    ),
    Rule(
        "ADV-003",
        "Suggestive framing",
        "MEDIUM",
        r"(yerinizde olsam|bence (al|sat)|kaçırmayın|şimdi tam zamanı)",
        "Yönlendirici çerçeveleme, örtük tavsiye olarak okunur.",
        "Yönlendirici ifadeyi nötr bir gözlemle değiştirin.",
        replacement="[yönlendirici ifade kaldırıldı]",
    ),
    Rule(
        "GUA-001",
        "Performance guarantee",
        "CRITICAL",
        r"(garanti(li|dir)?\s+(getiri|kazanç|kâr|kar)|kesin kazanç|risksiz getiri|zarar etmezsiniz|kesinlikle kazan)",
        "Getiri garantisi vaadi her koşulda yasaktır.",
        "Garanti ifadesini tamamen kaldırın; geçmiş performansın gelecek için gösterge olmadığını belirtin.",
    ),
    Rule(
        "GUA-002",
        "Directional certainty",
        "HIGH",
        r"(kesinlikle (yükselecek|düşecek|artacak)|mutlaka (yükselecek|düşecek)|yüzde yüz)",
        "Fiyat yönü hakkında kesinlik iddiası, dayanaksız performans beklentisi yaratır.",
        "Kesinlik iddiasını olasılıksal ve kaynaklı bir ifadeyle değiştirin.",
        replacement="[kesinlik iddiası kaldırıldı]",
    ),
    Rule(
        "GUA-003",
        "Unhedged directional claim",
        "HIGH",
        # A forward-looking verb NOT reached by a conditional or a hedge.
        # `beklenebilir`, `olabilir`, `görünüyor` are excluded because they
        # ARE the hedge; a bare "yükselecek" is not.
        r"\b(yüksele|düşe|arta|kazandıra|katlana|getire)(cak|cek)\b"
        r"(?!\s*(mı|mi|diye|de[mğ]il))"
        r"(?!.{0,60}(belirlemez|garanti etmez|kesin de[gğ]il|diyemem|diyemez|söyleyemem))",
        "Çekinceye bağlanmamış yön iddiası, dayanaksız bir performans "
        "beklentisi yaratır.",
        "Yön okumasını koşula bağlayın ve geçmiş fiyat hareketinin geleceği "
        "belirlemediğini aynı cümlede belirtin.",
        replacement="[çekincesiz yön iddiası kaldırıldı]",
    ),
    # The pattern is unchanged; the REASON is. The system now stores a
    # declared tolerance (`risk.risk_profiles`), so "we hold no profile" is no
    # longer why this is blocked. The ban survives its original justification
    # because the two claims were never the same thing: saying a holding is
    # "size uygun" is a judgement ABOUT the user, while reporting that a
    # measured level sits above a tolerance they themselves declared is a
    # comparison of two stated facts. `profile.suitability` produces the
    # second and deliberately avoids this wording -- a test pins that it does
    # not trip this rule.
    Rule(
        "SUI-001",
        "Suitability claim on personal holdings",
        "HIGH",
        r"(size uygun|sizin için (doğru|ideal|uygun)|risk profilinize uygun)",
        "Uygunluk bir yargıdır; sistem ölçüm ile kullanıcının kendi beyanını "
        "karşılaştırır, bir ürünün kişiye uygunluğuna karar vermez.",
        "Uygunluk iddiasını kaldırın; ölçülen seviye ile beyan edilen toleransı "
        "olgu olarak aktarın.",
        replacement="[uygunluk değerlendirmesi kaldırıldı]",
        requires_personal_data=True,
    ),
    Rule(
        "EXE-001",
        "Execution claimed for a staged proposal",
        "CRITICAL",
        r"(emriniz (iletildi|gerçekleşti|verildi)|işlem (tamamlandı|gerçekleştirildi)|satın alındı|para gönderildi)",
        "Öneri aşamasındaki bir işlem, gerçekleşmiş gibi sunulamaz.",
        "\"Onayınıza hazırlandı\" ifadesini kullanın; hiçbir emir iletilmedi.",
    ),
    Rule(
        "SOL-001",
        "Unauthorized solicitation",
        "MEDIUM",
        r"(hemen hesap açın|şimdi yatırım yapın|bu fırsatı değerlendirin)",
        "Talep yaratıcı dil, izinsiz pazarlama sayılır.",
        "Çağrı cümlesini kaldırın.",
        replacement="[teşvik ifadesi kaldırıldı]",
    ),
    Rule(
        "TON-001",
        "Borderline suggestive tone",
        "LOW",
        r"(cazip görünüyor|iyi bir fırsat|güçlü duruyor)",
        "Değer yargısı içeren nitelemeler, STRICT modda örtük tavsiye sayılır.",
        "Niteleme yerine ölçülen veriyi aktarın.",
        replacement="[değer yargısı kaldırıldı]",
        strict_only=True,
    ),
]


DISCLOSURES: Dict[str, Dict[str, str]] = {
    "DISC-GENERAL": {
        "disclosure_id": "DISC-GENERAL",
        "text": (
            "Bu içerik yatırım danışmanlığı değildir, genel bilgilendirme amaçlıdır. "
            "Geçmiş performans gelecekteki getiriyi garanti etmez."
        ),
        "placement": "APPEND",
    },
    "DISC-PERSONAL": {
        "disclosure_id": "DISC-PERSONAL",
        "text": (
            "Paylaşılan portföy verileri, belirtilen değerleme anına aittir ve "
            "kişiye özel bir uygunluk değerlendirmesi içermez."
        ),
        "placement": "APPEND",
    },
    "DISC-PROPOSAL": {
        "disclosure_id": "DISC-PROPOSAL",
        "text": (
            "Bu bir işlem önerisidir; onaylanana kadar hiçbir emir iletilmemiştir. "
            "Belirtilen tutarlar gösterge niteliğindedir."
        ),
        "placement": "APPEND",
    },
    "DISC-DELAYED": {
        "disclosure_id": "DISC-DELAYED",
        "text": "Piyasa verileri gecikmeli olabilir; anlık fiyatlardan farklılık gösterebilir.",
        "placement": "APPEND",
    },
}


def find_violations(draft: str, strictness: str, contains_personal_data: bool) -> List[Dict[str, Any]]:
    strict = strictness.upper() == "STRICT"
    findings: List[Dict[str, Any]] = []
    for rule in RULES:
        if rule.strict_only and not strict:
            continue
        if rule.requires_personal_data and not contains_personal_data:
            continue
        for match in rule.regex.finditer(draft):
            findings.append(
                {
                    "rule_id": rule.rule_id,
                    "rule_name": rule.name,
                    "severity": rule.severity,
                    "offending_span": {
                        "start": match.start(),
                        "end": match.end(),
                        "text": match.group(0),
                    },
                    "rationale": rule.rationale,
                    "remediation": rule.remediation,
                }
            )
    return findings


def rule_by_id(rule_id: str) -> Optional[Rule]:
    return next((rule for rule in RULES if rule.rule_id == rule_id), None)
