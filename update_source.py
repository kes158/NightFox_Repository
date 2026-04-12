import os
import json
import base64
import plistlib
import zipfile
import requests
from datetime import datetime
from github import Github, Auth

# --- 1. 설정 및 인증 ---
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
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                return {
                    'name': plist.get('CFBundleDisplayName') or plist.get('CFBundleName') or ipa_path,
                    'version': plist.get('CFBundleShortVersionString') or "1.0",
                    'bundleID': plist.get('CFBundleIdentifier'),
                    'size': os.path.getsize(ipa_path)
                }
    except Exception as e:
        print(f"⚠️ {ipa_path} 정보 추출 실패: {e}")
        return None

def apply_nightfox_branding(entry):
    entry["developerName"] = "NightFox"
    entry["subtitle"] = "NightFox"
    # [정당화] null 방지를 위해 빈 문자열로 설정
    entry["localizedDescription"] = "NightFox"

# --- 3. 기본 데이터 구조 및 기존 데이터 로드 ---
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

if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded_data = json.load(f)
            if 'apps' in loaded_data:
                base_data['apps'] = loaded_data['apps']
            
            # 불필요한 필드 정리
            if 'news' in loaded_data: del loaded_data['news']
            if 'patreonURL' in loaded_data: del loaded_data['patreonURL']
            
            for key in base_data:
                if key != 'apps' and key in loaded_data:
                    base_data[key] = loaded_data[key]
        except Exception as e:
            print(f"⚠️ 기존 JSON 로드 오류: {e}")

# --- 4. 외부 소스 퍼오기 및 데이터 정제 ---
other_sources = [
    "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/main/source.json"
]

for source_url in other_sources:
    try:
        print(f"🌐 외부 소스 동기화 중: {source_url}")
        response = requests.get(source_url, timeout=10)
        if response.status_code == 200:
            other_data = response.json()
            for other_app in other_data.get('apps', []):
                # [정당화] 외부 소스의 null 값 및 날짜 형식 보정
                for v in other_app.get('versions', []):
                    if v.get('buildVersion') is None: v['buildVersion'] = ""
                    if v.get('localizedDescription') is None: v['localizedDescription'] = ""
                    # 사이드스토어 호환성을 위한 날짜 형식 보정
                    if len(v.get('date', '')) == 10:
                        v['date'] = f"{v['date']}T00:00:00+09:00"

                exists = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == other_app.get('bundleIdentifier')), None)
                if not exists:
                    base_data['apps'].append(other_app)
                    print(f"   ✅ 외부 앱 추가됨: {other_app.get('name')}")
    except Exception as e:
        print(f"   ⚠️ 외부 소스 로드 실패: {e}")

# --- 5. 내 저장소 IPA 처리 (순서 유지 및 데이터 정제) ---
ipa_files = sorted([f for f in os.listdir('.') if f.lower().endswith('.ipa')])

all_release_assets = {asset.name: asset.browser_download_url 
                      for release in repo.get_releases() 
                      for asset in release.get_assets() 
                      if asset.name.lower().endswith('.ipa')}

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: continue

    current_bundle_id = info.get('bundleID')
    current_version = info.get('version', '1.0')
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/latest/{ipa_file.replace(' ', '%20')}"

    # 기존 순서(인덱스) 확인
    found_index = -1
    for i, a in enumerate(base_data['apps']):
        if a.get('bundleIdentifier') == current_bundle_id:
            found_index = i
            break

    # [정당화] 신규 버전 생성 시 buildVersion을 ""로 고정
    new_v = {
        "version": current_version,
        "buildVersion": "",
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url,
        "size": info.get('size', 0)
    }

    if found_index != -1:
        # 기존 앱 업데이트 (위치 고정)
        app_entry = base_data['apps'][found_index]
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: app_entry["versions"] = []
        
        # [정당화] 기존 버전 리스트 내 null 값 일괄 청소
        for v in app_entry["versions"]:
            if v.get('buildVersion') is None: v['buildVersion'] = ""
            if v.get('localizedDescription') is None: v['localizedDescription'] = ""

        # 중복 버전 제거 후 최신 버전 삽입
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
    else:
        # 새로운 앱 추가
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

# --- 6. JSON 저장 전 최종 클리닝 로직 추가 ---
def clean_nulls(obj):
    if isinstance(obj, list):
        return [clean_nulls(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: (clean_nulls(v) if v is not None else "") for k, v in obj.items()}
    return obj

# 저장 직전에 실행
base_data = clean_nulls(base_data)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 모든 작업이 완료되었습니다: {JSON_FILE}")
