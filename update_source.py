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
# SideStore가 오해하지 않도록 필수 필드만 정확히 세팅합니다.
base_data["name"] = "NightFox"
base_data["identifier"] = "com.nightfox.repository"
base_data.pop("notarized", None) 
base_data.pop("sourceURL", None)

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
    spotify_apps = [app for app in base_data.get("apps", []) if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]

# --- 4. 앱 목록 조합 (순서 유지) ---
final_apps = []
spotify_inserted = set()
for app in base_data.get("apps", []):
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

# --- 5. "Notarized" 오인 방지 및 데이터 정제 (Whitelist 방식) ---
# SideStore 구버전이 거부할 수 있는 비표준 필드를 모두 걸러냅니다.
cleaned_apps = []
ALLOWED_APP_KEYS = {"name", "bundleIdentifier", "developerName", "subtitle", "localizedDescription", "iconURL", "versions"}
ALLOWED_VER_KEYS = {"version", "buildVersion", "date", "downloadURL", "localizedDescription", "size", "minOSVersion"}

for app in final_apps:
    # 앱 레벨 세척
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    
    if "versions" in app:
        new_versions = []
        for v in app["versions"]:
            # 버전 레벨 세척 (notarized, appID, isNotarized 등 자동 제거)
            new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
            
            # buildVersion 필수 보완 (없으면 SideStore에서 오류 발생)
            if not new_v.get("buildVersion"):
                new_v["buildVersion"] = new_v.get("version", "1.0.0")
            
            # null 값 방지
            for key in ["localizedDescription", "minOSVersion"]:
                if new_v.get(key) is None:
                    new_v[key] = ""
            
            new_versions.append(new_v)
        
        # 버전 날짜순 정렬
        new_app["versions"] = sorted(new_versions, key=lambda x: x.get("date", ""), reverse=True)
    
    # 설명글 null 방지
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
        
    cleaned_apps.append(new_app)

base_data["apps"] = cleaned_apps

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 SideStore 호환성 강제 패치 및 데이터 정제 완료!")
