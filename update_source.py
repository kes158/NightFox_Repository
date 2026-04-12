import os
import json
import plistlib
import zipfile
import requests
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 및 인증 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_NAME = "kes158/NightFox_Repository" 
JSON_FILE = "NightFox.json" 

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
repo = g.get_repo(REPO_NAME)

# --- 2. 필수 함수 ---
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

def deep_clean_nulls(obj):
    if isinstance(obj, list): return [deep_clean_nulls(x) for x in obj]
    elif isinstance(obj, dict): return {k: (deep_clean_nulls(v) if v is not None else "") for k, v in obj.items()}
    return obj

# --- 3. 기본 데이터 복구 (여기에 사라진 필드들을 다시 넣었습니다) ---
base_data = {
    "name": "NightFox",
    "identifier": "com.nightfox1.repo",
    "subtitle": "NightFox's App Repository",
    "description": "Welcome to NightFox's source!",
    "iconURL": "https://i.imgur.com/Se6jHAj.png",
    "website": f"https://github.com/{REPO_NAME}",
    "patreonURL": "https://patreon.com/altstudio", # 요청하신 필드 복구
    "tintColor": "#00b39e",
    "featuredApps": [], # 요청하신 필드 복구
    "apps": []
}

# 기존 앱 리스트 로드 (순서 유지용)
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded = json.load(f)
            if 'apps' in loaded: base_data['apps'] = loaded['apps']
        except: pass

# --- 4. 앱 데이터 정밀 세척 및 업데이트 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

updated_apps = []

for app in base_data['apps']:
    bid = app.get("bundleIdentifier")
    # 사이드스토어 필수 필드만 남기고 appPermissions 등은 제외하며 재조립
    clean_app = {
        "name": app.get("name"),
        "bundleIdentifier": bid,
        "developerName": "NightFox",
        "subtitle": "NightFox",
        "localizedDescription": "NightFox",
        "iconURL": app.get("iconURL", "https://i.imgur.com/nAsnPKq.png"),
        "tintColor": app.get("tintColor", "#00b39e"),
        "category": "other",
        "version": app.get("version"),
        "downloadURL": app.get("downloadURL"),
        "size": app.get("size", 0),
        "versions": app.get("versions", [])
    }
    updated_apps.append(clean_app)

# 새 IPA 반영
for ipa in ipa_files:
    info = extract_ipa_info(ipa)
    if not info: continue
    
    url = assets.get(ipa) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa.replace(' ', '%20')}"
    new_v = {"version": info['version'], "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size'], "buildVersion": "1"}
    
    idx = next((i for i, a in enumerate(updated_apps) if a.get('bundleIdentifier') == info['bundleID']), -1)
    
    if idx != -1:
        updated_apps[idx].update({"version": info['version'], "downloadURL": url, "size": info['size']})
        updated_apps[idx]["versions"] = [v for v in updated_apps[idx]["versions"] if v.get('version') != info['version']]
        updated_apps[idx]["versions"].insert(0, new_v)
    else:
        new_app = {
            "name": info['name'], "bundleIdentifier": info['bundleID'], "developerName": "NightFox",
            "subtitle": "NightFox", "localizedDescription": "NightFox", "iconURL": "https://i.imgur.com/nAsnPKq.png",
            "tintColor": "#00b39e", "category": "other", "version": info['version'], 
            "downloadURL": url, "size": info['size'], "versions": [new_v]
        }
        updated_apps.append(new_app)

# --- 5. 저장 ---
base_data['apps'] = updated_apps
base_data = deep_clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("✅ 필드 복구 및 앱 세척 완료!")
