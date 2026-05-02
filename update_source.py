import os
import json
import requests

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

# --- JSON 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
            if "apps" not in base_data:
                base_data["apps"] = []
        except:
            base_data = {"name": "NightFox", "apps": []}
else:
    print("❌ NightFox.json 파일을 찾을 수 없습니다!")
    exit(1)

# --- 스포티파이 외부 소스 미러링 ---
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

# --- 최종 앱 목록 조합 (순서 유지) ---
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

# --- [핵심 수정] 데이터 정제 및 버전 정렬 ---
for app in final_apps:
    # 1. 앱 루트 레벨의 null 필드 처리
    if app.get("localizedDescription") is None:
        app["localizedDescription"] = ""

    if "versions" in app:
        # 2. 버전 정보 내 null 필드를 ""으로 치환
        for v in app["versions"]:
            for key in ["buildVersion", "localizedDescription", "minOSVersion"]:
                if v.get(key) is None:
                    v[key] = ""
        
        # 3. [이전 요청 반영] 버전을 날짜(date) 기준 최신순으로 정렬
        # 날짜 정보가 없는 경우를 대비해 안전하게 처리합니다.
        app["versions"].sort(key=lambda x: x.get("date", ""), reverse=True)

# --- 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"🎉 완료! null 값 정제 및 버전 정렬이 적용되었습니다.")
