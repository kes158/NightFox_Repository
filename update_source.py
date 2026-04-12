import os
import json
import base64
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

# 사이드스토어 호환성을 위해 모든 null을 빈 문자열로 바꾸는 딥 클리닝 함수
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

# --- 4. 외부 소스 동기화 ---
other_sources = ["https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/main/source.json"]
for source_url in other_sources:
    try:
        response = requests.get(source_url, timeout=10)
        if response.status_code == 200:
            for other_app in response.json().get('apps', []):
                exists = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == other_app.get('bundleIdentifier')), None)
                if not exists: base_data['apps'].append(other_app)
    except: pass

# --- 5. 내 IPA 처리 (순서 유지) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
all_release_assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue
    
    bid = info['bundleID']
    ver = info['version']
    url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file}"
    
    new_v = {"version": ver, "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), "downloadURL": url, "size": info['size'], "buildVersion": "", "localizedDescription": f"NightFox Build - {ver}"}
    
    idx = next((i for i, a in enumerate(base_data['apps']) if a.get('bundleIdentifier') == bid), -1)
    if idx != -1:
        app = base_data['apps'][idx]
        app.update({"version": ver, "downloadURL": url, "size": info['size']}) # 최상위 필드 갱신
        apply_nightfox_branding(app)
        app["versions"] = [v for v in app.get("versions", []) if v.get("version") != ver]
        app["versions"].insert(0, new_v)
    else:
        new_app = {"name": info['name'], "bundleIdentifier": bid, "version": ver, "downloadURL": url, "size": info['size'], "iconURL": "https://i.imgur.com/nAsnPKq.png", "category": "other", "versions": [new_v]}
        apply_nightfox_branding(new_app)
        base_data['apps'].append(new_app)

# --- 6. 사이드스토어용 최종 강제 정제 ---
for app in base_data['apps']:
    # 최상위 필드가 비어있으면 첫 번째 버전에서 가져와서 채움 (사이드스토어 필수 로직)
    if app.get('versions'):
        latest = app['versions'][0]
        app["version"] = app.get("version") or latest.get("version", "")
        app["downloadURL"] = app.get("downloadURL") or latest.get("downloadURL", "")
        app["size"] = app.get("size") or latest.get("size", 0)
    
    # 사이드스토어가 싫어하는 복잡한 권한 필드 삭제 (필요 시 주석 처리)
    if "appPermissions" in app:
        del app["appPermissions"]

# 모든 데이터에서 null을 완전히 제거
base_data = deep_clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)
