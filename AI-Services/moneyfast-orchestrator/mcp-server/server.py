# filename: server.py
"""MoneyFast MCP server entrypoint.

Creates the shared FastMCP instance and binds every domain module to it.
Each module exposes a `register(mcp)` function; the tool callables stay at
module level so they can be imported and unit-tested without a running
server.

Contracts follow "MCP Tools Interface Definitions v2.19" (see
CONTRACT_VERSION below -- that constant is the authority; this paragraph
described v2.9 long after the constant had moved on). It is the union of two
lineages that developed in parallel: v2.4 on main added
get_risk_profile_summary, v2.8 on the banking branch added lookup_bill and
prepare_payment_proposal. Both are kept; the version is bumped past both
rather than to the higher of the two, because "v2.8" would claim main's risk
tool was never added.

The v2.4 lineage, unchanged: the six v2.1 tools
are unchanged, get_market_data was added at v2.2 because v2.1 had no way to
reach the price of an instrument the user does not own, v2.3 put cash on
get_portfolio_positions, and v2.4 adds get_risk_profile_summary -- the risk
score and band are produced by the backend's profile layer and no v2.1 tool
could reach them, so the assistant answered "how risky is my portfolio" with a
volatility figure while the risk page answered with a 0-100 score.

The constant below sat at v2.2 through the v2.3 change; it is corrected here
rather than left drifting further.

Seven of the eight tools call a real HTTP service: get_portfolio_positions,
prepare_transaction_proposal, calculate_portfolio_risk_metrics and
validate_compliance_rules reach the backend, and rag_semantic_market_search
reaches the rag service. Only classify_and_route_intent is computed locally,
because routing needs no state. Nothing here falls back to canned data when a
service is unreachable; every failure raises.

Run:
    pip install "mcp[cli]"
    python server.py                 # stdio transport
    mcp dev server.py                # inspector UI
"""

#from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

import backend_client
import compliance_tools
import cash_flow_tools
import report_tools
import fundamentals_tools
import instrument_tools
import market_data_tools
import market_research_tools
import news_tools
import orchestrator_tools
import portfolio_tools
import risk_strategy_tools
import scenario_tools
import banking_tools
import technical_tools
import transaction_tools

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("moneyfast.mcp")

SERVER_NAME = "moneyfast"
#: v2.9: iki ayrı soydan gelen eklemelerin BİRLEŞİMİ. `main` v2.4'te
#: `get_risk_profile_summary`'i ekledi, bu dal v2.8'de iki bankacılık aracını.
#: İkisi de gerçek ve farklı; birleşmiş sözleşme ikisinden de yeni olduğu için
#: yüksek olanı almak yerine bir üstüne çıkılıyor -- v2.8 demek, main'in risk
#: aracının hiç eklenmediğini söylemek olurdu.
#: v2.10: `get_technical_signals`. `get_market_data`'nın v2.2 şeması
#: DEĞİŞMEDİ -- o "şu an ne ediyor" sorusunun cevabı, hareketli ortalama ise
#: başka bir soru ve başka bir başarısızlık biçimi var (geçmiş ister, ve
#: geçmiş cevaplayamayacak kadar kısa olabilir).
#: v2.11: `get_portfolio_news`. Sahiplik ile haber etiketinin KESİŞİMİ, bir
#: arama değil -- `rag_semantic_market_search` genişletilmedi, çünkü o araç
#: serbest metin sorgusu bekliyor ve "portföyümdeki hisselerle ilgili haber"
#: sorgusu orada gürültü bandında (~0,39) puanlanıyor.
#: v2.12: `get_portfolio_technicals`. `get_technical_signals` TEK sembol
#: alıyor ve portföy geneli onun tekrarı değil: sayı ile değer ayrışabiliyor
#: (ölçüldü -- üç pozisyonun ikisi ortalamasının altında ama değerin %95'i),
#: ve bu ayrımı modele n tane tek-sembol çağrısından çıkarttırmak, her turda
#: biraz farklı bir toplam üretirdi.
#: v2.13: koşullu senaryo, stres testi ve pozisyon simülasyonu. Üçü de
#: ÖLÇÜM: ikisi geçmiş getirilerin aritmetiği, biri gerçekten olan günler.
#: `simulate_position_change` yeni bir yetenek değil -- `/risk/simulate`
#: aylardır yazılmış ve testliydi, hiçbir araç onu çağırmıyordu.
#: v2.14: `get_company_fundamentals`. YENİ VERİ DEĞİL -- 1.011 enstrümanda
#: dolu duran otuz beş alan sohbete taşındı. `GET /market/fundamentals`
#: hepsini zaten veriyordu ve yalnızca hisse detay sayfası okuyordu; ajanın
#: bir şirket hakkında görebildiği her şey fiyat, değişim, hacim ve dört
#: orandan ibaretti. `get_market_data`'nın donuk v2.2 şeması DEĞİŞMEDİ.
#: v2.15: `get_quarterly_financials`. v2.14'ün sahip OLMADIĞI şey: SERİ.
#: O araç alan başına tek güncel değer saklıyor; bu araç her çeyreği ayrı
#: saklıyor ve "son çeyrek kârı" sorusunu cevaplayabilen tek yol. Sağlayıcı
#: çeyrek atlıyor -- 40 hissenin 3'ünde 2025Q3 yok -- dolayısıyla bitişiklik
#: bayrak olarak taşınıyor ve karşılaştırma ona bağlı.
#: v2.19: `resolve_instruments`. Ölçülmüş bir hatanın karşılığı: kullanıcı
#: "türk hava yolları ne durumda" diye sordu, cevapta kaynak olarak üç EKGYO
#: bildirimi listelendi. Yönlendirici `entities.company_names` çıkarıyordu ama
#: orkestratörde o alanı OKUYAN tek satır yoktu, dolayısıyla adı sembole
#: çeviren hiçbir şey yoktu ve arama süzgeçsiz çalıştı.
#: `rag_semantic_market_search` genişletilmedi: "türk hava yolları" ile THYAO
#: arasındaki bağ ölçülen bir benzerlik değil, kayıtlı bir gerçek.
CONTRACT_VERSION = "v2.19"

SERVER_INSTRUCTIONS = """\
MoneyFast tool server. Twenty-one tools across fifteen domains.

Routing: call classify_and_route_intent first on every user turn.
Data:    get_portfolio_positions, get_market_data,
         rag_semantic_market_search and calculate_portfolio_risk_metrics
         return as_of, source and is_delayed at the top level. Propagate
         them.
Prices:  get_market_data is the ONLY source for the price or valuation of an
         instrument the user does not hold. A null fundamental means the
         provider does not publish it; report "veri yok", never 0.
Quarter: get_quarterly_financials is the only tool with a SERIES. Name the
         quarter in every figure, and compare two quarters ONLY when the
         payload says they are adjacent -- the provider skips quarters.
Company: get_company_fundamentals answers "how is the BUSINESS doing" --
         margins, debt, cash flow, analyst consensus. It is a SNAPSHOT, not
         a series: there is no previous period stored, so never say "son
         çeyrek", "arttı" or "düştü" from it. A null field means the
         provider does not publish it, never zero.
Trend:   get_technical_signals answers "how is it DOING" as opposed to "what
         does it cost". Relay its `narrative` verbatim, caveat included; a
         null field there means the history is too short to compute it, and
         you must not describe an indicator that came back null.
         get_portfolio_technicals is the same reading across every HOLDING,
         plus one aggregate sentence. Its COUNT and its WEIGHT are separate
         claims and can point opposite ways; never merge them.
News:    get_portfolio_news is the ONLY tool that links news to what the
         user OWNS. It reports a window; state the window whenever you
         report that nothing was published. It carries no sentiment,
         importance or ranking, and you must not supply one.
Empty:   an empty list is a valid, complete answer. Never substitute
         remembered or illustrative data for it.
What-if: run_portfolio_scenario answers "if X moved", simulate_position_change
         answers "if I traded", get_portfolio_stress_test answers "what
         already happened". All three are ARITHMETIC OVER PAST DATA, never a
         forecast. Relay their statement with its caveat, report the
         assumptions, and never say what a factor will do. There is NO
         interest-rate series: rate scenarios cannot be measured and must not
         be approximated with a currency.
Budget:  get_cash_flow_summary is what someone EARNS and SPENDS, which is a
         different question from what they OWN. Read `income_events` before
         reporting a zero income -- monthly salary means a short window can
         contain none, and "you have no income" is a false statement about
         someone's salary. `monthly_net` is a measured leftover, never a
         recommended investment amount.
Gate:    validate_compliance_rules runs on every user-facing draft that
         references an instrument, a figure, a market view or a
         transaction. Fail closed.
Staging: prepare_transaction_proposal stages only. Nothing in this server
         executes an order. Confirmation happens in the frontend.
"""

mcp = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS, host="0.0.0.0", port=8000)

DOMAIN_MODULES = (
    ("orchestrator", orchestrator_tools),
    ("portfolio", portfolio_tools),
    ("market_data", market_data_tools),
    ("market_research", market_research_tools),
    ("risk_strategy", risk_strategy_tools),
    ("compliance", compliance_tools),
    ("transaction", transaction_tools),
    ("banking", banking_tools),
    ("technical", technical_tools),
    ("news", news_tools),
    ("scenario", scenario_tools),
    ("fundamentals", fundamentals_tools),
    ("cash_flow", cash_flow_tools),
    ("report", report_tools),
    ("instrument", instrument_tools),
)


def build_server() -> FastMCP:
    """Register every domain module against the shared FastMCP instance."""
    for domain, module in DOMAIN_MODULES:
        module.register(mcp)
        log.info("registered domain: %s (%s)", domain, module.__name__)
    log.info(
        "moneyfast mcp ready, contract %s, backend=%s rag=%s",
        CONTRACT_VERSION,
        backend_client.base_url(),
        backend_client.rag_base_url(),
    )
    return mcp


build_server()


if __name__ == "__main__":
    # SADECE SSE İLE ÇALIŞTIR (host ve port'u sildik)
    mcp.run(transport="sse")