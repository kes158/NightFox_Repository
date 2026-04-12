import os
import json
import base64
import plistlib
import zipfile
import requests  # 외부 소스 데이터를 가져오기 위해 필수
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

# --- 2. 필수 함수 ---
def extract_ipa_info_only(ipa_path):
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

# --- 3. 기본 데이터 구조 및 기존 데이터 로드 (순서 고정) ---
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
            
            if 'news' in loaded_data: del loaded_data['news']
            if 'patreonURL' in loaded_data: del loaded_data['patreonURL']
            
            for key in base_data:
                if key != 'apps' and key in loaded_data:
                    base_data[key] = loaded_data[key]
        except Exception as e:
            print(f"⚠️ 기존 JSON 로드 오류: {e}")

# --- 4. 외부 소스 퍼오기 ---
other_sources = [
    "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/main/source.json"
]

for source_url in other_sources:
    try:
        print(f"🌐 외부 소스 동기화 중: {source_url}")
        response = requests.get(source_url, timeout=10)
        if response.status_code == 200:
            other_data = response.json()
            for other_app in other_data.get('apps', []):
                # 내 저장소에 없는 앱만 추가하여 내 데이터를 보호합니다.
                exists = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == other_app.get('bundleIdentifier')), None)
                if not exists:
                    base_data['apps'].append(other_app)
                    print(f"   ✅ 외부 앱 추가됨: {other_app.get('name')}")
    except Exception as e:
        print(f"   ⚠️ 외부 소스 로드 실패: {e}")

# --- 5. 내 저장소 릴리즈 자산 및 IPA 처리 ---
for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue

    current_bundle_id = info.get('bundleID')
    current_version = info.get('version', '1.0')
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"

    # [정당화] 인덱스(순서)를 찾아서 그 자리 그대로 업데이트합니다.
    found_index = -1
    for i, a in enumerate(base_data['apps']):
        if a.get('bundleIdentifier') == current_bundle_id:
            found_index = i
            break

    new_v = {
        "version": current_version,
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url,
        "size": info.get('size', 0)
    }

    if found_index != -1:
        # [정당화] 기존 순서를 유지하며 내용만 업데이트
        app_entry = base_data['apps'][found_index]
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: app_entry["versions"] = []
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
        # base_data['apps'][found_index] = app_entry  # 리스트 내 위치 고정
    else:
        # 완전히 새로운 앱일 때만 맨 뒤에 추가
        new_app = {
            "name": info.get('name', ipa_file),
            "bundleIdentifier": current_bundle_id,
            "version": current_version,
            "downloadURL": download_url,
            "iconURL": "https://i.imgur.com/nAsnPKq.png", 
            "tintColor": "#00b39e",
            "category": "other",
            "versions": [new_v]
        }
        apply_nightfox_branding(new_app)
        base_data['apps'].append(new_app)

# --- 6. JSON 저장 ---
# (이하 생략)
# --- 6. JSON 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 모든 작업이 완료되었습니다: {JSON_FILE}")
