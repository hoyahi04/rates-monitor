"""대시보드 시안 만들기.

1) 다섯 매크로 섹션의 signals.js에서 지표 하나씩을 뽑아 macro_indicators.js 를 만든다.
2) macro_slim.html + index_slim.html 을 합치고 자료를 안에 넣어 combined.html 을 만든다
   (다른 파일 없이 열리는 한 파일).

실행:  python3 build.py        (이 폴더에서. 표준 라이브러리만 사용)
먼저 돌릴 것: 각 섹션의 fetch_data.py, pipeline/inputs/macro/scoreboard.py
"""
import json
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MACRO = ROOT / "inputs" / "macro"
N_MONTHS, N_DAYS = 36, 750


def load_js(path):
    s = path.read_text(encoding="utf-8")
    return json.loads(s[s.index("{"): s.rindex("}") + 1])


def tail_monthly(sig, key, cur_date, cur_val):
    m = sig["monthly"]
    d, v = m["date"][-N_MONTHS:], m[key][-N_MONTHS:]
    pts = [[a, b] for a, b in zip(d, v) if b is not None]
    if cur_val is not None and cur_date > pts[-1][0]:
        pts.append([cur_date, cur_val])
    return pts


def build_indicators():
    P = load_js(MACRO / "01_policy_path" / "signals.js")
    G = load_js(MACRO / "02_growth_jobs" / "signals.js")
    I = load_js(MACRO / "03_inflation" / "signals.js")
    S = load_js(MACRO / "04_supply_tp" / "signals.js")
    L = load_js(MACRO / "05_liquidity_vol" / "signals.js")
    pd_ = P["daily"]
    pol = [[a, b] for a, b in zip(pd_["dates"][-N_DAYS:], pd_["gap"][-N_DAYS:]) if b is not None]
    g, i, s = G["current"], I["current"], S["current"]
    lm = L["current"]["mtd"]
    items = [
        dict(no=1, key="s1_policy", name="정책 경로", folder="01_policy_path",
             what="시장이 가격한 2년 평균 금리 − 연준 점도표", unit="bp", digits=0, pts=pol,
             lines=[dict(v=P["thresholds"]["gap"], label="+1"), dict(v=-P["thresholds"]["gap"], label="−1")],
             detail=f"2년 금리 {P['current']['y2']:.2f}% · 정책금리 상단 {P['current']['upper']:.2f}%"),
        dict(no=2, key="s2_growth", name="성장·고용", folder="02_growth_jobs",
             what="고용 증가의 3개월 평균 − 12개월 평균", unit="천 명", digits=0,
             pts=tail_monthly(G, "gap", g["date"], g["gap"]),
             lines=[dict(v=G["thresholds"]["nfp_gap"], label="−1"), dict(v=-G["thresholds"]["nfp_gap"], label="+1")],
             detail=f"{int(g['ref'][5:])}월 고용 +{g['nfp']:.0f}천 명 · 실업률 {g['ur']:.1f}% ({g['release'][5:]} 발표)"),
        dict(no=3, key="s3_inflation", name="인플레이션", folder="03_inflation",
             what="Core PCE 3개월 연율 − 12개월 상승률", unit="%p", digits=2,
             pts=tail_monthly(I, "gap", i["date"], i["gap"]),
             lines=[dict(v=I["thresholds"]["momentum"], label="−1"), dict(v=-I["thresholds"]["momentum"], label="+1")],
             detail=f"{int(i['pce_ref'][5:])}월 Core PCE 3개월 연율 {i['ann3']:.1f}% · 12개월 {i['yoy']:.1f}% ({i['pce_release'][5:]} 발표)"),
        dict(no=4, key="s4_supply", name="수급", folder="04_supply_tp",
             what="장기물 순공급이 빨라진 정도 ÷ 민간 보유 잔액", unit="%", digits=2,
             pts=tail_monthly(S, "pct", s["date"], s["pct"]),
             lines=[dict(v=S["thresholds"]["supply_hi"], label="+1"), dict(v=S["thresholds"]["supply_lo"], label="−1")],
             detail=f"최근 3개월 순공급 USD {s['sum3']:.0f}bn · 직전 3개월 {s['prev3']:.0f}bn ({int(s['ref'][5:])}월분)"),
        dict(no=5, key="s5_liquidity_vol", name="유동성·변동성", folder="05_liquidity_vol",
             what="채권 변동성(MOVE) 월중 최고값의 3년 백분위", unit="", digits=0, signed=False,
             pts=tail_monthly(L, "V", lm["date"], lm["V"]),
             lines=[dict(v=L["thresholds"]["stress"], label="−1"), dict(v=L["thresholds"]["calm"], label="+1 조건")],
             detail=f"MOVE {lm['move_end']:.0f} · 이번 달 최고 {lm['move_peak']:.0f} ({lm['move_peak_date'][5:]})"),
    ]
    for it in items:
        it["asof"], it["value"] = it["pts"][-1]
    out = dict(generated=datetime.now().strftime("%Y-%m-%d %H:%M"), items=items, table=build_table())
    (HERE / "macro_indicators.js").write_text(
        "window.MACRO_INDICATORS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------- 지표 표
def _shift(d, months):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    m -= months
    while m <= 0:
        m += 12; y -= 1
    return f"{y:04d}-{m:02d}-{min(day, 28):02d}"


def _at(dates, vals, target):
    """target 날짜 이하에서 값이 있는 마지막 관측."""
    for k in range(len(dates) - 1, -1, -1):
        if dates[k] <= target and vals[k] is not None:
            return k
    return None


def row(label, ko, dates, vals, unit, digits, freq, chg_unit=None, scale=1.0, star=False):
    k = _at(dates, vals, "9999")
    if k is None:
        return None
    if freq == "M":       # 월간: 직전 발표, 12개월 전 발표
        kp = next((j for j in range(k - 1, -1, -1) if vals[j] is not None), None)
        ky = _at(dates, vals, _shift(dates[k], 12))
        asof = f"{int(dates[k][5:7])}월분"
    else:                 # 일간·주간: 한 달 전, 1년 전
        kp = _at(dates, vals, _shift(dates[k], 1))
        ky = _at(dates, vals, _shift(dates[k], 12))
        asof = dates[k][5:]
    v = vals[k]
    prev = vals[kp] if kp is not None else None
    yago = vals[ky] if ky is not None else None
    return dict(label=label, ko=ko, unit=unit, digits=digits, value=v, prev=prev, yago=yago, asof=asof, date=dates[k],
                chg=None if prev is None else (v - prev) * scale, chg_unit=chg_unit or unit,
                chg_digits=0 if chg_unit == "bp" else digits, star=star)


def build_table():
    PD = load_js(MACRO / "01_policy_path" / "data.js"); PS = load_js(MACRO / "01_policy_path" / "signals.js")
    GD = load_js(MACRO / "02_growth_jobs" / "data.js")
    ID = load_js(MACRO / "03_inflation" / "data.js")
    SD = load_js(MACRO / "04_supply_tp" / "data.js")
    LD = load_js(MACRO / "05_liquidity_vol" / "data.js")
    U = load_js(ROOT / "inputs" / "curve" / "data.js")
    pd_, ps, gm, gw = PD["daily"], PS["daily"], GD["monthly"], GD["weekly"]
    im, idy, sm, sw, sdy, ld, lw = ID["monthly"], ID["daily"], SD["monthly"], SD["weekly"], SD["daily"], LD["daily"], LD["weekly"]
    groups = [
        ("s1_policy", [
            row("Federal Funds Target Range, Upper Limit", "연방기금금리 목표 범위 상단", pd_["dates"], pd_["upper"], "%", 2, "D", "bp", 100),
            row("2-Year Treasury Constant Maturity Rate", "2년 국채 금리", U["dates"], U["yields"]["2Y"], "%", 2, "D", "bp", 100),
            row("10-Year Treasury Constant Maturity Rate", "10년 국채 금리", U["dates"], U["yields"]["10Y"], "%", 2, "D", "bp", 100),
            row("FOMC SEP Median Fed Funds Projection, 2-Year Average", "점도표 중앙값의 2년 평균", ps["dates"], ps["dot2"], "%", 2, "D", "bp", 100),
            row("Market-Implied 2-Year Average Rate − SEP Median", "시장이 가격한 금리 − 점도표", ps["dates"], ps["gap"], "bp", 0, "D", star=True),
        ]),
        ("s2_growth", [
            row("Nonfarm Payrolls, Monthly Change", "비농업 고용 증감", gm["dates"], gm["payems_chg"], "천 명", 0, "M"),
            row("Nonfarm Payrolls, 3-Month Average Change", "고용 증감 3개월 평균", gm["dates"], gm["payems_chg_3m_avg"], "천 명", 0, "M"),
            row("Nonfarm Payrolls, 3-Month − 12-Month Average", "고용 증가 속도의 변화", gm["dates"], gm["payems_mom_gap"], "천 명", 0, "M", star=True),
            row("Unemployment Rate (U-3)", "실업률", gm["dates"], gm["unrate"], "%", 1, "M", "%p"),
            row("Initial Jobless Claims, 4-Week Moving Average", "신규 실업수당 청구 4주 평균", gw["dates"], gw["ic4wsa_k"], "천 건", 0, "W"),
        ]),
        ("s3_inflation", [
            row("Core CPI (All Items Less Food and Energy), YoY", "근원 소비자물가 전년 대비", im["dates"], im["core_cpi_12m"], "%", 1, "M", "%p"),
            row("Core CPI, 3-Month Annualized", "근원 소비자물가 3개월 연율", im["dates"], im["core_cpi_3m_ann"], "%", 1, "M", "%p"),
            row("Core PCE Price Index, YoY", "근원 개인소비지출 물가 전년 대비", im["dates"], im["core_pce_12m"], "%", 1, "M", "%p"),
            row("Core PCE Price Index, 3-Month Annualized", "근원 개인소비지출 물가 3개월 연율", im["dates"], im["core_pce_3m_ann"], "%", 1, "M", "%p", star=True),
            row("University of Michigan Inflation Expectations, 1-Year", "미시간대 1년 기대 인플레이션", im["dates"], im["mich_1y"], "%", 1, "M", "%p"),
            row("10-Year Breakeven Inflation Rate", "10년 기대 인플레이션 (BEI)", idy["dates"], idy["bei_10y"], "%", 2, "D", "bp", 100),
            row("5-Year, 5-Year Forward Inflation Expectation Rate", "5년 뒤 5년 기대 인플레이션", idy["dates"], idy["fwd_5y5y"], "%", 2, "D", "bp", 100),
        ]),
        ("s4_supply", [
            row("Treasury Bonds Net Supply to the Public (Issuance − SOMA)", "장기물 순공급 (발행 − 연준 매입)", sm["dates"], sm["long_net_bn"], "USD bn", 1, "M", star=True),
            row("Treasury Bills Share of Marketable Debt", "시장성 국채 중 단기물 비중", sm["dates"], sm["bill_share_pct"], "%", 1, "M", "%p"),
            row("Federal Reserve SOMA Treasury Holdings", "연준 보유 국채", sw["dates"], sw["soma_total_bn"], "USD bn", 0, "W"),
            row("ACM 10-Year Treasury Term Premium", "10년 기간 프리미엄 (뉴욕연준 ACM)", sdy["dates"], sdy["acm_tp10"], "%", 2, "D", "bp", 100),
        ]),
        ("s5_liquidity_vol", [
            row("ICE BofA MOVE Index", "채권 변동성 지수", ld["dates"], ld["move"], "", 0, "D", star=True),
            row("CBOE Volatility Index (VIX)", "주식 변동성 지수", ld["dates"], ld["vix"], "", 1, "D"),
            row("ICE BofA US High Yield Index Option-Adjusted Spread", "하이일드 회사채 스프레드", ld["dates"], ld["hy_oas"], "%", 2, "D", "bp", 100),
            row("Moody's Baa Corporate Bond Yield − 10-Year Treasury", "Baa 회사채 스프레드", ld["dates"], ld["baa_spread"], "%", 2, "D", "bp", 100),
            row("SOFR − Interest Rate on Reserve Balances (IORB)", "SOFR − 지준 금리", ld["dates"], ld["sofr_minus_rr_bp"], "bp", 0, "D"),
            row("Reserve Balances with Federal Reserve Banks", "지급준비금", lw["dates"], lw["reserves_bn"], "USD bn", 0, "W"),
        ]),
    ]
    return [dict(key=k, rows=[r for r in rows if r]) for k, rows in groups]


def one(s, a, b):
    assert s.count(a) == 1, f"찾는 글이 {s.count(a)}번 나옴: {a[:60]}"
    return s.replace(a, b)


def build_combined():
    mac = (HERE / "macro_slim.html").read_text(encoding="utf-8")
    por = (HERE / "index_slim.html").read_text(encoding="utf-8")

    def script(s):
        i = s.index('<script>\n"use strict";')
        return s[i: s.index("</script>", i) + 9]

    head = one(mac[: mac.index("<body")], "<title>매크로 · 간결한 시안</title>", "<title>Rates Monitor · 시안</title>")
    ms, ps = script(mac), script(por)
    ms = one(ms, "document.getElementById('app')", "document.getElementById('app-macro')")
    ms = one(ms, '<a aria-current="page">매크로</a><a href="index_slim.html">운용</a>',
             '<a href="#macro" aria-current="page">매크로</a><a href="#port">운용</a>')
    ps = one(ps, "document.getElementById('app')", "document.getElementById('app-port')")
    ps = one(ps, '<a href="macro_slim.html">매크로</a><a aria-current="page">운용</a>',
             '<a href="#macro">매크로</a><a href="#port" aria-current="page">운용</a>')
    ps = one(ps, "draw(); let lw=innerWidth,t; addEventListener('resize',()=>{if(innerWidth===lw)return;lw=innerWidth;clearTimeout(t);t=setTimeout(draw,120);});",
             "let lw=0,t; const vis=()=>!app.hidden; window.__drawPort=()=>{if(vis()){lw=innerWidth;draw();}}; addEventListener('resize',()=>{if(!vis()||innerWidth===lw)return;clearTimeout(t);t=setTimeout(window.__drawPort,120);});")
    router = """<script>
(function(){const a=document.getElementById('app-macro'),b=document.getElementById('app-port');
function show(){const port=location.hash==='#port';a.hidden=port;b.hidden=!port;if(port&&window.__drawPort)window.__drawPort();if(!port&&window.__drawMacro)window.__drawMacro();if(window.__anim)window.__anim(port?b:a);scrollTo(0,0);}
addEventListener('hashchange',show);show();})();
</script>"""
    data = ""
    for p in (HERE / "anim.js", MACRO / "scoreboard.js", HERE / "macro_indicators.js", HERE / "portfolio.js"):
        d = p.read_text(encoding="utf-8")
        assert "</script" not in d.lower()
        data += "<script>\n" + d + "\n</script>\n"
    page = (head + '<body class="deck">\n<div class="in" id="app-macro"></div>\n<div class="in" id="app-port" hidden></div>\n'
            + data + ms + "\n" + ps + "\n" + router + "\n</body>\n</html>\n")
    (HERE / "combined.html").write_text(page, encoding="utf-8")
    return len(page.encode("utf-8"))


if __name__ == "__main__":
    ind = build_indicators()
    for it in ind["items"]:
        print(f"  {it['no']}. {it['name']}: {it['value']} {it['unit']} ({it['asof']}, {len(it['pts'])}점)")
    for g in ind["table"]:
        print(f"  표 {g['key']}: {len(g['rows'])}줄")
    print(f"combined.html {build_combined() / 1024:.0f} KB")
