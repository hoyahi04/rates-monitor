"""데스크 대시보드에 새로 필요한 공개 자료를 받는다 → data/raw/extra.json, data/raw/fedinvest.csv

묶음 (하나가 실패해도 나머지는 계속하고, 실패한 묶음은 지난번 값을 그대로 둔다)
  fred_daily   FRED 일별: 크로스에셋, 실질금리·BEI, 신용 스프레드(등급·만기별 지수 OAS)
  intl         FRED 월별(OECD): 나라별 10년 금리, 3개월 금리, 실업률, 정부부채
  yahoo        Yahoo Finance: 금·구리 선물, KOSPI (비공식 경로라 막힐 수 있다)
  cftc         CFTC TFF 보고서: 국채선물 투자자별 포지션 (주 1회)
  upcoming     재무부 잠정 입찰 일정(XML) + TreasuryDirect 공고: 예정 입찰
  calendar     연준 일정(FOMC·연설), BEA 발표일(GDP·PCE), FRED 발표 달력(CPI·고용 등)
  news         연준 보도자료·연설·의회 증언 RSS, 한국은행 보도자료 RSS
  fedinvest    재무부 FedInvest 종목별 종가 (가장 최근에 값이 채워진 영업일)

실행:  python3 fetch_extra.py            전부
       python3 fetch_extra.py cftc news   고른 묶음만
"""
import csv, html, http.cookiejar, io, json, re, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from common import RAW, UA, UA_BROWSER, UA_YAHOO, fred, get, get_bytes, log, now_utc, num, read_json, write_json

START = "2014-01-01"
OUT = RAW / "extra.json"

FRED_DAILY = {
    # 크로스에셋
    "sp500": "SP500", "nasdaq": "NASDAQCOM", "dxy_broad": "DTWEXBGS", "usdkrw": "DEXKOUS", "usdjpy": "DEXJPUS",
    "eurusd": "DEXUSEU", "wti": "DCOILWTICO",
    # 실질금리, BEI, 단기
    "real5": "DFII5", "real10": "DFII10", "real30": "DFII30", "bei5": "T5YIE", "tbill3m": "DTB3",
    # 신용 스프레드 (ICE BofA 지수 OAS, %). FRED는 최근 3년치만 준다.
    "oas_ig": "BAMLC0A0CM", "oas_hy": "BAMLH0A0HYM2",
    "oas_aaa": "BAMLC0A1CAAA", "oas_aa": "BAMLC0A2CAA", "oas_a": "BAMLC0A3CA", "oas_bbb": "BAMLC0A4CBBB",
    "oas_bb": "BAMLH0A1HYBB", "oas_b": "BAMLH0A2HYB", "oas_ccc": "BAMLH0A3HYC", "oas_em": "BAMLEMCBPIOAS",
    "oas_ig_1_3": "BAMLC1A0C13Y", "oas_ig_3_5": "BAMLC2A0C35Y", "oas_ig_5_7": "BAMLC3A0C57Y",
    "oas_ig_7_10": "BAMLC4A0C710Y", "oas_ig_10_15": "BAMLC7A0C1015Y", "oas_ig_15p": "BAMLC8A0C15PY",
}
COUNTRIES = [("US", "미국"), ("KR", "한국"), ("JP", "일본"), ("DE", "독일"), ("GB", "영국"), ("FR", "프랑스"),
             ("IT", "이탈리아"), ("CA", "캐나다"), ("AU", "호주")]
INTL = {"y10": "IRLTLT01{c}M156N", "r3m": "IR3TIB01{c}M156N", "unemp": "LRHUTTTT{c}M156S"}
YAHOO = {"gold": "GC=F", "copper": "HG=F", "kospi": "^KS11"}
CFTC = [("042601", "2Y", "2년 선물"), ("044601", "5Y", "5년 선물"), ("043602", "10Y", "10년 선물"),
        ("043607", "U10", "울트라 10년 선물"), ("020601", "UB20", "T-Bond 선물"), ("020604", "UB30", "울트라 본드 선물")]
# FRED 발표 달력: (release id, 제목에 들어 있어야 할 말, 화면 이름, 미 동부 시각, 중요도)
FRED_RELEASES = [(10, "Consumer Price Index", "소비자물가 (CPI)", "08:30", 3),
                 (50, "Employment Situation", "고용보고서 (비농업 고용·실업률)", "08:30", 3),
                 (46, "Producer Price Index", "생산자물가 (PPI)", "08:30", 2),
                 (192, "Job Openings", "구인·이직 (JOLTS)", "10:00", 2),
                 (9, "Retail", "소매판매", "08:30", 2),
                 (180, "Unemployment Insurance", "신규 실업수당 청구", "08:30", 1)]
BEA_RELEASES = [("Gross Domestic Product", "GDP", 2), ("Personal Income and Outlays", "개인소득·지출 (PCE 물가)", 3)]


def series_pack(rows):
    return {"d": [a for a, _ in rows], "v": [round(b, 5) for _, b in rows]}


# ───────────────────────── 묶음별 수집 ─────────────────────────
def g_fred_daily():
    out, miss = {}, []
    for key, sid in FRED_DAILY.items():
        try:
            out[key] = series_pack(fred(sid, START))
            log(f"  {sid:16s} {out[key]['d'][0]} ~ {out[key]['d'][-1]}  {len(out[key]['d'])}개")
        except Exception as e:
            miss.append(f"{sid}: {e}")
    if not out:
        raise RuntimeError("; ".join(miss))
    return out, miss


def g_intl():
    out, miss = {"countries": [{"code": c, "name": n} for c, n in COUNTRIES], "series": {}}, []
    for c, _ in COUNTRIES:
        row = {}
        for key, pat in INTL.items():
            try:
                row[key] = series_pack(fred(pat.format(c=c), "2015-01-01"))
            except Exception as e:
                miss.append(f"{pat.format(c=c)}: {e}")
        try:
            row["debt_gdp"] = series_pack(fred(f"GGGDTA{c}A188N", "2010-01-01"))
        except Exception as e:
            miss.append(f"GGGDTA{c}A188N: {e}")
        out["series"][c] = row
        log(f"  {c}: " + ", ".join(f"{k} {v['d'][-1]}" for k, v in row.items()))
    if not any(out["series"].values()):
        raise RuntimeError("; ".join(miss))
    return out, miss


def g_yahoo():
    out, miss = {}, []
    p1 = int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.now(timezone.utc).timestamp())
    for key, sym in YAHOO.items():
        try:
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
                   f"?period1={p1}&period2={p2}&interval=1d")
            j = json.loads(get(url, UA_YAHOO, tries=2))["chart"]["result"][0]
            close = j["indicators"]["quote"][0]["close"]
            rows = {}
            for t, v in zip(j["timestamp"], close):
                if v is not None:
                    rows[datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")] = v
            out[key] = series_pack(sorted(rows.items()))
            log(f"  {sym:8s} {out[key]['d'][0]} ~ {out[key]['d'][-1]}  {len(rows)}개")
        except Exception as e:
            miss.append(f"Yahoo {sym}: {e}")
    if not out:
        raise RuntimeError("; ".join(miss))
    return out, miss


def g_cftc():
    codes = ",".join(f"'{c}'" for c, _, _ in CFTC)
    q = {"$select": "report_date_as_yyyy_mm_dd,cftc_contract_market_code,open_interest_all,"
                    "dealer_positions_long_all,dealer_positions_short_all,asset_mgr_positions_long,"
                    "asset_mgr_positions_short,lev_money_positions_long,lev_money_positions_short",
         "$where": f"cftc_contract_market_code in ({codes}) AND report_date_as_yyyy_mm_dd > '2021-10-01T00:00:00'",
         "$order": "report_date_as_yyyy_mm_dd", "$limit": "6000"}
    rows = json.loads(get("https://publicreporting.cftc.gov/resource/gpe5-46if.json?" + urllib.parse.urlencode(q)))
    if not rows:
        raise RuntimeError("CFTC: 빈 응답")
    out = []
    for code, key, name in CFTC:
        mine = [x for x in rows if x.get("cftc_contract_market_code") == code]
        g = lambda x, k: int(float(x.get(k) or 0))
        out.append({"key": key, "name": name, "code": code,
                    "d": [x["report_date_as_yyyy_mm_dd"][:10] for x in mine],
                    "oi": [g(x, "open_interest_all") for x in mine],
                    "am": [g(x, "asset_mgr_positions_long") - g(x, "asset_mgr_positions_short") for x in mine],
                    "lev": [g(x, "lev_money_positions_long") - g(x, "lev_money_positions_short") for x in mine],
                    "dealer": [g(x, "dealer_positions_long_all") - g(x, "dealer_positions_short_all") for x in mine]})
        log(f"  {key:5s} {len(mine)}주  ~ {out[-1]['d'][-1] if mine else '-'}")
    return out, [f"CFTC {c['key']}: 자료 없음" for c in out if not c["d"]]


def g_upcoming():
    """재무부 잠정 입찰 일정(분기 리펀딩 때 공개하는 XML)에 TreasuryDirect 공고(물량, CUSIP, 낙찰 금리)를 붙인다."""
    today = date.today()
    lo, hi = today - timedelta(days=4), today + timedelta(days=70)
    miss = []
    day = lambda v: (v or "")[:10]
    td = {}
    try:
        for path in ("announced?format=json&days=21", "upcoming?format=json"):
            for x in json.loads(get("https://www.treasurydirect.gov/TA_WS/securities/" + path, UA_BROWSER)):
                # 이표채 재발행은 공고의 만기 표기가 "9-Year 11-Month"처럼 남은 기간이라, 처음 발행 때의 만기로 맞춘다
                k = (day(x.get("competitiveAuctionCloseDate")) or day(x.get("auctionDate")),
                     x.get("securityTerm") if x.get("securityType") == "Bill"
                     else (x.get("originalSecurityTerm") or x.get("securityTerm")),
                     x.get("floatingRate") == "Yes", x.get("inflationProtected") == "Yes")
                amt = num(x.get("offeringAmount"))
                td[k] = {"cusip": x.get("cusip"), "offering_bn": None if not amt else round(amt / 1e9, 1),
                         "high_yield": num(x.get("highYield")) or num(x.get("highDiscountRate")),
                         "type": x.get("securityType"), "issue_date": day(x.get("issueDate")),
                         "announce_date": day(x.get("announcementDate")), "reopening": x.get("reopening") == "Yes",
                         "tips": x.get("inflationProtected") == "Yes", "frn": x.get("floatingRate") == "Yes"}
    except Exception as e:
        miss.append(f"TreasuryDirect 공고: {e}")

    out, seen = [], set()
    try:
        xml = get("https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml", UA_BROWSER)
        for blk in re.findall(r"<AuctionCalendarDate>(.*?)</AuctionCalendarDate>", xml, re.S):
            f = lambda t: (re.search(rf"<{t}>\s*(.*?)\s*</{t}>", blk, re.S) or [None, ""])[1]
            ad = f("AuctionDate")
            if not ad or not (lo.isoformat() <= ad <= hi.isoformat()):
                continue
            term = f("SecurityTermWeekYear")
            typ = {"NOTE": "Note", "BOND": "Bond", "BILL": "Bill", "CMB": "Bill"}.get(f("SecurityType").upper(), f("SecurityType").title())
            key = (ad, term, f("FloatingRate") == "Y", f("TIPS") == "Y")
            more = td.get(key, {})
            seen.add(key)
            out.append({"auction_date": ad, "announce_date": f("AnnouncementDate"), "issue_date": f("SettlementDate"),
                        "maturity_date": f("MaturityDate"), "type": typ, "term": term,
                        "reopening": f("ReOpeningIndicator") == "Y", "tips": f("TIPS") == "Y", "frn": f("FloatingRate") == "Y",
                        "cusip": more.get("cusip"), "offering_bn": more.get("offering_bn"),
                        "high_yield": more.get("high_yield"), "tentative": not more})
    except Exception as e:
        miss.append(f"재무부 잠정 입찰 일정: {e}")
    for key, more in td.items():                 # 잠정 일정에 없는 공고(현금관리 단기채 등)
        ad, term = key[0], key[1]
        if key in seen or not ad or not (lo.isoformat() <= ad <= hi.isoformat()):
            continue
        out.append({"auction_date": ad, "announce_date": more["announce_date"], "issue_date": more["issue_date"],
                    "maturity_date": None, "type": more["type"], "term": term, "reopening": more["reopening"],
                    "tips": more["tips"], "frn": more["frn"], "cusip": more["cusip"],
                    "offering_bn": more["offering_bn"], "high_yield": more["high_yield"], "tentative": False})
    if not out:
        raise RuntimeError("; ".join(miss) or "예정 입찰이 없음")
    out.sort(key=lambda x: (x["auction_date"], x["type"] == "Bill", x["term"]))
    n_cpn = sum(1 for x in out if x["type"] != "Bill")
    log(f"  예정 입찰 {len(out)}건 (이표채 {n_cpn}건)  {out[0]['auction_date']} ~ {out[-1]['auction_date']}")
    return out, miss


def _hhmm(text):
    """'2:30 p.m.' → '14:30'. 읽지 못하면 빈 문자열."""
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*([ap])\.?m", (text or "").lower())
    if not m:
        return ""
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "p" else 0)
    return f"{h:02d}:{m.group(2)}"


def g_calendar():
    out, miss = [], []
    today = date.today()
    lo, hi = today - timedelta(days=14), today + timedelta(days=75)

    def keep(dt):
        return lo <= dt <= hi

    # 1) 연준 일정
    try:
        ev = json.loads(get("https://www.federalreserve.gov/json/calendar.json", UA_BROWSER))["events"]
        for e in ev:
            typ, title = e.get("type"), html.unescape((e.get("title") or "").strip())
            if typ not in ("FOMC", "Speeches", "Testimony", "Beige"):
                continue
            for day in re.findall(r"\d+", e.get("days") or ""):
                try:
                    dt = date.fromisoformat(f"{e['month']}-{int(day):02d}")
                except Exception:
                    continue
                if not keep(dt):
                    continue
                kind = {"FOMC": "FOMC", "Speeches": "연설", "Testimony": "의회 증언", "Beige": "연준 자료"}[typ]
                imp = 3 if (typ == "FOMC" and "Minutes" not in title) else 2 if typ in ("FOMC", "Testimony") else 1
                if typ == "Speeches" and re.search(r"Chair(man)?\s", title) and "Vice" not in title:
                    imp = 2
                note = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(e.get("description") or ""))).strip()
                out.append({"date": dt.isoformat(), "time": _hhmm(e.get("time")), "kind": kind,
                            "title": title, "note": note[:140], "imp": imp, "src": "연준"})
    except Exception as e:
        miss.append(f"연준 일정: {e}")

    # 2) BEA (GDP, PCE)
    try:
        bea = json.loads(get("https://apps.bea.gov/API/signup/release_dates.json", UA_BROWSER))
        for name, label, imp in BEA_RELEASES:
            for ts in (bea.get(name) or {}).get("release_dates", []):
                dt = datetime.fromisoformat(ts).astimezone(timezone(timedelta(hours=-5)))
                if keep(dt.date()):
                    out.append({"date": dt.date().isoformat(), "time": "08:30", "kind": "지표", "title": label,
                                "note": name, "imp": imp, "src": "BEA"})
    except Exception as e:
        miss.append(f"BEA 발표일: {e}")

    # 3) FRED 발표 달력 (BLS 사이트는 자동 접속을 막는다)
    for rid, must, label, tm, imp in FRED_RELEASES:
        try:
            page = get(f"https://fred.stlouisfed.org/releases/calendar?rid={rid}&vs={lo.isoformat()}&ve={hi.isoformat()}")
            if must.lower() not in page[:4000].lower():
                raise ValueError("다른 발표의 달력이 옴")
            for m in re.finditer(r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+([A-Z][a-z]+ \d{1,2}, \d{4})", page):
                dt = datetime.strptime(m.group(1), "%B %d, %Y").date()
                if keep(dt):
                    out.append({"date": dt.isoformat(), "time": tm, "kind": "지표", "title": label, "note": must,
                                "imp": imp, "src": "FRED 발표 달력"})
        except Exception as e:
            miss.append(f"FRED 발표 달력 {label}: {e}")

    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: (e["date"], -e["imp"], e["title"])):
        k = (e["date"], e["title"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    if not uniq:
        raise RuntimeError("; ".join(miss))
    log(f"  일정 {len(uniq)}건  ({lo} ~ {hi})")
    return uniq, miss


def _rss(url, headers=UA_BROWSER):
    text = get(url, headers)
    items = []
    for it in re.findall(r"<item>(.*?)</item>", text, re.S):
        def tag(t):
            m = re.search(rf"<{t}>(.*?)</{t}>", it, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip()) if m else ""
        try:
            ts = parsedate_to_datetime(tag("pubDate")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        except Exception:
            continue
        items.append({"ts": ts, "title": re.sub(r"\s+", " ", tag("title")), "link": tag("link"), "cat": tag("category")})
    return items


def g_news():
    feeds = [("https://www.federalreserve.gov/feeds/press_all.xml", "연준", "보도자료"),
             ("https://www.federalreserve.gov/feeds/speeches.xml", "연준", "연설"),
             ("https://www.federalreserve.gov/feeds/testimony.xml", "연준", "의회 증언"),
             ("https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690", "한국은행", "보도자료")]
    out, miss = [], []
    for url, src, kind in feeds:
        try:
            got = _rss(url)
            for it in got[:40]:
                if not it["link"].startswith("http"):
                    continue
                out.append({"ts": it["ts"], "src": src, "kind": kind, "cat": it["cat"], "title": it["title"][:220],
                            "link": it["link"]})
            log(f"  {src} {kind}: {len(got)}건")
        except Exception as e:
            miss.append(f"{src} {kind} RSS: {e}")
    if not out:
        raise RuntimeError("; ".join(miss))
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out[:80], miss


def _fedinvest_csv(day):
    """한 날짜의 FedInvest 종가 CSV. 세션 쿠키와 CSRF 토큰이 필요해 네 단계를 거친다."""
    base = "https://www.treasurydirect.gov/GA-FI/FedInvest"
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.addheaders = list(UA_BROWSER.items())

    def call(path, data=None, referer=None):
        req = urllib.request.Request(f"{base}/{path}", data=urllib.parse.urlencode(data).encode() if data else None)
        if referer:
            req.add_header("Referer", f"{base}/{referer}")
        with op.open(req, timeout=90) as r:
            return r.read().decode("utf-8", errors="replace")

    def token(page):
        m = re.search(r'name="_csrf" value="([^"]*)"', page)
        if not m:
            raise ValueError("CSRF 토큰을 찾지 못함")
        return m.group(1)

    form = call("selectSecurityPriceDate")
    detail = call("selectSecurityPriceDate", {"priceDate": day.isoformat(), "submit": "Show Prices", "_csrf": token(form)},
                  "selectSecurityPriceDate")          # 302 → securityPriceDetail 을 따라간다
    if "_csrf" not in detail:
        detail = call("securityPriceDetail", referer="selectSecurityPriceDate")
    return call("securityPriceDetail", {"priceDateDay": day.day, "priceDateMonth": day.month, "priceDateYear": day.year,
                                        "fileType": "csv", "csv": "CSV FORMAT", "_csrf": token(detail)},
                "securityPriceDetail")


def g_fedinvest():
    day, tried = date.today(), []
    for _ in range(10):
        if day.weekday() < 5:
            try:
                text = _fedinvest_csv(day)
                rows = [x for x in csv.reader(io.StringIO(text)) if len(x) >= 8 and "MARKET BASED" in x[1]]
                coupons = [x for x in rows if x[1] in ("MARKET BASED NOTE", "MARKET BASED BOND")]
                filled = [x for x in coupons if (num(x[7]) or 0) > 0]
                tried.append(f"{day} {len(filled)}/{len(coupons)}")
                if len(coupons) > 200 and len(filled) > 0.9 * len(coupons):   # 종가가 채워진 날만 쓴다
                    (RAW / "fedinvest.csv").write_text(text, encoding="utf-8")
                    log(f"  FedInvest {day}: 이표채 {len(filled)}종목 종가")
                    return {"price_date": day.isoformat(), "n": len(filled)}, []
            except Exception as e:
                tried.append(f"{day} 오류 {e}")
        day -= timedelta(days=1)
    raise RuntimeError("종가가 채워진 날을 찾지 못함: " + "; ".join(tried))

def _fomc_statement(url):
    page = get(url, UA_BROWSER)
    i = page.find('id="article"')
    body = page[i:] if i >= 0 else page
    paras = []
    for raw in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()
        if not t:
            continue
        if t.startswith("For media inquiries") or t.startswith("Implementation Note"):
            break
        if t.startswith("For release at") or t == "Share" or re.fullmatch(r"[A-Z][a-z]+ \d{1,2}, \d{4}", t):
            continue
        paras.append(t)
    if not paras:
        raise RuntimeError(f"성명 본문을 찾지 못함: {url}")
    v = re.search(r"by an? (\d+)\s*(?:&ndash;|–|-|to)\s*(\d+) vote", page)
    return paras, ([int(v.group(1)), int(v.group(2))] if v else None)


def g_fomc():
    """FOMC 성명 최근 6개. 일정 페이지에서 성명 보도자료 링크(monetaryYYYYMMDDa.htm)를 모아 본문 문단을 저장한다."""
    base = "https://www.federalreserve.gov"
    cal = get(base + "/monetarypolicy/fomccalendars.htm", UA_BROWSER)
    links = sorted(set(re.findall(r'href="(/newsevents/pressreleases/monetary(\d{8})a\.htm)"', cal)), key=lambda x: x[1])
    if not links:
        raise RuntimeError("FOMC 성명 링크를 찾지 못함")
    out, miss = [], []
    for path, d in links[-6:]:
        try:
            paras, vote = _fomc_statement(base + path)
            if not any("Committee" in t for t in paras):
                miss.append(f"{d}: 성명이 아닌 보도자료로 보여 건너뜀")
                continue
            out.append({"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "url": base + path, "paras": paras, "vote": vote})
        except Exception as e:
            miss.append(f"{d}: {e}")
    if not out:
        raise RuntimeError("; ".join(miss))
    log(f"  FOMC 성명 {len(out)}개 ({out[0]['date']} ~ {out[-1]['date']})")
    return out, miss
_MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def _sme_table(lines, k):
    """lines[k] = 'Federal Funds Target Rate or Range Modal Forecasts'. 그 아래 머리글과 25/중간/75 백분위 줄을 읽는다."""
    head, rows = [], {}
    for ln in lines[k + 1:k + 9]:
        t = ln.strip()
        for key, lab in (("p25", "25th Percentile"), ("med", "Median"), ("p75", "75th Percentile")):
            if t.startswith(lab):
                rows[key] = [float(x) for x in re.findall(r"(-?\d+\.\d+)%", t)]
        if not rows and t:
            head.append(t)
    return head, rows


def g_sme():
    """뉴욕 연은 시장참가자 설문(SME) 결과 PDF에서 정책금리 중간값 경로(3a)와 장기 금리(3b)를 읽는다.
    PDF를 글자로 바꾸는 데 poppler의 pdftotext가 필요하다 (맥: brew install poppler)."""
    if not shutil.which("pdftotext"):
        raise RuntimeError("pdftotext 없음 (poppler 설치 필요) → SME 건너뜀")
    base = "https://www.newyorkfed.org"
    page = get(base + "/markets/market-intelligence/survey-of-market-expectations", UA_BROWSER)
    links = re.findall(r'href="(/medialibrary/media/markets/survey/(\d{4})/([a-z]{3})-\d{4}-sme-results\.pdf)"', page)
    if not links:
        raise RuntimeError("SME 결과 PDF 링크를 찾지 못함")
    path, yr, mon = max(links, key=lambda x: (x[1], _MON.get(x[2], 0)))
    with tempfile.TemporaryDirectory() as td:
        pdf = f"{td}/sme.pdf"
        open(pdf, "wb").write(get_bytes(base + path, UA_BROWSER))
        subprocess.run(["pdftotext", "-layout", pdf, f"{td}/sme.txt"], check=True)
        lines = open(f"{td}/sme.txt", encoding="utf-8", errors="replace").read().splitlines()
    idx = [k for k, ln in enumerate(lines) if "Federal Funds Target Rate or Range Modal Forecasts" in ln]
    if len(idx) < 3:
        raise RuntimeError("SME 3a/3b 표를 찾지 못함")
    pts, y, last_m = [], int(yr), 0
    # 표 1: FOMC 회의별 (머리글 = 월 이름 줄 + 날짜 줄)
    head, rows = _sme_table(lines, idx[0])
    months = [_MON[m.lower()[:3]] for m in re.findall(r"([A-Z][a-z]{2})\.?", head[0]) if m.lower()[:3] in _MON]
    days = re.findall(r"\d+-\d+", head[1]) if len(head) > 1 else []
    for j, m in enumerate(months):
        if m < last_m:
            y += 1
        last_m = m
        pts.append({"label": f"{y}-{m:02d} FOMC" + (f" ({days[j]}일)" if j < len(days) else ""), "month": f"{y}-{m:02d}",
                    "kind": "meeting"})
    # 표 2: 분기 말·연말
    head2, rows2 = _sme_table(lines, idx[1])
    for t in re.findall(r"(\d{4})(?:\s+Q(\d))?", head2[0]):
        qy, q = int(t[0]), t[1]
        pts.append({"label": f"{qy} Q{q} 말" if q else f"{qy}년 말", "month": f"{qy}-{int(q) * 3 if q else 12:02d}",
                    "kind": "quarter" if q else "year"})
    for key in ("p25", "med", "p75"):
        vals = rows.get(key, []) + rows2.get(key, [])
        if len(vals) != len(pts):
            raise RuntimeError(f"SME 표 열 수가 맞지 않음 ({key}: {len(vals)} vs {len(pts)})")
        for p, v in zip(pts, vals):
            p[key] = v
    _, rows3 = _sme_table(lines, idx[2])
    lr = rows3.get("med", [None, None])
    log(f"  SME {mon} {yr}: {len(pts)}개 시점")
    return {"survey": f"{yr}-{_MON[mon]:02d}", "url": base + path, "points": pts,
            "avg10": lr[0] if len(lr) > 1 else None, "lr": lr[-1]}, []

def _cells(tr):
    return [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)]


def g_sep():
    """최신 SEP(경제전망 요약): 표 1의 정책금리 중간값(이번·직전)과 그림 2의 점도표 분포(위원별 점 개수)."""
    base = "https://www.federalreserve.gov"
    cal = get(base + "/monetarypolicy/fomccalendars.htm", UA_BROWSER)
    links = sorted(set(re.findall(r'href="(/monetarypolicy/fomcprojtabl(\d{8})\.htm)"', cal)), key=lambda x: x[1])
    if not links:
        raise RuntimeError("SEP 링크를 찾지 못함")
    path, d = links[-1]
    page = get(base + path, UA_BROWSER)
    tables = re.findall(r"<table.*?</table>", page, re.S)
    t1 = next((t for t in tables if "Federal funds rate" in t), None)
    if not t1:
        raise RuntimeError("SEP 표 1을 찾지 못함")
    rows = [_cells(tr) for tr in re.findall(r"<tr.*?</tr>", t1, re.S)]
    head = next(r for r in rows if any(c.startswith("Longer") for c in r))
    nlr = next(i for i, c in enumerate(head) if c.startswith("Longer"))
    years = head[:nlr] + ["LR"]
    k = next(i for i, r in enumerate(rows) if r and r[0].startswith("Federal funds rate"))
    val = lambda x: float(x) if re.fullmatch(r"-?\d+(\.\d+)?", x or "") else None
    med = [val(x) for x in rows[k][1:1 + len(years)]]
    prev_row = rows[k + 1] if k + 1 < len(rows) and "projection" in rows[k + 1][0] else None
    prev = [val(x) for x in prev_row[1:1 + len(years)]] if prev_row else []
    econ = {}
    for name, key in (("Change in real GDP", "gdp"), ("Unemployment rate", "unemp"), ("PCE inflation", "pce"), ("Core PCE inflation", "core_pce")):
        row = next((r_ for r_ in rows if r_ and r_[0].startswith(name)), None)
        if row:
            econ[key] = {y: v for y, v in zip(years, [val(x) for x in row[1:1 + len(years)]]) if v is not None}
    out = {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "url": base + path, "econ": econ,
           "median": dict(zip(years, med)), "prev_label": prev_row[0] if prev_row else None,
           "prev_median": {y: v for y, v in zip(years, prev) if v is not None}}
    t2 = next((t for t in tables if "Midpoint of target range" in t or "midpoint of target range" in t), None)
    if t2:
        rows2 = [_cells(tr) for tr in re.findall(r"<tr.*?</tr>", t2, re.S)]
        h2 = next((r for r in rows2 if any(re.fullmatch(r"\d{4}", c) for c in r)), [])
        cols = [c for c in h2 if re.fullmatch(r"\d{4}", c) or c.startswith("Longer")]
        dots = {c if c[0].isdigit() else "LR": {} for c in cols}
        for r in rows2:
            if r and re.fullmatch(r"\d\.\d{3}", r[0]):
                for c, v in zip(cols, r[1:]):
                    if v.isdigit():
                        dots[c if c[0].isdigit() else "LR"][r[0]] = int(v)
        out["dots"] = dots
    log(f"  SEP {out['date']}: 중간값 {out['median']} (직전 {out['prev_median']})")
    return out, []


GROUPS = [("fred_daily", g_fred_daily), ("intl", g_intl), ("yahoo", g_yahoo), ("cftc", g_cftc),
          ("upcoming", g_upcoming), ("calendar", g_calendar), ("news", g_news), ("fedinvest", g_fedinvest),
          ("sme", g_sme), ("fomc", g_fomc), ("sep", g_sep)]


def main(argv):
    RAW.mkdir(parents=True, exist_ok=True)
    old = read_json(OUT, {}) or {}
    out = dict(old)
    status = dict(old.get("status") or {})
    want = set(argv) or {k for k, _ in GROUPS}
    for key, fn in GROUPS:
        if key not in want:
            continue
        log(f"[{key}]")
        try:
            data, miss = fn()
            out[key] = data
            status[key] = {"ok": True, "at": now_utc(), "problems": miss}
            for m in miss:
                log("  ! " + m)
        except Exception as e:
            log(f"  실패: {e}  → 지난번 값을 그대로 둠")
            prev = status.get(key) or {}
            status[key] = {"ok": False, "at": prev.get("at"), "problems": [str(e)[:300]]}
    out["status"] = status
    out["generated"] = now_utc()
    write_json(OUT, out)
    bad = [k for k, v in status.items() if not v["ok"]]
    log(f"저장 {OUT.name}" + (f"  (실패: {', '.join(bad)})" if bad else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
