"""매크로 통합 점수표: 신호 5개 → 커브 뷰 3개 → 포지션 4개  →  scoreboard.csv + scoreboard.js

다섯 섹션 폴더의 signals_monthly.csv에서 팀 점수 열만 읽어 합친다. 섹션별 계산은 건드리지 않는다.

1단계  신호 점수 (−1 / 0 / +1, 매월 마지막 거래일 판정 → 다음 달 적용)
   1 정책 경로      score_policy         +1 = 시장이 연준보다 높게 가격      (금리 하락 쪽)
   2 성장·고용      score_growth         +1 = 둔화                          (금리 하락 쪽)
   3 인플레이션     score_momentum       +1 = 물가 둔화                      (금리 하락 쪽)
   4 수급           score_supply         +1 = 장기물 공급 가속               (스티프닝 쪽)
   5 유동성·변동성  score_liquidity_vol  +1 = 셋 다 안정, −1 = 스트레스
2단계  커브 뷰
   수준   = 1번 + 2번 + 3번                      (−3 ~ +3, 양수 = 금리 하락 예상)
   기울기 = 1번 + 4번                            (−2 ~ +2, 양수 = 스티프닝 예상)
   곡률   = 5번이 +1 이고 Fly z-score ≥ +1       (충족 1 / 미충족 0)
3단계  포지션
   Duration         수준 +2 이상 / +1 / 0 → 액티브 듀레이션 +0.5년 / +0.25년 / 0 (음수는 반대)
   Curve Slope      기울기 +2 → 스티프너(1–3y 확대·20y+ 축소), −2 → 플래트너(반대), DV01 중립
   Curve Curvature  곡률 충족 → 불릿(5–7y 확대, 1–3y·10–20y 축소), DV01 중립
   Carry & Rolldown 항상 (버킷 안에서 carry+roll 상위 종목)
   브레이크         5번이 −1 → 벨리 불릿 청산, 모든 액티브 포지션 절반   ← 5번 섹션의 제안, 팀 확정 전

Fly = 2 × 5년 − 2년 − 10년 (bp, 재무부 CMT). z-score는 판정일까지의 직전 FLY_LOOKBACK_M개월 일별 값 기준.
룩백(1년 / 3년)은 팀 확정 전이라 3년을 기본으로 쓰고 1년 값도 함께 적어 둔다.

실행: python3 scoreboard.py     (섹션 점수를 새로 받으려면 먼저 각 폴더에서 python3 fetch_data.py)
"""
import bisect, csv, json, math
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parent / "curve" / "data.js"       # 일별 CMT 금리(공통 데이터)

SIGNALS = [  # (열 이름, 폴더, 섹션 파일의 점수 열, 한글 이름)
    ("s1_policy", "01_policy_path", "score_policy", "정책 경로"),
    ("s2_growth", "02_growth_jobs", "score_growth", "성장·고용"),
    ("s3_inflation", "03_inflation", "score_momentum", "인플레이션"),
    ("s4_supply", "04_supply_tp", "score_supply", "수급"),
    ("s5_liquidity_vol", "05_liquidity_vol", "score_liquidity_vol", "유동성·변동성"),
]
FLY_LOOKBACK_M = 36      # Fly z-score 룩백(개월). 팀 확정 전: 1년 / 3년 중 3년을 기본으로 둠
FLY_Z_TH = 1.0
DUR_STEP = 0.25          # 년
BT_START, TEST_START = "2015-01", "2021-01"


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    last = [31, 29 if (y2 % 4 == 0 and (y2 % 100 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(day, last):02d}"


def load_fly():
    """일별 2s5s10s Fly (bp)"""
    t = CURVE_JS.read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    dates, fly = [], []
    for i, day in enumerate(d["dates"]):
        y2, y5, y10 = (d["yields"][k][i] for k in ("2Y", "5Y", "10Y"))
        if None not in (y2, y5, y10):
            dates.append(day)
            fly.append((2 * y5 - y2 - y10) * 100)
    return dates, fly


def zscore(dates, vals, d, months):
    """d 이하 마지막 값이 직전 months개월(그 값 포함) 분포에서 몇 표준편차인가"""
    b = bisect.bisect_right(dates, d)
    a = bisect.bisect_right(dates, months_ago(d, months))
    w = vals[a:b]
    if len(w) < 60:
        return None, None
    mu = sum(w) / len(w)
    sd = math.sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
    return w[-1], ((w[-1] - mu) / sd if sd else None)


def duration_rule(level):
    return max(-2, min(2, level)) * DUR_STEP


def sg(x, d=2):
    return "0" if not x else f"{x:+.{d}f}".rstrip("0").rstrip(".")


def main():
    # ----- 1단계: 섹션 점수 읽기 -----
    tables = {}
    for col, folder, src, _ in SIGNALS:
        with open(HERE / folder / "signals_monthly.csv", encoding="utf-8") as f:
            tables[col] = {r["decision_date"]: r for r in csv.DictReader(f)}
    base = tables["s1_policy"]
    dates = sorted(base)
    for col, folder, _, _ in SIGNALS:
        if sorted(tables[col]) != dates:
            raise SystemExit(f"{folder}의 판정일이 다른 섹션과 다릅니다. 각 폴더에서 fetch_data.py를 다시 실행하세요.")
    fdates, fly = load_fly()

    rows = []
    for d in dates:
        s = {}
        for col, folder, src, _ in SIGNALS:
            v = num(tables[col][d][src])
            if v is None:
                raise SystemExit(f"{folder} {d}: {src} 값이 비어 있습니다.")
            s[col] = int(v)
        # ----- 2단계: 커브 뷰 -----
        level = s["s1_policy"] + s["s2_growth"] + s["s3_inflation"]
        slope = s["s1_policy"] + s["s4_supply"]
        fv, z = zscore(fdates, fly, d, FLY_LOOKBACK_M)
        _, z1 = zscore(fdates, fly, d, 12)
        curv = int(s["s5_liquidity_vol"] == 1 and z is not None and z >= FLY_Z_TH)
        # ----- 3단계: 포지션 -----
        dur = duration_rule(level)
        slope_pos = "steepener" if slope >= 2 else "flattener" if slope <= -2 else "none"
        brake = int(s["s5_liquidity_vol"] == -1)
        mult = 0.5 if brake else 1.0
        parts = [f"Duration {sg(dur)}년" if dur else "Duration 중립",
                 {"steepener": "Slope 스티프너", "flattener": "Slope 플래트너", "none": "Slope 없음"}[slope_pos],
                 "Curvature 불릿" if curv else "Curvature 없음", "Carry 유지"]
        if brake:
            parts.append("브레이크: 포지션 절반")
        p, l5 = tables["s1_policy"][d], tables["s5_liquidity_vol"][d]
        rows.append({
            "decision_date": d, "apply_month": p["apply_month"], **s,
            "view_level": level, "view_slope": slope,
            "fly_2s5s10s_bp": None if fv is None else round(fv, 1),
            "fly_z_3y": None if z is None else round(z, 2), "fly_z_1y": None if z1 is None else round(z1, 2),
            "view_curvature": curv,
            "duration_active_yr": dur, "slope_position": slope_pos, "curvature_position": "bullet" if curv else "none",
            "carry_rolldown": "on", "brake": brake, "size_multiplier": mult,
            "duration_active_yr_with_brake": dur * mult,
            "position_ko": " · ".join(parts), "regime": p["regime"],
            "next_d10y_bp": num(p["next_d10y_bp"]), "next_d2s10s_bp": num(p["next_d2s10s_bp"]),
            "next_dfly_bp": num(l5["next_dfly_bp"]), "next_rv10y_bp_ann": num(l5["next_rv10y_bp_ann"]),
        })

    cols = list(rows[0])
    with open(HERE / "scoreboard.csv", "w", newline="", encoding="utf-8-sig") as f:   # 엑셀에서 한글이 깨지지 않게 BOM 포함
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    # ----- 포지션별 빈도와 다음 달 결과 (참고용 요약) -----
    done = [r for r in rows if r["next_d10y_bp"] is not None and r["apply_month"] >= BT_START]

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

    sign = lambda x: (x > 0) - (x < 0)
    summary = {
        "duration": stat(lambda r: sign(r["duration_active_yr"]), "next_d10y_bp", -1),       # 롱 듀레이션 → 10년 금리 하락이면 적중
        "slope": stat(lambda r: {"steepener": 1, "flattener": -1, "none": 0}[r["slope_position"]], "next_d2s10s_bp", 1),
        "curvature": stat(lambda r: r["view_curvature"], "next_dfly_bp", -1),                # 불릿 → Fly 하락이면 적중
    }
    freq = {
        "duration": {str(k): sum(1 for r in done if r["duration_active_yr"] == k) for k in (-0.5, -0.25, 0.0, 0.25, 0.5)},
        "slope": {k: sum(1 for r in done if r["slope_position"] == k) for k in ("steepener", "none", "flattener")},
        "curvature": sum(r["view_curvature"] for r in done),
        "curvature_if_1y": sum(1 for r in done if r["s5_liquidity_vol"] == 1 and r["fly_z_1y"] is not None and r["fly_z_1y"] >= FLY_Z_TH),
        "brake": sum(r["brake"] for r in done), "months": len(done),
    }

    cur = rows[-1]
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "signals": [{"key": c, "folder": f, "name": n} for c, f, _, n in SIGNALS],
        "rules": {"fly_lookback_m": FLY_LOOKBACK_M, "fly_z_th": FLY_Z_TH, "dur_step": DUR_STEP,
                  "brake_status": "제안 (팀 확정 전)"},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["apply_month"]},
        "current": cur, "freq": freq, "summary": summary,
        "monthly": {c: [r[c] for r in rows] for c in cols},
    }
    (HERE / "scoreboard.js").write_text(
        "window.MACRO_SCOREBOARD = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda v: {1: "+1", 0: " 0", -1: "−1"}[v]
    print(f"[적용 중인 판정] {cur['decision_date']} 판정 → {cur['apply_month']} 적용")
    for c, _, _, n in SIGNALS:
        print(f"  {n:8s} {sc(cur[c])}")
    print(f"  수준 뷰 {sg(cur['view_level'])} · 기울기 뷰 {sg(cur['view_slope'])} · 곡률 {'충족' if cur['view_curvature'] else '미충족'}"
          f" (Fly {cur['fly_2s5s10s_bp']}bp, z {cur['fly_z_3y']} / 1년 기준 {cur['fly_z_1y']})")
    print(f"  → {cur['position_ko']}")
    print(f"\n[포지션 빈도] 성과월 {BT_START} ~ {done[-1]['apply_month']} ({len(done)}개월)")
    print("  Duration " + "  ".join(f"{float(k):+.2f}년: {v}" for k, v in freq["duration"].items()))
    print(f"  Slope 스티프너 {freq['slope']['steepener']} · 없음 {freq['slope']['none']} · 플래트너 {freq['slope']['flattener']}")
    print(f"  Curvature 불릿 {freq['curvature']} (룩백 1년이면 {freq['curvature_if_1y']}) · 브레이크 {freq['brake']}")
    print("\n[포지션이 있던 달의 다음 달 결과]  (적중 = 포지션이 버는 방향으로 움직임, 평균 = 포지션 방향 기준 bp)")
    for name, key, unit in (("Duration", "duration", "10년 금리"), ("Slope", "slope", "2s10s"), ("Curvature", "curvature", "Fly")):
        s_ = summary[key]
        print(f"  {name:9s} ({unit}) " + "  ".join(
            f"{lab} {v['hits']}/{v['on']}" + (f" {v['hit']}% 평균 {v['mean_bp']:+.1f}" if v["on"] else "")
            for lab, v in (("전체", s_["all"]), ("설정", s_["train"]), ("검증", s_["test"]))))
    print(f"\n→ scoreboard.csv, scoreboard.js 저장 (월 {len(rows)}개)")


if __name__ == "__main__":
    main()
