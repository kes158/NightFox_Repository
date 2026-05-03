import os
import json
import requests

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

# --- 1. JSON 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
        except:
            base_data = {"name": "NightFox", "apps": []}
else:
    base_data = {"name": "NightFox", "apps": []}

# --- 2. 최상위 필드 보존 로직 (identifier 및 tintColor 유지) ---
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

# --- 3. 스포티파이 외부 소스 미러링 ---
spotify_apps_from_mirror = []
mirror_failed = False
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        for app in external_data.get("apps", []):
            if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS:
                spotify_apps_from_mirror.append(app)
    else:
        mirror_failed = True
except Exception as e:
    print(f"❌ 외부 소스 로드 실패: {e}")
    mirror_failed = True

# --- 4. 버전/앱 정제 함수 ---
ALLOWED_APP_KEYS = {
    "name", "bundleIdentifier", "developerName", "subtitle",
    "localizedDescription", "iconURL", "versions", "tintColor"
}
ALLOWED_VER_KEYS = {
    "version", "buildVersion", "date", "downloadURL",
    "localizedDescription", "size", "minOSVersion"
}

def clean_version(v):
    new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
    current_build_ver = new_v.get("buildVersion")
    if current_build_ver is None or str(current_build_ver).strip() == "":
        new_v["buildVersion"] = new_v.get("version", "1.0.0")
    for key in ["localizedDescription", "minOSVersion"]:
        if new_v.get(key) is None:
            new_v[key] = ""
    return new_v

def clean_app(app, cleaned_versions):
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    new_app["versions"] = sorted(cleaned_versions, key=lambda x: x.get("date", ""), reverse=True)
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
    return new_app

# --- 5. 앱 목록 조합 ---
#   - 스포티파이: 내 JSON 버전 기준으로 보존 + 미러에만 있는 버전만 추가
#   - 스포티파이 외: 내 JSON 그대로 보존
#   - 미러에 새로 생긴 스포티파이 bundleId → 통째로 추가

original_apps = base_data.get("apps", [])
final_apps = []
spotify_inserted = set()

for app in original_apps:
    bid = app.get("bundleIdentifier")

    if bid in SPOTIFY_BUNDLE_IDS:
        if bid in spotify_inserted:
            continue

        # 내 JSON 버전 목록 (version 문자열을 키로)
        my_versions = {v.get("version"): clean_version(v) for v in app.get("versions", [])}

        if not mirror_failed:
            mirror_app = next(
                (s for s in spotify_apps_from_mirror if s.get("bundleIdentifier") == bid), None
            )
            if mirror_app:
                for v in mirror_app.get("versions", []):
                    ver_str = v.get("version")
                    if ver_str and ver_str not in my_versions:
                        # 내 JSON에 없는 버전만 미러에서 가져옴
                        my_versions[ver_str] = clean_version(v)
                        print(f"  ➕ [{bid}] 새 버전 추가: {ver_str}")
                    else:
                        print(f"  ✅ [{bid}] 기존 버전 유지: {ver_str}")

        merged_versions = list(my_versions.values())
        final_apps.append(clean_app(app, merged_versions))
        spotify_inserted.add(bid)

    else:
        # 스포티파이 외 앱은 그대로 보존
        cleaned_versions = [clean_version(v) for v in app.get("versions", [])]
        final_apps.append(clean_app(app, cleaned_versions))

# 미러에만 있고 내 JSON에 없는 새 스포티파이 앱 → 통째로 추가
if not mirror_failed:
    for mirror_app in spotify_apps_from_mirror:
        bid = mirror_app.get("bundleIdentifier")
        if bid not in spotify_inserted:
            cleaned_versions = [clean_version(v) for v in mirror_app.get("versions", [])]
            final_apps.append(clean_app(mirror_app, cleaned_versions))
            spotify_inserted.add(bid)
            print(f"  🆕 새 스포티파이 앱 추가: {bid}")

clean_base["apps"] = final_apps

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"🎉 수동 버전 보존 + 미러 병합 완료! (총 앱 수: {len(final_apps)})")
