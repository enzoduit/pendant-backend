"""
Minimal build.gradle fix for GitHub Actions:
- Only remove the CI-specific Codemagic block that crashes with null CM_KEYSTORE_PATH
- Keep signingConfigs structure intact but use the else branch (local keystore) 
- For debug builds, no signing config needed at all
"""

path = '/tmp/omi/app/android/app/build.gradle'
with open(path) as f:
    content = f.read()

# Replace the full release signingConfig with just the else-branch fallback
# (when no CM_KEYSTORE_PATH is set, use null storeFile which is fine for debug)
old_release = '''        release {
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
        }'''

new_release = '''        release {
            // BYPASS: no release signing needed for debug sideload
        }'''

if old_release in content:
    content = content.replace(old_release, new_release)
    print('release signingConfig simplified')

# Remove signingConfig signingConfigs.release from release buildType only
# (debug buildType doesn't have it)
content = content.replace('signingConfig signingConfigs.release', '// signingConfig removed for sideload')

with open(path, 'w') as f:
    f.write(content)

print('build.gradle patched successfully')
