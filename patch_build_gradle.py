"""Patch build.gradle to remove Codemagic signing config (causes null crash in GitHub Actions)."""
import re

path = '/tmp/omi/app/android/app/build.gradle'
with open(path) as f:
    content = f.read()

# Replace entire signingConfigs block with empty placeholders
content = re.sub(
    r'signingConfigs \{.*?\n    \}',
    'signingConfigs { release { } debug { } }',
    content,
    count=1,
    flags=re.DOTALL
)

# Remove signingConfig references in buildTypes
content = content.replace('signingConfig signingConfigs.release', '')

with open(path, 'w') as f:
    f.write(content)

print('build.gradle signing config patched')
