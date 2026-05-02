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

# --- 2. 필수 최상위 필드 보완 (Code 101 해결 핵심) ---
# SideStore 소스 인식을 위해 identifier가 반드시 필요합니다.
if "identifier" not in base_data or not base_data["identifier"]:
    base_data["identifier"] = "com.nightfox.repository" # 고유 식별자 추가
if "apps" not in base_data:
    base_data["apps"] = []

# --- 3. 스포티파이 외부 소스 미러링 ---
spotify_apps = []
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        for app in external_data.get("apps", []):
            if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS:
                spotify_apps.append(app)
except Exception as e:
    print(f"❌ 외부 소스 로드 실패: {e}")
    spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]

# --- 4. 앱 목록 조합 (순서 유지) ---
final_apps = []
spotify_inserted = set()
for app in base_data["apps"]:
    bid = app.get("bundleIdentifier")
    if bid in SPOTIFY_BUNDLE_IDS:
        new_spotify = next((s for s in spotify_apps if s.get("bundleIdentifier") == bid), None)
        if new_spotify and bid not in spotify_inserted:
            final_apps.append(new_spotify)
            spotify_inserted.add(bid)
        elif bid not in spotify_inserted:
            final_apps.append(app)
            spotify_inserted.add(bid)
    else:
        final_apps.append(app)

for s_app in spotify_apps:
    if s_app.get("bundleIdentifier") not in spotify_inserted:
        final_apps.append(s_app)

base_data["apps"] = final_apps

# --- 5. 데이터 정제 (SideStore 호환성 작업) ---
for app in base_data["apps"]:
    if app.get("localizedDescription") is None:
        app["localizedDescription"] = ""

    if "versions" in app:
        for v in app["versions"]:
            current_ver = v.get("version", "1.0.0")
            
            # SideStore는 buildVersion에 실제 값이 있어야 합니다 (Code 4865 방지)
            if not v.get("buildVersion") or v["buildVersion"] == "":
                v["buildVersion"] = current_ver
            
            # 모든 null 값을 빈 문자열로 치환
            for key in ["localizedDescription", "minOSVersion"]:
                if v.get(key) is None:
                    v[key] = ""

        # 버전 날짜순 정렬
        app["versions"].sort(key=lambda x: x.get("date", ""), reverse=True)

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    # indent=2를 유지하여 가독성을 높이고 문법 오류를 방지합니다.
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 작업 완료! identifier 추가 및 모든 데이터 정제가 끝났습니다.")
