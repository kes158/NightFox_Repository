import os
import json
import requests
import re
from datetime import datetime, timezone

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

YTPLUS_RELEASES_API = "https://api.github.com/repos/kes158/YT_5.2.1/releases"
YOUTUBE_BUNDLE_ID = "com.google.ios.youtube"

YTMUSIC_RELEASES_API = "https://api.github.com/repos/kes158/YTMusicUltimate/releases"
YTMUSIC_BUNDLE_ID = "com.google.ios.youtubemusic"


NIGHTFOX_REPO = "kes158/NightFox_Repository"
NIGHTFOX_RELEASES_API = f"https://api.github.com/repos/{NIGHTFOX_REPO}/releases"


def get_release_date(release):
    """published_at을 우선 사용, 없으면 created_at 폴백"""
    return release.get("published_at") or release.get("created_at")


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

# news는 list일 때만 그대로 사용, 아니면 빈 리스트
_news_value = base_data.get("news")
preserved_news = _news_value if isinstance(_news_value, list) else []

# headerURL은 문자열일 때만 사용
_header_value = base_data.get("headerURL")
preserved_header = _header_value if isinstance(_header_value, str) else ""

clean_base = {
    "name": base_data.get("name", "NightFox"),
    "identifier": current_identifier,
    "subtitle": base_data.get("subtitle", "NightFox's App Repository"),
    "description": base_data.get("description", "Welcome to NightFox's source!"),
    "iconURL": base_data.get("iconURL", "https://i.imgur.com/Se6jHAj.png"),
    "website": base_data.get("website", "https://github.com/kes158/NightFox_Repository"),
    "tintColor": base_data.get("tintColor", "#00b39e"),
    "headerURL": preserved_header,
    "apps": [],
    "news": preserved_news
}


# --- 3. 외부 데이터 수집 ---

# 3-1. Spotify 미러
spotify_apps_from_mirror = []
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        spotify_apps_from_mirror = [app for app in external_data.get("apps", []) if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]
except Exception as e:
    print(f"❌ 스포티파이 미러 로드 실패: {e}")

# 3-2. YouTube
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
                release_date = get_release_date(release)
                print(f"  📅 [YouTube] {version_str} → published_at: {release.get('published_at')} / created_at: {release.get('created_at')} → 사용: {release_date}")
                yt_releases_from_github.append({
                    "version": version_str,
                    "buildVersion": version_str,
                    "date": release_date,
                    "downloadURL": ipa_asset.get("browser_download_url"),
                    "size": ipa_asset.get("size"),
                    "localizedDescription": release.get("body", "")
                })
except Exception as e:
    print(f"❌ YouTube 릴리즈 로드 실패: {e}")


# 3-3. YouTube Music
ytmusic_releases_from_github = []
try:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"token {os.getenv('GITHUB_TOKEN')}"
    response = requests.get(YTMUSIC_RELEASES_API, headers=headers, timeout=15)
    if response.status_code == 200:
        for release in response.json():
            ipa_asset = next((a for a in release.get("assets", []) if a.get("name", "").lower().endswith(".ipa")), None)
            if ipa_asset:
                tag = release.get("tag_name", "")
                version_match = re.search(r'(\d+\.\d+\.\d+)$', tag)
                version_str = version_match.group(1) if version_match else tag.lstrip("v")
                release_date = get_release_date(release)
                print(f"  📅 [YouTube Music] {version_str} → published_at: {release.get('published_at')} / created_at: {release.get('created_at')} → 사용: {release_date}")
                ytmusic_releases_from_github.append({
                    "version": version_str,
                    "buildVersion": version_str,
                    "date": release_date,
                    "downloadURL": ipa_asset.get("browser_download_url"),
                    "size": ipa_asset.get("size"),
                    "localizedDescription": release.get("body", "")
                })
    else:
        print(f"❌ YouTube Music 릴리즈 로드 실패: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ YouTube Music 릴리즈 로드 실패: {e}")


# === 3-3. 본인 릴리즈 Spotify (NightFox fallback 적용) ===
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

                        body = release.get("body") or ""
                        body = body.strip().replace('\r\n', '\n').replace('\r', '\n')

                        if body:
                            localized_desc = body
                            print(f"  ✅ [NightFox] 릴리즈 노트 감지됨")
                        else:
                            localized_desc = "NightFox"
                            print(f"  ⚠️ [NightFox] 릴리즈 노트 없음 → 'NightFox' 적용")

                        release_date = get_release_date(release)
                        nightfox_spotify[bid].append({
                            "version": ver,
                            "buildVersion": ver,
                            "date": release_date,
                            "downloadURL": asset.get("browser_download_url"),
                            "size": asset.get("size"),
                            "localizedDescription": localized_desc
                        })
                        print(f"  ➕ [NightFox Release] {name} 추가 → {bid}")
except Exception as e:
    print(f"❌ NightFox 본인 릴리즈 로드 실패: {e}")


# --- 4. 정제 함수 ---
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
    new_app["versions"] = sorted(cleaned_versions, key=lambda x: [int(p) for p in x.get("version", "0").split(".")], reverse=True)
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
    return new_app


# --- 5. 앱 병합 ---
original_apps = base_data.get("apps", [])
final_apps = []
processed_bids = set()

for app in original_apps:
    bid = app.get("bundleIdentifier")
    if bid in processed_bids: continue

    my_versions = {v.get("version"): clean_version(v) for v in app.get("versions", [])}

    if bid == YOUTUBE_BUNDLE_ID and yt_releases_from_github:
        for rel in yt_releases_from_github:
            v_str = rel.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(rel)
                print(f"  ➕ [YouTube] 새 릴리즈 추가: {v_str}")

    elif bid == YTMUSIC_BUNDLE_ID and ytmusic_releases_from_github:
        for rel in ytmusic_releases_from_github:
            v_str = rel.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(rel)
                print(f"  ➕ [YouTube Music] 새 릴리즈 추가: {v_str}")

    elif bid in SPOTIFY_BUNDLE_IDS:
        mirror_app = next((s for s in spotify_apps_from_mirror if s.get("bundleIdentifier") == bid), None)
        if mirror_app:
            for v in mirror_app.get("versions", []):
                v_str = v.get("version")
                if v_str not in my_versions:
                    my_versions[v_str] = clean_version(v)
                    print(f"  ➕ [Spotify Mirror] 새 버전 추가: {v_str}")

        for v in nightfox_spotify.get(bid, []):
            v_str = v.get("version")
            if v_str not in my_versions:
                my_versions[v_str] = clean_version(v)
                print(f"  ➕ [NightFox Release] 새 버전 추가: {v_str} → {bid}")

    final_apps.append(clean_app(app, list(my_versions.values())))
    processed_bids.add(bid)

# --- 6. 저장 ---
clean_base["apps"] = final_apps

# headerURL이 빈 문자열이면 키 제거 (news는 항상 보존)
if not clean_base.get("headerURL"):
    clean_base.pop("headerURL", None)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"\n🎉 통합 업데이트 완료! (총 앱 수: {len(final_apps)})")
print(f"📰 news 항목 수: {len(clean_base['news'])}")
