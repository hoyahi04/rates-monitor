"""한국 금리 자료: 한국은행 ECOS → data/raw/korea.json

ECOS는 인증키가 있어야 한다 (https://ecos.bok.or.kr/api/ 에서 무료 발급).
키는 환경변수 ECOS_API_KEY, 또는 `4. desk/.env` 파일의 `ECOS_API_KEY=...` 한 줄에서 읽는다.
`.env`는 .gitignore에 들어 있어 저장소에 올라가지 않는다. 키를 코드나 다른 파일에 적지 말 것.

키가 없으면 status = "no_key"만 적고 정상 종료한다 (화면은 한국 칸을 "키 필요"로 표시).

실행:  python3 fetch_korea.py           키로 전부 받기
       python3 fetch_korea.py --check   키 없이 형식만 확인 (ECOS의 시험용 키로 10줄만 받아 보고 저장하지 않음)
"""
import json, os, sys
from datetime import date

from common import DESK, RAW, UA, get, log, now_utc, num, read_json, write_json

START = "20140101"
OUT = RAW / "korea.json"
# (이름, 통계표, 주기, 항목코드, 화면 이름)
DAILY = [
    ("ktb1", "817Y002", "010190000", "국고채 1년"), ("ktb2", "817Y002", "010195000", "국고채 2년"),
    ("ktb3", "817Y002", "010200000", "국고채 3년"), ("ktb5", "817Y002", "010200001", "국고채 5년"),
    ("ktb10", "817Y002", "010210000", "국고채 10년"), ("ktb20", "817Y002", "010220000", "국고채 20년"),
    ("ktb30", "817Y002", "010230000", "국고채 30년"), ("ktb50", "817Y002", "010240000", "국고채 50년"),
    ("cd91", "817Y002", "010502000", "CD 91일"), ("call", "817Y002", "010101000", "콜금리 (1일)"),
    ("kofr", "817Y002", "010901000", "KOFR"), ("msb91", "817Y002", "010400000", "통안증권 91일"),
    ("msb1", "817Y002", "010400001", "통안증권 1년"), ("msb2", "817Y002", "010400002", "통안증권 2년"),
    ("corp_aa", "817Y002", "010300000", "회사채 3년 AA-"), ("corp_bbb", "817Y002", "010320000", "회사채 3년 BBB-"),
    ("base", "722Y001", "0101000", "한국은행 기준금리"), ("usdkrw", "731Y001", "0000001", "원/달러 매매기준율"),
]
MONTHLY = [("cpi", "901Y009", "0", "소비자물가지수 (2020=100)")]


def find_key():
    k = os.environ.get("ECOS_API_KEY", "").strip()
    if k:
        return k
    env = DESK / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("ECOS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def ecos(key, stat, cycle, item, start, end, rows=10000):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{rows}/{stat}/{cycle}/{start}/{end}/{item}"
    j = json.loads(get(url, UA))
    if "StatisticSearch" not in j:
        res = j.get("RESULT", {})
        raise RuntimeError(f"{res.get('CODE')}: {res.get('MESSAGE')}")
    out = []
    for r in j["StatisticSearch"]["row"]:
        v, t = num(r["DATA_VALUE"]), r["TIME"]
        if v is not None:
            out.append((f"{t[:4]}-{t[4:6]}-{t[6:8]}" if len(t) == 8 else f"{t[:4]}-{t[4:6]}-01", v))
    return out


def main(argv):
    RAW.mkdir(parents=True, exist_ok=True)
    check = "--check" in argv
    key = "sample" if check else find_key()
    if not key:
        old = read_json(OUT, {}) or {}
        if old.get("status") == "ok":
            log("ECOS 키가 없음 → 지난번에 받은 한국 자료를 그대로 둠")
            return 0
        write_json(OUT, {"status": "no_key", "generated": now_utc(),
                         "message": "한국은행 ECOS 인증키가 없습니다. 4. desk/.env 파일에 ECOS_API_KEY=발급받은키 한 줄을 넣고 다시 실행하세요."})
        log("ECOS 키가 없음 → korea.json에 no_key 기록")
        return 0
    today = date.today().strftime("%Y%m%d")
    out = {"status": "ok", "generated": now_utc(), "source": "한국은행 ECOS", "daily": {}, "monthly": {}, "names": {},
           "problems": []}
    for name, stat, item, label in DAILY:
        try:
            rows = ecos(key, stat, "D", item, "20261101" if check else START, today, 10 if check else 10000)
            out["daily"][name] = {"d": [a for a, _ in rows], "v": [b for _, b in rows]}
            out["names"][name] = label
            log(f"  {label:14s} {rows[0][0]} ~ {rows[-1][0]}  {len(rows)}개")
        except Exception as e:
            out["problems"].append(f"{label}: {e}")
            log(f"  ! {label}: {e}")
    for name, stat, item, label in MONTHLY:
        try:
            rows = ecos(key, stat, "M", item, "202601" if check else START[:6], today[:6], 10 if check else 10000)
            out["monthly"][name] = {"d": [a for a, _ in rows], "v": [b for _, b in rows]}
            out["names"][name] = label
            log(f"  {label:14s} {rows[0][0]} ~ {rows[-1][0]}  {len(rows)}개")
        except Exception as e:
            out["problems"].append(f"{label}: {e}")
            log(f"  ! {label}: {e}")
    if check:
        log(f"형식 확인 끝 (저장하지 않음). 받은 시리즈 {len(out['daily']) + len(out['monthly'])}개, 문제 {len(out['problems'])}건")
        return 0 if out["daily"] else 1
    if not out["daily"].get("ktb10"):
        old = read_json(OUT, {}) or {}
        log("국고채 10년을 받지 못함 → " + ("지난번 자료를 그대로 둠" if old.get("status") == "ok" else "실패로 기록"))
        if old.get("status") != "ok":
            write_json(OUT, {"status": "error", "generated": now_utc(), "message": "; ".join(out["problems"])[:400]})
        return 0
    write_json(OUT, out)
    log(f"저장 {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
