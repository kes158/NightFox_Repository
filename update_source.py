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

# [유지] 스포티파이 외부 소스 URL
EXTERNAL_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"

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
                    'name': str(plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ""),
                    'version': str(plist.get('CFBundleShortVersionString') or "1.0"),
                    'bundleID': str(plist.get('CFBundleIdentifier') or ""),
                    'size': os.path.getsize(ipa_path)
                }
    except: return None

def clean_for_sidestore(obj):
    if isinstance(obj, list):
        return [clean_for_sidestore(x) for x in obj]
    elif isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if k == "size":
                try: new_dict[k] = int(v) if v is not None else 0
                except: new_dict[k] = 0
            else: new_dict[k] = clean_for_sidestore(v)
        return new_dict
    return str(obj) if obj is not None else ""

# --- 2. 데이터 로드 (파일 경로 명확화) ---
# GitHub Actions 환경에서 파일 경로를 확실히 잡기 위해 절대 경로를 사용하거나 존재 여부를 더 꼼꼼히 체크합니다.
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
            if "apps" not in base_data: base_data["apps"] = []
        except:
            base_data = {"name": "NightFox", "apps": []}
else:
    base_data = {
        "name": "NightFox",
        "identifier": "com.nightfox1.repo",
        "subtitle": "NightFox's App Repository",
        "iconURL": "https://i.imgur.com/Se6jHAj.png",
        "website": f"https://github.com/{REPO_NAME}",
        "tintColor": "#00b39e",
        "apps": []
    }

# --- 3. 외부 소스 동기화 (기존 앱 보호 로직) ---
def sync_external_source(base_data, url):
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            external_data = response.json()
            ext_apps = external_data.get("apps", [])
            existing_bids = {app.get("bundleIdentifier") for app in base_data.get("apps", []) if app.get("bundleIdentifier")}
            
            for ext_app in ext_apps:
                bid = ext_app.get("bundleIdentifier")
                if not bid: continue
                if bid not in existing_bids:
                    base_data["apps"].append(ext_app)
                else:
                    for i, app in enumerate(base_data["apps"]):
                        if app.get("bundleIdentifier") == bid:
                            # 기존 정보를 지우지 않고 외부 정보를 업데이트
                            base_data["apps"][i].update(ext_app)
                            break
    except Exception as e: print(f"❌ 외부 소스 로드 실패: {e}")

sync_external_source(base_data, EXTERNAL_SOURCE_URL)

# --- 4. 로컬 IPA 기반 앱 강제 보호 및 업데이트 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

# [중요] 로컬에 있는 IPA를 먼저 돌면서 JSON에 해당 앱이 없으면 새로 만듭니다.
# 이렇게 하면 JSON이 비어있더라도 IPA 파일만 있다면 앱 정보가 사라지지 않습니다.
for ipa_file in ipa_files:
    info = extract_ipa_info(ipa_file)
    if not info: continue
    
    bid = info['bundleID']
    # JSON에서 해당 번들 ID를 가진 앱 찾기
    app = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == bid), None)
    
    if not app:
        # JSON에 앱이 없으면 새로 생성 (삭제 방지 핵심 로직)
        app = {
            "name": info['name'],
            "bundleIdentifier": bid,
            "developerName": "NightFox",
            "iconURL": "https://i.imgur.com/Se6jHAj.png",
            "localizedDescription": "NightFox",
            "versions": []
        }
        base_data['apps'].append(app)

    # 버전 정보 업데이트[cite: 5]
    url = assets.get(ipa_file) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_file.replace(' ', '%20')}"
    new_v = {
        "version": str(info['version']), 
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
        "downloadURL": str(url), 
        "size": int(info['size']),
        "localizedDescription": "NightFox"
    }
    
    if "versions" not in app: app["versions"] = []
    
    # 동일 버전 중복 체크[cite: 5]
    version_exists = False
    for i, v in enumerate(app["versions"]):
        if v.get("version") == info['version']:
            app["versions"][i] = new_v
            version_exists = True
            break
    if not version_exists:
        app["versions"].insert(0, new_v)

    # 버전 내림차순 정렬 (최신이 위로)[cite: 2, 5]
    if len(app["versions"]) > 1:
        app["versions"].sort(
            key=lambda x: [int(part) if part.isdigit() else 0 for part in x.get("version", "0").split('.')],
            reverse=True
        )
    
    # 최신 정보를 상위 필드에 동기화[cite: 5]
    latest_v = app["versions"][0]
    app["version"] = str(latest_v.get("version", ""))
    app["downloadURL"] = str(latest_v.get("downloadURL", ""))
    app["size"] = int(latest_v.get("size", 0))

# --- 5. 최종 클리닝 및 저장 ---
for root_key in ["featuredApps", "marketplaceID", "patreonURL"]:
    base_data.pop(root_key, None)

for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

base_data = clean_for_sidestore(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 NightFox.json 업데이트 완료! (로컬 앱 보호 및 스포티파이 병합)")
