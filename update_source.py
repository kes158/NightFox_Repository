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

# 스크립트 위치 기준 절대경로로 JSON 파일 경로 고정
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

# 스포티파이 외부 소스 URL
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
    except:
        return None

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

# --- 2. 데이터 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
            if "apps" not in base_data:
                base_data["apps"] = []
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

print(f"✅ JSON 로드 완료: 앱 {len(base_data['apps'])}개")

# --- 3. 외부 소스 동기화 (기존 앱 보호) ---
# [핵심 수정] 기존 앱을 .update()로 통째로 덮어쓰지 않고,
# bundleIdentifier가 없는 앱만 추가하고, 이미 있는 앱은 버전 정보만 병합합니다.
def sync_external_source(base_data, url):
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            print(f"❌ 외부 소스 응답 오류: {response.status_code}")
            return

        external_data = response.json()
        ext_apps = external_data.get("apps", [])
        existing_bids = {app.get("bundleIdentifier") for app in base_data.get("apps", []) if app.get("bundleIdentifier")}

        for ext_app in ext_apps:
            bid = ext_app.get("bundleIdentifier")
            if not bid:
                continue

            if bid not in existing_bids:
                # 기존에 없는 앱이면 새로 추가
                base_data["apps"].append(ext_app)
                existing_bids.add(bid)
                print(f"  ➕ 외부 소스 앱 추가: {ext_app.get('name', bid)}")
            else:
                # 이미 있는 앱이면 버전 목록만 병합 (기존 앱 메타데이터 유지)
                for i, app in enumerate(base_data["apps"]):
                    if app.get("bundleIdentifier") == bid:
                        ext_versions = ext_app.get("versions", [])
                        existing_versions = {v.get("version") for v in app.get("versions", [])}
                        added = 0
                        for v in ext_versions:
                            if v.get("version") not in existing_versions:
                                app.setdefault("versions", []).append(v)
                                existing_versions.add(v.get("version"))
                                added += 1
                        if added:
                            print(f"  🔄 외부 소스 버전 {added}개 병합: {app.get('name', bid)}")
                        break

    except Exception as e:
        print(f"❌ 외부 소스 로드 실패: {e}")

sync_external_source(base_data, EXTERNAL_SOURCE_URL)

# --- 4. 로컬 IPA 기반 앱 업데이트 ---
# IPA가 없는 앱은 건드리지 않고 그대로 유지됩니다.
ipa_files = sorted([f for f in os.listdir(SCRIPT_DIR) if f.lower().endswith('.ipa')])
assets = {asset.name: asset.browser_download_url for r in repo.get_releases() for asset in r.get_assets()}

print(f"📦 IPA 파일 {len(ipa_files)}개 발견")

for ipa_file in ipa_files:
    ipa_path = os.path.join(SCRIPT_DIR, ipa_file)
    info = extract_ipa_info(ipa_path)
    if not info:
        continue

    bid = info['bundleID']
    app = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == bid), None)

    if not app:
        app = {
            "name": info['name'],
            "bundleIdentifier": bid,
            "developerName": "NightFox",
            "iconURL": "https://i.imgur.com/Se6jHAj.png",
            "localizedDescription": "NightFox",
            "versions": []
        }
        base_data['apps'].append(app)
        print(f"  ➕ 새 앱 추가 (IPA): {info['name']}")

    url = assets.get(ipa_file) or f"https://github.com/{REPO_NAME}/releases/download/latest/{ipa_file.replace(' ', '%20')}"
    new_v = {
        "version": str(info['version']),
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "downloadURL": str(url),
        "size": int(info['size']),
        "localizedDescription": "NightFox"
    }

    if "versions" not in app:
        app["versions"] = []

    version_exists = False
    for i, v in enumerate(app["versions"]):
        if v.get("version") == info['version']:
            app["versions"][i] = new_v
            version_exists = True
            break
    if not version_exists:
        app["versions"].insert(0, new_v)

    if len(app["versions"]) > 1:
        app["versions"].sort(
            key=lambda x: [int(part) if part.isdigit() else 0 for part in x.get("version", "0").split('.')],
            reverse=True
        )

    latest_v = app["versions"][0]
    app["version"] = str(latest_v.get("version", ""))
    app["downloadURL"] = str(latest_v.get("downloadURL", ""))
    app["size"] = int(latest_v.get("size", 0))
    print(f"  ✅ 업데이트: {app['name']} v{app['version']}")

# --- 5. 최종 클리닝 및 저장 ---
for root_key in ["featuredApps", "marketplaceID", "patreonURL"]:
    base_data.pop(root_key, None)

for app in base_data.get('apps', []):
    for key in ["appPermissions", "patreon", "screenshots", "marketplaceID", "featuredApps"]:
        app.pop(key, None)

base_data = clean_for_sidestore(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"\n🎉 NightFox.json 업데이트 완료! 총 앱 {len(base_data['apps'])}개")
