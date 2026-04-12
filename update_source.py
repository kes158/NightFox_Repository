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

# 파일명도 NightFox.json으로 고정했습니다.
JSON_FILE = "NightFox.json" 

# 최신 PyGithub 인증 방식
auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)

try:
    repo = g.get_repo(REPO_NAME)
    print(f"✅ 저장소 연결 성공: {REPO_NAME}")
except Exception as e:
    print(f"❌ 저장소 연결 실패: {REPO_NAME}")
    print(f"상세 오류: {e}")
    raise
# 최신 PyGithub 라이브러리 방식(DeprecationWarning 해결)
auth = Auth.Token(GITHUB_TOKEN)
g = Github(auth=auth)

try:
    repo = g.get_repo(REPO_NAME)
    print(f"✅ 저장소 연결 성공: {REPO_NAME}")
except Exception as e:
    print(f"❌ 저장소를 찾을 수 없습니다: {REPO_NAME}")
    print(f"오류 내용: {e}")
    raise  # 에러를 중단시키고 전체 내용을 보여줌

# --- 2. 필수 함수 (기존 로직 유지 필요) ---
def extract_ipa_info_only(ipa_path):
    """IPA 파일 내부를 분석하여 정보와 아이콘 데이터를 추출합니다."""
    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            # Info.plist 경로 찾기
            plist_path = next(f for f in z.namelist() if f.startswith('Payload/') and f.endswith('.app/Info.plist'))
            app_dir = os.path.dirname(plist_path)
            
            with z.open(plist_path) as f:
                plist = plistlib.load(f)
                bundle_id = plist.get('CFBundleIdentifier')
                
                # 아이콘 파일명 찾기 (CFBundleIcons 로직)
                icon_data = None
                try:
                    icon_files = plist.get('CFBundleIcons', {}).get('CFBundlePrimaryIcon', {}).get('CFBundleIconFiles', [])
                    if not icon_files: # 아이패드 등 다른 경로 대응
                        icon_files = plist.get('CFBundleIconFiles', [])
                    
                    if icon_files:
                        # 가장 큰 사이즈의 아이콘을 찾기 위해 마지막 파일 선택
                        target_icon_name = icon_files[-1]
                        # 실제 파일명은 'icon@3x.png' 형태일 수 있으므로 유사 패턴 탐색
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
                    'icon_data': icon_data # 아이콘 바이트 데이터 추가
                }
    except Exception as e:
        print(f"⚠️ {ipa_path} 정보 추출 실패: {e}")
        return None

def apply_nightfox_branding(entry):
    """앱 항목에 NightFox 브랜딩을 적용합니다."""
    entry["developerName"] = "NightFox"
    entry["subtitle"] = "NightFox"
    entry["localizedDescription"] = "NightFox"

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
    # "news": [] 필드를 아예 정의하지 않습니다.
}

# --- 4. 기존 데이터 로드 및 필수 필드 강제 보정 (뉴스 로직 제거) ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            loaded_data = json.load(f)
            
            # 1. 기존 앱 리스트 가져오기
            base_data['apps'] = loaded_data.get('apps', [])
            
            # 2. 필수 필드 보정
            required_fields = [
                'name', 'identifier', 'subtitle', 'description', 
                'iconURL', 'website', 'tintColor'
            ]
            for field in required_fields:
                if field in base_data:
                    loaded_data[field] = base_data[field]

            # 3. [수정] 뉴스 데이터 처리 로직을 완전히 삭제했습니다.
            # 기존에는 여기서 loaded_data.get('news')를 처리했으나 이를 건너뜁니다.
            
            # 4. 보정된 내용을 base_data에 반영 (뉴스는 제외됨)
            if 'news' in loaded_data:
                del loaded_data['news'] # 혹시 있을 뉴스 데이터 삭제
            
            base_data.update(loaded_data)
            
        except Exception as e:
            print(f"기존 JSON 읽기 또는 보정 중 오류 발생: {e}")
            
# B. 모든 릴리즈에서 실제 IPA 다운로드 주소 수집
all_release_assets = {}
print("GitHub 모든 릴리즈에서 최신 다운로드 링크를 검색 중...")
for release in repo.get_releases():
    for asset in release.get_assets():
        if asset.name.lower().endswith('.ipa'):
            if asset.name not in all_release_assets:
                all_release_assets[asset.name] = asset.browser_download_url
                print(f"찾음: {asset.name} (태그: {release.tag_name})")

# C. 기존 JSON 앱 데이터 업데이트 (에러 방지 강화)
print("기존 JSON 앱 데이터의 링크를 검증 및 업데이트 중...")
for app in base_data.get("apps", []):
    # versions 리스트가 없는 항목은 아예 건너뜁니다.
    if "versions" not in app: continue
    
    for v in app["versions"]:
        # v가 딕셔너리가 아니거나 downloadURL이 없으면 패스
        if not isinstance(v, dict) or "downloadURL" not in v: continue
        
        file_name_in_url = v["downloadURL"].split('/')[-1].replace('%20', ' ')
        actual_url = all_release_assets.get(file_name_in_url)
        
        if actual_url and v["downloadURL"] != actual_url:
            print(f"링크 갱신: {app.get('name', '알 수 없는 앱')} ({v.get('version', '?.?')})")
            v["downloadURL"] = actual_url
            
            # 여기서 .get()을 써야 안전합니다.
            if app.get("version") == v.get("version") and app.get("version") is not None:
                app["downloadURL"] = actual_url

# D. 로컬 IPA 파일 처리 (대표 정보 업데이트 + 버전별 개별 링크 유지)
ipa_files = [f for f in os.listdir('.') if f.lower().endswith('.ipa')]

# 파일들을 이름순으로 정렬하여 처리 (일관성 유지)
ipa_files.sort()

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: 
        print(f"⚠️ {ipa_file}에서 정보를 추출할 수 없어 건너뜜")
        continue

    current_version = info.get('version', '1.0')
    current_bundle_id = info.get('bundleID')
    # 릴리즈에서 자산 링크 확인, 없으면 1.4.3 태그 기본값 사용
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/1.4.3/{ipa_file.replace(' ', '%20')}"

    # 1. 번들 ID가 정확히 일치하는 앱 항목 찾기
    app_entry = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == current_bundle_id), None)

    # 2. 이번 IPA 전용 '버전 객체' 생성 (이 객체 안에 해당 버전의 링크를 고정)
    new_v = {
        "version": current_version,
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url, # 해당 버전만의 고유 링크
        "size": info.get('size', 0),
        "buildVersion": info.get('buildVersion', None),
        "minOSVersion": info.get('minOSVersion', None)
    }

    if app_entry:
        # [정당화] 앱의 대표 정보(겉모습)는 현재 처리 중인 최신 파일로 갱신 [cite: 2026-03-31]
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: 
            app_entry["versions"] = []
        
        # [정당화] '현재 버전'과 같은 항목만 리스트에서 삭제 후 새 객체 삽입
        # 이 필터링 덕분에 다른 버전(예: 21.03.2)의 링크는 삭제되지 않고 보존됩니다. [cite: 2026-03-31]
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
        # 날짜순 정렬 (선택 사항: 최신 버전이 위로 오게 함)
        app_entry["versions"].sort(key=lambda x: x.get('version', ''), reverse=True)
    else:
        # 신규 앱 등록 (최초 등록 시)
        new_app = {
            "name": info.get('name', ipa_file),
            "bundleIdentifier": current_bundle_id,
            "version": current_version,
            "downloadURL": download_url,
            "iconURL": "https://i.imgur.com/nAsnPKq.png", # 기본 아이콘
            "tintColor": "#00b39e",
            "category": "other",
            "screenshots": [],
            "versions": [new_v]
        }
        apply_nightfox_branding(new_app)
        base_data['apps'].append(new_app)

print("✅ 버전별 링크 격리 및 대표 정보 업데이트 완료")

# 파일들을 이름순으로 정렬하여 처리 (일관성 유지)
ipa_files.sort()

for ipa_file in ipa_files:
    info = extract_ipa_info_only(ipa_file)
    if not info: 
        print(f"⚠️ {ipa_file}에서 정보를 추출할 수 없어 건너뜜")
        continue

    current_version = info.get('version', '1.0')
    current_bundle_id = info.get('bundleID')
    # 릴리즈에서 자산 링크 확인, 없으면 1.4.3 태그 기본값 사용
    download_url = all_release_assets.get(ipa_file) or f"{REPO_URL}/releases/download/1.4.3/{ipa_file.replace(' ', '%20')}"

    # 1. 번들 ID가 정확히 일치하는 앱 항목 찾기
    app_entry = next((a for a in base_data['apps'] if a.get('bundleIdentifier') == current_bundle_id), None)

    # 2. 이번 IPA 전용 '버전 객체' 생성 (이 객체 안에 해당 버전의 링크를 고정)
    new_v = {
        "version": current_version,
        "date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "localizedDescription": f"NightFox Build - {current_version}", 
        "downloadURL": download_url, # 해당 버전만의 고유 링크
        "size": info.get('size', 0),
        "buildVersion": info.get('buildVersion', None),
        "minOSVersion": info.get('minOSVersion', None)
    }

    if app_entry:
        # [정당화] 앱의 대표 정보(겉모습)는 현재 처리 중인 최신 파일로 갱신 [cite: 2026-03-31]
        app_entry["version"] = current_version
        app_entry["downloadURL"] = download_url
        apply_nightfox_branding(app_entry)
        
        if "versions" not in app_entry: 
            app_entry["versions"] = []
        
        # [정당화] '현재 버전'과 같은 항목만 리스트에서 삭제 후 새 객체 삽입
        # 이 필터링 덕분에 다른 버전(예: 21.03.2)의 링크는 삭제되지 않고 보존됩니다. [cite: 2026-03-31]
        app_entry["versions"] = [v for v in app_entry["versions"] if v.get('version') != current_version]
        app_entry["versions"].insert(0, new_v)
        # 날짜순 정렬 (선택 사항: 최신 버전이 위로 오게 함)
        app_entry["versions"].sort(key=lambda x: x.get('version', ''), reverse=True)
    else:
        # 신규 앱 등록 (최초 등록 시)
        new_app = {
            "name": info.get('name', ipa_file),
            "bundleIdentifier": current_bundle_id,
            "version": current_version,
            "downloadURL": download_url,
            "iconURL": "https://i.imgur.com/nAsnPKq.png", # 기본 아이콘
            "tintColor": "#00b39e",
            "category": "other",
            "screenshots": [],
            "versions": [new_v]
        }
        apply_nightfox_branding(new_app)
        base_data['apps'].append(new_app)

print("✅ 버전별 링크 격리 및 대표 정보 업데이트 완료")

# --- 5. 원자 단위 데이터 정제 (Feather 무한 로딩 해결책) ---

def atomic_clean(obj):
    """
    None, "", [], {} 등 모든 비어있는 요소를 재귀적으로 제거합니다.
    """
    if isinstance(obj, dict):
        # 값이 비어있지 않은 것만 골라서 다시 딕셔너리 생성
        cleaned_dict = {
            k: atomic_clean(v) 
            for k, v in obj.items() 
            if v is not None and v != "" and v != [] and v != {}
        }
        return cleaned_dict
    elif isinstance(obj, list):
        # 리스트 내부 요소 정제 후 비어있지 않은 것만 남김
        cleaned_list = [
            atomic_clean(i) 
            for i in obj 
            if i is not None and i != "" and i != [] and i != {}
        ]
        return cleaned_list
    else:
        return obj

# 전체 데이터에 청소 함수 적용
base_data = atomic_clean(base_data)

# --- 6. JSON 파일 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

# [꼼꼼한 수정 4] 변수명을 사용하여 정확한 로그 출력
print(f"🎉 모든 작업이 완료되었습니다! 파일명: {JSON_FILE}")
