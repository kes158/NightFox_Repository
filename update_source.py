import os
import json
import requests

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

# 스포티파이 외부 소스 URL
SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"

# 스포티파이 bundleIdentifier 목록
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

# --- 1. JSON 로드 ---
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

print(f"✅ JSON 로드 완료: 현재 앱 {len(base_data['apps'])}개")

# --- 2. 스포티파이 외부 소스 미러링 ---
spotify_apps = []
try:
    response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
    if response.status_code == 200:
        external_data = response.json()
        for app in external_data.get("apps", []):
            if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS:
                spotify_apps.append(app)
                print(f"  🎵 외부 스포티파이 데이터 확보: {app.get('name')}")
    else:
        print(f"❌ 외부 소스 응답 오류: {response.status_code}")
        spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]
except Exception as e:
    print(f"❌ 외부 소스 로드 실패: {e}")
    spotify_apps = [app for app in base_data["apps"] if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS]

# --- 3. 최종 앱 목록 조합 (기존 앱 순서 유지) ---
final_apps = []
spotify_inserted = set()

for app in base_data["apps"]:
    bid = app.get("bundleIdentifier")
    if bid in SPOTIFY_BUNDLE_IDS:
        new_spotify = next((s for s in spotify_apps if s.get("bundleIdentifier") == bid), None)
        if new_spotify and bid not in spotify_inserted:
            final_apps.append(new_spotify)
            spotify_inserted.add(bid)
            print(f"  🔄 스포티파이 업데이트 적용: {bid}")
        elif bid not in spotify_inserted:
            final_apps.append(app)
            spotify_inserted.add(bid)
    else:
        final_apps.append(app)

# 새롭게 추가된 스포티파이 앱이 있다면 하단에 추가
for s_app in spotify_apps:
    if s_app.get("bundleIdentifier") not in spotify_inserted:
        final_apps.append(s_app)
        print(f"  ➕ 새 스포티파이 앱 추가: {s_app.get('name')}")

base_data["apps"] = final_apps

# --- 4. 데이터 정제 및 사이드스토어 호환성 작업 (핵심) ---
for app in base_data["apps"]:
    # 앱 루트 레벨 null 방지
    if app.get("localizedDescription") is None:
        app["localizedDescription"] = ""

    if "versions" in app:
        for v in app["versions"]:
            # A. 버전 숫자 가져오기
            current_ver = v.get("version", "1.0.0")

            # B. buildVersion이 null이거나 ""이면 SideStore에서 오류가 나므로 version 값으로 강제 채움[cite: 13]
            if not v.get("buildVersion") or v["buildVersion"] == "":
                v["buildVersion"] = current_ver
            
            # C. 기타 필수 문자열 필드 null 방지
            if v.get("localizedDescription") is None:
                v["localizedDescription"] = ""
            if v.get("minOSVersion") is None:
                v["minOSVersion"] = ""

        # D. 앱 순서는 유지하되, 각 앱 내의 버전들만 날짜순 정렬 (최신이 위로)
        app["versions"].sort(key=lambda x: x.get("date", ""), reverse=True)

# --- 5. 저장 ---
with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(base_data, f, ensure_ascii=False, indent=2)

print(f"\n🎉 모든 작업 완료!")
print(f"- SideStore 호환을 위해 빈 buildVersion을 version 값으로 보완했습니다.[cite: 13]")
print(f"- 모든 null 값을 빈 문자열(\"\")로 치환했습니다.")
