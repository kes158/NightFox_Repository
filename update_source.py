import os
import json
import base64
import plistlib
import zipfile
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 및 인증 (kes158님 환경 최적화) ---
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
    """IPA 파일 내부 정보를 추출합니다."""
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            app_dir = os.path.dirname(plist_path)
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                return {
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ipa_path,
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier'),
                    'size': os.path.getsize(ipa_path),
                    'buildVersion': plist.get('CFBundleVersion')
                }
    except Exception as e:
        print(f"⚠️ {ipa_path} 정보 추출 실패: {e}")
        return None

def apply_nightfox_branding(entry):
    """브랜딩 정보를 적용합니다. (이름은 건드리지 않음)"""
    entry["developerName"] = "NightFox"
    entry["subtitle"] = "NightFox"
    entry["localizedDescription"] = "NightFox"

# --- 3. 기본 데이터 구조 정의 (뉴스 삭제) ---
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

# --- 4. 기존 데이터 로드 및 뉴스 로직 제거 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded_data = json.load(f)
            # 뉴스 필드가 있다면 삭제
            if 'news' in loaded_data:
                del loaded_data['news']
            base_data.update(loaded_data)
        except Exception as e:
            print(f"기존 JSON 읽기 오류: {e}")

# --- 5. 릴리즈 자산 및 IPA 처리 ---
all_release_assets = {asset.name: asset.browser_download_url 
                      for release in repo.get_releases() 
                      for asset in release.get_assets() 
                      if asset.name.lower().endswith('.ipa')}

ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue

    current_version = info.get('version', '1.0')
    current_bundle_id = info.get('bundleID')
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"

    # 기존에 등록된 앱인지 확인
    app_entry = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == current_bundle_id), None)

    new_v = {
        "version": current_version,
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url,
        "size": info.get('size', 0)
    }

    if app_entry:
        # [정당화] 기존 앱이 있다면 버전과 URL만 업데이트하고 'name'은 건드리지 않습니다.
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: app_entry["versions"] = []
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
    else:
        # 새로운 앱인 경우에만 추출된 이름을 사용합니다.
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
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 작업 완료: {JSON_FILE} (기존 이름 유지 모드)")
