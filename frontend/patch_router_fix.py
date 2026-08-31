import re

with open('../backend/app/modules/auth/router.py', 'r') as f:
    content = f.read()

new_func = """async def export_data(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    \"\"\"Kullanıcının tüm kişisel verilerinin dışa aktarılması talebini alır.\"\"\"
    return await service.request_data_export(user.tc_no, db, background_tasks)
"""

content = re.sub(r'async def export_data\([\s\S]*?\):\n(?:.*?)\n    return service\.request_data_export\(user\.tc_no, db\)', new_func, content)

# Let's try replacing it if the regex failed:
if "background_tasks: BackgroundTasks," not in content:
    # manual replacement
    start = content.find("async def export_data(")
    end = content.find("def deactivate_account(", start)
    end = content.rfind("@router.delete", start, end)
    
    if start != -1 and end != -1:
        content = content[:start] + new_func + "\n\n" + content[end:]

with open('../backend/app/modules/auth/router.py', 'w') as f:
    f.write(content)
print("Fixed router.py")
