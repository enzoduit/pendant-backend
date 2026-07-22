"""
Patch build.gradle: remove Codemagic signing logic that crashes when CM_KEYSTORE_PATH is null.
Replace the if(CI)/else block with just the debug signing fallback (no-op for debug builds).
"""
import re

path = '/tmp/omi/app/android/app/build.gradle'
with open(path) as f:
    content = f.read()

# Replace the entire signingConfigs block — keep only the outer structure, remove all content
# This makes the release config empty (uses default debug signing)
old_signing_block = '''    signingConfigs {
        release {
            if (System.getenv()["CI"]) { // CI=true is exported by Codemagic
                storeFile file(System.getenv()["CM_KEYSTORE_PATH"])
                storePassword System.getenv()["CM_KEYSTORE_PASSWORD"]
                keyAlias System.getenv()["CM_KEY_ALIAS"]
                keyPassword System.getenv()["CM_KEY_PASSWORD"]
            } else {
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
                storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
                storePassword keystoreProperties['storePassword']
            }
        }
        debug {
            if (keystorePropertiesFile.exists()) {
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
                storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
                storePassword keystoreProperties['storePassword']
            }
        }'''

new_signing_block = '''    signingConfigs {
        release {
        }
        debug {
        }'''

if old_signing_block in content:
    content = content.replace(old_signing_block, new_signing_block)
    print('signingConfigs block replaced')
else:
    print('WARNING: exact block not found - trying regex fallback')
    content = re.sub(
        r'signingConfigs \{.*?(?=\n    \})\n    \}',
        'signingConfigs {\n        release {\n        }\n        debug {\n        }\n    }',
        content,
        count=1,
        flags=re.DOTALL
    )

# Remove signingConfig references in buildTypes (optional for debug)
content = content.replace('signingConfig signingConfigs.release', '// signingConfig removed')

with open(path, 'w') as f:
    f.write(content)

print('build.gradle patched successfully')
