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

# --- 3. 데이터 로드 ---
base_data = {"name": "NightFox", "identifier": "com.nightfox1.repo", "subtitle": "NightFox's App Repository", "apps": []}

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try: base_data['apps'] = json.load(f).get('apps', [])
        except: pass

# --- 4. 필드 재조립 및 세척 (중요: 화이트리스트 방식) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {a.name: a.browser_download_url for r in repo.get_releases() for a in r.get_assets()}

cleaned_apps = []

# 기존 앱들을 화이트리스트 방식으로 재구성 (appPermissions 등 자동 제거)
for app in base_data['apps']:
    bid = app.get("bundleIdentifier")
    # IPA 파일이 현재 폴더에 있으면 정보를 새로 업데이트, 없으면 기존 정보 유지
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        current_version = info['version']
        current_url = assets.get(ipa_match) or app.get("downloadURL", "")
        current_size = info['size']
    else:
        current_version = app.get("version", "")
        current_url = app.get("downloadURL", "")
        current_size = app.get("size", 0)

    # 사이드스토어 필수 필드만 딱 골라서 넣음 (Data missing 에러 방지)
    clean_app = {
        "name": app.get("name"),
        "bundleIdentifier": bid,
        "developerName": "NightFox",
        "subtitle": "NightFox",
        "localizedDescription": "NightFox",
        "iconURL": app.get("iconURL", "https://i.imgur.com/nAsnPKq.png"),
        "tintColor": app.get("tintColor", "#00b39e"),
        "category": "other",
        "version": current_version,     # 필수
        "downloadURL": current_url,    # 필수
        "size": current_size,          # 필수
        "versions": app.get("versions", [])
    }
    
    # 버전 리스트 내의 null 제거 및 최신 버전 동기화
    if clean_app["versions"]:
        # 최신 버전이 위로 오도록
        if clean_app["versions"][0].get("version") != current_version and ipa_match:
            new_v = {"version": current_version, "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": current_url, "size": current_size, "buildVersion": "1"}
            clean_app["versions"].insert(0, new_v)
    
    cleaned_apps.append(clean_app)

# 신규 앱 처리 (기존 리스트에 없는 경우)
for ipa in ipa_files:
    info = extract_ipa_info(ipa)
    if not info or any(a['bundleIdentifier'] == info['bundleID'] for a in cleaned_apps): continue
    
    url = assets.get(ipa) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa.replace(' ', '%20')}"
    new_v = {"version": info['version'], "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size'], "buildVersion": "1"}
    
    new_app = {
        "name": info['name'], "bundleIdentifier": info['bundleID'], "developerName": "NightFox",
        "subtitle": "NightFox", "localizedDescription": "NightFox", "iconURL": "https://i.imgur.com/nAsnPKq.png",
        "tintColor": "#00b39e", "category": "other", "version": info['version'], 
        "downloadURL": url, "size": info['size'], "versions": [new_v]
    }
    cleaned_apps.append(new_app)

# --- 5. 최종 저장 ---
base_data['apps'] = cleaned_apps
base_data = deep_clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("✅ 사이드스토어 전용 필드 재조립 완료!")
