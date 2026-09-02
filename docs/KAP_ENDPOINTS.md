# KAP'ın uçları — ne var, ne veriyor, neye dokunmuyoruz

KAP hiçbir API belgesi yayımlamıyor. Buradaki her satır ya doğrudan çağrılarak
ya da tarayıcının ağ kaydından (`docs/kap-har/`, gitignore'da) okunarak
doğrulandı. Tarih: 2026-09-02.

Hepsi kimlik doğrulaması istemiyor ve dürüst bir `User-Agent`'a cevap veriyor.
**`Referer` başlığı gerekmiyor** — ölçüldü: sahte referrer ile ve olmadan
yanıtlar bayt bayt aynı (122.486 bayt, 236 kayıt).

## Kullandıklarımız

| Uç | Yöntem | Ne verir |
|---|---|---|
| `/tr/api/disclosure/members/byCriteria` | POST | Tarih aralığındaki bildirimler. Gövde `{fromDate, toDate, mkkMemberOidList, subjectList}`, tarihler `YYYY-MM-DD`. **2000 kayıtta kesiyor**, sayfalama yok → pencere ikiye bölünüyor |
| `/tr/api/notification/attachment-detail/{index}` | GET | Gövde (HTML listesi), ek listesi, `disclosureBasic` |
| `/tr/api/file/download/{objId}` | GET | Ek. `Content-Type: application/pdf` diyor ve bu YALAN: serileştirilmiş Java bayt dizisi |

## Ağ kaydından çıkanlar

| Uç | Yöntem | Ne verir |
|---|---|---|
| `/tr/api/member/filter/{sorgu}` | GET | İhraççı kadrosu. `sorgu="a"` **tek istekte 1.124 üye** döndürdü: `{companyCode, mkkMemberOid, title, permaLink}` |
| `/tr/api/ca/allCa/{yıl}/{ay}` | GET | KAP'ın KENDİ kurumsal işlem sınıflandırması, gün gün: `dividendPayment`, `capitalIncreaseDecrease`, `mergerDemergerAssignSubject`, `tenderOffer`, `generalMeeting`, `retirementRight`, `saleOutRight` — şirket adı ve `disclosureIndex` ile |
| `/tr/api/financialTable/listCompanyExcelMembers/{oid}/{yıl}/T` | GET | Hangi finansal raporlar var: `stockCode`, `disclosureIndex`, `year`, `period` |
| `/tr/api/home-financial/download-file/{oid}/{yıl}/T` | GET | Finansal tablolar, **Excel** olarak |
| `/tr/api/disclosure/list/main` | POST | Ana sayfa listesi. Gövde `{fromDate, toDate, memberTypes}` — dikkat, tarihler burada `DD.MM.YYYY`. `byCriteria`'dan daha zengin: `mkkMemberOid`, `disclosureId`, `relatedDisclosureOid`, `isChanged` de geliyor |

İki tanesi tasarımı değiştirdi:

**`allCa`, kurumsal işlemi kendisi sınıflandırıyor.** Türkçe `subject`
metinlerini düzenli ifadeyle eşlemek yerine, yönü en yüksek olayların türü
doğrudan alan adı olarak geliyor. Sınıflandırmada birincil anahtar bu;
`subject` eşlemesi yalnızca `allCa`'nın kapsamadıkları için.

**Finansal tablolar Excel.** `openpyxl` backend'de zaten var ve
`documents.py::_read_xlsx` çalışıyor. Çeyreklik raporlar için Java zarfı ve
çözülemeyen yazı tipi sorununun ikisi de ortadan kalkıyor.

## Dokunmadığımız

Her sayfa yüklemesinden önce onaltılık bir yola bir `POST` gidiyor
(`/6fa9c9ad70eeec80c521dd056692c3150dd6d5c6`): bot tespit işareti. Sürekli
listelemede bizi kısıtlayan şey bu.

**Bunu taklit etmiyoruz.** Tarayıcı gibi görünmeye çalışmak, ingestor
README'sinin açıkça reddettiği şey. Çözüm olduğu yerde kalıyor: daha az istek
(61 pencere yerine tek bir `member/filter`) ve reddedildiğinde geri çekilmek
(`MAX_CONSECUTIVE_FAILURES`).
