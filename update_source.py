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

# [정당화] 사이드스토어 호환성을 위해 모든 null을 빈 문자열로 바꾸는 함수
def clean_data(obj):
    if isinstance(obj, list): return [clean_data(x) for x in obj]
    if isinstance(obj, dict): return {k: (clean_data(v) if v is not None else "") for k, v in obj.items()}
    return obj

# --- 2. 기본 구조 설정 ---
base_data = {
    "name": "NightFox",
    "identifier": "com.nightfox1.repo",
    "subtitle": "NightFox's App Repository",
    "description": "Welcome to NightFox's source!",
    "iconURL": "https://i.imgur.com/Se6jHAj.png",
    "website": f"https://github.com/{REPO_NAME}",
    "tintColor": "#00b39e",
    "apps": []
}

# 기존 앱 순서 유지를 위해 로드
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try: base_data['apps'] = json.load(f).get('apps', [])
        except: pass

# --- 3. IPA 처리 및 업데이트 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {a.name: a.browser_download_url for r in repo.get_releases() for a in r.get_assets()}

for ipa in ipa_files:
    info = extract_ipa_info(ipa)
    if not info: continue
    
    url = assets.get(ipa, "")
    new_v = {
        "version": info['version'],
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": "NightFox Build",
        "downloadURL": url,
        "size": info['size'],
        "buildVersion": "1"
    }

    idx = next((i for i, a in enumerate(base_data['apps']) if a.get('bundleIdentifier') == info['bundleID']), -1)
    
    # [정당화] 사이드스토어 성공 파일의 '최소한의 필드'만 유지하는 구조
    app_entry = {
        "name": info['name'],
        "bundleIdentifier": info['bundleID'],
        "developerName": "NightFox",
        "subtitle": "NightFox",
        "localizedDescription": "NightFox",
        "iconURL": "https://i.imgur.com/nAsnPKq.png",
        "tintColor": "#00b39e",
        "category": "other",
        "version": info['version'], # 최상위 필수
        "downloadURL": url,        # 최상위 필수
        "size": info['size'],       # 최상위 필수
        "versions": []
    }

    if idx != -1:
        existing_app = base_data['apps'][idx]
        app_entry["iconURL"] = existing_app.get("iconURL", app_entry["iconURL"])
        app_entry["tintColor"] = existing_app.get("tintColor", app_entry["tintColor"])
        app_entry["versions"] = [v for v in existing_app.get("versions", []) if v.get("version") != info['version']]
        app_entry["versions"].insert(0, new_v)
        base_data['apps'][idx] = app_entry
    else:
        app_entry["versions"] = [new_v]
        base_data['apps'].append(app_entry)
# --- 4. 내 IPA 처리 (순서 유지 및 필드 최적화) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
all_release_assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue
    
    bid = info['bundleID']
    ver = info['version']
    url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"
    
    new_v = {
        "version": ver, 
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
        "downloadURL": url, 
        "size": info['size'], 
        "buildVersion": "", 
        "localizedDescription": f"NightFox Build - {ver}"
    }
    
    idx = next((i for i, a in enumerate(base_data['apps']) if a.get('bundleIdentifier') == bid), -1)
    if idx != -1:
        app = base_data['apps'][idx]
        # 잘 되는 파일 구조에 맞춰 최상위 필드 강제 업데이트
        app.update({"version": ver, "downloadURL": url, "size": info['size']})
        apply_nightfox_branding(app)
        app["versions"] = [v for v in app.get("versions", []) if v.get("version") != ver]
        app["versions"].insert(0, new_v)
    else:
        new_app = {
            "name": info['name'], 
            "bundleIdentifier": bid, 
            "version": ver, 
            "downloadURL": url, 
            "size": info['size'], 
            "iconURL": "https://i.imgur.com/nAsnPKq.png", 
            "category": "other", 
            "versions": [new_v]
        }
        apply_nightfox_branding(new_app)
        base_data['apps'].append(new_app)

# --- 5. 최종 세척 및 저장 ---
base_data = clean_data(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("✅ 사이드스토어 최적화 완료!")
