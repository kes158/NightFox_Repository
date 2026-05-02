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

# --- 2. 최상위 필드 정리 (SideStore 호환성 강화) ---
base_data["name"] = "NightFox"
base_data["identifier"] = "com.nightfox.repository"
# 공증 오류 방지를 위해 최상단에 관련 필드가 있다면 제거합니다.
base_data.pop("notarized", None) 

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

# --- 5. 데이터 정제 및 Notarized 오류 방지 (핵심) ---
for app in base_data["apps"]:
    # 앱 레벨에서 notarized 필드 강제 제거
    app.pop("notarized", None)
    
    if app.get("localizedDescription") is None:
        app["localizedDescription"] = ""

    if "versions" in app:
        for v in app["versions"]:
            # SideStore 호환을 위해 단순 버전 문자열만 사용
            current_ver = v.get("version", "1.0.0")
            
            # buildVersion이 비어있으면 공증 관련 오류를 유발할 수 있으므로 version으로 채움
            if not v.get("buildVersion") or v["buildVersion"] == "":
                v["buildVersion"] = current_ver
            
            # 버전 레벨에서도 notarized 관련 필드 삭제
            v.pop("notarized", None)
            v.pop("isNotarized", None)

            # null 값 방지
            for key in ["localizedDescription", "minOSVersion"]:
                if v.get(key) is None:
                    v[key] = ""

        # 버전 정렬
        app["versions"].sort(key=lambda x: x.get("date", ""), reverse=True)

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 Notarized 필드 제거 및 SideStore 호환성 패치 완료!")
