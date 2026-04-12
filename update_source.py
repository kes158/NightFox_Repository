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
REPO_URL = f"https://github.com/{REPO_NAME}"
JSON_FILE = "NightFox.json" 

auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)

try:
    repo = g.get_repo(REPO_NAME)
    print(f"✅ 저장소 연결 성공: {REPO_NAME}")
except Exception as e:
    print(f"❌ 저장소 연결 실패: {REPO_NAME}")
    raise

# --- 2. 필수 함수 (이름 통일: extract_ipa_info) ---
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
    except Exception as e:
        print(f"⚠️ {ipa_path} 정보 추출 실패: {e}")
        return None

def apply_nightfox_branding(entry):
    entry["developerName"] = "NightFox"
    entry["subtitle"] = "NightFox"
    entry["localizedDescription"] = "NightFox"

def deep_clean_nulls(obj):
    if isinstance(obj, list):
        return [deep_clean_nulls(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: (deep_clean_nulls(v) if v is not None else "") for k, v in obj.items()}
    return obj

# --- 3. 기본 데이터 구조 로드 ---
base_data = {
    "name": "NightFox",
    "identifier": "com.nightfox1.repo",
    "subtitle": "NightFox's App Repository",
    "description": "Welcome to NightFox's source!",
    "iconURL": "https://i.imgur.com/Se6jHAj.png",
    "website": REPO_URL,
    "tintColor": "#00b39e",
    "apps": []
}

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded_data = json.load(f)
            if 'apps' in loaded_data:
                base_data['apps'] = loaded_data['apps']
        except: pass

# --- 4. 내 IPA 처리 (함수 호출 이름 수정 완료) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
all_release_assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for ipa_file in ipa_files:
    info = extract_ipa_info(ipa_file)  # 여기서 오류 났던 부분을 수정했습니다.
    if not info: continue
    
    bid = info['bundleID']
    ver = info['version']
    url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"
    
    new_v = {
        "version": ver, 
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
        "downloadURL": url, 
        "size": info['size'], 
        "buildVersion": "1", 
        "localizedDescription": f"NightFox Build - {ver}"
    }
    
    idx = next((i for i, a in enumerate(base_data['apps']) if a.get('bundleIdentifier') == bid), -1)
    
    # 사이드스토어 규격에 맞춘 최소한의 필드 구성
    app_entry = {
        "name": info['name'],
        "bundleIdentifier": bid,
        "developerName": "NightFox",
        "subtitle": "NightFox",
        "localizedDescription": "NightFox",
        "iconURL": "https://i.imgur.com/nAsnPKq.png",
        "tintColor": "#00b39e",
        "category": "other",
        "version": ver,
        "downloadURL": url,
        "size": info['size'],
        "versions": []
    }

    if idx != -1:
        # 기존 앱 정보 유지하며 업데이트 (순서 유지)
        existing_app = base_data['apps'][idx]
        app_entry["iconURL"] = existing_app.get("iconURL", app_entry["iconURL"])
        app_entry["versions"] = [v for v in existing_app.get("versions", []) if v.get("version") != ver]
        app_entry["versions"].insert(0, new_v)
        base_data['apps'][idx] = app_entry
    else:
        app_entry["versions"] = [new_v]
        base_data['apps'].append(app_entry)

# --- 5. 최종 세척 및 저장 ---
base_data = deep_clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 모든 오류 수정 및 검수 완료: {JSON_FILE}")
