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
