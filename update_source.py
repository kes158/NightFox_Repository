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

# --- 2. 최상위 필드 정리 및 tintColor 보존 ---
# SideStore 호환을 위해 필수 필드와 요청하신 시각적 필드만 남깁니다.
clean_base = {
    "name": "NightFox",
    "identifier": "com.nightfox.repository",
    "subtitle": base_data.get("subtitle", "NightFox's App Repository"),
    "description": base_data.get("description", "Welcome to NightFox's source!"),
    "iconURL": base_data.get("iconURL", "https://i.imgur.com/Se6jHAj.png"),
    "website": base_data.get("website", "https://github.com/kes158/NightFox_Repository"),
    "tintColor": base_data.get("tintColor", "#00b39e"), # tintColor를 유지합니다.
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

# --- 4. 앱 목록 조합 (순서 유지) ---
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

# --- 5. Notarized 오인 방지 강제 세척 (Whitelist 방식) ---
# SideStore 구버전이 거부할 수 있는 비표준 필드를 완전히 제거합니다.
cleaned_apps = []
ALLOWED_APP_KEYS = {"name", "bundleIdentifier", "developerName", "subtitle", "localizedDescription", "iconURL", "versions"}
ALLOWED_VER_KEYS = {"version", "buildVersion", "date", "downloadURL", "localizedDescription", "size", "minOSVersion"}

for app in final_apps:
    # 앱 레벨 세척
    new_app = {k: v for k, v in app.items() if k in ALLOWED_APP_KEYS}
    
    if "versions" in app:
        new_versions = []
        for v in app["versions"]:
            # 버전 레벨 세척 (notarized 관련 필드 자동 제거)
            new_v = {k: v_val for k, v_val in v.items() if k in ALLOWED_VER_KEYS}
            
            # buildVersion 필수 보완 (Code 4865 방지)
            if not new_v.get("buildVersion") or new_v["buildVersion"] == "":
                new_v["buildVersion"] = new_v.get("version", "1.0.0")
            
            # null 값 방지 및 데이터 정제
            for key in ["localizedDescription", "minOSVersion"]:
                if new_v.get(key) is None:
                    new_v[key] = ""
            
            new_versions.append(new_v)
        
        # 앱 내 버전 정렬 (최신순)
        new_app["versions"] = sorted(new_versions, key=lambda x: x.get("date", ""), reverse=True)
    
    # 필수 문자열 필드 null 방지
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
        
    cleaned_apps.append(new_app)

clean_base["apps"] = cleaned_apps

# --- 6. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    # 문법 오류를 방지하기 위해 정형화된 JSON으로 저장합니다.
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"🎉 tintColor를 포함한 SideStore 호환성 패치 완료!")
