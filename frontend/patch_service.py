import re

with open('../backend/app/modules/auth/service.py', 'r') as f:
    content = f.read()

# Make request_data_export async and take background_tasks
new_func = """async def request_data_export(user_tc: str, db: Session, background_tasks: BackgroundTasks) -> dict:
    \"\"\"Kullanıcının KVKK/GDPR kapsamındaki veri dışa aktarma talebini alır.\"\"\"
    user = db.query(User).filter(User.tc_no == user_tc).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanıcı bulunamadı.",
        )
    
    # Kullanıcı verilerini derle
    user_data = {
        "profile": {
            "tc_no": user.tc_no,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone_number": user.phone_number,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "user_preferences": user.user_preferences,
        }
    }
    
    from app.core.email import send_data_export_email
    background_tasks.add_task(send_data_export_email, user.email, user_data)
    
    return {
        "message": f"Veri dışa aktarma talebiniz alındı. Dosyanız hazırlandığında {user.email} adresine gönderilecektir."
    }
"""

content = re.sub(r'def request_data_export\(user_tc: str, db: Session\) -> dict:[\s\S]*?(?=\ndef deactivate_account)', new_func, content)

with open('../backend/app/modules/auth/service.py', 'w') as f:
    f.write(content)
print("Patched service.py")
