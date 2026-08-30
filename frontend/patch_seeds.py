import os
import re

seed_dir = '../seeds/users'
for filename in os.listdir(seed_dir):
    if filename.endswith('.sql'):
        filepath = os.path.join(seed_dir, filename)
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Replace column name list
        content = content.replace(', "is_verified", "wants_email_notifications")', ', "is_verified", "notification_preferences", "user_preferences")')
        
        # Replace VALUES (... , FALSE, TRUE) -> VALUES (... , FALSE, '{}'::jsonb, '{}'::jsonb)
        content = re.sub(r", (TRUE|FALSE), (TRUE|FALSE)\) ON CONFLICT", r", \1, '{}'::jsonb, '{}'::jsonb) ON CONFLICT", content)
        
        with open(filepath, 'w') as f:
            f.write(content)

print("Seed files patched.")
