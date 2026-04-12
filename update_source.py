import os
import json
import base64
import plistlib
import zipfile
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 및 인증 (kes158님 환경에 최적화) ---
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
    print(f"상세 오류: {e}")
    raise

# --- 2. 필수 함수 ---
def extract_ipa_info_only(ipa_path):
    """IPA 파일 내부를 분석하여 정보와 아이콘 데이터를 추출합니다."""
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            app_dir = os.path.dirname(plist_path)
            
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                bundle_id = plist.get('CFBundleIdentifier')
                
                icon_data = None
                try:
                    icon_files = plist.get('CFBundleIcons', {}).get('CFBundlePrimaryIcon', {}).get('CFBundleIconFiles', [])
                    if not icon_files:
                        icon_files = plist.get('CFBundleIconFiles', [])
                    
                    if icon_files:
                        target_icon_name = icon_files[-1]
                        icon_path = next(f for f in z.namelist() if f.startswith(app_dir) and target_icon_name in f and f.endswith('.png'))
                        with z.open(icon_path) as img_f:
                            icon_data = img_f.read()
                except:
                    print(f"⚠️ {ipa_path}에서 아이콘을 찾는 데 실패했습니다.")

                return {
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ipa_path,
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': bundle_id,
                    'size': os.path.getsize(ipa_path),
                    'buildVersion': plist.get('CFBundleVersion'),
                    'icon_data': icon_data 
                }
    except Exception as e:
        print(f"⚠️ {ipa_path} 정보 추출 실패: {e}")
        return None

def apply_nightfox_branding(entry):
    """앱 항목에 NightFox 브랜딩 및 이름 변경을 적용합니다."""
    entry["developerName"] = "NightFox"
    entry["subtitle"] = "NightFox"
    entry["localizedDescription"] = "NightFox"
    
    # [정당화] 유튜브 번들 ID인 경우 이름을 YTPlus로 강제 고정합니다. [cite: 2026-03-31]
    if entry.get("bundleIdentifier") == "com.google.ios.youtube":
        entry["name"] = "YTPlus"

# --- 3. 기본 데이터 구조 정의 (뉴스 필드 삭제) ---
base_data = {
    "name": "NightFox",
    "identifier": "com.nightfox1.repo",
    "subtitle": "NightFox's App Repository",
    "description": "Welcome to NightFox's source!",
    "iconURL": "https://i.imgur.com/Se6jHAj.png",
    "website": REPO_URL,
    "tintColor": "#00b39e",
    "featuredApps": [],
    "apps": []
}

# --- 4. 기존 데이터 로드 및 뉴스 로직 제거 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded_data = json.load(f)
            base_data['apps'] = loaded_data.get('apps', [])
            
            # [정당화] 기존 데이터에 뉴스가 있다면 삭제하여 Feather 무한 로딩을 방지합니다. [cite: 2026-03-31]
            if 'news' in loaded_data:
                del loaded_data['news']
            
            # 필수 필드 보정
            required_fields = ['name', 'identifier', 'subtitle', 'description', 'iconURL', 'website', 'tintColor']
            for field in required_fields:
                if field in base_data:
                    loaded_data[field] = base_data[field]
            
            base_data.update(loaded_data)
        except Exception as e:
            print(f"기존 JSON 읽기 또는 보정 중 오류 발생: {e}")

# --- 5. 릴리즈 자산 및 IPA 처리 ---
all_release_assets = {}
for release in repo.get_releases():
    for asset in release.get_assets():
        if asset.name.lower().endswith('.ipa'):
            if asset.name not in all_release_assets:
                all_release_assets[asset.name] = asset.browser_download_url

ipa_files = [f for f in os.listdir('.') if f.lower().endswith('.ipa')]
ipa_files.sort()

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue

    current_version = info.get('version', '1.0')
    current_bundle_id = info.get('bundleID')
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"

    app_entry = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == current_bundle_id), None)

    new_v = {
        "version": current_version,
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url,
        "size": info.get('size', 0),
        "buildVersion": info.get('buildVersion', None)
    }

    if app_entry:
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        # 브랜딩 함수에서 YTPlus 이름 변경이 적용됩니다.
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: app_entry["versions"] = []
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
        app_entry["versions"].sort(key=lambda x: x.get('version', ''), reverse=True)
    else:
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

# --- 6. 원자 단위 데이터 정제 ---
def atomic_clean(obj):
    if isinstance(obj, dict):
        return {k: atomic_clean(v) for k, v in obj.items() if v is not None and v != "" and v != [] and v != {}}
    elif isinstance(obj, list):
        return [atomic_clean(i) for i in obj if i is not None and i != "" and i != [] and i != {}]
    else:
        return obj

base_data = atomic_clean(base_data)

# --- 7. JSON 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 작업 완료: {JSON_FILE} (YouTube -> YTPlus 적용됨)")
