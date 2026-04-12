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

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try: base_data['apps'] = json.load(f).get('apps', [])
        except: pass

# --- 3. IPA 처리 및 '상위 등록' 로직 ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

for ipa in ipa_files:
    info = extract_ipa_info(ipa)
    if not info: continue
    
    bid = info['bundleID']
    url = assets.get(ipa) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa.replace(' ', '%20')}"
    
    # [정당화] 사이드스토어 호환을 위해 '상위' 필드에 데이터 강제 주입
    app_entry = {
        "name": info['name'],
        "bundleIdentifier": bid,
        "developerName": "NightFox",
        "subtitle": "NightFox",
        "localizedDescription": "NightFox",
        "iconURL": "https://i.imgur.com/nAsnPKq.png",
        "tintColor": "#00b39e",
        "category": "other",
        "version": info['version'],     # <--- 상위에 등록
        "downloadURL": url,            # <--- 상위에 등록
        "size": info['size'],           # <--- 상위에 등록
        "versions": [                   # <--- 하위는 최소한의 정보만 유지
            {
                "version": info['version'],
                "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "downloadURL": url,
                "size": info['size']
            }
        ]
    }

    # 기존 앱 찾아서 교체 (순서 유지)
    idx = next((i for i, a in enumerate(base_data['apps']) if a.get('bundleIdentifier') == bid), -1)
    if idx != -1:
        # 기존 아이콘/색상 유지
        app_entry["iconURL"] = base_data['apps'][idx].get("iconURL", app_entry["iconURL"])
        app_entry["tintColor"] = base_data['apps'][idx].get("tintColor", app_entry["tintColor"])
        base_data['apps'][idx] = app_entry
    else:
        base_data['apps'].append(app_entry)

# --- 4. 최종 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print("✅ 하위 데이터를 상위 필드로 모두 끌어올렸습니다!")
