from app.modules.market.kap import validated_kap_url


def test_accepts_exact_kap_hosts_and_preserves_query():
    assert validated_kap_url("https://kap.org.tr/tr/Bildirim/1?a=2#section") == (
        "https://kap.org.tr/tr/Bildirim/1?a=2",
        "kap.org.tr",
    )
    assert validated_kap_url("https://www.kap.org.tr") == (
        "https://www.kap.org.tr/",
        "www.kap.org.tr",
    )


def test_rejects_untrusted_or_malformed_urls():
    rejected = [
        None,
        "",
        "//kap.org.tr/tr/Bildirim/1",
        "http://kap.org.tr/tr/Bildirim/1",
        "javascript:kap.org.tr",
        "https://kap.org.tr.attacker.example/",
        "https://attacker.example/kap.org.tr",
        "https://attacker.example/?next=kap.org.tr",
        "https://user@kap.org.tr/",
        "https://kap.org.tr:444/",
        "https://kap.org.tr:bad/",
    ]
    assert all(validated_kap_url(url) is None for url in rejected)
