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
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName'),
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier'),
                    'size': os.path.getsize(ipa_path)
                }
    except: return None

# --- 2. 데이터 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        base_data = json.load(f)
else:
    # 헤더 정보가 날아가지 않게 기본값 설정
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

# --- 3. GitHub 릴리즈에서 최신 에셋 정보 가져오기 ---
# [정당화] IPA 파일이 로컬에 없어도 릴리즈 정보를 바탕으로 JSON을 업데이트하기 위함
all_releases = repo.get_releases()
assets_info = []

for r in all_releases:
    for asset in r.get_assets():
        if asset.name.lower().endswith('.ipa'):
            assets_info.append({
                "name": asset.name,
                "url": asset.browser_download_url,
                "size": asset.size,
                "date": asset.created_at.strftime("%Y-%m-%dT%H:%M:%S+09:00")
            })

# --- 4. 앱 데이터 업데이트 로직 ---
# 현재 폴더에 있는 IPA 파일들도 체크
local_ipa_files = [f for f in os.listdir('.') if f.lower().endswith('.ipa')]

for asset in assets_info:
    # 파일 이름에서 대략적인 정보 추측 (추출이 안 될 경우 대비)
    # 실제로는 로컬에 파일이 있어야 bundleID 추출이 정확합니다.
    
    # 릴리즈된 IPA 이름과 일치하는 앱 찾기
    found = False
    for app in base_data.get('apps', []):
        # 파일명에 앱 이름이 포함되어 있는지 확인하거나, 기존 downloadURL과 매칭
        if asset['name'] in app.get('downloadURL', '') or asset['url'] == app.get('downloadURL', ''):
            app["version"] = app.get("version") # 기존 버전 유지 또는 수동 수정 필요
            app["downloadURL"] = asset['url']
            app["size"] = asset['size']
            
            # 최상위 필드 업데이트
            new_v = {
                "version": app["version"],
                "date": asset['date'],
                "downloadURL": asset['url'],
                "size": asset['size']
            }
            if "versions" not in app: app["versions"] = []
            # 중복 방지 로직
            if not any(v.get('downloadURL') == asset['url'] for v in app["versions"]):
                app["versions"].insert(0, new_v)
            found = True
            break

# --- 5. 최종 세척 및 저장 ---
# 사이드스토어 에러 유발 필드 제거
for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID"]:
        app.pop(key, None)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 총 {len(assets_info)}개의 릴리즈 에셋을 확인하고 JSON을 업데이트했습니다.")
