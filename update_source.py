import os
import json
import plistlib
import zipfile
import requests
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_NAME = "kes158/NightFox_Repository" 
REPO_URL = f"https://github.com/{REPO_NAME}"
JSON_FILE = "NightFox.json" 

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)
repo = g.get_repo(REPO_NAME)

# --- 2. 함수 정의 ---
def extract_ipa_info(ipa_path):
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                return {
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ipa_path,
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier'),
                    'size': os.path.getsize(ipa_path)
                }
    except: return None

def deep_clean_nulls(obj):
    if isinstance(obj, list): return [deep_clean_nulls(x) for x in obj]
    elif isinstance(obj, dict): return {k: (deep_clean_nulls(v) if v is not None else "") for k, v in obj.items()}
    return obj

# --- 3. 기본 데이터 로드 ---
base_data = {"name": "NightFox", "identifier": "com.nightfox1.repo", "subtitle": "NightFox's App Repository", "apps": []}

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try: base_data['apps'] = json.load(f).get('apps', [])
        except: pass

# --- 4. IPA 처리 및 '필드 세척' ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {a.name: a.browser_download_url for r in repo.get_releases() for a in r.get_assets()}

new_apps_list = []

# 기존 앱들을 먼저 정리 (불필요한 필드 제거)
for app in base_data['apps']:
    clean_app = {
        "name": app.get("name"),
        "bundleIdentifier": app.get("bundleIdentifier"),
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
    new_apps_list.append(clean_app)

# 새 IPA 파일 업데이트
for ipa in ipa_files:
    info = extract_ipa_info(ipa)
    if not info: continue
    
    url = assets.get(ipa) or f"{REPO_URL}/releases/download/latest/{ipa.replace(' ', '%20')}"
    new_v = {"version": info['version'], "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size'], "buildVersion": "1"}

    idx = next((i for i, a in enumerate(new_apps_list) if a.get('bundleIdentifier') == info['bundleID']), -1)
    
    if idx != -1:
        app = new_apps_list[idx]
        app.update({"version": info['version'], "downloadURL": url, "size": info['size']})
        app["versions"] = [v for v in app.get("versions", []) if v.get("version") != info['version']]
        app["versions"].insert(0, new_v)
    else:
        new_app = {
            "name": info['name'], "bundleIdentifier": info['bundleID'], "developerName": "NightFox",
            "subtitle": "NightFox", "localizedDescription": "NightFox", "iconURL": "https://i.imgur.com/nAsnPKq.png",
            "tintColor": "#00b39e", "category": "other", "version": info['version'], 
            "downloadURL": url, "size": info['size'], "versions": [new_v]
        }
        new_apps_list.append(new_app)

# --- 5. 최종 저장 ---
base_data['apps'] = new_apps_list
base_data = deep_clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 appPermissions 제거 및 사이드스토어 최적화 완료!")
