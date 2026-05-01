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

# 병합할 외부 소스 URL (Spotify 미러 등)
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

# [정당화] 사이드스토어 규격 준수: size는 Int, 나머지는 String 강제
def clean_for_sidestore(obj):
    if isinstance(obj, list):
        return [clean_for_sidestore(x) for x in obj]
    elif isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if k == "size":
                try:
                    new_dict[k] = int(v) if v is not None else 0
                except:
                    new_dict[k] = 0
            else:
                new_dict[k] = clean_for_sidestore(v)
        return new_dict
    return str(obj) if obj is not None else ""

# --- 2. 데이터 로드 및 헤더 설정 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
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

def sync_external_source(base_data, url):
    try:
        print(f"🌐 외부 소스 동기화 중: {url}")
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            external_data = response.json()
            ext_apps = external_data.get("apps", [])
            existing_bids = {app.get("bundleIdentifier") for app in base_data.get("apps", []) if app.get("bundleIdentifier")}
            
            for ext_app in ext_apps:
                bid = ext_app.get("bundleIdentifier")
                if not bid: continue
                if bid not in existing_bids:
                    # 새로운 앱은 리스트 끝에 추가하여 기존 앱 순서를 방해하지 않음
                    base_data["apps"].append(ext_app)
                else:
                    for i, app in enumerate(base_data["apps"]):
                        if app.get("bundleIdentifier") == bid:
                            base_data["apps"][i].update(ext_app)
                            break
    except Exception as e:
        print(f"❌ 외부 소스 로드 실패: {e}")

# 외부 소스 병합 실행
sync_external_source(base_data, EXTERNAL_SOURCE_URL)

# --- 3. 업데이트 및 데이터 동기화 (버전만 최신순 정렬) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

# [앱 순환] base_data['apps']의 순서는 그대로 유지하면서 내부 데이터만 업데이트
for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        
        new_v = {
            "version": str(info['version']), 
            "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
            "downloadURL": str(url), 
            "size": int(info['size']),
            "buildVersion": "",
            "localizedDescription": "NightFox", 
            "minOSVersion": ""
        }
        
        if "versions" not in app:
            app["versions"] = []
            
        version_exists = False
        for i, v in enumerate(app["versions"]):
            if v.get("version") == info['version']:
                # 이미 동일 버전이 있으면 최신 정보로 업데이트
                app["versions"][i] = new_v
                version_exists = True
                break
        
        if not version_exists:
            # 새로운 버전이면 일단 맨 앞에 추가
            app["versions"].insert(0, new_v)

    # [버전 정렬] 버전 번호를 숫자로 분리하여 정확하게 내림차순 정렬 (최신 버전이 맨 위로)[cite: 2]
    # 이 과정을 통해 JSON 파일에 기록될 때 항상 최신 버전이 가장 먼저 작성됨[cite: 2]
    if "versions" in app and len(app["versions"]) > 1:
        app["versions"].sort(
            key=lambda x: [int(part) if part.isdigit() else 0 for part in x.get("version", "0").split('.')],
            reverse=True
        )
        
    # 최상위 앱 정보(대표 버전) 동기화
    if "versions" in app and len(app["versions"]) > 0:
        latest_v = app["versions"][0] # 정렬된 버전 중 가장 첫 번째(최신)[cite: 2]
        app["version"] = str(latest_v.get("version", ""))
        app["downloadURL"] = str(latest_v.get("downloadURL", ""))
        app["size"] = int(latest_v.get("size", 0))

# --- 4. 최종 클리닝 및 저장 (필요 없는 필드 제거) ---

# 최상위(Root) 레벨 클리닝
for root_key in ["featuredApps", "marketplaceID", "patreonURL"]:
    base_data.pop(root_key, None)

# 각 앱 레벨 클리닝
for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

# 최종 사이드스토어 규격 세척
base_data = clean_for_sidestore(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    # indent=2 설정을 통해 사람이 읽기 좋은 형태로 저장[cite: 2]
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 NightFox.json 업데이트 완료! (앱 순서 유지 및 버전별 최신순 정렬 적용)")
