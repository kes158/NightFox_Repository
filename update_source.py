import os
import json
import requests
import re
from datetime import datetime

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

# 외부 소스
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

YTPLUS_RELEASES_API = "https://api.github.com/repos/kes158/YT_5.2.1/releases"
YOUTUBE_BUNDLE_ID = "com.google.ios.youtube"

# === 새로 추가: 본인 릴리즈에서 Spotify 가져오기 ===
NIGHTFOX_REPO = "kes158/NightFox_Repository"
NIGHTFOX_RELEASES_API = f"https://api.github.com/repos/{NIGHTFOX_REPO}/releases"


# --- 1. JSON 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
        except:
            base_data = {"name": "NightFox", "apps": []}
else:
    base_data = {"name": "NightFox", "apps": []}


# --- 2. 최상위 필드 보존 ---
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


# --- 3. 외부 데이터 수집 ---

# 3-1. Spotify 미러 (기존)
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
    print(f"❌ 스포티파이 미러 로드 실패: {e}")

# 3-2. YouTube (기존)
yt_releases_from_github = []
try:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.getenv('GITHUB_TOKEN')}"
        
    response = requests.get(YTPLUS_RELEASES_API, headers=headers, timeout=15)
    if response.status_code == 200:
        for release in response.json():
            ipa_asset = next((a for a in release.get("assets", []) if a.get("name", "").endswith(".ipa")), None)
            if ipa_asset:
                tag = release.get("tag_name", "")
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


# === 3-3. 본인 릴리즈에서 Spotify 감지 (새로 추가) ===
nightfox_spotify = {"com.spotify.client": [], "com.spotify.client.patched": []}

try:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.getenv('GITHUB_TOKEN')}"
    
    response = requests.get(NIGHTFOX_RELEASES_API, headers=headers, timeout=15)
    if response.status_code == 200:
        for release in response.json():
            for asset in release.get("assets", []):
                name = asset.get("name", "")
                if name.startswith("EeveeSpotify_v") and name.endswith(".ipa"):
                    version_match = re.search(r'EeveeSpotify_v(\d+\.\d+\.\d+)', name)
                    if version_match:
                        ver = version_match.group(1)
                        is_patched = "_Patched" in name or "_patched" in name
                        bid = "com.spotify.client.patched" if is_patched else "com.spotify.client"
                        
                        nightfox_spotify[bid].append({
                            "version": ver,
                            "buildVersion": ver,
                            "date": release.get("created_at") or datetime.now().isoformat(),
                            "downloadURL": asset.get("browser_download_url"),
                            "size": asset.get("size"),
                            "localizedDescription": release.get("body", "") or f"EeveeSpotify {ver}" + (" (Patched)" if is_patched else "")
                        })
                        print(f"  ➕ [NightFox Release] {name} 감지 → {bid}")
except Exception as e:
    print(f"❌ NightFox 본인 릴리즈 로드 실패: {e}")


# --- 4. 정제 함수 (기존과 동일) ---
ALLOWED_APP_KEYS = {"name", "bundleIdentifier", "developerName", "subtitle", "localizedDescription", "iconURL", "versions", "tintColor"}
ALLOWED_VER_KEYS = {"version", "buildVersion", "date", "downloadURL", "localizedDescription", "size", "minOSVersion"}

def clean_version(v):
    new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
    if not new_v.get("buildVersion"):
        new_v["buildVersion"] = new_v.get("version", "1.0.0")
    new_v["minOSVersion"] = "16.1"
    if new_v.get("localizedDescription") is None:
        new_v["localizedDescription"] = ""
    return new_v

def clean_app(app, cleaned_versions):
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    new_app["versions"] = sorted(
        cleaned_versions,
        key=lambda x: [int(p) for p in x.get("version", "0").split(".")],
        reverse=True
    )
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
    return new_app


# --- 5. 앱 병합 (여기서 본인 릴리즈도 함께 병합) ---
original_apps = base_data.get("apps", [])
final_apps = []
processed_bids = set()

for app in original_apps:
    bid = app.get("bundleIdentifier")
    if bid in processed_bids: continue

    my_versions = {v.get("version"): clean_version(v) for v in app.get("versions", [])}

    # YouTube (기존)
    if bid == YOUTUBE_BUNDLE_ID and yt_releases_from_github:
        for rel in yt_releases_from_github:
            v_str = rel.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(rel)
                print(f"  ➕ [YouTube] 새 릴리즈 추가: {v_str}")

    # Spotify (미러 + 본인 릴리즈)
    elif bid in SPOTIFY_BUNDLE_IDS:
        # 미러 데이터 병합
        mirror_app = next((s for s in spotify_apps_from_mirror if s.get("bundleIdentifier") == bid), None)
        if mirror_app:
            for v in mirror_app.get("versions", []):
                v_str = v.get("version")
                if v_str not in my_versions:
                    my_versions[v_str] = clean_version(v)
                    print(f"  ➕ [Spotify Mirror] 새 버전 추가: {v_str}")

        # 본인 릴리즈 데이터 병합 (우선순위 높음)
        for v in nightfox_spotify.get(bid, []):
            v_str = v.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(v)
                print(f"  ➕ [NightFox Release] 새 버전 추가: {v_str} → {bid}")

    final_apps.append(clean_app(app, list(my_versions.values())))
    processed_bids.add(bid)

# --- 6. 저장 ---
clean_base["apps"] = final_apps
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"🎉 통합 업데이트 완료! (총 앱 수: {len(final_apps)})")
