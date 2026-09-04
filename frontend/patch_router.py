import re

with open('../backend/app/modules/auth/router.py', 'r') as f:
    content = f.read()

# Add BackgroundTasks to imports if not present
if "from fastapi import" in content and "BackgroundTasks" not in content:
    content = content.replace("from fastapi import ", "from fastapi import BackgroundTasks, ")

new_func = """async def export_data(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(deps.get_current_user)
):
    \"\"\"Kullanıcının tüm kişisel verilerinin dışa aktarılması talebini alır.\"\"\"
    return await service.request_data_export(user.tc_no, db, background_tasks)
"""

content = re.sub(r'async def export_data\([\s\S]*?\):\n(?:.*?)\n    return service\.request_data_export\(user\.tc_no, db\)', new_func, content)

with open('../backend/app/modules/auth/router.py', 'w') as f:
    f.write(content)
print("Patched router.py")
