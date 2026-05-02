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
# 기존 JSON에 identifier가 있다면 그것을 사용하고, 없으면 기본값을 할당합니다.
current_identifier = base_data.get("identifier") or "com.nightfox.repository"

clean_base = {
    "name": base_data.get("name", "NightFox"),
    "identifier": current_identifier, # 기존 identifier를 보존합니다.
    "subtitle": base_data.get("subtitle", "NightFox's App Repository"),
    "description": base_data.get("description", "Welcome to NightFox's source!"),
    "iconURL": base_data.get("iconURL", "https://i.imgur.com/Se6jHAj.png"),
    "website": base_data.get("website", "https://github.com/kes158/NightFox_Repository"),
    "tintColor": base_data.get("tintColor", "#00b39e"), # 최상위 tintColor 보존
    "apps": []
}

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

# --- 4. 앱 목록 조합 (기존 순서 및 데이터 유지) ---
final_apps = []
spotify_inserted = set()
original_apps = base_data.get("apps", [])

for app in original_apps:
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

# --- 5. 데이터 정제 및 앱별 tintColor 보존 (SideStore 호환성 패치) ---
cleaned_apps = []
# 앱 레벨 허용 키 (tintColor 포함)
ALLOWED_APP_KEYS = {
    "name", "bundleIdentifier", "developerName", "subtitle", 
    "localizedDescription", "iconURL", "versions", "tintColor"
}
# 버전 레벨 허용 키
ALLOWED_VER_KEYS = {
    "version", "buildVersion", "date", "downloadURL", 
    "localizedDescription", "size", "minOSVersion"
}

for app in final_apps:
    # 앱 레벨 필터링 (개별 앱의 tintColor 보존)
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    
    if "versions" in app:
        new_versions = []
        for v in app["versions"]:
            # 버전 레벨 필터링 (공증 관련 필드 제거)
            new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
            
            # buildVersion 보완 (SideStore 필수 요구사항)
            if not new_v.get("buildVersion") or new_v["buildVersion"] == "":
                new_v["buildVersion"] = new_v.get("version", "1.0.0")
            
            # null 값 방지
            for key in ["localizedDescription", "minOSVersion"]:
                if new_v.get(key) is None:
                    new_v[key] = ""
            
            new_versions.append(new_v)
        
        # 버전 최신순 정렬
        new_app["versions"] = sorted(new_versions, key=lambda x: x.get("date", ""), reverse=True)
    
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
        
    cleaned_apps.append(new_app)

clean_base["apps"] = cleaned_apps

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"🎉 identifier, tintColor(최상위/앱별)가 모두 보존된 SideStore 호환 패치가 완료되었습니다!")
