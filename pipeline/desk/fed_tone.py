"""연준 발언 성향(매파·중립·비둘기파) 분류 → desk/data/raw/fed_tone.json

연준 트래커 확장안 ①(발언별 성향)과 ③(기조 점수 S1·S3·S4)의 재료를 만든다.
- 대상: extra.json의 연준 연설·의회 증언(RSS), FOMC 성명(extra.json fomc), FOMC 기자회견 녹취(PDF)
- 방법: 문장을 하나씩 FOMC-RoBERTa로 분류(H/N/D) → 성향 = (매파 문장 − 비둘기파 문장) ÷ 전체 문장 (−1~+1)
- 통화정책과 관련 없는 발언(은행 감독, 결제, 지역 개발 등)은 정책 키워드가 든 문장 비율로 가른다.
- 이미 분류한 발언은 다시 분류하지 않는다(파일에 남겨 둠). 새 발언만 받아서 분류한다.

준비 (한 번만):  pip install torch transformers   (CPU면 충분, 모델 약 500MB를 처음에 받음)
                 기자회견 PDF를 읽으려면 pdftotext (맥: brew install poppler)
실행:            python3 pipeline/desk/fed_tone.py      (fetch_extra.py 다음, build_data.py 전에)
이 파일이 없거나 오래돼도 build_data.py는 돌아간다. 성향 칸만 비어 있게 된다.
"""
import html, re, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone

from common import RAW, UA_BROWSER, get, get_bytes, log, now_utc, read_json, write_json

OUT = RAW / "fed_tone.json"
MODEL = "tim9510019/FOMC-RoBERTa"          # gtfintechlab/FOMC-RoBERTa(Shah et al. 2023)의 공개 사본
LABELS = {"LABEL_0": "D", "LABEL_1": "H", "LABEL_2": "N"}
POLICY_RE = re.compile(r"inflation|monetary policy|federal funds|interest rate|policy rate|policy stance|labor market|"
                       r"unemployment|employment|price stability|FOMC|Committee|rate cut|rate increase|tighten|easing|"
                       r"balance sheet|neutral rate|r-star|tariff", re.I)
POLICY_SHARE = 0.20                          # 정책 키워드 문장 비율이 이보다 낮으면 '정책 무관'
MAX_SENT = 160


def _paras(page):
    i = page.find('id="article"')
    body = page[i:] if i >= 0 else page
    out = []
    for raw in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
        if not t:
            continue
        if t.endswith("Return to text") or t.startswith("Board of Governors of the Federal Reserve System"):
            break
        out.append(t)
    return out


def _sentences(paras):
    sents = []
    for p in paras:
        if len(p) < 80:            # 날짜, 이름, 장소 줄
            continue
        p = re.sub(r"\s\d{1,2}(?=\s|$)", " ", p)      # 각주 번호
        sents += [s.strip() for s in re.split(r"(?<=[.?!])\s+(?=[A-Z\"“])", p) if 30 < len(s.strip()) < 600]
    return sents[:MAX_SENT]


def _presconf_sentences(d):
    """FOMC 기자회견 녹취 PDF에서 의장 발언 문장만 (기자 질문은 뺀다)."""
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext 없음")
    url = f"https://www.federalreserve.gov/mediacenter/files/FOMCpresconf{d.replace('-', '')}.pdf"
    with tempfile.TemporaryDirectory() as td:
        open(f"{td}/p.pdf", "wb").write(get_bytes(url, UA_BROWSER))
        subprocess.run(["pdftotext", f"{td}/p.pdf", f"{td}/p.txt"], check=True)
        txt = open(f"{td}/p.txt", encoding="utf-8", errors="replace").read()
    m = re.search(r"Chair(?:man)? (\w+)[’']s Press Conference", txt)
    txt = re.sub(r"Page \d+ of \d+|(?:Transcript of )?Chair(?:man)? \w+[’']s Press Conference|FINAL|[A-Z][a-z]+ \d{1,2}, \d{4}", " ", txt)
    # 화자 표시(CHAIR WARSH. / NAME LASTNAME.)로 끊어 의장 몫만 모은다
    parts = re.split(r"\n\s*([A-Z][A-Z .'’-]{3,40})\.\s", "\n" + txt)
    chair, speak = [], None
    for k in range(1, len(parts) - 1, 2):
        speak, said = parts[k].strip(), parts[k + 1]
        if speak.startswith("CHAIR"):
            chair.append(re.sub(r"\s+", " ", said))
    return url, _sentences(chair), (m.group(1) if m else "")


def main():
    ex = read_json(RAW / "extra.json", {}) or {}
    old = read_json(OUT, {}) or {}
    items = dict(old.get("items") or {})
    todo = []
    for n in ex.get("news") or []:
        if n.get("src") == "연준" and n.get("kind") in ("연설", "의회 증언") and n["link"] not in items:
            todo.append({"key": n["link"], "date": n["ts"][:10], "kind": n["kind"], "speaker": n["title"].split(",")[0].strip(),
                         "title": n["title"].split(",", 1)[-1].strip(), "url": n["link"], "src": "page"})
    for st in ex.get("fomc") or []:
        if "stmt:" + st["date"] not in items:
            todo.append({"key": "stmt:" + st["date"], "date": st["date"], "kind": "성명", "speaker": "FOMC", "title": "FOMC 성명",
                         "url": st["url"], "src": "stmt", "paras": [p for p in st["paras"] if not p.startswith("Voting")]})
        if "presconf:" + st["date"] not in items:
            todo.append({"key": "presconf:" + st["date"], "date": st["date"], "kind": "기자회견", "speaker": "의장",
                         "title": "FOMC 기자회견 (의장 발언)", "url": None, "src": "presconf"})
    log(f"새로 분류할 발언 {len(todo)}건 (이미 {len(items)}건)")
    if not todo:
        write_json(OUT, dict(old, generated=now_utc()))
        return 0
    from transformers import pipeline                       # 무거워서 필요할 때만 불러온다
    clf = pipeline("text-classification", model=MODEL, truncation=True)
    problems = []
    for t in todo:
        try:
            if t["src"] == "page":
                sents = _sentences(_paras(get(t["url"], UA_BROWSER)))
            elif t["src"] == "stmt":
                sents = _sentences(t["paras"])
            else:
                t["url"], sents, chair = _presconf_sentences(t["date"])
                if chair:
                    t["speaker"] = chair
            if not sents:
                raise RuntimeError("문장을 찾지 못함")
            labs = [LABELS.get(o["label"], o["label"]) for o in clf(sents, batch_size=16)]
            h, d = labs.count("H"), labs.count("D")
            pol = sum(bool(POLICY_RE.search(s)) for s in sents) / len(sents)
            ex_h = [s for s, l in zip(sents, labs) if l == "H"][:2]
            ex_d = [s for s, l in zip(sents, labs) if l == "D"][:2]
            items[t["key"]] = {"date": t["date"], "kind": t["kind"], "speaker": t["speaker"], "title": t["title"][:200],
                               "url": t["url"], "n": len(sents), "h": h, "d": d, "net": round((h - d) / len(sents), 3),
                               "policy_share": round(pol, 3), "policy": pol >= POLICY_SHARE or t["src"] != "page",
                               "ex_h": [s[:240] for s in ex_h], "ex_d": [s[:240] for s in ex_d]}
            log(f"  {t['date']} {t['speaker']:<10} {t['kind']:<5} 문장 {len(sents):>3}  성향 {items[t['key']]['net']:+.2f}"
                f"  정책 {pol:.0%}")
        except Exception as e:
            problems.append(f"{t['key']}: {str(e)[:150]}")
            log(f"  ! {t['key']}: {e}")
    write_json(OUT, {"generated": now_utc(), "model": MODEL, "policy_share_th": POLICY_SHARE, "items": items,
                     "problems": problems})
    log(f"저장 {OUT.name}  ({len(items)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
