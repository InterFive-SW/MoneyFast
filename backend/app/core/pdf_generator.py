import logging
from fpdf import FPDF
from datetime import datetime
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)

class MoneyFastPDF(FPDF):
    """
    Kurumsal MoneyFast PDF Şablon Sınıfı.
    
    KVKK/GDPR kapsamında kullanıcıların veri dışa aktarma taleplerinde kullanılacak
    olan bu sınıf, belge başlığı, kurumsal footer (altbilgi) ve sayfa numaralandırma
    işlemlerini otomatik olarak gerçekleştirir. Temiz ve profesyonel bir tipografi 
    kullanarak verilerin okunabilirliğini artırır.
    """
    
    def header(self):
        """
        Sayfa üstbilgisi (Header) oluşturur.
        
        MoneyFast kurumsal kimliğini yansıtan başlık ve doküman tipini
        her sayfanın en üstünde gösterir. Logo ekler.
        """
        logo_path = "/app/assets/logo-inline.png"
        if os.path.exists(logo_path):
            # Logoyu sayfanın üst orta kısmına yerleştir
            self.image(logo_path, x='C', y=10, w=50)
            self.ln(15)
        
        banner_path = "/app/assets/8.png"
        if os.path.exists(banner_path):
            self.image(banner_path, x='C', y=30, w=40)
            self.ln(30)
        else:
            self.set_font('Helvetica', 'B', 20)
            self.set_text_color(26, 31, 46)  # Kurumsal Koyu Mavi
            self.cell(0, 10, 'MoneyFast', ln=True, align='C')
        
        self.set_font('Helvetica', 'I', 12)
        self.set_text_color(113, 128, 150)  # Gri Alt Başlık
        self.cell(0, 10, 'Kisisel Veriler ve Portfoy Ozeti', ln=True, align='C')
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(10)

    def footer(self):
        """
        Sayfa altbilgisi (Footer) oluşturur.
        """
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(160, 174, 192)
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y() - 2, 200, self.get_y() - 2)
        
        page_info = f"Sayfa {self.page_no()}/{{nb}}"
        date_info = f"Olusturulma Tarihi: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        self.cell(0, 10, f"{date_info} | {page_info}", align='C')


def generate_user_data_pdf(user_data: Dict[str, Any], portfolio_summary: Dict[str, Any], output_path: str) -> None:
    try:
        pdf = MoneyFastPDF()
        pdf.alias_nb_pages()
        pdf.add_page()
        
        def section_title(title: str):
            pdf.set_font('Helvetica', 'B', 14)
            pdf.set_text_color(26, 31, 46)
            pdf.set_fill_color(241, 245, 249) # Light slate
            pdf.cell(0, 12, f"   {title}", ln=True, fill=True, border=0)
            pdf.ln(5)

        def add_row(label: str, value: Any, border_bottom: bool = True):
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(74, 85, 104)
            pdf.cell(60, 10, f"  {label}", border='B' if border_bottom else 0)
            pdf.set_font('Helvetica', '', 11)
            pdf.set_text_color(26, 31, 46)
            pdf.cell(0, 10, str(value), border='B' if border_bottom else 0, ln=True)

        # 1. KİŞİSEL BİLGİLER BÖLÜMÜ
        section_title("1. Kisisel Bilgiler")
        profile = user_data.get("profile", {})
        add_row("Ad Soyad:", f"{profile.get('first_name', '')} {profile.get('last_name', '')}")
        add_row("TC Kimlik No:", profile.get("tc_no", "-"))
        add_row("E-posta:", profile.get("email", "-"))
        add_row("Telefon:", profile.get("phone_number", "-"))
        add_row("Uyelik Tarihi:", profile.get("created_at", "-"), border_bottom=False)
        
        pdf.ln(10)
        
        # 2. PORTFÖY ÖZETİ BÖLÜMÜ
        section_title("2. Portfoy Ozeti")
        add_row("Toplam Bakiye:", f"{portfolio_summary.get('total_value', 0):,.2f} TRY")
        add_row("Nakit Bakiye:", f"{portfolio_summary.get('cash', 0):,.2f} TRY")
        add_row("BIST Hisseleri:", f"{portfolio_summary.get('bist', 0):,.2f} TRY")
        add_row("ABD Hisseleri:", f"{portfolio_summary.get('us', 0):,.2f} TRY", border_bottom=False)
        
        pdf.ln(15)
        
        # KVKK Uyarısı
        pdf.set_font('Helvetica', 'I', 9)
        pdf.set_text_color(160, 174, 192)
        kvkk_text = (
            "YASAL UYARI: Bu belge, 6698 sayili Kisisel Verilerin Korunmasi Kanunu (KVKK) "
            "ve AB Genel Veri Koruma Tuzugu (GDPR) kapsaminda, kullanicinin talebi uzerine "
            "otomatik olarak uretilmistir. Icerdigi veriler yuksek gizlilik derecesine "
            "sahiptir. Belgenin ucuncu kisilerle paylasimi tamamen kullanici sorumlulugundadir."
        )
        pdf.multi_cell(0, 5, kvkk_text)
        
        pdf.output(output_path)
        logger.info(f"PDF belgesi basariyla olusturuldu: {output_path}")
        
    except Exception as e:
        logger.error(f"PDF olusturma surecinde kritik hata: {str(e)}")
        raise


#: Türkçe yazabilen font. `fpdf`'in gömülü çekirdek fontları (Helvetica,
#: Times) latin-1 ve ı, ş, ğ harflerini TAŞIMIYOR -- yukarıdaki KVKK dışa
#: aktarımı bu yüzden "Kisisel", "Olusturulma" diye yazmak zorunda kalmış.
#:
#: Backend imajına `fonts-dejavu-core` paketiyle geliyor (bkz. Dockerfile).
#: Dosya bulunamazsa PDF ÜRETİLMİYOR: aksanları düşürülmüş Türkçe, yanlış
#: yazılmış Türkçedir ve kullanıcıya gösterilen bir belgede sessizce bozuk
#: metin, hiç belge olmamasından kötüdür.
DEJAVU_DIR = "/usr/share/fonts/truetype/dejavu"
DEJAVU_REGULAR = f"{DEJAVU_DIR}/DejaVuSans.ttf"
DEJAVU_BOLD = f"{DEJAVU_DIR}/DejaVuSans-Bold.ttf"


class UnicodeFontMissing(RuntimeError):
    """Türkçe yazabilen font kurulu değil."""


class ReportPDF(FPDF):
    """Detaylı rapor şablonu.

    `MoneyFastPDF`'ten AYRI ve bilerek: o, KVKK dışa aktarımı için yazılmış,
    kendi başlığını ("Kisisel Veriler ve Portfoy Ozeti") her sayfaya basıyor
    ve latin-1 fontla çalışıyor. İkisini tek sınıfa sıkıştırmak, birinin
    başlığını değiştiren birinin diğerini bozmasına açık olurdu.
    """

    def __init__(self) -> None:
        super().__init__()
        if not (os.path.exists(DEJAVU_REGULAR) and os.path.exists(DEJAVU_BOLD)):
            raise UnicodeFontMissing(DEJAVU_REGULAR)
        self.add_font("DejaVu", "", DEJAVU_REGULAR)
        self.add_font("DejaVu", "B", DEJAVU_BOLD)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self) -> None:
        logo_path = "/app/assets/logo-inline.png"
        if os.path.exists(logo_path):
            self.image(logo_path, x=10, y=8, w=32)
        self.set_font("DejaVu", "B", 15)
        self.set_text_color(26, 31, 46)
        self.cell(0, 12, "Detaylı Rapor", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(226, 232, 240)
        self.line(10, self.get_y() + 1, 200, self.get_y() + 1)
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(160, 174, 192)
        self.cell(0, 10, f"MoneyFast · Sayfa {self.page_no()}/{{nb}}", align="C")


def generate_report_pdf(report: Dict[str, Any]) -> bytes:
    """Raporu PDF'e basar ve baytları döndürür.

    Metin ÜRETMİYOR. Bölüm başlıkları, cümleleri ve satırları
    `analytics/report.py`'de bir kez kuruluyor; burası yalnızca onları
    sayfaya yerleştiriyor. Ekran, sohbet ve PDF aynı metni okumalı, ve
    PDF'in kendi cümlesini kurması bu kuralın en kolay kırıldığı yer olurdu.

    Dosyaya değil BAYTA yazıyor: raporun diskte bir izi kalmıyor ve
    pozisyonları, bakiyeyi, maaşı bir arada taşıyan bir belgenin geçici
    dizinde unutulması, temizlenmesi hatırlanması gereken bir şey olurdu.
    """
    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(113, 128, 150)
    for line in _meta_lines(report):
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for section in report.get("sections") or []:
        pdf.set_font("DejaVu", "B", 12)
        pdf.set_text_color(26, 31, 46)
        pdf.set_fill_color(241, 245, 249)
        pdf.cell(0, 9, f"  {section.get('title', '')}", fill=True,
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        if section.get("summary"):
            pdf.set_font("DejaVu", "B", 10)
            pdf.set_text_color(45, 55, 72)
            _wrapped(pdf, section["summary"], 5.5)
            pdf.ln(1)

        pdf.set_font("DejaVu", "", 9.5)
        pdf.set_text_color(74, 85, 104)
        for line in section.get("lines") or []:
            _wrapped(pdf, f"·  {line}", 5)
        pdf.ln(4)

    return bytes(pdf.output())


def _wrapped(pdf: FPDF, text: str, height: float) -> None:
    """Sarmalanan bir metin bloğu, HER ZAMAN sol kenardan.

    `multi_cell(0, ...)` "kalan genişliği kullan" demek ve imleç satırın
    ortasındaysa kalan genişlik bir karaktere bile yetmiyor -- fpdf bunu
    "Not enough horizontal space to render a single character" ile
    reddediyor. Genişliği imlecin nerede olduğuna bırakmak yerine burada
    sabitleniyor.
    """
    pdf.set_x(pdf.l_margin)
    # Sola yaslı. `multi_cell` varsayılanı iki yana yaslı ve tek satıra
    # sığmayan bir cümlede kelimeleri açıyor: "En  büyük  fark  BIST  Hisse".
    pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin, height, text, align="L")


def _meta_lines(report: Dict[str, Any]) -> list:
    """Belgenin üretildiği an ve fiyatların ait olduğu an -- AYRI satırlar.

    Raporu üretim saatiyle tarihlemek, fiyatları olduğundan taze göstermek
    olurdu.
    """
    lines = [f"Oluşturulma: {report.get('generated_at', '')}"]
    lines.append(freshness_note(report))
    return lines


def freshness_note(report: Dict[str, Any]) -> str:
    """Fiyat tazeliğini anlatan TEK cümle, üç yüzey için bir kez.

    İki DURUM var ve tek cümle ikisine birden yetmiyor:

    * Gözlem taze: besleme gecikmesi bildirilir ("15 dakika gecikmeli").
    * Gözlem eski: fiyat son gözlemdir ve ona "gecikme" demek yanlış olur.
      Ölçüldü -- kapalı bir borsanın son kapanışı on sekiz saat yaşlanınca
      kullanıcıya "1095 dakika gecikmeli" deniyordu. Besleme o kadar
      gecikmiyor; piyasa kapalı.

    NEDENİ SÖYLENMİYOR. "Piyasa kapalı" demek, sistemin bilmediği bir şeyi
    iddia etmek olurdu: aynı eskime, ingestor durduğunda da olur. Söylenen
    şey her iki durumda da doğru -- fiyat şu ana ait değil, şu ana.
    """
    at = report.get("as_of", "")
    if report.get("is_stale"):
        if report.get("stale_reason") == "MARKET_CLOSED":
            # Sebep artık BİLİNİYOR: ingestor hangi piyasaların açık olduğunu
            # bildiriyor. Bilinmediği sürece bunu söylemek, bilinmeyeni bir
            # tespite çevirmek olurdu.
            return f"Piyasa kapalı; fiyatlar son kapanışa ait, {at} itibarıyla."
        return f"Fiyatlar son işlem verisi; {at} itibarıyla güncellendi."
    if report.get("is_delayed"):
        return (
            f"Fiyatlar en az {report.get('delay_minutes', 0)} dakika gecikmeli; "
            f"{at} itibarıyla."
        )
    return f"Fiyatlar {at} itibarıyla."
