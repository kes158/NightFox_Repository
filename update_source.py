import os
import json
import requests
import re

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

# 외부 소스 URL 설정[cite: 5, 6]
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

YTPLUS_RELEASES_API = "https://api.github.com/repos/kes158/YT_5.2.1/releases"
YOUTUBE_BUNDLE_ID = "com.google.ios.youtube"

# --- 1. JSON 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
        except:
            base_data = {"name": "NightFox", "apps": []}
else:
    base_data = {"name": "NightFox", "apps": []}

# --- 2. 최상위 필드 보존 로직 (identifier 및 기존 설정 유지) ---
current_identifier = base_data.get("identifier") or "com.nightfox.repository"

clean_base = {
    "name": base_data.get("name", "NightFox"),
    "identifier": current_identifier,
    "subtitle": base_data.get("subtitle", "NightFox's App Repository"),
    "description": base_data.get("description", "Welcome to NightFox's source!"),
    "iconURL": base_data.get("iconURL", "https://i.imgur.com/Se6jHAj.png"),
    "website": base_data.get("website", "https://github.com/kes158/NightFox_Repository"),
    "tintColor": base_data.get("tintColor", "#00b39e"),
    "headerURL": base_data.get("headerURL", ""),
    "apps": []
}

# --- 3. 외부 소스 데이터 가져오기 (Spotify & YouTube) ---[cite: 5, 6]
# 3-1. 스포티파이 미러링 데이터 로드
spotify_apps_from_mirror = []
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        spotify_apps_from_mirror = [
            app for app in external_data.get("apps", []) 
            if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS
        ]
except Exception as e:
    print(f"❌ 스포티파이 소스 로드 실패: {e}")

# 3-2. YouTube GitHub 릴리즈 데이터 로드
yt_releases_from_github = []
try:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.getenv('GITHUB_TOKEN')}"
        
    response = requests.get(YTPLUS_RELEASES_API, headers=headers, timeout=15)
    if response.status_code == 200:
        for release in response.json():
            # .ipa 파일 에셋 검색[cite: 6]
            ipa_asset = next((a for a in release.get("assets", []) if a.get("name", "").endswith(".ipa")), None)
            if ipa_asset:
                tag = release.get("tag_name", "")
                # 태그에서 버전 번호 추출 (예: 21.18.4)[cite: 6]
                version_match = re.search(r'(\d+\.\d+\.\d+)$', tag)
                version_str = version_match.group(1) if version_match else tag
                
                yt_releases_from_github.append({
                    "version": version_str,
                    "buildVersion": version_str,
                    "date": release.get("created_at"),
                    "downloadURL": ipa_asset.get("browser_download_url"),
                    "size": ipa_asset.get("size"),
                    "localizedDescription": release.get("body", "")
                })
except Exception as e:
    print(f"❌ YouTube 릴리즈 로드 실패: {e}")

# --- 4. 정제 함수 ---
ALLOWED_APP_KEYS = {"name", "bundleIdentifier", "developerName", "subtitle", "localizedDescription", "iconURL", "versions", "tintColor"}
ALLOWED_VER_KEYS = {"version", "buildVersion", "date", "downloadURL", "localizedDescription", "size", "minOSVersion"}

def clean_version(v):
    # 허용된 키만 필터링
    new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
    
    # buildVersion 누락 시 처리[cite: 5]
    if not new_v.get("buildVersion"):
        new_v["buildVersion"] = new_v.get("version", "1.0.0")
    
    # minOSVersion 16.1 고정 (핵심 요구사항)[cite: 5, 7]
    new_v["minOSVersion"] = "16.1"
    
    if new_v.get("localizedDescription") is None:
        new_v["localizedDescription"] = ""
    return new_v

def clean_app(app, cleaned_versions):
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    # 날짜 기준 최신순 정렬[cite: 7]
    new_app["versions"] = sorted(cleaned_versions, key=lambda x: x.get("date", ""), reverse=True)
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
    return new_app

# --- 5. 앱 목록 조합 및 미러링 병합 ---[cite: 6, 7]
original_apps = base_data.get("apps", [])
final_apps = []
processed_bids = set()

for app in original_apps:
    bid = app.get("bundleIdentifier")
    if bid in processed_bids: continue

    # 현재 내 JSON에 있는 버전들 (중복 방지용)[cite: 6]
    my_versions = {v.get("version"): clean_version(v) for v in app.get("versions", [])}

    # 5-1. YouTube 미러링 처리[cite: 6]
    if bid == YOUTUBE_BUNDLE_ID and yt_releases_from_github:
        for rel in yt_releases_from_github:
            v_str = rel.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(rel)
                print(f"  ➕ [YouTube] 새 릴리즈 추가: {v_str}")

    # 5-2. Spotify 미러링 처리[cite: 5, 7]
    elif bid in SPOTIFY_BUNDLE_IDS:
        mirror_app = next((s for s in spotify_apps_from_mirror if s.get("bundleIdentifier") == bid), None)
        if mirror_app:
            for v in mirror_app.get("versions", []):
                v_str = v.get("version")
                if v_str not in my_versions:
                    my_versions[v_str] = clean_version(v)
                    print(f"  ➕ [Spotify] 새 버전 추가: {v_str}")

    # 정제된 앱 추가
    final_apps.append(clean_app(app, list(my_versions.values())))
    processed_bids.add(bid)

# --- 6. 저장 ---
clean_base["apps"] = final_apps
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"🎉 통합 업데이트 완료! (총 앱 수: {len(final_apps)})")
