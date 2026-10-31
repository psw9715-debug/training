#!/usr/bin/env python3
"""인바디 앱 계정에서 체성분 측정값을 받아 config/inbody.json 에 쌓는다.

헬스장에서 인바디를 재면 그 결과가 등록된 전화번호의 인바디 앱 계정으로
올라간다. 이 스크립트는 그 앱이 쓰는 REST API 를 그대로 호출해서 측정값을
가져온다. GitHub Actions 에서 하루 한 번 돌리면 손으로 옮겨 적을 일이 없다.

  INBODY_LOGIN_ID       가입한 전화번호 (숫자만, 국가번호 없이)
  INBODY_LOGIN_PW       인바디 앱 비밀번호
  INBODY_COUNTRY_CODE   ISO 국가코드 (기본 KR)

공식 공개 API 가 아니라 앱이 쓰는 비공개 엔드포인트다. 인바디가 바꾸면
멈출 수 있고, 그때는 로그에 실패가 남는다. 표준 라이브러리만 쓴다.
"""

import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

COMMON_URL = "https://appapicommon.lookinbody.com"
FULL_SYNC = "1990-01-01 11:11:11"
APP_ENVELOPE = {
    "Language": "en",
    "LogCode": "",
    "AppType": "Android",
    "OSVersion": "14",
    "PhoneModel": "Google Pixel 6 Pro",
    "RegAppType": "InBody",
    "AppVersion": "2.8.31_914",
}
UA_OKHTTP = "okhttp/4.12.0"
UA_DALVIK = ("Dalvik/2.1.0 (Linux; U; Android 14; Pixel 6 Pro "
             "Build/AP2A.240905.003.F1)")

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "inbody.json"
KST = timezone(timedelta(hours=9))
MAX_SCANS = 400


class InBodyError(Exception):
    pass


def post(url, payload, token=None, ua=UA_OKHTTP):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": ua,
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise InBodyError(f"{url} -> HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise InBodyError(f"{url} -> {e.reason}") from None


def envelope(country_number, **extra):
    return {**APP_ENVELOPE, "CountryCode": country_number, **extra}


def resolve_host(country_iso):
    """국가별 API 서버 주소를 찾는다 (KR -> 한국 서버)."""
    data = post(f"{COMMON_URL}/CommonAPI/GetCountryInfoV2",
                envelope("", SyncDatetime=FULL_SYNC))
    if not data.get("IsSuccess"):
        raise InBodyError(f"국가 목록 실패: {data.get('ErrorMsg')}")
    rows = data.get("Data") or []
    for r in rows:
        if r.get("Type") == "API" and str(r.get("Code2", "")).upper() == country_iso.upper():
            return r["Domain"].rstrip("/"), str(r.get("Number"))
    codes = sorted({str(r.get("Code2")) for r in rows if r.get("Type") == "API"})
    raise InBodyError(f"{country_iso} 서버를 못 찾음. 쓸 수 있는 코드: {codes}")


ERROR_HINTS = {
    "PW_FAIL": "비밀번호가 맞지 않습니다. 인바디 앱에서 쓰는 비밀번호인지 확인해주세요. "
               "(카카오·애플 계정으로만 가입했다면 비밀번호 로그인이 안 됩니다 — 앱에서 비밀번호를 먼저 만들어주세요)",
    "EMPTYDATA": "그 아이디로 계정을 찾지 못했습니다. 전화번호를 숫자만, 가입할 때 쓴 번호로 넣어주세요.",
    "ID_FAIL": "그 아이디로 계정을 찾지 못했습니다.",
    "LOCK": "로그인 시도가 많아 잠긴 것 같습니다. 인바디 앱에서 직접 로그인해 풀어주세요.",
}


def hint_for(msg):
    up = (msg or "").upper()
    for key, text in ERROR_HINTS.items():
        if key in up:
            return text
    return ""


def login(base, country_number, login_id, password):
    payload = envelope(
        country_number,
        AuthProvider="", AuthProviderID="", AuthToken="", CustomKey="",
        DeviceType="Pixel 6 Pro 14",
        LoginID=login_id, LoginPW=password, Type="Login",
        SyncDatetime=FULL_SYNC,
        SyncDatetimeBasalMedical=FULL_SYNC, SyncDatetimeCardiac=FULL_SYNC,
        SyncDatetimeExercise=FULL_SYNC, SyncDatetimeInBody=FULL_SYNC,
        SyncDatetimeNutrition=FULL_SYNC, SyncDatetimeSleep=FULL_SYNC,
        SyncType="Main;InBody;Exercise;Nutrition;Sleep;EasyTrainning;BasalMedical;",
    )
    data = post(f"{base}/V2/Main/GetLoginWithSyncDataPartV2", payload)
    if not data.get("IsSuccess") or not data.get("Token"):
        msg = data.get("ErrorMsg") or "응답에 토큰 없음"
        hint = hint_for(msg)
        # 여기서 다른 조합으로 다시 시도하지 않는다 — 실패가 쌓이면 계정이 잠길 수 있다
        raise InBodyError(f"로그인 실패: {msg}" + (f"\n  → {hint}" if hint else ""))
    uid = (data.get("Data") or {}).get("UID")
    if not uid:
        raise InBodyError("로그인은 됐는데 UID 가 없음")
    return data["Token"], uid


def get_scans(base, country_number, token, uid, number=60):
    payload = envelope(
        country_number, uid=uid, syncDatetime=FULL_SYNC,
        NumberPerData=str(number), CurrentIndex="0",
        Language="en-US", UseInBodyHomeDevice="false",
    )
    data = post(f"{base}/V2/InBody/GetInBodyData", payload, token=token, ua=UA_DALVIK)
    if not data.get("IsSuccess"):
        raise InBodyError(f"측정 기록 실패: {data.get('ErrorMsg')}")
    return data.get("Data") or []


def flatten(rec):
    """BCA/MFA/IMP 로 나뉜 블록을 한 겹으로 펴고 키를 소문자로 맞춘다."""
    flat = {}
    def walk(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                else:
                    flat.setdefault(str(k).lower(), v)
        elif isinstance(d, list):
            for v in d:
                walk(v)
    walk(rec)
    return flat


def num(flat, *names):
    for n in names:
        v = flat.get(n.lower())
        if v in (None, "", "-"):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        return round(f, 2)
    return None


def pick_datetime(flat):
    for k in ("testdatetime", "datetimes", "testdate", "regdatetime", "datetime"):
        v = flat.get(k)
        if isinstance(v, str) and len(v) >= 10:
            s = v.replace("T", " ")
            return s[:10].replace("/", "-"), s[11:16]
    return None, None


def normalize(rec):
    flat = flatten(rec)
    date, time = pick_datetime(flat)
    if not date:
        return None
    return {
        "date": date,
        "time": time or "",
        "weight": num(flat, "WT", "Weight"),
        "smm": num(flat, "SMM", "SkeletalMuscleMass"),
        "bfm": num(flat, "BFM", "BodyFatMass"),
        "pbf": num(flat, "PBF", "PercentBodyFat"),
        "bmi": num(flat, "BMI"),
        "tbw": num(flat, "TBW", "TotalBodyWater"),
        "protein": num(flat, "PROTEIN", "Protein"),
        "mineral": num(flat, "MINERAL", "Mineral", "OSMINERAL"),
        "vfl": num(flat, "VFL", "VisceralFatLevel"),
        "bmr": num(flat, "BMR", "BasalMetabolicRate"),
        "whr": num(flat, "WHR"),
        "score": num(flat, "INBODYSCORE", "Score", "IBS"),
    }


def diagnose():
    """계정을 건드리지 않고 오류 코드의 뜻만 알아본다.

    등록돼 있지 않을 번호로 로그인을 한 번 해 본다. 그때 나오는 코드가
    PW_FAIL_4 와 다르면, 우리 번호는 서버가 알아본다는 뜻이라 문제는
    비밀번호 쪽이다. 같은 코드가 나오면 PW_FAIL_4 는 '아이디든 비번이든
    틀림' 을 뭉뚱그린 코드라 번호 형식을 의심해야 한다.
    """
    country = (os.getenv("INBODY_COUNTRY_CODE") or "KR").strip() or "KR"
    base, number = resolve_host(country)
    print(f"서버: {base} (국가번호 {number})")
    for label, login_id in (("없는 번호", "99999999999"), ("형식이 이상한 번호", "1")):
        payload = envelope(
            number,
            AuthProvider="", AuthProviderID="", AuthToken="", CustomKey="",
            DeviceType="Pixel 6 Pro 14",
            LoginID=login_id, LoginPW="zzzz-not-a-real-password-zzzz", Type="Login",
            SyncDatetime=FULL_SYNC,
            SyncDatetimeBasalMedical=FULL_SYNC, SyncDatetimeCardiac=FULL_SYNC,
            SyncDatetimeExercise=FULL_SYNC, SyncDatetimeInBody=FULL_SYNC,
            SyncDatetimeNutrition=FULL_SYNC, SyncDatetimeSleep=FULL_SYNC,
            SyncType="Main;InBody;Exercise;Nutrition;Sleep;EasyTrainning;BasalMedical;",
        )
        try:
            data = post(f"{base}/V2/Main/GetLoginWithSyncDataPartV2", payload)
            print(f"  {label}: IsSuccess={data.get('IsSuccess')} ErrorMsg={data.get('ErrorMsg')!r}")
        except InBodyError as e:
            print(f"  {label}: {e}")
    print("PW_FAIL_4 와 다른 코드가 나왔다면, 시우님 번호는 서버가 알아보는 것이고"
          " 막힌 곳은 비밀번호입니다.")
    return 0


def main():
    if os.getenv("INBODY_MODE") == "diag":
        return diagnose()

    login_id = "".join(ch for ch in (os.getenv("INBODY_LOGIN_ID") or "") if ch.isdigit())
    password = (os.getenv("INBODY_LOGIN_PW") or "").strip()
    country = (os.getenv("INBODY_COUNTRY_CODE") or "KR").strip() or "KR"
    if not login_id or not password:
        print("INBODY_LOGIN_ID / INBODY_LOGIN_PW 가 비어 있습니다 "
              "(저장소 Settings > Secrets > Actions 에 넣어주세요)", file=sys.stderr)
        return 2

    base, country_number = resolve_host(country)
    print(f"서버: {base} (국가번호 {country_number})")

    token, uid = login(base, country_number, login_id, password)
    print(f"로그인 성공 (uid={uid})")

    raw = get_scans(base, country_number, token, uid)
    print(f"받은 측정 기록: {len(raw)}건")
    if raw:
        # 첫 실행에서 필드 이름을 확인하려고 키 목록만 남긴다 (값은 안 찍는다)
        print("최근 기록 필드:", ",".join(sorted(flatten(raw[0]).keys()))[:1500])

    fresh = [n for n in (normalize(r) for r in raw) if n]
    if not fresh:
        print("쓸 수 있는 기록이 없습니다", file=sys.stderr)
        return 1

    old = {"scans": []}
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")) or {"scans": []}
        except json.JSONDecodeError:
            pass

    merged = {}
    for s in (old.get("scans") or []) + fresh:
        if s.get("date"):
            merged[s["date"] + "T" + (s.get("time") or "")] = s
    scans = sorted(merged.values(), key=lambda s: (s["date"], s.get("time") or ""), reverse=True)[:MAX_SCANS]

    out = {
        "updatedAt": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "source": "inbody-app",
        "scans": scans,
    }
    before = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    text = json.dumps(out, ensure_ascii=False, indent=2) + "\n"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")

    latest = scans[0]
    print(f"최신: {latest['date']} {latest.get('time','')} "
          f"체중 {latest.get('weight')} / 골격근 {latest.get('smm')} / 체지방 {latest.get('bfm')}")
    print(f"총 {len(scans)}건 저장")
    # 내용이 그대로면 커밋 단계에서 걸러진다
    print("변경 없음" if before.strip() and json.loads(before or "{}").get("scans") == scans else "변경 있음")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except InBodyError as e:
        print(f"인바디 동기화 실패: {e}", file=sys.stderr)
        sys.exit(1)
