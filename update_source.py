import os
import json
import plistlib
import zipfile
import requests # 외부 JSON 로드를 위해 추가
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
REPO_NAME = "kes158/NightFox_Repository" 
JSON_FILE = "NightFox.json" 

# [추가] 병합할 외부 소스 URL (EeveeSpotify 등 포함된 미러)
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

# [정당화] 사이드스토어는 'size'만 Int형(Int64)을 원하고 나머지는 String을 원함
def clean_for_sidestore(obj):
    if isinstance(obj, list):
        return [clean_for_sidestore(x) for x in obj]
    elif isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            # 'size' 필드만큼은 따옴표 없는 숫자로 유지
            if k == "size":
                try:
                    new_dict[k] = int(v) if v is not None else 0
                except:
                    new_dict[k] = 0
            # 나머지는 모두 문자열로 처리 (unrecognized selector 에러 방지)
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

# --- [핵심 추가] 외부 소스 병합 로직 ---
def sync_external_source(base_data, url):
    try:
        print(f"🌐 외부 소스 동기화 중: {url}")
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            external_data = response.json()
            ext_apps = external_data.get("apps", [])
            
            # 기존 앱 목록의 번들 ID 세트 생성
            existing_bids = {app.get("bundleIdentifier") for app in base_data.get("apps", []) if app.get("bundleIdentifier")}
            
            for ext_app in ext_apps:
                bid = ext_app.get("bundleIdentifier")
                if not bid: continue
                
                # 내 소스에 없는 앱이면 새로 추가
                if bid not in existing_bids:
                    print(f"✅ 새 앱 추가: {ext_app.get('name')}")
                    base_data["apps"].append(ext_app)
                else:
                    # 기존에 있는 앱이면 외부의 최신 정보를 반영
                    for i, app in enumerate(base_data["apps"]):
                        if app.get("bundleIdentifier") == bid:
                            # 기존 데이터를 외부 소스 데이터로 업데이트
                            base_data["apps"][i].update(ext_app)
                            break
    except Exception as e:
        print(f"❌ 외부 소스 로드 실패: {e}")

# 외부 소스 병합 실행
sync_external_source(base_data, EXTERNAL_SOURCE_URL)

# --- 3. 업데이트 및 데이터 동기화 (과거 버전 보존 로직) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    # 현재 폴더에 있는 IPA 중 번들ID가 일치하는 파일 찾기
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        
        # 1. 앱의 기본 정보를 현재 파일 기준으로 업데이트
        app["version"] = str(info['version'])
        app["downloadURL"] = str(url)
        app["size"] = int(info['size'])
        
        # 2. 새로운 버전 객체 생성
        new_v = {
            "version": str(info['version']), 
            "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
            "downloadURL": str(url), 
            "size": int(info['size']),
            "buildVersion": "",
            "localizedDescription": "NightFox Build", 
            "minOSVersion": ""
        }
        
        # 3. [핵심] 과거 버전 유지 로직
        if "versions" not in app:
            app["versions"] = []
            
        # 이미 같은 버전이 리스트에 있는지 확인
        version_exists = False
        for i, v in enumerate(app["versions"]):
            if v.get("version") == info['version']:
                # 같은 버전이 이미 있다면 최신 정보(URL 등)만 업데이트
                app["versions"][i] = new_v
                version_exists = True
                break
        
        # 새로운 버전이라면 리스트의 맨 앞에 추가 (기존 데이터는 뒤로 밀림)
        if not version_exists:
            app["versions"].insert(0, new_v)
            
    # IPA 파일이 없더라도 기존에 저장된 versions 데이터가 있다면 상위 필드 유지
    elif app.get("versions"):
        latest = app["versions"][0]
        app["version"] = str(latest.get("version", app.get("version", "")))
        app["downloadURL"] = str(latest.get("downloadURL", app.get("downloadURL", "")))
        app["size"] = int(latest.get("size", app.get("size", 0)))


# --- 4. 최종 클리닝 및 저장 ---
# 사이드스토어에서 불필요하거나 문제를 일으킬 수 있는 필드 제거
for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

# [정당화] 전체 데이터를 사이드스토어 규격(size=Int, 나머지=String)으로 일괄 세척
base_data = clean_for_sidestore(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 외부 소스 병합 및 모든 데이터 최적화 완료!")
