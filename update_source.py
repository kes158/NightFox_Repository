import os
import json
import plistlib
import zipfile
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_NAME = "kes158/NightFox_Repository" 
JSON_FILE = "NightFox.json" 

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
repo = g.get_repo(REPO_NAME)

def extract_ipa_info(ipa_path):
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                return {
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName'),
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier'),
                    'size': os.path.getsize(ipa_path)
                }
    except: return None

# --- 2. 데이터 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        base_data = json.load(f)
else:
    base_data = {"name": "NightFox", "apps": []}

# --- 3. 업데이트 및 데이터 끌어올리기 로직 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

# [생각하며 정당화] 
# 모든 앱을 순회하며 '상위 필드'가 비어있으면 '하위(versions)'에서 데이터를 가져와 채웁니다.
for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    
    # 1. 현재 폴더에 새 IPA가 있는 경우 정보 갱신
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        app["version"] = info['version']
        app["downloadURL"] = url
        app["size"] = info['size']
        
        # versions 리스트 업데이트
        new_v = {"version": info['version'], "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size']}
        if "versions" not in app: app["versions"] = []
        app["versions"] = [v for v in app["versions"] if v.get('version') != info['version']]
        app["versions"].insert(0, new_v)
        
    # 2. 새 IPA는 없지만 상위 필드가 비어있는 경우 (기존 데이터 이관)
    elif not app.get("version") or app.get("version") == "":
        if app.get("versions") and len(app["versions"]) > 0:
            latest = app["versions"][0] # 가장 최근 버전 정보
            app["version"] = latest.get("version", "")
            app["downloadURL"] = latest.get("downloadURL", "")
            app["size"] = latest.get("size", 0)

# --- 4. 최종 세척 및 저장 ---
# 불필요한 필드(appPermissions 등) 제거
for app in base_data['apps']:
    app.pop("appPermissions", None)
    app.pop("patreon", None)
    app.pop("screenshots", None)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 모든 앱의 상위 필드 복구 및 세척 완료!")
