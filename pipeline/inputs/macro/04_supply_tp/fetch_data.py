"""매크로 · 수급·기간 프리미엄 데이터 수집: 재무부 FiscalData + NY Fed + FRED → data.js + CSV

1) 입찰 결과 (FiscalData auctions_query)            → auctions.csv
   명목 고정금리 이표채(2·3·5·7·10·20·30년)만. 물가연동채(TIPS)·변동금리채(FRN)·단기채(Bills) 제외.
   낙찰금리, 응찰률(bid-to-cover), 배정 비중(프라이머리 딜러 / 간접 / 직접, 경쟁입찰 낙찰액 대비 %).
   FiscalData는 몇 주 늦게 갱신될 때가 있어, 최근 120일은 TreasuryDirect로 빈 입찰을 채운다.
2) 종류별 국채 잔액, 월말 (FiscalData MSPD 표 1)     → supply_monthly.csv
   Bills / Notes / Bonds / TIPS / FRN 잔액 + 연준 보유(월의 마지막 수요일) + 만기별 월 발행액.
   파생: 민간이 받아야 하는 장기물 순공급 = Bonds 잔액 증감 − 연준의 Bonds 보유 증감.
3) 연준 보유 국채, 주별 (FRED, H.4.1 수요일 기준)    → soma_weekly.csv
   종류별(단기채 / 명목 이표채 / TIPS)과 잔존만기별(1년 이하 ~ 10년 초과).
4) 기간 프리미엄, 일별 (NY Fed ACM + FRED Kim-Wright) → tp_daily.csv
   ACM 2·5·10년 기간 프리미엄, 10년 적합 금리, 10년 위험중립 금리(기대 단기금리 경로).
5) 분기 환매(QRA) 발표일                              → refunding_dates.csv
   2·5·8·11월 15일 전후 발행되는 10년 신규물의 입찰 공고일 = 분기 환매 발표일.
6) 정책금리 목표 상단 변경일 (FRED DFEDTARU)          → policy_rate.csv  (국면 구분용)

실행:  python3 fetch_data.py          (analyze.py가 있으면 이어서 실행. 수집만 하려면 --no-analyze)
필요:  ACM 파일이 .xls라 xlrd가 있어야 한다 (python3 -m pip install --user xlrd).
       없으면 ACM 열은 비우고 Kim-Wright(kw_tp10)만 채운다.

주의
- supply_monthly.csv의 날짜는 '기준 월말'이다. MSPD는 다음 달 초(4영업일쯤)에 발표되므로
  월말 판정에는 전월 말 값까지만 쓸 수 있다.
- 연준 보유는 주 1회(보통 수요일) 기준이라 월말과 최대 7일 어긋난다 (soma_asof 열이 실제 기준일).
- Bonds = 발행 만기 20·30년(CUSIP 912810). 연준의 Bonds 보유도 같은 기준으로 종목별 자료에서 합산한다.
- 입찰 tail(낙찰금리 − 입찰 직전 WI 금리)은 WI가 Bloomberg에만 있어 여기에는 없다.
- 수익률은 `pipeline/inputs/curve/data.js`에 있다 (analyze 단계에서 읽는다).
"""
import csv, io, json, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).parent
START = "2010-01-01"   # 2015년 시작 + 룩백 여유
FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
ACM_URL = "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls"
SOMA_URL = "https://markets.newyorkfed.org/api/soma/tsy/get/asof/{}.json"
SOMA_ASOF_URL = "https://markets.newyorkfed.org/api/soma/asofdates/list.json"
TD_URL ="https://www.treasurydirect.gov/TA_WS/securities/auctioned"
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"}

TENORS = ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
AUC_FIELDS = ["auction_date", "announcemt_date", "issue_date", "maturity_date",
              "security_term", "reopening", "cusip", "int_rate",
              "offering_amt", "total_accepted", "soma_accepted", "comp_accepted", "high_yield",
              "bid_to_cover_ratio", "primary_dealer_accepted", "indirect_bidder_accepted",
              "direct_bidder_accepted", "inflation_index_security", "floating_rate"]
AUC_COLS = ["auction_date", "announce_date", "issue_date", "maturity_date", "tenor", "security_term",
            "reopening", "cusip", "coupon", "offering_bn", "accepted_bn", "soma_bn", "high_yield",
            "bid_to_cover", "dealer_pct", "indirect_pct", "direct_pct"]
MSPD_CLASS = {"Bills": "bills_bn", "Notes": "notes_bn", "Bonds": "bonds_bn",
              "Treasury Inflation-Protected Securities": "tips_bn", "Floating Rate Notes": "frn_bn"}
SOMA_WEEKLY = [("soma_total_bn", "TREAST"), ("soma_bills_bn", "WSHOBL"), ("soma_coupon_bn", "WSHONBNL"),
               ("soma_tips_bn", "WSHONBIIL"), ("soma_le15d_bn", "TREAS15"), ("soma_16to90d_bn", "TREAS1590"),
               ("soma_91dto1y_bn", "TREAS911Y"), ("soma_1to5y_bn", "TREAS1T5"),
               ("soma_5to10y_bn", "TREAS5T10"), ("soma_over10y_bn", "TREAS10Y")]
ACM_COLS = [("acm_tp2", "ACMTP02"), ("acm_tp5", "ACMTP05"), ("acm_tp10", "ACMTP10"),
            ("acm_y10", "ACMY10"), ("acm_rn10", "ACMRNY10")]
MONTH_COLS = (["bills_bn", "notes_bn", "bonds_bn", "tips_bn", "frn_bn", "marketable_bn", "bill_share_pct",
               "soma_asof", "soma_bonds_bn", "soma_notes_bn", "bonds_chg_bn", "soma_bonds_chg_bn",
               "long_net_bn", "coupon_chg_bn", "soma_coupon_chg_bn", "coupon_net_bn"]
              + [f"gross_{t.lower()}_bn" for t in TENORS])


def get_bytes(url, headers=UA, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def get(url, headers=UA, tries=3):
    return get_bytes(url, headers, tries).decode("utf-8-sig")


def num(s):
    s = (s or "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def bn(s, digits=3):
    v = num(s)
    return None if v is None else round(v / 1e9, digits)


def fiscal(path, params):
    """FiscalData 한 엔드포인트의 모든 페이지를 모아 반환."""
    rows, page = [], 1
    while True:
        d = json.loads(get(f"{FISCAL}{path}?{params}&page[size]=10000&page[number]={page}"))
        rows += d["data"]
        if page >= d["meta"]["total-pages"]:
            return rows
        page += 1


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows([["" if v is None else v for v in r] for r in rows])


# ───────────────────────── 1) 입찰 ─────────────────────────
def auction_row(r):
    """FiscalData 필드 이름으로 된 입찰 한 건 → auctions.csv 한 줄. 결과가 아직 없으면 None.
    만기(tenor)는 입찰 시점의 잔존만기에서 가장 가까운 표준 만기다
    ('29-Year 10-Month' 재발행 → 30Y, 옛 5년물과 같은 종목으로 나온 2년 입찰 → 2Y)."""
    if r["inflation_index_security"] == "Yes" or r["floating_rate"] == "Yes":
        return None
    comp = num(r["comp_accepted"])
    if num(r["high_yield"]) is None or not comp:
        return None
    if (num(r["offering_amt"]) or 0) < 1e9:
        return None   # 비상 대비 시험 입찰(2,500만 달러짜리: 2019-06-21, 2021-12-02)
    years = (date.fromisoformat(r["maturity_date"]) - date.fromisoformat(r["issue_date"])).days / 365.25
    share = lambda k: round(num(r[k]) / comp * 100, 2) if num(r[k]) is not None else None
    return {
        "auction_date": r["auction_date"], "announce_date": r["announcemt_date"],
        "issue_date": r["issue_date"], "maturity_date": r["maturity_date"],
        "tenor": min(TENORS, key=lambda t: abs(int(t[:-1]) - years)),
        "security_term": r["security_term"], "reopening": r["reopening"],
        "cusip": r["cusip"], "coupon": num(r["int_rate"]),
        "offering_bn": bn(r["offering_amt"]), "accepted_bn": bn(r["total_accepted"]),
        "soma_bn": bn(r["soma_accepted"]), "high_yield": num(r["high_yield"]),
        "bid_to_cover": num(r["bid_to_cover_ratio"]),
        "dealer_pct": share("primary_dealer_accepted"),
        "indirect_pct": share("indirect_bidder_accepted"),
        "direct_pct": share("direct_bidder_accepted"),
    }


def fetch_recent_td(days=120):
    """TreasuryDirect의 최근 입찰. FiscalData가 몇 주씩 늦게 갱신될 때 빈 구간을 채운다.
    필드 이름을 FiscalData 형식으로 바꿔 돌려준다. 실패하면 빈 목록."""
    day = lambda s: (s or "")[:10]
    out = []
    try:
        for typ in ("Note", "Bond"):
            for r in json.loads(get(f"{TD_URL}?format=json&type={typ}&days={days}", headers=UA_BROWSER)):
                out.append({
                    "auction_date": day(r["competitiveAuctionCloseDate"]),
                    "announcemt_date": day(r["announcementDate"]),
                    "issue_date": day(r["issueDate"]), "maturity_date": day(r["maturityDate"]),
                    "security_term": r["securityTerm"], "reopening": r["reopening"], "cusip": r["cusip"],
                    "int_rate": r["interestRate"], "offering_amt": r["offeringAmount"],
                    "total_accepted": r["grandTotalParAwarded"],
                    "soma_accepted": r["somaNoncompetitiveParAwarded"],
                    "comp_accepted": r["subtotalCompetitiveParAwardedInsideOfOfferingAmount"],
                    "high_yield": r["highYield"], "bid_to_cover_ratio": r["bidToCoverRatio"],
                    "primary_dealer_accepted": r["primaryDealersCompetitiveParAwarded"],
                    "indirect_bidder_accepted": r["indirectBiddersCompetitiveParAwarded"],
                    "direct_bidder_accepted": r["directBiddersCompetitiveParAwarded"],
                    "inflation_index_security": r["inflationProtected"], "floating_rate": r["floatingRate"],
                })
    except Exception as e:
        print(f"  TreasuryDirect 실패({e}) → FiscalData만 사용", file=sys.stderr)
        return []
    return out


def fetch_auctions():
    raw = fiscal("/v1/accounting/od/auctions_query",
                 f"filter=security_type:in:(Note,Bond),auction_date:gte:{START}"
                 f"&fields={','.join(AUC_FIELDS)}&sort=auction_date")
    rows = {}
    for r in raw:
        a = auction_row(r)
        if a:
            rows[(a["auction_date"], a["cusip"])] = a
    n_fiscal = len(rows)
    for r in fetch_recent_td():   # FiscalData에 결과가 있는 입찰은 그대로 두고 없는 것만 채운다
        a = auction_row(r)
        if a:
            rows.setdefault((a["auction_date"], a["cusip"]), a)
    out = [rows[k] for k in sorted(rows)]
    print(f"  auctions ok (FiscalData {n_fiscal}건 + TreasuryDirect로 채움 {len(out) - n_fiscal}건)",
          file=sys.stderr)
    return out


def refunding_dates(auctions):
    """분기 환매 발표일: 2·5·8·11월에 발행되는 10년 신규물의 입찰 공고일."""
    return sorted({a["announce_date"] for a in auctions
                   if a["tenor"] == "10Y" and a["reopening"] == "No"
                   and int(a["issue_date"][5:7]) in (2, 5, 8, 11)})


# ───────────────────────── 2) 잔액 + 연준 보유 ─────────────────────────
def fetch_mspd():
    raw = fiscal("/v1/debt/mspd/mspd_table_1",
                 f"filter=record_date:gte:{int(START[:4]) - 1}-12-01,"
                 "security_type_desc:in:(Marketable,Total%20Marketable)"
                 "&fields=record_date,security_type_desc,security_class_desc,debt_held_public_mil_amt")
    rows = {}
    for r in raw:
        v = num(r["debt_held_public_mil_amt"])
        if v is None:
            continue
        if r["security_type_desc"] == "Total Marketable":
            rows.setdefault(r["record_date"], {})["marketable_bn"] = round(v / 1e3, 3)
        elif r["security_class_desc"] in MSPD_CLASS:
            rows.setdefault(r["record_date"], {})[MSPD_CLASS[r["security_class_desc"]]] = round(v / 1e3, 3)
    print(f"  MSPD ok ({len(rows)}개월)", file=sys.stderr)
    return rows


def soma_by_class(asof):
    """기준일의 연준 보유를 종목별 자료에서 합산.
    명목 이표채를 Bonds(CUSIP 912810)와 Notes로 나눈다 → (기준일, bonds_bn, notes_bn)"""
    if not asof:
        return None, None, None
    h = json.loads(get(SOMA_URL.format(asof)))["soma"]["holdings"]
    bonds = sum(float(r["parValue"] or 0) for r in h
                if r["securityType"] == "NotesBonds" and r["cusip"].startswith("912810"))
    notes = sum(float(r["parValue"] or 0) for r in h
                if r["securityType"] == "NotesBonds" and not r["cusip"].startswith("912810"))
    return asof, round(bonds / 1e9, 3), round(notes / 1e9, 3)


def fetch_soma_monthly(month_ends):
    """월말별 연준 보유. 기준일은 NY Fed가 공개한 기준일 중 그 달 말일 이전의 마지막 날이다
    (보통 수요일, 연말에는 12-31). 이미 받아 둔 달은 supply_monthly.csv에서 재사용하고,
    기준일이 달라졌거나 최근 2개월인 달만 다시 받는다."""
    asofs = sorted(json.loads(get(SOMA_ASOF_URL))["soma"]["asOfDates"])
    target = {d: next((a for a in reversed(asofs) if a <= d), None) for d in month_ends}
    cache, path = {}, HERE / "supply_monthly.csv"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("soma_asof") and num(r.get("soma_bonds_bn")) is not None:
                    cache[r["date"]] = (r["soma_asof"], num(r["soma_bonds_bn"]), num(r["soma_notes_bn"]))
    need = [d for d in month_ends
            if cache.get(d, (None,))[0] != target[d] or d in month_ends[-2:]]
    with ThreadPoolExecutor(4) as ex:
        got = dict(zip(need, ex.map(soma_by_class, [target[d] for d in need])))
    print(f"  SOMA 종목별 ok (새로 받음 {len(need)}개월, 재사용 {len(month_ends) - len(need)}개월)",
          file=sys.stderr)
    return {d: got.get(d) or cache[d] for d in month_ends}


def build_monthly(mspd, soma, auctions):
    dates = sorted(mspd)
    gross = {}   # 'YYYY-MM' -> {tenor: 발행액}
    for a in auctions:
        g = gross.setdefault(a["issue_date"][:7], {})
        g[a["tenor"]] = round(g.get(a["tenor"], 0) + (a["accepted_bn"] or 0), 3)
    rows, prev = {}, None
    for d in dates:
        r = dict(mspd[d])
        if r.get("bills_bn") is not None and r.get("marketable_bn"):
            r["bill_share_pct"] = round(r["bills_bn"] / r["marketable_bn"] * 100, 2)
        r["soma_asof"], r["soma_bonds_bn"], r["soma_notes_bn"] = soma.get(d, (None, None, None))
        if prev:
            def chg(*keys):
                vals = [(r.get(k), prev.get(k)) for k in keys]
                if any(a is None or b is None for a, b in vals):
                    return None
                return round(sum(a - b for a, b in vals), 3)
            r["bonds_chg_bn"] = chg("bonds_bn")
            r["soma_bonds_chg_bn"] = chg("soma_bonds_bn")
            r["coupon_chg_bn"] = chg("notes_bn", "bonds_bn")
            r["soma_coupon_chg_bn"] = chg("soma_notes_bn", "soma_bonds_bn")
            for out, a, b in (("long_net_bn", "bonds_chg_bn", "soma_bonds_chg_bn"),
                              ("coupon_net_bn", "coupon_chg_bn", "soma_coupon_chg_bn")):
                if r[a] is not None and r[b] is not None:
                    r[out] = round(r[a] - r[b], 3)
        for t in TENORS:
            r[f"gross_{t.lower()}_bn"] = gross.get(d[:7], {}).get(t, 0)
        rows[d], prev = r, r
    keep = [d for d in dates if d >= START]
    return keep, {c: [rows[d].get(c) for d in keep] for c in MONTH_COLS}


# ───────────────────────── 3) 연준 보유 주별 ─────────────────────────
def fetch_fred(series, scale=1.0):
    rows = {}
    for name, fid in series:
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={START}")
        for r in csv.DictReader(io.StringIO(text)):
            v = num(r.get(fid))
            if v is not None:
                rows.setdefault(r.get("observation_date") or r.get("DATE"), {})[name] = round(v * scale, 4)
        print(f"  {fid} ok", file=sys.stderr)
    return rows


# ───────────────────────── 4) 기간 프리미엄 ─────────────────────────
def fetch_acm():
    try:
        import xlrd
    except ImportError:
        print("  xlrd 없음 → ACM 열은 비워 둠 (python3 -m pip install --user xlrd)", file=sys.stderr)
        return {}
    try:
        sh = xlrd.open_workbook(file_contents=get_bytes(ACM_URL, headers=UA_BROWSER)).sheet_by_name("ACM Daily")
        head = sh.row_values(0)
        idx = {name: head.index(col) for name, col in ACM_COLS}
        out = {}
        for i in range(1, sh.nrows):
            row = sh.row_values(i)
            d = datetime.strptime(row[0], "%d-%b-%Y").strftime("%Y-%m-%d")
            if d >= START:
                out[d] = {n: round(float(row[j]), 4) for n, j in idx.items() if row[j] != ""}
        print(f"  ACM ok ({len(out)}일)", file=sys.stderr)
        return out
    except Exception as e:
        print(f"  ACM 실패({e}) → ACM 열은 비워 둠", file=sys.stderr)
        return {}


def policy_rate():
    """정책금리 상단이 바뀐 날짜만 저장 (국면 구분용, 03_inflation과 같은 형식)."""
    text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd=2008-12-16")
    rows, prev = [], None
    for r in csv.DictReader(io.StringIO(text)):
        v = num(r.get("DFEDTARU"))
        if v is not None and v != prev:
            rows.append([r.get("observation_date") or r.get("DATE"), v])
            prev = v
    write_csv(HERE / "policy_rate.csv", ["date", "upper"], rows)
    print(f"policy            변경 {len(rows) - 1}회, 현재 상단 {rows[-1][1]}% ({rows[-1][0]}~)")


def main():
    auctions = fetch_auctions()
    refund = refunding_dates(auctions)
    mspd = fetch_mspd()
    soma = fetch_soma_monthly(sorted(mspd))
    m_dates, monthly = build_monthly(mspd, soma, auctions)

    w_rows = fetch_fred(SOMA_WEEKLY, scale=1e-3)   # 백만 달러 → 십억 달러
    w_cols = [n for n, _ in SOMA_WEEKLY]
    w_dates = sorted(w_rows)
    weekly = {c: [w_rows[d].get(c) for d in w_dates] for c in w_cols}

    tp_rows = fetch_acm()
    for d, r in fetch_fred([("kw_tp10", "THREEFYTP10")]).items():
        tp_rows.setdefault(d, {}).update(r)
    tp_cols = [n for n, _ in ACM_COLS] + ["kw_tp10"]
    tp_dates = sorted(tp_rows)
    daily = {c: [tp_rows[d].get(c) for d in tp_dates] for c in tp_cols}

    write_csv(HERE / "auctions.csv", AUC_COLS, [[a[c] for c in AUC_COLS] for a in auctions])
    write_csv(HERE / "refunding_dates.csv", ["date"], [[d] for d in refund])
    for path, dates, cols, table in ((HERE / "supply_monthly.csv", m_dates, MONTH_COLS, monthly),
                                     (HERE / "soma_weekly.csv", w_dates, w_cols, weekly),
                                     (HERE / "tp_daily.csv", tp_dates, tp_cols, daily)):
        write_csv(path, ["date"] + cols, [[d] + [table[c][i] for c in cols] for i, d in enumerate(dates)])

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "U.S. Treasury FiscalData (auctions, MSPD), NY Fed (SOMA holdings, ACM term premium), "
                  "FRED (H.4.1, Kim-Wright)",
        "series": {**{n: f for n, f in SOMA_WEEKLY}, **{n: f for n, f in ACM_COLS}, "kw_tp10": "THREEFYTP10"},
        "auctions": {c: [a[c] for a in auctions] for c in AUC_COLS},
        "refunding": refund,
        "monthly": {"dates": m_dates, **monthly},
        "weekly": {"dates": w_dates, **weekly},
        "daily": {"dates": tp_dates, **daily},
    }
    js = "window.SUPPLY_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n"
    (HERE / "data.js").write_text(js, encoding="utf-8")

    for t in TENORS:
        a = [x for x in auctions if x["tenor"] == t]
        if a:
            print(f"입찰 {t:4s}         {len(a):4d}건  {a[0]['auction_date']} ~ {a[-1]['auction_date']}"
                  f"  최근 낙찰 {a[-1]['high_yield']}%  응찰률 {a[-1]['bid_to_cover']}")
    print(f"환매 발표일        {len(refund):4d}회  {refund[0]} ~ {refund[-1]}")
    for label, dates, cols, table in (("월별", m_dates, MONTH_COLS, monthly), ("주별", w_dates, w_cols, weekly),
                                      ("일별", tp_dates, tp_cols, daily)):
        for c in cols:
            have = [d for d, v in zip(dates, table[c]) if v is not None]
            if have:
                print(f"{c:18s} {label} {len(have):5d}개  {have[0]} ~ {have[-1]}"
                      f"  최신값 {table[c][dates.index(have[-1])]}")
            else:
                print(f"{c:18s} {label}     0개  (받지 못함)")

    policy_rate()
    if "--no-analyze" not in sys.argv and (HERE / "analyze.py").exists():
        sys.dont_write_bytecode = True   # __pycache__ 폴더를 만들지 않는다
        import analyze
        analyze.main()


if __name__ == "__main__":
    main()
