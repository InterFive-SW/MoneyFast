import re

with open('../backend/app/core/email.py', 'r') as f:
    content = f.read()

new_func = """
async def send_data_export_email(email: str, user_data: dict) -> None:
    \"\"\"
    Kullanıcıya veri dışa aktarma (export) dosyasını e-posta ile asenkron olarak gönderir.
    \"\"\"
    import json
    import tempfile
    
    html_content = _get_email_html_template(
        title="Kişisel Verileriniz Hazır",
        content="KVKK/GDPR kapsamında talep ettiğiniz kişisel verileriniz ve hesap dökümünüz ekteki dosyada yer almaktadır. Dosya JSON formatındadır.",
        action_url="https://moneyfast.com/security",
        action_text="Güvenlik Merkezine Git"
    )
    
    # Veriyi geçici bir dosyaya yaz
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, "moneyfast_export_data.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)
    
    message = MessageSchema(
        subject="MoneyFast - Kişisel Verileriniz (Data Export)",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html,
        attachments=[file_path]
    )
    
    try:
        if 'fm' in globals():
            await fm.send_message(message)
            logger.info(f"Data export email sent to {email}")
        else:
            logger.warning(f"SMTP yapılandırması eksik, e-posta gönderilemedi. Dosya yolu: {file_path}")
    except Exception as e:
        logger.error(f"E-posta gönderilirken (Data Export) beklenmeyen bir hata oluştu: {str(e)}")
"""

if "send_data_export_email" not in content:
    with open('../backend/app/core/email.py', 'a') as f:
        f.write(new_func)
    print("Added send_data_export_email to email.py")
else:
    print("Function already exists")
