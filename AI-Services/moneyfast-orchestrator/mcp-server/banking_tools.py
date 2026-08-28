# filename: banking_tools.py
"""Banking domain tools: look a bill up, and PREPARE a payment.

MoneyFast MCP server. New in contract v2.8.

The important thing about this module is what it cannot do. There is no
`execute_payment` and there will not be one: every tool here stops at a
proposal, and the money moves only when the user presses Onayla in the
interface. That is the same contract the investment side already holds for
orders, and the reason is the same -- an assistant acting on its own reading
of "evet" is an assistant that can empty an account on a misheard word.

Administrator endpoints are deliberately absent too. Nothing here can credit a
balance, grant a holding or issue a bill, however the conversation is phrased.
"""

# from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

import backend_client
from backend_client import ContractViolationError

LOOKUP_TOOL = "lookup_bill"
STAGE_TOOL = "prepare_payment_proposal"

#: The only payment kinds a conversation can prepare.
PAYMENT_TYPES = frozenset({"TRANSFER", "BILL_PAYMENT", "CARD_PAYMENT"})


async def lookup_bill(institution: str, subscriber_no: str) -> dict[str, Any]:
    """Bir abone numarasına ait ödenmemiş faturayı sorgular.

    Fatura KİMSEYE ait değildir; abone numarasıyla bulunur. Kağıdın üzerindeki
    numara anahtardır ve o numarayı bilen öder. Bu yüzden "faturalarım" diye
    bir liste yoktur ve bu araç bir kullanıcının borçlarını listelemez --
    yalnızca verilen numaraya ait açık borcu söyler.

    WHEN TO USE
        - Kullanıcı bir faturayı sormuşsa ve kurum ile abone numarası
          elinizdeyse: "BEDAŞ 123456 numaralı aboneliğin borcu ne kadar",
          "su faturamı sorgula, abone no 900112".
        - Ödeme önerisi hazırlamadan ÖNCE tutarı teyit etmek için. Öneri
          tutarı zaten faturadan alır, ama kullanıcıya ne ödeyeceğini
          söylemek için borcu önce okumak gerekir.

    WHEN NOT TO USE
        - Kurum veya abone numarası eksikse. TEK bir soru sorup öğrenin;
          numara UYDURMAYIN. Yanlış numara başka birinin faturasıdır.
        - Kullanıcının bütün faturalarını listelemek için. Böyle bir kavram
          yok: fatura kullanıcıya değil numaraya bağlıdır.
        - Ödeme yapmak için. Bu araç yalnızca okur; ödeme
          `prepare_payment_proposal` ile hazırlanır ve kullanıcı onaylar.
        - Geçmiş/ödenmiş faturaları görmek için. Yalnızca AÇIK borç döner.

    Args:
        institution (str): Kurum adı, örn. "BEDAŞ", "İSKİ", "Turkcell",
            "Türk Telekom". Kullanıcının yazdığı biçimde iletin.
        subscriber_no (str): Faturanın üzerindeki abone numarası. Boşluk ve
            biçim kullanıcının verdiği gibi bırakılır.

    Returns:
        dict: Şu alanlarla:
            found (bool): Açık fatura var mı.
            institution (str | None): Kurum adı, yalnızca found=True ise.
            subscriber_no (str | None): Abone numarası, yalnızca found=True ise.
            amount (float | None): Borç tutarı, yalnızca found=True ise.
            due_day (int | None): Ayın kaçında son ödeme günü olduğu.

        found=False bir HATA DEĞİLDİR. "Bu numaraya ait ödenmemiş fatura yok"
        geçerli ve tam bir cevaptır; kullanıcıya böyle söyleyin, sistemin
        çalışmadığı izlenimi vermeyin.

    Raises:
        ContractViolationError: Yanıtta `found` yoksa. Eksik bir alan
            varsayılana çekilmez; sözleşme ihlali olarak bildirilir.
        UpstreamUnavailableError: Backend'e ulaşılamadığında.

    Constraints:
        - Yalnızca OKUR. Hiçbir argüman kombinasyonu para hareket ettirmez.
        - Tutarı siz belirlemezsiniz; tutar faturanın kendisindedir.
        - Bulunamayan fatura için tahmin yürütmeyin, tutar uydurmayın.
        - Bir abone numarası için aynı anda EN FAZLA BİR açık fatura vardır.
          Ödenen fatura kapanır ve bir sonraki dönemin faturası ayrı bir
          kayıt olarak açılır; yani "bu ayınki" diye ayrıca sormanız gerekmez,
          dönen borç zaten güncel olandır.

    Kurum adları
        Sistemde tanımlı kurumlar yöneticinin girdiği adlarla eşleşir.
        Yaygın olanlar: "BEDAŞ" (elektrik), "İSKİ" (su), "Türk Telekom"
        (internet), "Turkcell" (telefon). Kullanıcı "elektrik faturam" derse
        kurumu ona sorun; hangi dağıtım şirketi olduğunu VARSAYMAYIN --
        Türkiye'de elektrik dağıtımı bölgeye göre değişir ve yanlış kurum
        yanlış aboneliktir.

    Ödeme ile ilişkisi
        Bu araç sorgular, `prepare_payment_proposal` ödemeyi HAZIRLAR,
        kullanıcı onaylar. Üç ayrı adım ve sırası önemli: sorgulamadan
        hazırlanan bir öneri kullanıcının görmediği bir tutarı onaylatır.
        Tipik akış:
            1. lookup_bill -> borcu kullanıcıya söyleyin,
            2. kullanıcı ödemek isterse prepare_payment_proposal,
            3. onay arayüzde, sizin elinizde değil.

    Kayıtlı işlemler
        Kullanıcı bir abone numarasını "kayıtlı işlemlerine" eklemişse, o
        numarayı tekrar sormanıza gerek kalmayabilir; ama kayıtlı listeyi bu
        araç döndürmez. Numara elinizde yoksa sorun, hatırladığınızı
        varsaymayın -- bir önceki turda geçen bir numara ile bu turda
        kastedilen numara aynı olmak zorunda değildir.
    """
    payload = await backend_client.request(
        "GET",
        "/banking/bills/lookup",
        tool=LOOKUP_TOOL,
        params={"institution": institution, "subscriber_no": subscriber_no},
    )
    if not isinstance(payload, dict) or "found" not in payload:
        raise ContractViolationError(f"{LOOKUP_TOOL}: response must carry `found`.")

    if not payload.get("found"):
        return {"found": False}
    return {
        "found": True,
        "institution": payload.get("institution"),
        "subscriber_no": payload.get("subscriber_no"),
        "amount": payload.get("amount"),
        "due_day": payload.get("due_day"),
    }


async def prepare_payment_proposal(
    user_id: str,
    payment_type: str,
    idempotency_key: str,
    amount: Optional[float] = None,
    destination: Optional[str] = None,
    institution: Optional[str] = None,
    subscriber_no: Optional[str] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    """Bir ödeme ÖNERİSİ hazırlar. Para HAREKET ETMEZ.

    Bu araç hiçbir şeyi ödemez. Bir öneri kaydı üretir ve orada durur; tutar
    ancak kullanıcı arayüzdeki "Onayla" düğmesine kendi eliyle bastığında
    hesaptan çıkar. Sohbette "evet", "tamam", "onaylıyorum" demek ONAY
    SAYILMAZ ve bu aracın hiçbir argümanı o adımı atlatmaz.

    Yatırım tarafındaki `prepare_transaction_proposal` ile aynı sözleşme,
    aynı sebeple: kendi başına işlem yapan bir asistan, yanlış duyduğu bir
    kelimeyle hesabı boşaltabilen bir asistandır.

    `user_id` doğrulanmış oturum zarfından gelir, kullanıcının yazdığı bir
    değerden değil. Kullanıcının kendi hesabı backend'de çözülür, sorulmaz.

    WHEN TO USE
        - Kullanıcı somut bir ödeme niyeti belirtmişse ve gerekli bilgiler
          elinizdeyse: "BEDAŞ faturamı öde, abone no 900112", "Ayşe'ye 500 TL
          gönder", "kredi kartı borcumu öde".
        - Kullanıcı bir ödemenin ne tutacağını görmek istiyorsa. Öneri
          bağlayıcı değildir; göstermek için hazırlamak doğrudur.

    WHEN NOT TO USE
        - Kullanıcı düşünüyorsa, soruyorsa ya da "ödesem mi" diyorsa. Öneri
          hazırlamak, verilmemiş bir kararı verilmiş gibi gösterir.
        - Gerekli bilgi eksik veya belirsizse (hangi kurum, hangi abone no,
          ne kadar, kime). TEK bir soru sorun. Tutar, IBAN, abone numarası
          UYDURMAYIN -- yanlış alıcıya gitmiş para geri gelmez.
        - Bir ödemeyi gerçekleştirmek, onaylamak veya kesinleştirmek için.
          Onay bu katmanda YOKTUR.
        - Bakiye yüklemek, hesaba para eklemek, hisse tanımlamak için. Bunlar
          yönetici işlemleridir ve bu sunucuda hiçbir aracı yoktur.

    Args:
        user_id (str): Doğrulanmış oturumdan gelen kullanıcı kimliği.
            Kullanıcının yazdığı bir değer DEĞİLDİR; sohbet zarfından gelir.
        payment_type (str): "TRANSFER", "BILL_PAYMENT" veya "CARD_PAYMENT".
            Başka bir değer sözleşme ihlalidir.
        idempotency_key (str): Tekrarlanan çağrının aynı öneriye çözülmesini
            sağlar. Aynı niyet için aynı anahtarı kullanın; yeniden üretmek
            kullanıcıya iki ayrı bekleyen ödeme gösterir.
        amount (float | None): Tutar. BILL_PAYMENT için YOK SAYILIR: tutar
            faturanın kendisinden gelir, çağıranın söylediğinden değil. Bu
            kasıtlıdır -- yanlış tutar söyleyen bir tur eksik ya da fazla
            ödeme yaptıramaz.
        destination (str | None): TRANSFER için alıcı IBAN veya hesap no.
        institution (str | None): BILL_PAYMENT için kurum adı.
        subscriber_no (str | None): BILL_PAYMENT için abone numarası.
        description (str | None): İsteğe bağlı açıklama.

    Returns:
        dict: Şu alanlarla:
            proposal_id (str): Onay adımının kullanacağı kimlik.
            status (str): "PENDING" -- bekleyen, uygulanmamış.
            payment_type (str): Hazırlanan ödemenin türü.
            amount (float): Onaylanırsa çıkacak tutar.
            currency (str): Tutarın para birimi.
            destination (str | None): Alıcı ya da abone numarası.
            description (str | None): Açıklama.
            expires_at (str): ISO 8601. Bu andan sonra öneri onaylanamaz.

    Raises:
        ContractViolationError: payment_type geçersizse ya da yanıtta
            zorunlu bir alan eksikse. Kimliği veya son kullanma zamanı olmayan
            bir öneri, kullanıcıdan onayı istenebilecek bir öneri değildir.
        InvalidInputError: Bakiye yetersizse, fatura bulunamazsa, alıcı hesap
            geçersizse. Kullanıcıya sebebi olduğu gibi aktarılır.
        UpstreamUnavailableError: Backend'e ulaşılamadığında.

    Constraints:
        - PARA HAREKET ETTİRMEZ. Onay kullanıcının kendi eylemidir.
        - Fatura ödemesinde tutarı siz belirlemezsiniz.
        - Kaynak hesap sorulmaz; kullanıcının kendi hesabı backend'de çözülür.
        - Yönetici uçlarına erişimi yoktur; bakiye yükleme, hisse tanımlama
          ve fatura oluşturma bu sunucudan yapılamaz.
    """
    if payment_type not in PAYMENT_TYPES:
        raise ContractViolationError(
            f"{STAGE_TOOL}: payment_type must be one of {sorted(PAYMENT_TYPES)}."
        )

    payload = await backend_client.request(
        "POST",
        "/banking/payments/stage",
        tool=STAGE_TOOL,
        headers={"Idempotency-Key": idempotency_key},
        json_body={
            "user_id": user_id,
            "payment_type": payment_type,
            "amount": amount,
            "destination": destination,
            "institution": institution,
            "subscriber_no": subscriber_no,
            "description": description,
            "idempotency_key": idempotency_key,
        },
    )
    return _normalize(payload)


def _normalize(payload: Any) -> dict[str, Any]:
    """Project the backend response onto the frozen payload.

    Every field is required. A proposal missing its id or its expiry is not a
    proposal the user can be asked to confirm, so a gap is a contract
    violation rather than something to default.
    """
    if not isinstance(payload, dict):
        raise ContractViolationError(f"{STAGE_TOOL}: response must be an object.")

    required = ("proposal_id", "status", "payment_type", "amount", "currency", "expires_at")
    missing = [key for key in required if payload.get(key) is None]
    if missing:
        raise ContractViolationError(
            f"{STAGE_TOOL}: response is missing {', '.join(missing)}."
        )

    return {
        "proposal_id": payload["proposal_id"],
        "status": payload["status"],
        "payment_type": payload["payment_type"],
        "amount": payload["amount"],
        "currency": payload["currency"],
        "destination": payload.get("destination"),
        "description": payload.get("description"),
        "expires_at": payload["expires_at"],
    }


def register(mcp: FastMCP) -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(lookup_bill)
    mcp.tool()(prepare_payment_proposal)
