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
                    'name': str(plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ""),
                    'version': str(plist.get('CFBundleShortVersionString') or "1.0"),
                    'bundleID': str(plist.get('CFBundleIdentifier') or ""),
                    'size': os.path.getsize(ipa_path) # 내부 계산용 숫자
                }
    except: return None

# [정당화] 사이드스토어는 'size'만 Int형을 원하고 나머지는 String을 원함
def clean_for_sidestore(obj):
    if isinstance(obj, list):
        return [clean_for_sidestore(x) for x in obj]
    elif isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            # 'size' 필드만큼은 따옴표 없는 숫자로 유지 (Int64 대응)
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
        "description": "Welcome to NightFox's source!",
        "iconURL": "https://i.imgur.com/Se6jHAj.png",
        "website": f"https://github.com/{REPO_NAME}",
        "tintColor": "#00b39e",
        "apps": []
    }

# 불필요한 필드 즉시 제거
for unwanted in ["featuredApps", "patreonURL"]:
    base_data.pop(unwanted, None)

# --- 3. 업데이트 및 데이터 동기화 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for app in base_data.get('apps', []):
    bid = app.get("bundleIdentifier")
    ipa_match = next((f for f in ipa_files if extract_ipa_info(f) and extract_ipa_info(f)['bundleID'] == bid), None)
    
    if ipa_match:
        info = extract_ipa_info(ipa_match)
        url = assets.get(ipa_match) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_match.replace(' ', '%20')}"
        
        # 최신 정보 업데이트 (임시로 변수에 저장, 최종 세척기에서 타입 결정)
        app["version"] = str(info['version'])
        app["downloadURL"] = str(url)
        app["size"] = int(info['size'])
        
        new_v = {
            "version": str(info['version']), 
            "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"), 
            "downloadURL": str(url), 
            "size": int(info['size']),
            "buildVersion": "",
            "localizedDescription": "NightFox Build", 
            "minOSVersion": ""
        }
        
        if "versions" not in app: app["versions"] = []
        app["versions"] = [v for v in app["versions"] if v.get('version') != info['version']]
        app["versions"].insert(0, new_v)
        
    elif app.get("versions"):
        # IPA 파일이 없어도 기존 데이터에서 상위 필드 복구
        latest = app["versions"][0]
        app["version"] = str(latest.get("version", ""))
        app["downloadURL"] = str(latest.get("downloadURL", ""))
        try:
            app["size"] = int(latest.get("size", 0))
        except:
            app["size"] = 0

# --- 4. 최종 클리닝 및 저장 ---
for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

# [핵심] 전체 데이터를 사이드스토어 규격(size=Int, 나머지=String)으로 일괄 변환
base_data = clean_for_sidestore(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("🎉 모든 에러 해결 및 사이드스토어 최적화 완료!")
