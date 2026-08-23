import os
import sys
import json
import requests
import re
from datetime import datetime, timezone, timedelta

# --- 설정 ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(SCRIPT_DIR, "NightFox.json")

SPOTIFY_SOURCE_URL = "https://raw.githubusercontent.com/titouan336/Spotify-AltStoreRepo-mirror/refs/heads/main/source.json"
SPOTIFY_BUNDLE_IDS = {"com.spotify.client", "com.spotify.client.patched"}

# 트윅 빌드 저장소. 외부 소유이므로 환경변수로만 교체한다.
YTPLUS_REPO = os.getenv("YTPLUS_REPO", "kes158/YT_")
YTPLUS_RELEASES_API = f"https://api.github.com/repos/{YTPLUS_REPO}/releases"
YOUTUBE_BUNDLE_ID = "com.google.ios.youtube"

YTMUSIC_REPO = os.getenv("YTMUSIC_REPO", "kes158/YTMusicUltimate")
YTMUSIC_RELEASES_API = f"https://api.github.com/repos/{YTMUSIC_REPO}/releases"
YTMUSIC_BUNDLE_ID = "com.google.ios.youtubemusic"

# 실행 중인 저장소 (Actions가 GITHUB_REPOSITORY로 넘겨준다)
NIGHTFOX_REPO = os.getenv("GITHUB_REPOSITORY") or "kes158/NightFox_Repository"

# IPA 에셋이 올라오는 저장소 목록. 카탈로그의 downloadURL이 다른 저장소를
# 가리키는 경우 실행 중인 저장소만 훑으면 새 빌드를 찾지 못하므로,
# 쉼표로 구분해 ASSET_REPOS 환경변수로 추가 저장소를 지정할 수 있다.
ASSET_REPOS = [r.strip() for r in os.getenv("ASSET_REPOS", NIGHTFOX_REPO).split(",") if r.strip()]
ASSET_REPOS = list(dict.fromkeys(ASSET_REPOS))  # 순서 유지 중복 제거

DEFAULT_MIN_OS_VERSION = os.getenv("DEFAULT_MIN_OS_VERSION", "16.1")

# date 표기를 통일할 기준 타임존. 표기만 맞추고 가리키는 시각은 바꾸지 않는다.
SOURCE_TZ = timezone(timedelta(hours=float(os.getenv("SOURCE_TZ_OFFSET", "9"))))

# 수집이 하나라도 실패하면 부분 결과를 저장하지 않는다.
#    STRICT_FETCH=false로 두면 경고만 하고 저장한다.
STRICT_FETCH = os.getenv("STRICT_FETCH", "true").strip().lower() not in ("false", "0", "no")

# --- Spotify 미러 동기화 여부 ---
# 자동 트리거에서는 워크플로가 'true'를 넘기고, workflow_dispatch에서는
# 체크박스 값이 그대로 전달된다.
# 이 플래그는 외부 미러만 제어한다. 에셋 저장소의 IPA는 항상 반영된다.
_mirror_env = os.getenv("USE_SPOTIFY_MIRROR", "true").strip().lower()
USE_SPOTIFY_MIRROR = _mirror_env not in ("false", "0", "no")

if USE_SPOTIFY_MIRROR:
    print("✅ Spotify 미러 동기화: ON")
else:
    print("⏭️  Spotify 미러 동기화: OFF (현재 소스 JSON 그대로 유지)")


def get_release_date(release):
    """published_at을 우선 사용, 없으면 created_at 폴백"""
    return release.get("published_at") or release.get("created_at")


def normalize_date(value):
    """date 표기를 SOURCE_TZ 기준 ISO 8601 하나로 맞춘다.

       소스에는 '...Z', '...+09:00', 'YYYY-MM-DD'가 섞여 들어온다.
       가리키는 시각은 그대로 두고 표기만 바꾸며,
       타임존이 없는 값은 SOURCE_TZ의 현지 시각으로 간주한다."""
    if not isinstance(value, str) or not value.strip():
        return value
    raw = value.strip()
    # Python 3.10의 fromisoformat은 'Z'를 못 읽으므로 먼저 치환한다
    text = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        print(f"  ⚠️  날짜 형식을 해석하지 못해 원본 유지: {raw}")
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SOURCE_TZ)
    return dt.astimezone(SOURCE_TZ).replace(microsecond=0).isoformat()


# --- 1. JSON 로드 ---
if os.path.exists(JSON_FILE):
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        try:
            base_data = json.load(f)
        except json.JSONDecodeError as e:
            # 파싱 실패를 삼키고 빈 소스로 저장하면 앱 목록이 통째로 사라진 결과가
            # 그대로 커밋된다. 복구가 어려우므로 여기서 중단한다.
            print(f"❌ {JSON_FILE} 파싱 실패: {e}")
            print("   빈 소스로 덮어쓰면 앱 목록이 전부 사라지므로 실행을 중단한다.")
            sys.exit(1)
else:
    print(f"ℹ️  {JSON_FILE} 없음 → 새 소스로 시작")
    base_data = {"name": "NightFox", "apps": []}


# --- 2. 최상위 필드 보존 ---
current_identifier = base_data.get("identifier") or "com.nightfox.repository"

def clean_news_item(item):
    if not isinstance(item, dict):
        return item
    new_item = dict(item)
    new_item.pop("url", None)
    if new_item.get("date"):
        new_item["date"] = normalize_date(new_item["date"])
    if new_item.get("imageURL") == "":
        new_item.pop("imageURL", None)
    return new_item

_news_value = base_data.get("news")
if isinstance(_news_value, list):
    preserved_news = [clean_news_item(n) for n in _news_value]
else:
    preserved_news = []

_header_value = base_data.get("headerURL")
preserved_header = _header_value if isinstance(_header_value, str) else ""

# 알 수 없는 최상위 키(patreonURL, featuredApps 등)를 보존한다.
# 새 dict를 만들면 손으로 넣은 필드가 실행할 때마다 사라진다.
clean_base = dict(base_data)
clean_base.update({
    "name": base_data.get("name", "NightFox"),
    "identifier": current_identifier,
    "subtitle": base_data.get("subtitle", "NightFox's App Repository"),
    "description": base_data.get("description", "Welcome to NightFox's source!"),
    "iconURL": base_data.get("iconURL", "https://i.imgur.com/Se6jHAj.png"),
    "website": base_data.get("website", f"https://github.com/{NIGHTFOX_REPO}"),
    "tintColor": base_data.get("tintColor", "#00b39e"),
    "headerURL": preserved_header,
    "apps": [],
    "news": preserved_news
})


# --- 3. 외부 데이터 수집 ---
# 수집 실패를 모아 두었다가 마지막에 한 번에 알린다.
# 실패를 그냥 넘기면 '변경 없음'으로 성공 종료해 문제가 드러나지 않는다.
fetch_errors = []

# 3-1. Spotify 미러 (USE_SPOTIFY_MIRROR가 True일 때만 fetch)
spotify_apps_from_mirror = []
if USE_SPOTIFY_MIRROR:
    try:
        response = requests.get(SPOTIFY_SOURCE_URL, timeout=15)
        if response.status_code == 200:
            external_data = response.json()
            spotify_apps_from_mirror = [
                app for app in external_data.get("apps", [])
                if app.get("bundleIdentifier") in SPOTIFY_BUNDLE_IDS
            ]
            print(f"  📦 [Spotify Mirror] {len(spotify_apps_from_mirror)}개 앱 로드됨")
        else:
            msg = f"Spotify 미러 HTTP {response.status_code}"
            print(f"❌ {msg}")
            fetch_errors.append(msg)
    except Exception as e:
        print(f"❌ 스포티파이 미러 로드 실패: {e}")
        fetch_errors.append(f"Spotify 미러 로드 실패: {e}")
else:
    print("  📦 [Spotify Mirror] 스킵 — 기존 소스 JSON 유지")

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
    else:
        msg = f"YouTube 릴리즈 API HTTP {response.status_code}"
        print(f"❌ {msg}")
        fetch_errors.append(msg)
except Exception as e:
    print(f"❌ YouTube 릴리즈 로드 실패: {e}")
    fetch_errors.append(f"YouTube 릴리즈 로드 실패: {e}")


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
        msg = f"YouTube Music 릴리즈 API HTTP {response.status_code}"
        print(f"❌ {msg}")
        fetch_errors.append(msg)
except Exception as e:
    print(f"❌ YouTube Music 릴리즈 로드 실패: {e}")
    fetch_errors.append(f"YouTube Music 릴리즈 로드 실패: {e}")


# === 3-4. 본인 릴리즈 에셋 ===
# 릴리즈 하나에 여러 앱의 IPA가 함께 올라오므로 특정 앱 이름만 걸러서는 안 된다.
# 에셋 이름 → (앱, 버전) 규칙표로 전부 훑고, 규칙에 없는 이름은 버리지 않고 출력한다.
OWN_ASSET_RULES = [
    # YouTube — 이름 규칙이 세 가지 쓰였다
    (re.compile(r'^YTKACE_[\d.]+_(?:YouTube_)?(\d+\.\d+\.\d+)_.*\.ipa$', re.I), YOUTUBE_BUNDLE_ID),
    (re.compile(r'^YTPlus_[\d.]+_(\d+\.\d+\.\d+)\.ipa$', re.I), YOUTUBE_BUNDLE_ID),
    (re.compile(r'^(\d+\.\d+\.\d+)_YouTubePlus_.*\.ipa$', re.I), YOUTUBE_BUNDLE_ID),
    # Spotify — EeveeSpotify_v9.1.46 / EeveeSpotify_9.1.40 / EeveeSpotify-6.6.7-9.1.68
    #           (patched 여부는 아래에서 이름을 보고 갈라낸다)
    (re.compile(r'^EeveeSpotify[_-](?:v)?(?:\d+\.\d+\.\d+-)?(\d+\.\d+\.\d+)(?:_patched)?\.ipa$', re.I), "com.spotify.client"),
    # Instagram 계열
    (re.compile(r'^RyukGram_(\d+\.\d+(?:\.\d+)?)\.ipa$', re.I), "com.burbn.instagram"),
    (re.compile(r'^Instagram[_-]Theta[_-](?:v[\d.]+[_-])?v?(\d+\.\d+(?:\.\d+)?)\.ipa$', re.I), "com.burbn.instagram"),
    (re.compile(r'^Theta[\d.]+Hotfix_(\d+\.\d+(?:\.\d+)?)\.ipa$', re.I), "com.burbn.instagram"),
    # 기타
    (re.compile(r'^NeoFreeBird-sideloaded-X_[\d.]+_(\d+\.\d+(?:\.\d+)?)\.ipa$', re.I), "com.atebits.Tweetie2"),
    (re.compile(r'^Threads_(\d+\.\d+\.\d+)_.*\.ipa$', re.I), "com.burbn.barcelona"),
    (re.compile(r'^Tiktok_(\d+\.\d+\.\d+)\.ipa$', re.I), "com.zhiliaoapp.musically"),
    (re.compile(r'^Reddit[_-]v?(\d+[._]\d+[._]\d+)\.ipa$', re.I), "com.reddit.Reddit"),
    (re.compile(r'^StikDebug-(\d+\.\d+\.\d+)\.ipa$', re.I), "com.stik.stikdebug"),
    (re.compile(r'^Infuse_Plus_(\d+\.\d+\.\d+)\.ipa$', re.I), "com.firecore.infuse"),
    (re.compile(r'^nPlayer\.Plus\.(\d+\.\d+\.\d+)\.ipa$', re.I), "com.newin.nplayer"),
    (re.compile(r'^iTorrent_(\d+\.\d+\.\d+)\.ipa$', re.I), "com.xitrix.iTorrent2"),
    (re.compile(r'^EnsWilde_v(\d+\.\d+\.\d+)\.ipa$', re.I), "com.yangjiii.EnsWilde"),
]

OWN_ASSET_SCAN = os.getenv("OWN_ASSET_SCAN", "true").strip().lower() not in ("false", "0", "no")

own_releases_by_bid = {}
unmatched_assets = []


def classify_own_asset(name):
    """에셋 이름에서 (bundleIdentifier, 버전)을 뽑는다. 못 뽑으면 None."""
    for pattern, bid in OWN_ASSET_RULES:
        m = pattern.match(name)
        if not m:
            continue
        ver = m.group(1).replace("_", ".")
        if bid == "com.spotify.client" and "patched" in name.lower():
            bid = "com.spotify.client.patched"
        return bid, ver
    return None


if OWN_ASSET_SCAN:
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if os.getenv("GITHUB_TOKEN"):
            headers["Authorization"] = f"token {os.getenv('GITHUB_TOKEN')}"

        for repo in ASSET_REPOS:
            response = requests.get(f"https://api.github.com/repos/{repo}/releases",
                                    headers=headers, timeout=15)
            if response.status_code != 200:
                msg = f"에셋 저장소({repo}) HTTP {response.status_code}"
                print(f"❌ {msg}")
                fetch_errors.append(msg)
                continue
            found = 0
            for release in response.json():
                body = (release.get("body") or "").strip().replace('\r\n', '\n').replace('\r', '\n')
                for asset in release.get("assets", []):
                    name = asset.get("name", "")
                    if not name.lower().endswith(".ipa"):
                        continue
                    hit = classify_own_asset(name)
                    if not hit:
                        unmatched_assets.append(f"{repo}: {name}")
                        continue
                    bid, ver = hit
                    # 에셋은 예전 릴리즈에 덧붙여 올리는 경우가 있어 릴리즈 날짜와 어긋난다.
                    # 업로드 시각(asset.created_at)이 실제 빌드 시점에 가깝다.
                    asset_date = asset.get("created_at") or get_release_date(release)
                    own_releases_by_bid.setdefault(bid, []).append({
                        "version": ver,
                        "buildVersion": ver,
                        "date": asset_date,
                        "downloadURL": asset.get("browser_download_url"),
                        "size": asset.get("size"),
                        "localizedDescription": body or os.path.splitext(name)[0]
                    })
                    found += 1
            print(f"  📦 [에셋] {repo}: {found}개 인식")
        if unmatched_assets:
            print(f"  ❔ 규칙에 없는 에셋 {len(unmatched_assets)}개:")
            for n in unmatched_assets:
                print(f"     - {n}")
    except Exception as e:
        print(f"❌ NightFox 본인 릴리즈 로드 실패: {e}")
        fetch_errors.append(f"본인 릴리즈 로드 실패: {e}")
else:
    print("  📦 [NightFox Release] 스캔 OFF")


# --- 4. 정제 함수 ---
# 모르는 키는 그대로 둔다. 알려진 키만 남기면 screenshotURLs / appPermissions /
# sha256 같은 스펙 필드와 손으로 넣은 값이 실행할 때마다 사라진다.

def version_sort_key(v):
    """버전 문자열에서 숫자만 뽑아 비교한다. 'x.y.z-beta1' 같은 값도 허용한다."""
    parts = re.findall(r'\d+', str(v.get("version") or ""))
    return [int(p) for p in parts] or [0]

def clean_version(v):
    new_v = dict(v)
    if not new_v.get("buildVersion"):
        new_v["buildVersion"] = new_v.get("version", "1.0.0")
    if not new_v.get("minOSVersion"):
        new_v["minOSVersion"] = DEFAULT_MIN_OS_VERSION
    if new_v.get("localizedDescription") is None:
        new_v["localizedDescription"] = ""
    if new_v.get("date"):
        new_v["date"] = normalize_date(new_v["date"])
    return new_v

def clean_app(app, cleaned_versions):
    new_app = dict(app)
    new_app["versions"] = sorted(cleaned_versions, key=version_sort_key, reverse=True)
    if new_app.get("localizedDescription") is None:
        new_app["localizedDescription"] = ""
    # 값을 임의로 고치지 않고 어긋난 사실만 알린다.
    dates = [v.get("date") or "" for v in new_app["versions"]]
    if dates != sorted(dates, reverse=True):
        print(f"  ⚠️  [{new_app.get('name')}] 버전 순서와 날짜 순서가 어긋남: {dates}")
    return new_app

def dedupe_keep_newest(releases, label):
    """같은 앱 버전을 담은 릴리즈가 여러 개면 가장 최신 릴리즈만 남긴다.

       응답 순서에 맡기면 마지막 항목이 이겨서, 한 번의 실행 안에서
       새 빌드로 덮어썼다가 다시 예전 빌드로 되돌아간다."""
    best = {}
    for rel in releases:
        v = rel.get("version")
        if not v:
            continue
        cur = best.get(v)
        if cur is None:
            best[v] = rel
        elif (rel.get("date") or "") > (cur.get("date") or ""):
            print(f"  ♻️  [{label}] {v}: 더 최신 릴리즈로 교체 ({cur.get('date')} → {rel.get('date')})")
            best[v] = rel
        else:
            print(f"  ♻️  [{label}] {v}: 더 오래된 릴리즈 무시 ({rel.get('date')})")
    return list(best.values())


def merge_own_assets(my_versions, releases, label):
    """에셋 저장소의 IPA를 카탈로그에 병합한다.

       에셋 저장소에는 카탈로그에서 이미 정리한 구버전 IPA가 남아 있어,
       전부 병합하면 지운 버전이 되살아난다. 규칙:
         - 카탈로그의 최신 버전보다 높은 버전만 추가한다
         - 최신 버전과 같은 버전은 더 나중에 올라온 에셋일 때만 교체한다 (재빌드 대응)
         - 그보다 낮은 버전은 건드리지 않는다"""
    if not releases:
        return
    releases = dedupe_keep_newest(releases, label)
    cur_max = max((version_sort_key(v) for v in my_versions.values()), default=[0])
    skipped = 0
    for rel in sorted(releases, key=version_sort_key):
        key = version_sort_key(rel)
        v_str = rel.get("version")
        if not v_str:
            continue
        if key > cur_max:
            my_versions[v_str] = clean_version(rel)
            cur_max = key
            print(f"  ➕ [{label}] 새 버전 추가: {v_str} ({rel.get('downloadURL', '').split('/')[-1]})")
        elif key == cur_max and v_str in my_versions:
            cur = my_versions[v_str]
            cur_url = cur.get("downloadURL") or ""
            # 원 개발자 릴리즈 등 에셋 저장소 밖을 가리키는 URL은 의도적으로 지정한
            # 것이므로 사본으로 덮어쓰지 않는다. 같은 버전 교체는 이미 에셋 저장소를
            # 쓰던 항목의 재빌드 갱신에만 적용한다.
            from_asset_repo = any(f"/{repo}/releases/download/" in cur_url for repo in ASSET_REPOS)
            newer = normalize_date(rel.get("date") or "") > normalize_date(cur.get("date") or "")
            if not from_asset_repo:
                print(f"  🔒 [{label}] {v_str}: 외부 저장소를 가리키도록 지정된 항목이라 유지 "
                      f"({cur_url.split('/')[-1]})")
            elif newer and rel.get("downloadURL") != cur_url:
                my_versions[v_str] = clean_version(rel)
                print(f"  🔄 [{label}] 같은 버전의 더 새 빌드로 교체: {v_str} "
                      f"({rel.get('downloadURL', '').split('/')[-1]})")
        else:
            skipped += 1
    if skipped:
        print(f"  ⏭️  [{label}] 카탈로그 최신보다 낮은 에셋 {skipped}개 건너뜀 (기존 목록 유지)")


def merge_releases(my_versions, releases, label, overwrite_on_url_change=True):
    """없으면 추가하고, URL이 바뀌었으면 갱신한다.

       외부 미러는 직접 지정한 downloadURL을 덮어쓰면 안 되므로 추가만 한다."""
    for rel in dedupe_keep_newest(releases, label):
        v_str = rel.get("version")
        if not v_str:
            continue
        if v_str not in my_versions:
            my_versions[v_str] = clean_version(rel)
            print(f"  ➕ [{label}] 새 버전 추가: {v_str}")
            continue
        if not overwrite_on_url_change:
            continue
        existing_url = my_versions[v_str].get("downloadURL", "")
        new_url = rel.get("downloadURL", "")
        if new_url and existing_url != new_url:
            my_versions[v_str] = clean_version(rel)
            print(f"  🔄 [{label}] URL 변경으로 덮어쓰기: {v_str} ({existing_url} → {new_url})")


# --- 5. 앱 병합 ---
original_apps = base_data.get("apps", [])
final_apps = []
processed_bids = set()

for app in original_apps:
    bid = app.get("bundleIdentifier")
    if bid in processed_bids: continue

    my_versions = {v.get("version"): clean_version(v) for v in app.get("versions", [])}

    if bid == YOUTUBE_BUNDLE_ID and yt_releases_from_github:
        merge_releases(my_versions, yt_releases_from_github, "YouTube")

    elif bid == YTMUSIC_BUNDLE_ID and ytmusic_releases_from_github:
        # 에셋 이름이 YTMusicUltimate.ipa로 고정이라 버전만 봐서는 재빌드를 알 수 없다.
        # URL 변경도 함께 본다.
        merge_releases(my_versions, ytmusic_releases_from_github, "YouTube Music")

    elif bid in SPOTIFY_BUNDLE_IDS:
        if USE_SPOTIFY_MIRROR:
            mirror_app = next((s for s in spotify_apps_from_mirror if s.get("bundleIdentifier") == bid), None)
            if mirror_app:
                merge_releases(my_versions, mirror_app.get("versions", []), "Spotify Mirror",
                               overwrite_on_url_change=False)

    # 에셋 저장소의 IPA는 앱 종류와 미러 플래그에 관계없이 항상 반영한다.
    # 미러 플래그에 묶으면 자동 트리거에서 통째로 건너뛰게 된다.
    merge_own_assets(my_versions, own_releases_by_bid.get(bid, []), "NightFox Release")

    final_apps.append(clean_app(app, list(my_versions.values())))
    processed_bids.add(bid)

# --- 6. 저장 ---
clean_base["apps"] = final_apps

if not clean_base.get("headerURL"):
    clean_base.pop("headerURL", None)

# 수집이 실패한 채로 저장하면 누락된 소스가 그대로 커밋되어 배포된다.
# 저장하지 않으면 워크플로의 커밋 단계도 돌지 않는다.
if fetch_errors:
    print("\n" + "=" * 60)
    print(f"❌ 수집 실패 {len(fetch_errors)}건:")
    for _msg in fetch_errors:
        print(f"   - {_msg}")
    if STRICT_FETCH:
        print("불완전한 결과를 저장하지 않고 중단한다 (무시하려면 STRICT_FETCH=false)")
        print("=" * 60)
        sys.exit(1)
    print("STRICT_FETCH=false → 경고만 남기고 저장을 계속한다")
    print("=" * 60)

with open(JSON_FILE, 'w', encoding='utf-8') as f:
    json.dump(clean_base, f, ensure_ascii=False, indent=2)

print(f"\n🎉 통합 업데이트 완료! (총 앱 수: {len(final_apps)})")
print(f"📰 news 항목 수: {len(clean_base['news'])}")
