import os
import json
import requests

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

# 스포티파이 외부 소스 URL
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"

# 스포티파이 bundleIdentifier 목록 (이것만 외부 소스에서 관리)
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

print(f"✅ JSON 로드 완료: 앱 {len(base_data['apps'])}개")

# 스포티파이가 아닌 기존 앱들은 절대 건드리지 않음
non_spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") not in SPOTIFY_BUNDLE_IDS]
print(f"🔒 보호된 기존 앱 {len(non_spotify_apps)}개 (스포티파이 제외)")

# --- 스포티파이 외부 소스 미러링 ---
spotify_apps = []
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        for app in external_data.get("apps", []):
            if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS:
                spotify_apps.append(app)
                print(f"  🎵 스포티파이 앱 미러링: {app.get('name')} ({app.get('bundleIdentifier')})")
    else:
        print(f"❌ 외부 소스 응답 오류: {response.status_code}")
        # 실패 시 기존 스포티파이 앱 유지
        spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]
        print(f"  ⚠️ 기존 스포티파이 데이터 유지: {len(spotify_apps)}개")
except Exception as e:
    print(f"❌ 외부 소스 로드 실패: {e}")
    # 실패 시 기존 스포티파이 앱 유지
    spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]
    print(f"  ⚠️ 기존 스포티파이 데이터 유지: {len(spotify_apps)}개")

# --- 최종 앱 목록 조합: 기존 앱 순서 유지 + 스포티파이 ---
# 기존 앱 순서 그대로 유지하되 스포티파이 자리에 새 데이터 삽입
final_apps = []
spotify_inserted = set()

for app in base_data["apps"]:
    bid = app.get("bundleIdentifier")
    if bid in SPOTIFY_BUNDLE_IDS:
        # 스포티파이 자리에 새로 미러링된 데이터 삽입
        new_spotify = next((s for s in spotify_apps if s.get("bundleIdentifier") == bid), None)
        if new_spotify and bid not in spotify_inserted:
            final_apps.append(new_spotify)
            spotify_inserted.add(bid)
            print(f"  🔄 스포티파이 업데이트: {new_spotify.get('name')}")
        elif bid not in spotify_inserted:
            # 미러링 실패 시 기존 유지
            final_apps.append(app)
            spotify_inserted.add(bid)
    else:
        # 스포티파이 아닌 앱은 그대로 유지
        final_apps.append(app)

# 기존에 없던 새 스포티파이 앱 추가 (예: patched 버전이 새로 생긴 경우)
for s_app in spotify_apps:
    if s_app.get("bundleIdentifier") not in spotify_inserted:
        final_apps.append(s_app)
        print(f"  ➕ 새 스포티파이 앱 추가: {s_app.get('name')}")

base_data["apps"] = final_apps

# --- 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"\n🎉 완료! 총 앱 {len(final_apps)}개 (기존 앱 보존 + 스포티파이 미러링)")
