"""Duration 규칙 개선 연구. 2015~2020(규칙 수립)에서 후보를 고르고 2021년 이후(검증)로 확인한다.
실행: python3 research/duration_rule_study.py   (pipeline/model 폴더에서)"""
import sys, math, json
sys.path.insert(0, ".")
import backtest as b

R = b.rows[:-1]                                   # 끝난 달만
N = len(R)
Y = lambda k, i: b.U["yields"][k][i]
long_bp, short_bp, feat = [], [], []
for i, r in enumerate(R):
    i0, i1 = b.starts[i], b.ends[i]
    def ex(d):
        p = b.build_position(i0, d, "none", "none")
        return (b.value_path(i0, i1, *p["dur"])[-1] - b.value_path(i0, i1, *p["bm"])[-1]) * 1e4
    long_bp.append(ex(0.25)); short_bp.append(ex(-0.25))
    back = lambda k: b.starts[i - k] if i - k >= 0 else b.idx_on_or_before(b._shift(b.DATES[i0], k) if hasattr(b, "_shift") else b.DATES[i0])
    def ago(months):                               # months개월 전 영업일
        y, m, d = int(b.DATES[i0][:4]), int(b.DATES[i0][5:7]), b.DATES[i0][8:]
        m -= months
        while m <= 0: m += 12; y -= 1
        return b.idx_on_or_before(f"{y:04d}-{m:02d}-{d}")
    feat.append(dict(
        s1=int(r["s1_policy"]), s2=int(r["s2_growth"]), s3=int(r["s3_inflation"]), s4=int(r["s4_supply"]), s5=int(r["s5_liquidity_vol"]),
        mom3=Y("10Y", i0) - Y("10Y", ago(3)), mom6=Y("10Y", i0) - Y("10Y", ago(6)), mom12=Y("10Y", i0) - Y("10Y", ago(12)),
        slope=Y("10Y", i0) - Y("2Y", i0), carry=Y("10Y", i0) - Y("3M", i0), month=r["apply_month"]))
TR = [i for i in range(N) if R[i]["apply_month"] < "2021-01"]
TE = [i for i in range(N) if R[i]["apply_month"] >= "2021-01"]
sgn = lambda x: (x > 0) - (x < 0)
clip = lambda x, lo=-2, hi=2: max(lo, min(hi, x))

def pnl(pos, idx):                                 # pos: 단위 0.25년 (−2..+2)
    out = []
    for i in idx:
        p = pos(feat[i])
        out.append(p * long_bp[i] if p > 0 else (-p) * short_bp[i] if p < 0 else 0.0)
    return out

def stat(x):
    n = len(x); tot = sum(x); mu = tot / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1)) or 1e-9
    on = [v for v in x if v != 0]
    return dict(tot=round(tot, 1), ann=round(mu * 12, 1), ir=round(mu / sd * math.sqrt(12), 2), t=round(mu / sd * math.sqrt(n), 2),
                on=len(on), win=sum(1 for v in on if v > 0))

RULES = {
 "A 지금 규칙 (정책+성장+물가)":      lambda f: clip(f["s1"] + f["s2"] + f["s3"]),
 "B 성장 빼기 (정책+물가)":          lambda f: clip(f["s1"] + f["s3"]),
 "C 물가만":                       lambda f: f["s3"],
 "D 정책만":                       lambda f: f["s1"],
 "E 강한 신호만 (|합|≥2일 때)":      lambda f: (lambda v: clip(v) if abs(v) >= 2 else 0)(f["s1"] + f["s2"] + f["s3"]),
 "F 추세 12개월 (금리 내렸으면 길게)": lambda f: -sgn(f["mom12"]),
 "G 추세 6개월":                    lambda f: -sgn(f["mom6"]),
 "H 추세 3개월":                    lambda f: -sgn(f["mom3"]),
 "I 캐리 (10년−3개월 > 0이면 길게)":  lambda f: 1 if f["carry"] > 0 else -1,
 "J 캐리, 길게만 (역전이면 중립)":    lambda f: 1 if f["carry"] > 0 else 0,
 "K 추세12 + 캐리":                 lambda f: -sgn(f["mom12"]) + (1 if f["carry"] > 0 else -1),
 "L 추세12 + 물가":                 lambda f: clip(-sgn(f["mom12"]) + f["s3"]),
 "M 추세12 + 캐리 + 물가":           lambda f: clip(-sgn(f["mom12"]) + (1 if f["carry"] > 0 else -1) + f["s3"]),
 "N 항상 길게 +0.25":               lambda f: 1,
}
res = {}
print(f"{'규칙':34s} | 수립 2015~2020 (bp, IR, t, 이긴 달) | 검증 2021~ ")
for nm, fn in RULES.items():
    a, c = stat(pnl(fn, TR)), stat(pnl(fn, TE))
    res[nm] = dict(train=a, test=c)
    print(f"{nm:34s} | {a['tot']:7.1f} {a['ir']:5.2f} {a['t']:5.2f} {a['win']:3d}/{a['on']:<3d} | {c['tot']:7.1f} {c['ir']:5.2f} {c['t']:5.2f} {c['win']:3d}/{c['on']:<3d}")
json.dump(res, open("research/duration_rule_study.json", "w"), ensure_ascii=False, indent=1)
print("수립", len(TR), "개월 · 검증", len(TE), "개월 · 단위는 누적 bp (포지션 1단위 = 0.25년)")
