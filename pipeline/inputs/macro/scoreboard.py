"""매크로 통합 점수표: 신호 5개 → 커브 뷰 3개 → 포지션 4개  →  scoreboard.csv + scoreboard.js

다섯 섹션 폴더에서 팀 점수만 읽어 합친다. 섹션별 계산은 건드리지 않는다.
   적용 중인 줄 (월말 판정)     각 폴더 signals_monthly.csv 의 점수 열
   잠정 줄 (기준일 현재 값)     각 폴더 signals.js 의 current. 월말에 확정되기 전까지는 참고용이다.

1단계  신호 점수 (−1 / 0 / +1, 매월 마지막 거래일 판정 → 다음 달 적용)
   1 정책 경로      score_policy         +1 = 시장이 연준보다 높게 가격      (금리 하락 쪽)
   2 성장·고용      score_growth         +1 = 둔화                          (금리 하락 쪽)
   3 인플레이션     score_momentum       +1 = 물가 둔화                      (금리 하락 쪽)
   4 수급           score_supply         +1 = 장기물 공급 가속               (스티프닝 쪽)
   5 유동성·변동성  score_liquidity_vol  +1 = 셋 다 안정, −1 = 스트레스
2단계  커브 뷰      ← compose() 하나가 월별 줄·적용 중인 줄·잠정 줄을 모두 만든다
   수준   = 1번 + 2번 + 3번                      (−3 ~ +3, 양수 = 듀레이션 길게 쪽)
   기울기 = 1번 + 4번                            (−2 ~ +2, 양수 = 스티프너 쪽)
   곡률   = 5번이 +1 이고 Fly z-score ≥ +1       (충족 1 / 미충족 0)
3단계  포지션
   Duration         수준 +2 이상 / +1 / 0 → 액티브 듀레이션 +0.5년 / +0.25년 / 0 (음수는 반대)
   Curve Slope      기울기 +2 → 스티프너(1–3y 확대·20y+ 축소), −2 → 플래트너(반대), DV01 중립
   Curve Curvature  곡률 충족 → 불릿(5–7y 확대, 1–3y·10–20y 축소), DV01 중립
   Carry & Rolldown 항상 (버킷 안에서 carry+roll 상위 종목)
   브레이크         5번이 −1 → 모든 액티브 포지션 절반   ← 5번 섹션의 제안(미채택). 열로만 남기고 포지션에는 적용하지 않는다

Fly = 2 × 5년 − 2년 − 10년 (bp, 재무부 CMT). z-score는 판정일까지의 직전 FLY_LOOKBACK_M개월 일별 값 기준.
룩백은 3년을 쓰고 1년 값도 함께 적어 둔다.
적중 기준: 수준·Duration → 다음 달 10년 금리, 기울기 → 다음 달 2s10s, 곡률 → 다음 달 Fly.

실행: python3 scoreboard.py     (섹션 점수를 새로 받으려면 먼저 각 폴더에서 python3 fetch_data.py → python3 analyze.py)
고정: python3 scoreboard.py --freeze 2026-12 --asof 2026-11-30 [--dry-run] [--note "메모"] [--early]
      잠정 줄을 그 달의 판정으로 decisions.csv 에 한 줄 덧붙인다. --dry-run 은 줄만 보여 주고 아무 파일도 쓰지 않는다.
      기준일이 그 달의 마지막 평일이 아니면 고정하지 않는다. 그 달 줄은 한 번만 쓸 수 있어서, 미리 고정하면 월말 판정을 못 쓰기 때문이다.
      월말이 미국 휴장일이라 마지막 거래일이 더 이른 달에는 --early 를 붙인다.

입력이 빠졌거나 섹션끼리 맞지 않으면 scoreboard.js 를 status "error" 로 덮어쓰고 끝낸다(옛 파일이 멀쩡해 보이지 않게).
수익률 파일에 판정일의 금리가 없을 때도 마찬가지다(그 전날 값으로 Fly 를 대신 계산하지 않는다).
"""
import argparse, bisect, codecs, csv, json, math, re, sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parent / "curve" / "data.js"       # 일별 CMT 금리(공통 데이터)
DECISIONS = HERE / "decisions.csv"                         # --freeze 로 고정한 월말 판정 기록

# ----- 규칙 상수: 여기 한 곳에서만 정한다. scoreboard.js 의 rules 로 그대로 나간다 -----
VIEWS = {"level": ["s1_policy", "s2_growth", "s3_inflation"],     # 수준 = 정책 + 성장 + 물가
         "slope": ["s1_policy", "s4_supply"]}                      # 기울기 = 정책 + 수급
SLOPE_TRIGGER = 2        # 기울기 뷰가 ±2일 때만 Slope 포지션
GATE, GATE_SCORE = "s5_liquidity_vol", 1                           # 곡률 조건 1: 5번 점수가 +1
FLY_LOOKBACK_M = 36      # Fly z-score 룩백(개월). 3년을 쓰고 1년 값은 참고로 함께 적는다
FLY_Z_TH = 1.0           # 곡률 조건 2: Fly z-score ≥ +1
DUR_STEP = 0.25          # 년. 수준 뷰 1점에 0.25년
DUR_CAP = 2              # 수준 뷰 ±2점(±0.5년)까지만 Duration 에 반영한다
BRAKE_ADOPTED = False    # 브레이크(5번이 −1이면 포지션 절반)는 제안일 뿐 채택되지 않았다
YARDSTICK = {"level": "next_d10y_bp", "slope": "next_d2s10s_bp", "curvature": "next_dfly_bp"}   # 뷰마다 적중을 재는 결과 열
WANT = {"level": -1, "slope": 1, "curvature": -1}                  # 뷰(점수)가 +일 때 적중이 되는 결과의 부호: 10년 하락 / 2s10s 확대 / Fly 하락
YARD_KO = {"next_d10y_bp": "다음 달 10년 금리", "next_d2s10s_bp": "다음 달 2s10s", "next_dfly_bp": "다음 달 Fly"}
MOVE_KO = {"next_d10y_bp": {1: "10년 금리 상승", -1: "10년 금리 하락"},      # 결과가 움직인 방향을 부르는 말 (적중이 어느 쪽이었는지 적을 때)
           "next_d2s10s_bp": {1: "2s10s 확대", -1: "2s10s 축소"},
           "next_dfly_bp": {1: "Fly 상승", -1: "Fly 하락"}}
SIDE_KO = {"duration": {1: ("long", "길게"), -1: ("short", "짧게")},           # 포지션의 방향: 부호 → (키, 말)
           "slope": {1: ("steepener", "스티프너"), -1: ("flattener", "플래트너")},
           "curvature": {1: ("bullet", "불릿")}}
BT_START, TEST_START = "2015-01", "2021-01"
PAPER_START = "2026-12"  # 실시간 모의운용을 시작하는 적용월. 그 전 기록은 모두 백테스트다


def sym(x):
    """±x 로 쓰는 문턱"""
    return [x, -x]


def release_note(ref, asof):
    """월간 발표 자료가 월말 전에 더 나올 수 있는가. 어느 달 치든 그 달이 끝난 뒤에야 나오므로,
    직전 달 치가 이미 들어 있으면 이번 달 말까지 새 발표는 없다."""
    if ref >= months_ago(asof[:7] + "-01", 1)[:7]:
        return "월말까지 새 발표 없음"
    return f"월말 전에 {int(next_month(ref)[5:7])}월분이 나오면 바뀜"


# ----- 다섯 섹션 표: 섹션 파일에서 무엇을 어디서 읽는지는 이 표에만 적는다 -----
#   score_col   signals_monthly.csv 의 팀 점수 열 (월말 판정)
#   live        signals.js 에서 기준일 현재 값이 들어 있는 자리, live_score = 그 안의 점수 키
#   words       점수 +1 / 0 / −1 을 읽는 말
#   values      점수 뒤의 측정값. 한 조각 = (이름, csv 열, live 키, 나누는 수, 소수 자리, 단위, 부호를 붙일지, 이 값이 넘나드는 문턱들)
#   th          문턱 문장. 숫자는 그 섹션 signals.js 의 thresholds 에서만 가져온다(여기에 다시 적지 않는다)
#   vintage     잠정 값이 기대는 입력이 언제 것인지 (live 자리의 키로 만든다)
#   pending     그 입력이 월말 전에 더 바뀔 수 있는지 (live 자리, 기준일 → 문장)
#   th_origin   문턱을 자료에서 뽑은 섹션만: 어떤 자료로 정했는지 (나머지 섹션의 문턱은 백테스트 전에 정한 상수다)
SECTIONS = [
    dict(no=1, key="s1_policy", folder="01_policy_path", name="정책 경로", short="정책",
         score_col="score_policy", live=("current",), live_score="s1",
         words={1: "시장 > 점도표", 0: "시장 ≈ 점도표", -1: "시장 < 점도표"},
         values=[("경로 괴리", "path_gap_bp", "gap", 1, 0, "bp", True, lambda T: sym(T["gap"]))],
         th=lambda T: f"문턱 ±{T['gap']:g}bp",
         vintage=lambda c: f"SEP {c['sep'][5:]}",
         pending=lambda c, asof: "시장 금리에 따라 매일 바뀜"),
    dict(no=2, key="s2_growth", folder="02_growth_jobs", name="성장·고용", short="성장",
         score_col="score_growth", live=("current",), live_score="s",
         words={1: "둔화", 0: "중립", -1: "가속"},
         values=[("NFP 격차", "nfp_gap_k", "gap", 10, 1, "만 명", True, lambda T: sym(T["nfp_gap"])),            # 천 명 → 만 명
                 ("실업률 변화", "unrate_3m_avg_chg3", "ur_chg", 1, 2, "%p", True, lambda T: sym(T["ur_chg"]))],
         th=lambda T: f"투표 2개 합산 · NFP 격차 ±{T['nfp_gap'] / 10:g}만 명 · 실업률 변화 ±{T['ur_chg']:g}%p",
         vintage=lambda c: f"고용보고서 {int(c['ref'][5:7])}월분 · {c['release'][5:]} 발표",
         pending=lambda c, asof: release_note(c["ref"], asof)),
    dict(no=3, key="s3_inflation", folder="03_inflation", name="인플레이션", short="물가",
         score_col="score_momentum", live=("current",), live_score="s1",
         words={1: "물가 둔화", 0: "중립", -1: "물가 가속"},
         values=[("Core PCE 3개월−12개월", "momentum_gap", "gap", 1, 2, "%p", True, lambda T: sym(T["momentum"]))],
         th=lambda T: f"문턱 ±{T['momentum']:g}%p",
         vintage=lambda c: f"Core PCE {int(c['pce_ref'][5:7])}월분 · {c['pce_release'][5:]} 발표",
         pending=lambda c, asof: release_note(c["pce_ref"], asof)),
    dict(no=4, key="s4_supply", folder="04_supply_tp", name="수급", short="수급",
         score_col="score_supply", live=("current",), live_score="s1",
         words={1: "공급 가속", 0: "중립", -1: "공급 감속"},
         values=[("장기물 순공급 가속", "supply_accel_pct", "pct", 1, 2, "%", True, lambda T: [T["supply_lo"], T["supply_hi"]])],
         th=lambda T: f"문턱 {signed_g(T['supply_lo'])}% / {signed_g(T['supply_hi'])}%",
         vintage=lambda c: f"MSPD {int(c['ref'][5:7])}월분",
         pending=lambda c, asof: release_note(c["ref"], asof),
         th_origin=f"{BT_START[:4]}~{int(TEST_START[:4]) - 1}년 자료의 3분위"),      # 04_supply_tp/analyze.py: 설정 구간 신호 분포의 1/3 · 2/3 분위
    dict(no=5, key="s5_liquidity_vol", folder="05_liquidity_vol", name="유동성·변동성", short="변동성",
         score_col="score_liquidity_vol", live=("current", "mtd"), live_score="score",
         words={1: "안정", 0: "중립", -1: "스트레스"},
         values=[("변동성 백분위", "vol_pct", "V", 1, 0, "", False, lambda T: [T["calm"], T["stress"]])],
         th=lambda T: f"안정 = 변동성·심리 {T['calm']:g} 미만 + 자금 경보 꺼짐 · 스트레스 = 변동성 {T['stress']:g} 초과",
         vintage=lambda c: f"MOVE {c['date'][5:]}까지",
         pending=lambda c, asof: "월중 최고값 기준 · 최고값은 월말까지 오를 수만 있음"),
]
for _s in SECTIONS:      # 어느 뷰에 쓰이는지와 역할은 위 규칙 상수에서 나온다 (두 번 적지 않는다)
    _s["feeds"] = [v for v, keys in VIEWS.items() if _s["key"] in keys] + (["curvature"] if _s["key"] == GATE else [])
    _s["role"] = "gate" if _s["key"] == GATE else "addend"        # addend = 더해지는 점수, gate = 조건으로만 쓰는 점수
KEYS = [s["key"] for s in SECTIONS]
NAME = {s["key"]: s["name"] for s in SECTIONS}
SHORT = {s["key"]: s["short"] for s in SECTIONS}

OBS = {  # 규칙표 페이지(scoreboard_rules.html)의 '적용 예시'에 쓰는 관측값: 이름 → (섹션, csv 열)
    "path_gap_bp": ("s1_policy", "path_gap_bp"),
    "nfp_gap_k": ("s2_growth", "nfp_gap_k"), "vote_nfp": ("s2_growth", "vote_nfp"),
    "unrate_chg": ("s2_growth", "unrate_3m_avg_chg3"), "vote_unrate": ("s2_growth", "vote_unrate"),
    "momentum_gap": ("s3_inflation", "momentum_gap"),
    "supply_accel_pct": ("s4_supply", "supply_accel_pct"),
    "vol_pct": ("s5_liquidity_vol", "vol_pct"), "risk_pct": ("s5_liquidity_vol", "risk_pct"),
    "funding_alarm": ("s5_liquidity_vol", "funding_alarm"), "funding_bp": ("s5_liquidity_vol", "funding_20d_bp"),
}
SHARED = {  # 적용월·국면·다음 달 결과를 가져오는 섹션 파일
    "s1_policy": ["apply_month", "regime", "next_d10y_bp", "next_d2s10s_bp"],
    "s5_liquidity_vol": ["next_dfly_bp", "next_rv10y_bp_ann"],
}
DETAIL = ("level", "slope", "curvature")      # compose() 가 함께 돌려주는 뷰 내역. csv 와 monthly 에는 넣지 않는다
FREEZE_COLS = (["frozen_at", "apply_month", "asof"] + KEYS + [k + "_value_ko" for k in KEYS]
               + ["view_level", "view_slope", "curvature_met", "fly_bp", "fly_z_3y",
                  "duration_active_yr", "slope_position", "curvature_position", "note"])


class Stop(Exception):
    """미리 알 수 있는 실패(파일·열·점수 없음, 섹션끼리 판정일 다름). 한글 문장 목록을 들고 있다."""

    def __init__(self, problems):
        self.problems = [problems] if isinstance(problems, str) else list(problems)
        super().__init__(" / ".join(self.problems))


def num(s):
    """숫자로 읽는다. 빈칸 · 글자 · nan · inf 는 None."""
    try:
        x = float(s)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    last = [31, 29 if (y2 % 4 == 0 and (y2 % 100 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(day, last):02d}"


def next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def last_weekday(ym):
    """그 달의 마지막 평일(월~금). 미국 휴일은 따지지 않는다: 월말이 휴장이면 하루 어긋난다."""
    y, m = int(ym[:4]), int(ym[5:7])
    d = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def read_js(path):
    """'window.이름 = {...};' 한 줄짜리 파일 → (이름, 내용)"""
    t = path.read_text(encoding="utf-8")
    return t[:t.index("=")].replace("window.", "").strip(), json.loads(t[t.index("{"):t.rindex("}") + 1])


def load_fly():
    """일별 2s5s10s Fly (bp)"""
    try:
        _, d = read_js(CURVE_JS)
        dates, fly = [], []
        for i, day in enumerate(d["dates"]):
            y2, y5, y10 = (d["yields"][k][i] for k in ("2Y", "5Y", "10Y"))
            if None not in (y2, y5, y10):
                dates.append(day)
                fly.append((2 * y5 - y2 - y10) * 100)
    except OSError:
        raise Stop("수익률 파일(pipeline/inputs/curve/data.js)이 없습니다. 'pipeline/inputs/curve' 폴더에서 python3 fetch_data.py를 실행하세요.")
        if not dates:
            raise ValueError("no rows")
    except (ValueError, KeyError, IndexError, TypeError):
        raise Stop("수익률 파일(pipeline/inputs/curve/data.js)을 읽을 수 없습니다. 'pipeline/inputs/curve' 폴더에서 python3 fetch_data.py를 다시 실행하세요.")
    return dates, fly


_fly = None


def fly_series():
    """Fly 일별 값은 한 번만 읽어 둔다."""
    global _fly
    if _fly is None:
        _fly = load_fly()
    return _fly


def zscore(dates, vals, d, months):
    """d 날의 값이 직전 months개월(그 값 포함) 분포에서 몇 표준편차인가.
    d 날의 값이 없으면 (None, None): 그 전날 값으로 대신하지 않는다."""
    b = bisect.bisect_right(dates, d)
    if b == 0 or dates[b - 1] != d:
        return None, None
    a = bisect.bisect_right(dates, months_ago(d, months))
    w = vals[a:b]
    if len(w) < 60:
        return None, None
    mu = sum(w) / len(w)
    sd = math.sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
    return w[-1], ((w[-1] - mu) / sd if sd else None)


def duration_rule(level):
    return max(-DUR_CAP, min(DUR_CAP, level)) * DUR_STEP


def sg(x, d=2):
    """옛 열(position_ko)과 옛 콘솔 줄에 쓰는 표기. 음수 기호가 '-' 라서 새 문장에는 signed() 를 쓴다."""
    return "0" if not x else f"{x:+.{d}f}".rstrip("0").rstrip(".")


def signed(x, d=0):
    """화면에 내보내는 부호 붙은 숫자: +37 / −0.22 / 0  (음수 기호는 U+2212)"""
    if x is None:
        return "–"
    t = f"{abs(x):.{d}f}"
    return ("" if float(t) == 0 else "+" if x > 0 else "−") + t


def signed_g(x):
    """부호 붙은 숫자를 읽은 자릿수 그대로: −0.09 / +0.56 / +25"""
    return ("" if not x else "+" if x > 0 else "−") + f"{abs(x):g}"


def places(x, dec, ths):
    """몇 자리까지 적을지. 반올림한 값이 문턱과 같아 보이는데 실제로는 다르면 한 자리씩 더 적는다
    (−0.296 이 문턱 ±0.3 옆에서 −0.30 으로 보이지 않게)."""
    while dec < 6 and any(x != t and f"{x:.{dec}f}" == f"{t:.{dec}f}" for t in ths):
        dec += 1
    return dec


def show(key, v):
    """한 칸을 말로: 점수·뷰는 +1 / −1, 포지션은 이름으로."""
    if key == "duration_active_yr":
        return (signed(v, 2).rstrip("0").rstrip(".") + "년") if v else "중립"
    if key == "slope_position":
        return {"steepener": "스티프너", "flattener": "플래트너", "none": "없음"}[v]
    if key == "curvature_position":
        return {"bullet": "불릿", "none": "없음"}[v]
    if key == "view_curvature":
        return "충족" if v else "미충족"
    return signed(v)


def view_state(parts):
    """더한 점수들이 같은 쪽인가: aligned 같은 쪽 / conflict 부호가 엇갈림(상충) / no_signal 모두 0"""
    pos = any(p["score"] > 0 for p in parts)
    neg = any(p["score"] < 0 for p in parts)
    return "conflict" if pos and neg else "aligned" if pos or neg else "no_signal"


def compose(scores, decision_date, apply_month):
    """점수 5개 → 커브 뷰 3개 → 포지션 4개. 규칙은 이 함수 한 곳에만 있다.
    scores = {"s1_policy": 1, ...}. 월별 줄, 적용 중인 줄, 잠정 줄이 모두 이 함수를 쓴다."""
    fdates, fly = fly_series()
    # ----- 2단계: 커브 뷰 -----
    parts = {v: [{"key": k, "name": SHORT[k], "score": scores[k]} for k in keys] for v, keys in VIEWS.items()}
    level = sum(p["score"] for p in parts["level"])
    slope = sum(p["score"] for p in parts["slope"])
    fv, z = zscore(fdates, fly, decision_date, FLY_LOOKBACK_M)
    _, z1 = zscore(fdates, fly, decision_date, 12)
    gate_met = scores[GATE] == GATE_SCORE
    z_met = z is not None and z >= FLY_Z_TH
    curv = int(gate_met and z_met)
    # ----- 3단계: 포지션 -----
    dur = duration_rule(level)
    slope_pos = "steepener" if slope >= SLOPE_TRIGGER else "flattener" if slope <= -SLOPE_TRIGGER else "none"
    brake = int(scores[GATE] == -1)           # 제안(미채택): 아래 세 열로만 남긴다
    mult = 0.5 if brake else 1.0
    text = [f"Duration {sg(dur)}년" if dur else "Duration 중립",
            {"steepener": "Slope 스티프너", "flattener": "Slope 플래트너", "none": "Slope 없음"}[slope_pos],
            "Curvature 불릿" if curv else "Curvature 없음", "Carry 유지"]
    if brake:
        text.append("브레이크: 포지션 절반")
    fly_bp = None if fv is None else round(fv, 1)
    z_3y, z_1y = (None if x is None else round(x, 2) for x in (z, z1))
    z_ko = [None if x is None else signed(x, places(x, 2, [FLY_Z_TH])) for x in (z, z1)]      # 문턱 바로 밑이면 +1.00 이 아니라 +0.996
    return {
        "decision_date": decision_date, "apply_month": apply_month, **{k: scores[k] for k in KEYS},
        "view_level": level, "view_slope": slope,
        "fly_2s5s10s_bp": fly_bp, "fly_z_3y": z_3y, "fly_z_1y": z_1y,
        "view_curvature": curv,
        "duration_active_yr": dur, "slope_position": slope_pos, "curvature_position": "bullet" if curv else "none",
        "carry_rolldown": "on", "brake": brake, "size_multiplier": mult,
        "duration_active_yr_with_brake": dur * mult,
        "position_ko": " · ".join(text),      # 옛 열. 브레이크 문구가 섞여 있어 화면에는 쓰지 않는다
        # 뷰가 어떻게 나왔는지 (DETAIL)
        "level": {"value": level, "state": view_state(parts["level"]), "parts": parts["level"]},
        "slope": {"value": slope, "state": view_state(parts["slope"]), "parts": parts["slope"]},
        "curvature": {"met": bool(curv), "gate_score": scores[GATE], "gate_met": gate_met,
                      "fly_bp": fly_bp, "z_3y": z_3y, "z_1y": z_1y, "z_met": z_met, "z_3y_ko": z_ko[0], "z_1y_ko": z_ko[1]},
    }


# ---------------------------------------------------------------- 읽기
def check_rows(rows, with_apply):
    """월말 표의 줄이 제 꼴인가 → 문제 문장 (없으면 ""). 판정일은 날짜이고 한 번씩만, 적용월은 판정일의 다음 달."""
    seen, n_bad, first = set(), 0, ""
    for r in rows:
        d, why = r["decision_date"], ""
        try:
            date.fromisoformat(d or "")
            if len(d) != 10:
                raise ValueError(d)
        except (TypeError, ValueError):
            why = f"판정일 '{d}'이(가) 날짜 꼴(YYYY-MM-DD)이 아닙니다"
        else:
            if d in seen:
                why = f"판정일 {d}이(가) 두 번 있습니다"
            elif with_apply and r["apply_month"] != next_month(d[:7]):
                why = f"{d} 줄의 apply_month '{r['apply_month']}'이(가) 판정일의 다음 달({next_month(d[:7])})이 아닙니다"
        seen.add(d)
        if why:
            n_bad += 1
            first = first or why
    return first + (f" (이런 줄이 모두 {n_bad}개)." if n_bad > 1 else "." if first else "")


def read_sections():
    """다섯 폴더의 월말 표(signals_monthly.csv)와 기준일 현재 값(signals.js)을 읽는다.
    문제가 있으면 모두 모아서 Stop 으로 알린다."""
    tables, js, bad = {}, {}, []
    for s in SECTIONS:
        key, folder = s["key"], s["folder"]
        need = (["decision_date", s["score_col"]] + [v[1] for v in s["values"]]
                + [c for k, c in OBS.values() if k == key] + SHARED.get(key, []))
        try:
            with open(HERE / folder / "signals_monthly.csv", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows, have = list(reader), reader.fieldnames or []
            lack = [c for c in dict.fromkeys(need) if c not in have]
            if lack:
                bad.append(f"{folder}/signals_monthly.csv에 {', '.join(lack)} 열이 없습니다.")
            elif not rows:
                bad.append(f"{folder}/signals_monthly.csv에 줄이 없습니다.")
            else:
                wrong = check_rows(rows, "apply_month" in need)
                if wrong:
                    bad.append(f"{folder}/signals_monthly.csv: {wrong} 그 폴더에서 python3 analyze.py를 다시 실행하세요.")
                else:
                    tables[key] = {r["decision_date"]: r for r in rows}
        except OSError:
            bad.append(f"{folder}/signals_monthly.csv 파일이 없습니다. 그 폴더에서 python3 analyze.py를 실행하세요.")
        except (ValueError, csv.Error):         # UTF-8 이 아니거나(엑셀에서 다시 저장) 깨진 파일
            bad.append(f"{folder}/signals_monthly.csv를 읽을 수 없습니다 (UTF-8이 아니거나 깨진 파일). 그 폴더에서 python3 analyze.py를 다시 실행하세요.")
        try:
            glob, S = read_js(HERE / folder / "signals.js")
            date.fromisoformat(S["asof"])
            js[key] = {"global": glob, "asof": S["asof"], "generated": S["generated"],
                       "thresholds": S["thresholds"], "th_ko": s["th"](S["thresholds"]), "all": S}
        except OSError:
            bad.append(f"{folder}/signals.js 파일이 없습니다. 그 폴더에서 python3 analyze.py를 실행하세요.")
        except (ValueError, KeyError, TypeError):
            bad.append(f"{folder}/signals.js에서 asof · generated · thresholds를 읽을 수 없습니다. 그 폴더에서 python3 analyze.py를 다시 실행하세요.")
    if not bad and len({tuple(sorted(t)) for t in tables.values()}) > 1:
        each = " · ".join(f"{s['folder'][:2]} {len(tables[s['key']])}개(~{max(tables[s['key']])})" for s in SECTIONS)
        bad.append(f"섹션마다 판정일이 다릅니다 ({each}). 각 폴더에서 python3 fetch_data.py → python3 analyze.py를 다시 실행하세요.")
    if bad:
        raise Stop(bad)
    return tables, js


def monthly_rows(tables):
    """판정일마다 한 줄: 섹션 점수 5개를 compose() 에 넣고, 국면과 다음 달 결과를 붙인다."""
    bad = []
    dates = sorted(tables[KEYS[0]])
    fdates, _ = fly_series()
    have = set(fdates)
    late = [d for d in dates if d > fdates[-1]]            # 수익률 파일이 이 판정일까지 오지 않았다
    hole = [d for d in dates if d <= fdates[-1] and d not in have]
    if late:
        bad.append(f"수익률 파일(pipeline/inputs/curve/data.js)이 {fdates[-1]}까지라 {late[0]} 판정({tables[KEYS[0]][late[0]]['apply_month']} 적용분)의 Fly를 "
                   "계산할 수 없습니다. 'pipeline/inputs/curve' 폴더에서 python3 fetch_data.py를 실행한 뒤 다시 실행하세요.")
    if hole:
        bad.append(f"수익률 파일(pipeline/inputs/curve/data.js)에 판정일 {hole[0]}의 2년 · 5년 · 10년 금리가 없습니다"
                   + (f" (이런 판정일이 모두 {len(hole)}개)" if len(hole) > 1 else "")
                   + ". 'pipeline/inputs/curve' 폴더에서 python3 fetch_data.py를 다시 실행하세요.")
    for s in SECTIONS:
        blank = [d for d in dates if num(tables[s["key"]][d][s["score_col"]]) not in (-1, 0, 1)]
        if blank:
            bad.append(f"{s['folder']} {blank[0]}: {s['score_col']} 값이 비어 있거나 −1 / 0 / +1이 아닙니다"
                       + (f" (모두 {len(blank)}개 달)." if len(blank) > 1 else "."))
    if bad:
        raise Stop(bad)
    rows = []
    for d in dates:
        scores = {s["key"]: int(num(tables[s["key"]][d][s["score_col"]])) for s in SECTIONS}
        p, l5 = tables["s1_policy"][d], tables["s5_liquidity_vol"][d]
        row = compose(scores, d, p["apply_month"])
        row.update(regime=p["regime"],
                   next_d10y_bp=num(p["next_d10y_bp"]), next_d2s10s_bp=num(p["next_d2s10s_bp"]),
                   next_dfly_bp=num(l5["next_dfly_bp"]), next_rv10y_bp_ann=num(l5["next_rv10y_bp_ann"]))
        rows.append(row)
    return rows


POS_VIEW = {"duration": "level", "slope": "slope", "curvature": "curvature"}      # 포지션 → 그 포지션을 정하는 뷰


def side(pos, r):
    """그 달 포지션의 방향: +1 / −1 / 0(없음)"""
    if pos == "duration":
        return (r["duration_active_yr"] > 0) - (r["duration_active_yr"] < 0)
    if pos == "slope":
        return {"steepener": 1, "flattener": -1, "none": 0}[r["slope_position"]]
    return r["view_curvature"]


def rule_stats(rows):
    """포지션별 빈도와 다음 달 결과 (참고용 요약). 성과월 BT_START 부터, 결과가 나온 달만."""
    done = [r for r in rows if r["next_d10y_bp"] is not None and r["apply_month"] >= BT_START]
    if not done:
        raise Stop(f"성과월 {BT_START} 이후에 다음 달 결과가 있는 줄이 없습니다.")

    def stat(sel, key, want):
        """sel(r): 포지션 방향(+1/−1/0). want: 포지션 +1일 때 벌려면 key가 움직여야 하는 부호."""
        out = {}
        for name, sub in (("all", done), ("train", [r for r in done if r["apply_month"] < TEST_START]),
                          ("test", [r for r in done if r["apply_month"] >= TEST_START])):
            on = [(sel(r), r[key]) for r in sub if sel(r) and r[key] is not None]
            hits = sum(1 for s_, x in on if s_ * want * x > 0)
            pnl = [s_ * want * x for s_, x in on]
            out[name] = {"months": len(sub), "on": len(on), "hits": hits,
                         "hit": round(hits / len(on) * 100) if on else None,
                         "mean_bp": round(sum(pnl) / len(pnl), 1) if pnl else None}
        return out

    # 롱 듀레이션 → 10년 금리 하락이면 적중 / 스티프너 → 2s10s 확대면 적중 / 불릿 → Fly 하락이면 적중
    summary = {pos: stat(lambda r, pos=pos: side(pos, r), YARDSTICK[view], WANT[view]) for pos, view in POS_VIEW.items()}
    freq = {
        "duration": {str(k): sum(1 for r in done if r["duration_active_yr"] == k) for k in (-0.5, -0.25, 0.0, 0.25, 0.5)},
        "slope": {k: sum(1 for r in done if r["slope_position"] == k) for k in ("steepener", "none", "flattener")},
        "curvature": sum(r["view_curvature"] for r in done),
        "curvature_if_1y": sum(1 for r in done if r["s5_liquidity_vol"] == 1 and r["fly_z_1y"] is not None and r["fly_z_1y"] >= FLY_Z_TH),
        "brake": sum(r["brake"] for r in done), "months": len(done),
    }
    return done, summary, freq


# ---------------------------------------------------------------- 섹션 카드·잠정 줄·기록
def value_text(s, get, T):
    """측정값을 '경로 괴리 +37bp' 꼴로 적는다. get(조각) → 숫자, T = 그 섹션의 thresholds.
    반올림 때문에 문턱과 같아 보이면 자리를 더 적는다 (places)."""
    out = []
    for piece in s["values"]:
        label, _, _, div, dec, unit, with_sign, ths = piece
        x = get(piece)
        if x is None:
            out.append(f"{label} –")
            continue
        x = x / div
        dec = places(x, dec, [t / div for t in ths(T)])
        out.append(f"{label} " + (signed(x, dec) if with_sign else f"{x:.{dec}f}") + unit)
    return " · ".join(out)


def live_of(s, S):
    """signals.js 에서 기준일 현재 점수·값·입력 시점을 꺼낸다 → (내용, 빠진 이유). 하나라도 없으면 내용은 None."""
    where, node = [], S
    try:
        for k in s["live"]:                                   # current (5번은 current → mtd) 까지 내려간다
            where.append(k)
            node = node[k]
        for k in [s["live_score"]] + [v[2] for v in s["values"]]:
            where = list(s["live"]) + [k]
            v = node[k]
            if type(v) not in (int, float) or not math.isfinite(v):       # true / false / NaN 은 숫자로 치지 않는다
                raise KeyError(k)
        score = node[s["live_score"]]
        if type(score) is not int or score not in (-1, 0, 1):            # 점수는 정수 −1 / 0 / +1 만 (1.0 도 받지 않는다)
            where = list(s["live"]) + [s["live_score"]]
            raise KeyError(score)
    except (KeyError, TypeError):
        return None, (f"{s['folder']}/signals.js의 기준일 현재 값({'.'.join(where)})이 없거나 숫자가 아닙니다. 잠정 줄을 만들지 않았습니다. "
                      "그 폴더에서 python3 analyze.py를 다시 실행하세요.")
    note = {}
    for name in ("vintage", "pending"):         # 입력 시점과, 월말 전에 더 바뀔 수 있는지
        try:
            note[name] = s[name](node, S["asof"]) if name == "pending" else s[name](node)
        except (KeyError, TypeError, ValueError):
            note[name] = None
    return {"score": score, "word_ko": s["words"][score],
            "value_ko": value_text(s, lambda p: node[p[2]], S["thresholds"]),
            "input_ko": note["vintage"], "pending_ko": note["pending"]}, None


def own_record(s, done, applied):
    """이 점수 하나의 다음 달 기록(개수만). 적중 = 결과가 점수가 가리키는 쪽으로 움직임. 결과가 0이면 빗나간 것으로 센다.
    조건으로만 쓰는 점수(gate)는 규칙이 쓰는 값(+1)에만 방향이 있다. 그 밖의 값이었던 달은 세지 않는다."""
    key, col = s["key"], YARDSTICK[s["feeds"][0]]
    want = WANT[s["feeds"][0]]
    used = [GATE_SCORE] if s["role"] == "gate" else [1, -1]
    seen = [r[col] for r in done if r[col] is not None]
    base = {"down": sum(1 for x in seen if x < 0), "up": sum(1 for x in seen if x > 0),
            "zero": sum(1 for x in seen if x == 0), "n": len(seen)}

    def count(rows, only=None):
        on = [(r[key], r[col]) for r in rows if r[key] in used and r[col] is not None and only in (None, r[key])]
        return {"hits": sum(1 for s_, x in on if s_ * want * x > 0), "n": len(on)}

    def one(k):
        """그 점수였던 달의 기록. hit_ko = 적중으로 친 방향, base_hits = 점수와 상관없이 그 방향이었던 달 수"""
        way = k * want
        return {**count(done, k), "hit_ko": MOVE_KO[col][way], "base_hits": base["up" if way > 0 else "down"]}

    by = {str(k): one(k) if k in used else None for k in (1, -1)}
    return {"yardstick": col, "yardstick_ko": YARD_KO[col], "scores_used": used,
            "all": count(done), "test": count([r for r in done if r["apply_month"] >= TEST_START]),
            "by_score": by,
            "same_sign": {"score": applied, **by[str(applied)]} if applied in used else None,      # 지금 적용 중인 점수와 같은 부호였던 달
            "base": base}


def rule_record(done, summary, freq):
    """규칙 자체의 기록: 포지션이 있던 달의 적중 개수(summary), 기준선(결과가 오른 달·내린 달), 최근 6개월."""
    off = {"duration": freq["duration"]["0.0"], "slope": freq["slope"]["none"], "curvature": freq["months"] - freq["curvature"]}
    rec = {"start": BT_START, "test_start": TEST_START, "end": done[-1]["apply_month"], "months": len(done)}
    for pos, view in POS_VIEW.items():        # on = 포지션이 있던 달, off = 없던 달
        a, t = summary[pos]["all"], summary[pos]["test"]
        col, want = YARDSTICK[view], WANT[view]
        sides = {}                            # 방향별로 따로 센다: 길게 / 짧게, 스티프너 / 플래트너 (합치면 on · hits)
        for sign, (name, word) in SIDE_KO[pos].items():
            seen = [r[col] for r in done if side(pos, r) == sign and r[col] is not None]
            sides[name] = {"sign": sign, "name_ko": word, "on": len(seen), "hits": sum(1 for x in seen if sign * want * x > 0),
                           "hit_ko": MOVE_KO[col][sign * want]}
        rec[pos] = {"yardstick": col, "yardstick_ko": YARD_KO[col],
                    "on": a["on"], "hits": a["hits"], "off": off[pos], "test": {"on": t["on"], "hits": t["hits"]}, "sides": sides}
    rec["base"] = {}
    for col in YARDSTICK.values():            # 기준선: 그냥 오른 달·내린 달이 몇 번이었나
        seen = [r[col] for r in done if r[col] is not None]
        rec["base"][col] = {"up": sum(1 for x in seen if x > 0), "down": sum(1 for x in seen if x < 0),
                            "zero": sum(1 for x in seen if x == 0), "n": len(seen)}
    rec["last6"] = []
    for r in done[-6:]:                       # 다음 달 결과가 나온 마지막 여섯 달
        hit = {}
        for pos, view in POS_VIEW.items():    # 포지션이 없던 달은 None
            s_, x = side(pos, r), r[YARDSTICK[view]]
            hit[pos] = None if not s_ or x is None else s_ * WANT[view] * x > 0
        rec["last6"].append({**{k: r[k] for k in ["decision_date", "apply_month"] + KEYS + [
            "view_level", "view_slope", "view_curvature", "duration_active_yr", "slope_position", "curvature_position",
            "next_d10y_bp", "next_d2s10s_bp", "next_dfly_bp"]}, "hit": hit})
    return rec


def build(now):
    """모든 계산. 파일은 쓰지 않는다 → (scoreboard.js 내용, 월별 줄, csv 열)"""
    tables, js = read_sections()
    fdates, _ = fly_series()
    rows = monthly_rows(tables)
    cols = [c for c in rows[0] if c not in DETAIL]
    done, summary, freq = rule_stats(rows)
    problems = []

    # ----- 적용 중인 줄 (마지막 월말 판정) -----
    cur = rows[-1]
    d = cur["decision_date"]
    obs = {name: num(tables[key][d][col]) for name, (key, col) in OBS.items()}
    official = {"date": d, **cur}

    # ----- 섹션 카드: 월말 값은 csv 마지막 줄, 잠정 값은 signals.js -----
    cards = []
    for s in SECTIONS:
        key, J = s["key"], js[s["key"]]
        live, why = live_of(s, J["all"])
        if why:
            problems.append(why)
        last = tables[key][d]
        cards.append({
            "no": s["no"], "key": key, "folder": s["folder"], "name": s["name"], "short": s["short"],
            "global": J["global"], "feeds": s["feeds"], "role": s["role"], "asof": J["asof"], "generated": J["generated"],
            "official": {"score": cur[key], "word_ko": s["words"][cur[key]],
                         "value_ko": value_text(s, lambda p: num(last[p[1]]), J["thresholds"])},
            "live": live, "th_ko": J["th_ko"], "th_origin_ko": s.get("th_origin"),
            "record": own_record(s, done, cur[key]),
        })

    # ----- 잠정 줄: 기준일 현재 점수 5개를 같은 compose() 에 넣는다 -----
    asofs = sorted({c["asof"] for c in cards})
    asof = asofs[0]                                    # 섹션마다 다르면 가장 오래된 날
    live = None
    if len(asofs) > 1:
        each = " · ".join(f"{c['folder'][:2]} {c['asof']}" for c in cards)
        problems.append(f"섹션 기준일이 서로 다릅니다 ({each}). 잠정 줄을 만들지 않았습니다. "
                        "각 폴더에서 python3 fetch_data.py → python3 analyze.py를 다시 실행하세요.")
    elif asof <= d:                                    # 월말 표에는 이미 있는 판정일인데 signals.js 는 그보다 앞: 같은 적용월이 두 줄이 된다
        problems.append(f"섹션 기준일 {asof}이(가) 마지막 판정일 {d}보다 늦지 않습니다 (signals.js가 월말 표보다 오래됨). 잠정 줄을 만들지 않았습니다. "
                        "각 폴더에서 python3 analyze.py를 다시 실행하세요.")
    elif fdates[-1] < asof:
        problems.append(f"수익률 파일(pipeline/inputs/curve/data.js)이 {fdates[-1]}까지라 기준일 {asof}의 Fly를 계산할 수 없습니다. 잠정 줄을 만들지 않았습니다.")
    elif asof not in set(fdates):
        problems.append(f"수익률 파일(pipeline/inputs/curve/data.js)에 기준일 {asof}의 2년 · 5년 · 10년 금리가 없습니다. 잠정 줄을 만들지 않았습니다.")
    elif all(c["live"] for c in cards):
        live = compose({c["key"]: c["live"]["score"] for c in cards}, asof, next_month(asof[:7]))
        end = last_weekday(asof[:7])
        live = {"date": asof, **live, "month_end": end, "is_month_end": asof == end,      # 휴일은 따지지 않은 마지막 평일
                "regime": (js["s1_policy"]["all"].get("current") or {}).get("regime"),
                "next_d10y_bp": None, "next_d2s10s_bp": None, "next_dfly_bp": None, "next_rv10y_bp_ann": None}

    # ----- 바뀐 점: 적용 중인 줄 → 잠정 줄 -----
    changes = []
    if live:
        what = ([("score", k, NAME[k]) for k in KEYS]
                + [("view", "view_level", "수준"), ("view", "view_slope", "기울기"), ("view", "view_curvature", "곡률"),
                   ("position", "duration_active_yr", "Duration"), ("position", "slope_position", "Slope"),
                   ("position", "curvature_position", "Curvature")])
        changes = [{"kind": kind, "key": k, "name": name, "from": official[k], "to": live[k],
                    "from_ko": show(k, official[k]), "to_ko": show(k, live[k])}
                   for kind, k, name in what if official[k] != live[k]]

    # ----- 바뀐 점을 뷰마다 한 줄기로: 그 뷰에 들어가는 점수 → 뷰 → 포지션. 다른 뷰의 점수를 원인처럼 엮지 않는다 -----
    chains = []
    by = {c["key"]: c for c in changes}
    for view, keys, vkey, pkey in (("level", VIEWS["level"], "view_level", "duration_active_yr"),
                                   ("slope", VIEWS["slope"], "view_slope", "slope_position"),
                                   ("curvature", [GATE], "view_curvature", "curvature_position")):
        inputs = [by[k] for k in keys if k in by]
        if view == "curvature" and vkey in by and official["curvature"]["z_met"] != live["curvature"]["z_met"]:
            inputs.append({"kind": "input", "key": "fly_z", "name": "Fly z",      # 곡률은 점수가 그대로여도 Fly z 로 바뀔 수 있다
                           "from": official["curvature"]["z_3y"], "to": live["curvature"]["z_3y"],
                           "from_ko": official["curvature"]["z_3y_ko"] or "–", "to_ko": live["curvature"]["z_3y_ko"] or "–"})
        if inputs or vkey in by or pkey in by:
            chains.append({"view": view, "inputs": inputs, "view_change": by.get(vkey), "position_change": by.get(pkey)})

    # ----- 브레이크: 제안(미채택). 포지션에는 반영하지 않고 해당 여부만 알린다 -----
    stress = js[GATE]["thresholds"].get("stress")
    gate_card = [c for c in cards if c["key"] == GATE][0]
    on = cur[GATE] == -1
    brake_text = (f"제안(미채택): 5번이 −1이면 포지션 절반 · {int(cur['apply_month'][5:7])}월 적용분 {'해당' if on else '해당 없음'}"
                  f" ({gate_card['official']['value_ko']} · {'–' if stress is None else format(stress, 'g')} 초과면 해당)")
    if live:                                           # 두 줄 모두 달 이름으로 부른다 ('이번 달'이라고 하지 않는다)
        brake_text += (f" · {int(live['apply_month'][5:7])}월 {'판정값' if live['is_month_end'] else '잠정'} "
                       f"{'해당' if live[GATE] == -1 else '해당 없음'} ({gate_card['live']['value_ko']})")
    brake_text += " · 위 포지션에는 반영하지 않음"
    brake = {"adopted": BRAKE_ADOPTED, "on_official": on, "on_live": (live[GATE] == -1) if live else None,
             "text_ko": brake_text, "months_on": freq["brake"], "months": freq["months"]}

    out = {
        "schema": 2, "status": "partial" if problems else "ok", "problems": problems,
        "generated": now, "asof": asof,
        "signals": [{"key": s["key"], "folder": s["folder"], "name": s["name"]} for s in SECTIONS],
        "rules": {"fly_lookback_m": FLY_LOOKBACK_M, "fly_z_th": FLY_Z_TH, "dur_step": DUR_STEP,
                  "brake_status": "제안 (팀 확정 전)",
                  "views": VIEWS, "slope_trigger": SLOPE_TRIGGER, "curvature_gate": {"key": GATE, "score": GATE_SCORE},
                  "brake_adopted": BRAKE_ADOPTED, "yardstick": YARDSTICK, "dur_cap": DUR_CAP},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["apply_month"]},
        "paper_start": PAPER_START,
        "official": official, "live": live, "changes": changes, "change_chains": chains, "sections": cards,
        "record": rule_record(done, summary, freq), "brake": brake,
        "decisions": [], "decision_check": {"checked": [], "drift": [], "live": None},
        # 아래는 옛 키. 규칙표 페이지(scoreboard_rules.html)가 읽으므로 값과 모양을 바꾸지 않는다
        "current": {c: cur[c] for c in cols}, "current_obs": obs, "freq": freq, "summary": summary,
        "monthly": {c: [r[c] for r in rows] for c in cols},
    }
    return out, rows, cols


# ---------------------------------------------------------------- 월말 판정 고정 (decisions.csv)
def read_decisions():
    """decisions.csv → 줄 목록(숫자 열은 숫자로). 파일이 없거나 비어 있으면 빈 목록.
    읽을 수 없으면 Stop: 점수표는 그대로 만들고 상태만 partial 이 된다."""
    try:
        if not DECISIONS.exists() or DECISIONS.stat().st_size == 0:
            return []
        with open(DECISIONS, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows, have = list(reader), reader.fieldnames or []
    except (OSError, ValueError, csv.Error):    # 엑셀에서 'CSV (쉼표로 분리)'로 다시 저장하면 UTF-8 이 아니다
        raise Stop("decisions.csv를 읽을 수 없습니다 (UTF-8이 아니거나 열 수 없는 파일). 엑셀에서 고쳤다면 'CSV UTF-8'로 다시 저장하세요.")
    if have != FREEZE_COLS:
        raise Stop("decisions.csv의 열이 이 스크립트가 쓰는 열과 다릅니다. 손으로 고친 적이 있는지 확인하세요.")
    whole = set(KEYS) | {"view_level", "view_slope", "curvature_met"}
    for i, r in enumerate(rows):
        if None in r or None in r.values():     # 칸이 남거나 모자란 줄: 두 줄이 한 줄로 붙었을 때 생긴다
            raise Stop(f"decisions.csv {i + 2}번째 줄의 칸 수가 열 수와 다릅니다. 두 줄이 한 줄로 붙었는지 확인하세요.")
        for c in FREEZE_COLS:
            if c in whole:
                r[c] = None if num(r[c]) is None else int(num(r[c]))
            elif c in ("fly_bp", "fly_z_3y", "duration_active_yr"):
                r[c] = num(r[c])
    return rows


def check_decisions(decisions, rows, live):
    """고정해 둔 판정의 점수 5개를 견준다.
    그 달의 월말 줄이 이미 나왔으면 월말 줄과(checked · drift), 아직이면 지금의 잠정 줄과(live)."""
    by_month = {r["apply_month"]: r for r in rows}
    checked, drift, on_live = [], [], None
    for dec in decisions:
        row = by_month.get(dec["apply_month"])
        if row is None:                       # 아직 그 달의 월말 줄이 없다
            if live and dec["apply_month"] == live["apply_month"]:
                diff = [k for k in KEYS if dec[k] != live[k]]
                on_live = {"apply_month": dec["apply_month"], "frozen_at": dec["frozen_at"], "asof": dec["asof"],
                           "same_asof": dec["asof"] == live["date"],          # 고정한 날과 지금 자료의 기준일이 같은가
                           "match": not diff,
                           "diff": [{"key": k, "name": NAME[k], "frozen": dec[k], "live": live[k],
                                     "text_ko": f"{NAME[k]} 고정 {signed(dec[k])} → 지금 {signed(live[k])}"} for k in diff]}
            continue
        same = dec["asof"] == row["decision_date"]      # 월말 전에 미리 고정한 줄이면 날짜가 다르다
        diff = [k for k in KEYS if dec[k] != row[k]]
        checked.append({"apply_month": dec["apply_month"], "asof": dec["asof"], "frozen_at": dec["frozen_at"],
                        "decision_date": row["decision_date"], "same_date": same, "match": not diff})
        for k in diff:
            drift.append({"apply_month": dec["apply_month"], "key": k, "name": NAME[k], "frozen": dec[k], "official": row[k],
                          "text_ko": f"{dec['apply_month']} {NAME[k]}: 고정 {signed(dec[k])} → 다시 계산 {signed(row[k])}"
                                     + ("" if same else f" (고정은 {dec['asof']} 기준, 월말 판정은 {row['decision_date']})")})
    return {"checked": checked, "drift": drift, "live": on_live}


def freeze_row(out, decisions, args, now, dry):
    """잠정 줄을 decisions.csv 한 줄로 → (줄, 거절 이유). 거절이면 줄은 None."""
    live = out["live"]
    if live is None:
        return None, "잠정 줄이 없어 고정할 수 없습니다: " + " / ".join(out["problems"])
    if args.asof > out["asof"]:
        return None, (f"--asof {args.asof}가 자료 기준일 {out['asof']}보다 늦습니다. "
                      "각 폴더에서 fetch_data.py → analyze.py를 돌려 자료를 그날까지 받은 뒤 다시 실행하세요.")
    if args.asof < out["asof"]:
        if args.freeze != live["apply_month"]:          # 자료가 이미 다음 달로 넘어갔다: 그 달 판정은 더 고정할 수 없다
            return None, (f"--asof {args.asof}은(는) 이미 지났습니다. 자료가 {out['asof']}까지 와서 잠정 줄은 {live['apply_month']} 적용분입니다. "
                          f"{args.freeze} 적용분은 이제 고정할 수 없습니다. 그 달의 기록은 월말 줄({out['official']['decision_date']} 판정)입니다.")
        return None, f"--asof {args.asof}가 자료 기준일 {out['asof']}보다 이릅니다. 자료는 이미 {out['asof']}까지 받았습니다."
    if args.freeze != live["apply_month"]:
        return None, f"--freeze {args.freeze}가 잠정 줄의 적용월 {live['apply_month']}와 다릅니다."
    old = [(i, r) for i, r in enumerate(decisions) if r["apply_month"] == args.freeze]
    if old:
        i, r = old[0]
        return None, (f"decisions.csv에 {args.freeze} 줄이 이미 있습니다 ({i + 2}번째 줄 · 기준일 {r['asof']} · {r['frozen_at']} 고정). 덮어쓰지 않습니다. "
                      "잘못 고정한 줄이면 decisions.csv에서 그 줄만 지우고 저장한 뒤 다시 실행하세요.")
    if not live["is_month_end"] and not args.early and not dry:
        return None, (f"기준일 {out['asof']}이(가) 그 달의 마지막 평일({live['month_end']})이 아닙니다. 그 달 줄은 한 번만 쓸 수 있어서, "
                      "지금 고정하면 월말 판정을 고정하지 못합니다. 월말이 미국 휴장일이라 오늘이 마지막 거래일이면 --early 를 붙여 다시 실행하세요.")
    row = {"frozen_at": now, "apply_month": live["apply_month"], "asof": out["asof"],
           **{k: live[k] for k in KEYS}, **{c["key"] + "_value_ko": c["live"]["value_ko"] for c in out["sections"]},
           "view_level": live["view_level"], "view_slope": live["view_slope"], "curvature_met": live["view_curvature"],
           "fly_bp": live["fly_2s5s10s_bp"], "fly_z_3y": live["fly_z_3y"], "duration_active_yr": live["duration_active_yr"],
           "slope_position": live["slope_position"], "curvature_position": live["curvature_position"], "note": args.note}
    return row, None


def append_decision(row):
    """decisions.csv 끝에 한 줄. 파일이 줄바꿈 없이 끝나 있으면(편집기가 마지막 줄바꿈을 지운 경우) 먼저 줄을 바꾼다:
    새 줄이 머리줄이나 앞줄 끝에 붙지 않게."""
    new = not DECISIONS.exists() or DECISIONS.stat().st_size == 0
    glued = False
    if not new:
        with open(DECISIONS, "rb") as f:
            f.seek(-1, 2)
            glued = f.read(1) not in (b"\n", b"\r")
    with open(DECISIONS, "a", newline="", encoding="utf-8-sig" if new else "utf-8") as f:     # 엑셀용 BOM은 파일을 만들 때 한 번만
        if glued:
            f.write("\r\n")
        w = csv.writer(f)
        if new:
            w.writerow(FREEZE_COLS)
        w.writerow(["" if row[c] is None else row[c] for c in FREEZE_COLS])


# ---------------------------------------------------------------- 쓰기·콘솔
def write_js(out):
    (HERE / "scoreboard.js").write_text(
        "window.MACRO_SCOREBOARD = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")


def write_csv(rows, cols):
    with open(HERE / "scoreboard.csv", "w", newline="", encoding="utf-8-sig") as f:   # 엑셀에서 한글이 깨지지 않게 BOM 포함
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])


def one_line(row):
    """한 줄 요약: 점수 5개 → 뷰 → 포지션"""
    word = {"aligned": "", "conflict": " (상충)", "no_signal": " (신호 없음)"}
    pos = [f"Duration {show('duration_active_yr', row['duration_active_yr'])}"] if row["duration_active_yr"] else []
    if row["slope_position"] != "none":
        pos.append(f"Slope {show('slope_position', row['slope_position'])}")
    if row["view_curvature"]:
        pos.append("Curvature 불릿")
    return (", ".join(signed(row[k]) for k in KEYS)
            + f" → 수준 {signed(row['view_level'])}{word[row['level']['state']]} · 기울기 {signed(row['view_slope'])}{word[row['slope']['state']]}"
            + f" · 곡률 {show('view_curvature', row['view_curvature'])} → " + (" · ".join(pos) if pos else "Carry만"))


def report(out, n_rows, saved, csv_ok=True):
    cur, freq, summary, live = out["current"], out["freq"], out["summary"], out["live"]
    sc = lambda v: {1: "+1", 0: " 0", -1: "−1"}[v]
    print(f"[적용 중인 판정] {cur['decision_date']} 판정 → {cur['apply_month']} 적용")
    for s in SECTIONS:
        print(f"  {s['name']:8s} {sc(cur[s['key']])}")
    print(f"  수준 뷰 {sg(cur['view_level'])} · 기울기 뷰 {sg(cur['view_slope'])} · 곡률 {'충족' if cur['view_curvature'] else '미충족'}"
          f" (Fly {cur['fly_2s5s10s_bp']}bp, z {cur['fly_z_3y']} / 1년 기준 {cur['fly_z_1y']})")
    print(f"  → {cur['position_ko']}")
    print(f"  한 줄: {one_line(out['official'])}")
    if live:
        print(f"\n[잠정] {live['date']} 기준 → {live['apply_month']} 적용 예정 · "
              + ("기준일이 그 달의 마지막 평일 · 확정 전" if live["is_month_end"] else f"월말({live['month_end']}) 미국 종가에 확정"))
        print(f"  한 줄: {one_line(live)}")
        print(f"  Fly {signed(live['fly_2s5s10s_bp'], 1)}bp · z {signed(live['fly_z_3y'], 2)} (3년) / {signed(live['fly_z_1y'], 2)} (1년)")
        print("  바뀐 점: " + (", ".join(f"{c['name']} {c['from_ko']} → {c['to_ko']}" for c in out["changes"]) or "없음"))
    else:
        print("\n[잠정] 만들지 못했습니다 (아래 문제 참고)")
    print(f"\n[포지션 빈도] 성과월 {BT_START} ~ {out['split']['end']} ({freq['months']}개월)")
    print("  Duration " + "  ".join(f"{float(k):+.2f}년: {v}" for k, v in freq["duration"].items()))
    print(f"  Slope 스티프너 {freq['slope']['steepener']} · 없음 {freq['slope']['none']} · 플래트너 {freq['slope']['flattener']}")
    print(f"  Curvature 불릿 {freq['curvature']} (룩백 1년이면 {freq['curvature_if_1y']}) · 브레이크 {freq['brake']}")
    print("\n[포지션이 있던 달의 다음 달 결과]  (적중 = 포지션이 버는 방향으로 움직임, 평균 = 포지션 방향 기준 bp)")
    for name, key, unit in (("Duration", "duration", "10년 금리"), ("Slope", "slope", "2s10s"), ("Curvature", "curvature", "Fly")):
        s_ = summary[key]
        print(f"  {name:9s} ({unit}) " + "  ".join(
            f"{lab} {v['hits']}/{v['on']}" + (f" {v['hit']}% 평균 {v['mean_bp']:+.1f}" if v["on"] else "")
            for lab, v in (("전체", s_["all"]), ("설정", s_["train"]), ("검증", s_["test"]))))
    for x in out["decision_check"]["drift"]:
        print(f"\n[고정한 판정과 다름] {x['text_ko']}")
    for p in out["problems"]:
        print(f"\n[문제] {p}")
    if saved and csv_ok:
        print(f"\n→ scoreboard.csv, scoreboard.js 저장 (월 {n_rows}개, 상태 {out['status']})")
    elif saved:
        print(f"\n→ scoreboard.js만 저장 (scoreboard.csv는 쓰지 못함, 상태 {out['status']})")


def parse_args():
    class Parser(argparse.ArgumentParser):
        def error(self, message):           # 영어 오류 대신 한 줄 안내
            raise SystemExit('사용법: python3 scoreboard.py [--freeze YYYY-MM --asof YYYY-MM-DD [--dry-run] [--note "메모"] [--early]]')

    p = Parser(description="매크로 통합 점수표를 만든다. --freeze 는 잠정 줄을 decisions.csv 에 고정한다.")
    p.add_argument("--freeze", metavar="YYYY-MM", help="고정할 적용월 (잠정 줄의 적용월과 같아야 한다)")
    p.add_argument("--asof", metavar="YYYY-MM-DD", help="자료 기준일 (다섯 섹션의 기준일과 같아야 한다)")
    p.add_argument("--dry-run", action="store_true", help="고정할 줄만 보여 주고 아무 파일도 쓰지 않는다")
    p.add_argument("--note", default="", help="decisions.csv 에 함께 적을 메모")
    p.add_argument("--early", action="store_true", help="기준일이 그 달의 마지막 평일이 아니어도 고정한다 (월말이 휴장일인 달)")
    a = p.parse_args()
    if a.freeze is None:
        if a.asof or a.dry_run or a.note or a.early:       # 이 넷은 --freeze 와 함께만 쓴다
            p.error("")
    else:
        try:
            date.fromisoformat(a.asof or "")    # --asof 는 꼭 있어야 하고 날짜 꼴이어야 한다
        except ValueError:
            p.error("")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", a.freeze):
            p.error("")
    return a


def console_safe():
    """콘솔이 못 찍는 글자에서 멈추지 않게 한다. 한글 윈도우 콘솔(cp949)에는 '−'(U+2212)가 없어서,
    그대로 두면 파일은 썼는데 요약을 찍다가 오류로 끝난다. 못 찍는 글자는 비슷한 글자로 바꿔 찍는다."""
    swap = {"−": "-", "–": "-"}
    codecs.register_error("console_ko", lambda e: ("".join(swap.get(ch, "?") for ch in e.object[e.start:e.end]), e.end))
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="console_ko")
        except (AttributeError, ValueError):
            pass


def write_error(problems, now):
    """실패했을 때: 옛 scoreboard.js 가 멀쩡해 보이지 않게 오류 상태로 덮어쓴다 → 덧붙일 안내 문구"""
    try:
        write_js({"schema": 2, "status": "error", "problems": problems, "generated": now})
        return "  → scoreboard.js에 오류 상태를 적었습니다."
    except OSError:
        return "  → scoreboard.js도 쓸 수 없습니다. 옛 파일이 남아 있을 수 있습니다."


def main():
    console_safe()
    args = parse_args()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    dry = bool(args.freeze and args.dry_run)
    try:
        out, rows, cols = build(now)
        try:
            decisions = read_decisions()
        except Stop as e:                       # 기록 파일이 이상해도 점수표는 만든다
            decisions = None
            out["problems"] += e.problems
            out["status"] = "partial"
    except Stop as e:
        print("오류: " + " / ".join(e.problems) + ("" if dry else write_error(e.problems, now)), file=sys.stderr)
        return 1
    except Exception as e:                      # 미리 생각하지 못한 오류도 옛 파일을 멀쩡하게 남기지 않는다
        if not dry:
            write_error([f"scoreboard.py가 알 수 없는 오류로 멈췄습니다 ({type(e).__name__}). 터미널에 나온 메시지를 확인하세요."], now)
        raise

    # ----- 고정: 줄을 덧붙이기 전에 모든 거절 조건과 경고를 먼저 본다 -----
    frozen = refusal = trouble = None
    early = False
    if args.freeze:
        if decisions is None:
            refusal = "decisions.csv를 읽을 수 없습니다 (위 [문제] 참고). 파일을 고친 뒤 다시 실행하세요."
        else:
            frozen, refusal = freeze_row(out, decisions, args, now, dry)
        early = bool(frozen) and not out["live"]["is_month_end"]
        if frozen and not dry:
            if early:
                print(f"※ 기준일 {frozen['asof']}은(는) 그 달의 마지막 평일({out['live']['month_end']})이 아닙니다. --early 로 고정합니다. "
                      f"{frozen['apply_month']} 줄은 다시 쓸 수 없습니다.", file=sys.stderr)
            try:
                append_decision(frozen)
                decisions = read_decisions()    # 방금 쓴 줄이 제대로 읽히는지 본다
                last = decisions[-1] if decisions else {}
                if any(last.get(c) != frozen[c] for c in ["apply_month", "asof"] + KEYS):
                    raise Stop("decisions.csv에 덧붙인 줄이 다시 읽은 마지막 줄과 다릅니다. 파일을 열어 확인하세요.")
            except OSError:
                frozen, refusal = None, "decisions.csv에 쓸 수 없습니다 (엑셀 등에서 열려 있으면 닫고 다시 실행하세요)."
            except Stop as e:                   # 줄은 썼지만 다시 읽지 못했다
                decisions, trouble = None, " / ".join(e.problems)
                out["problems"] += e.problems
                out["status"] = "partial"
    out["decisions"] = decisions or []
    out["decision_check"] = check_decisions(decisions or [], rows, out["live"])

    # ----- 쓰기: scoreboard.js 먼저. scoreboard.csv 를 못 써도(엑셀에서 열려 있을 때) 옛 js 가 남지 않게 -----
    csv_ok = True
    if not dry:
        try:
            write_js(out)
        except OSError as e:
            print(f"오류: scoreboard.js를 쓸 수 없습니다 ({e.strerror}). 옛 파일이 그대로 남아 있습니다.", file=sys.stderr)
            return 1
        try:
            write_csv(rows, cols)
        except OSError:
            csv_ok = False
            out["problems"].append("scoreboard.csv를 쓸 수 없습니다 (엑셀 등에서 열려 있으면 닫고 다시 실행하세요). scoreboard.js만 새로 썼습니다.")
            out["status"] = "partial"
            write_js(out)
    report(out, len(rows), saved=not dry, csv_ok=csv_ok)

    if args.freeze:
        if refusal:
            print(f"\n고정하지 않았습니다: {refusal}", file=sys.stderr)
            return 2
        print(f"\n[{'고정 미리 보기' if dry else '고정'}] {frozen['apply_month']} 판정 · 기준일 {frozen['asof']}")
        for c in FREEZE_COLS:
            print(f"  {c:28s} {frozen[c]}")
        if early:
            print(f"  ※ 기준일이 그 달의 마지막 평일({out['live']['month_end']})이 아닙니다."
                  + (" 실제로 고정하려면 --early 가 필요합니다." if dry and not args.early else ""))
        if trouble:
            print(f"\n오류: decisions.csv에 한 줄을 덧붙였지만 다시 읽지 못했습니다: {trouble}", file=sys.stderr)
            return 1
        print("  (--dry-run: 아무 파일도 쓰지 않았습니다)" if dry else "  → decisions.csv에 한 줄 덧붙였습니다.")
    return 0 if csv_ok else 1


if __name__ == "__main__":
    sys.exit(main())
