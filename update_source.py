import os
import json
import plistlib
import zipfile
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
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or "",
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier') or "",
                    'size': os.path.getsize(ipa_path)
                }
    except: return None

# [중요] 모든 null(None) 값을 ""으로 바꾸는 함수
def clean_none_to_empty(obj):
    if isinstance(obj, list):
        return [clean_none_to_empty(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: (clean_none_to_empty(v) if v is not None else "") for k, v in obj.items()}
    return obj

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
        "description": "Welcome to NightFox's source!",
        "iconURL": "https://i.imgur.com/Se6jHAj.png",
        "website": f"https://github.com/{REPO_NAME}",
        "patreonURL": "https://patreon.com/altstudio",
        "tintColor": "#00b39e",
        "apps": []
    }

# 불필요한 필드 제거 (featuredApps 등)
base_data.pop("featuredApps", None)

# --- 3. 업데이트 및 데이터 끌어올리기 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    # IPA 파일이 있는 경우 최신 정보로 갱신
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        app["version"] = info['version']
        app["downloadURL"] = url
        app["size"] = info['size']
        
        new_v = {
            "version": info['version'], 
            "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
            "downloadURL": url, 
            "size": info['size'],
            "buildVersion": "", # null 대신 빈칸
            "localizedDescription": "NightFox", # null 대신 기본값
            "minOSVersion": "" # null 대신 빈칸
        }
        if "versions" not in app: app["versions"] = []
        app["versions"] = [v for v in app["versions"] if v.get('version') != info['version']]
        app["versions"].insert(0, new_v)
        
    # 상위 필드가 비어있으면 하위에서 가져옴
    elif not app.get("version") or app.get("version") == "":
        if app.get("versions"):
            latest = app["versions"][0]
            app["version"] = latest.get("version", "")
            app["downloadURL"] = latest.get("downloadURL", "")
            app["size"] = latest.get("size", 0)

# --- 4. 최종 세척 (null 제거 및 필드 삭제) ---
for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)
    
    # 각 버전 내부의 null 체크
    if "versions" in app:
        for v in app["versions"]:
            if v.get("buildVersion") is None: v["buildVersion"] = ""
            if v.get("localizedDescription") is None: v["localizedDescription"] = ""
            if v.get("minOSVersion") is None: v["minOSVersion"] = ""

# 전체 데이터에 대해 다시 한번 null 세척
base_data = clean_none_to_empty(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 null 제거 및 빈 칸 채우기 완료! 사이드스토어 최적화가 끝났습니다.")
