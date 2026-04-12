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

# --- 2. 데이터 로드 및 헤더 설정 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        base_data = json.load(f)
else:
    base_data = {
        "name": "NightFox",
        "identifier": "com.nightfox1.repo",
        "subtitle": "NightFox's App Repository",
        "description": "Welcome to NightFox's source!",
        "iconURL": "https://i.imgur.com/Se6jHAj.png",
        "website": f"https://github.com/{REPO_NAME}",
        "patreonURL": "https://patreon.com/altstudio",
        "tintColor": "#00b39e",
        "apps": [] # featuredApps 필드를 아예 삭제함
    }

# 혹시 기존 데이터에 featuredApps가 남아있다면 제거
base_data.pop("featuredApps", None)

# --- 3. 업데이트 로직 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

# 기존 앱 리스트 업데이트 및 상위 필드 채우기
for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        app["version"] = info['version']
        app["downloadURL"] = url
        app["size"] = info['size']
        
        new_v = {"version": info['version'], "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size']}
        if "versions" not in app: app["versions"] = []
        app["versions"] = [v for v in app["versions"] if v.get('version') != info['version']]
        app["versions"].insert(0, new_v)
    elif not app.get("version") or app.get("version") == "":
        if app.get("versions"):
            latest = app["versions"][0]
            app["version"] = latest.get("version", "")
            app["downloadURL"] = latest.get("downloadURL", "")
            app["size"] = latest.get("size", 0)

# --- 4. 최종 세척 및 저장 ---
for app in base_data.get('apps', []):
    # 사이드스토어 에러 유발 및 불필요 필드 제거
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("✅ featuredApps 필드 제거 및 상위 필드 최적화 완료!")
