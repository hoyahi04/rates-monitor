/* 미국 국채 계산 (반기 이자, Actual/Actual, street convention).
   pipeline/bondmath.py와 같은 수식이다. 화면에서 채권 상세와 Trade Builder가 쓴다.
   두 구현이 같은 값을 내는지는 `node assets/bondmath.js check`로 확인한다. */
(function (root) {
  'use strict';
  const DAY = 86400000;
  // 날짜는 UTC 자정의 Date로만 다룬다 (시간대 때문에 하루가 밀리지 않도록)
  const D = (s) => (s instanceof Date ? s : new Date(String(s).slice(0, 10) + 'T00:00:00Z'));
  const ymd = (d) => d.toISOString().slice(0, 10);
  const days = (a, b) => Math.round((b - a) / DAY);
  const monthEndDay = (y, m) => new Date(Date.UTC(y, m + 1, 0)).getUTCDate();   // m: 0~11
  const isMonthEnd = (d) => d.getUTCDate() === monthEndDay(d.getUTCFullYear(), d.getUTCMonth());

  function shiftMonths(d, n, eom) {
    const k = d.getUTCFullYear() * 12 + d.getUTCMonth() + n;
    const y = Math.floor(k / 12), m = ((k % 12) + 12) % 12;
    const last = monthEndDay(y, m);
    return new Date(Date.UTC(y, m, eom ? last : Math.min(d.getUTCDate(), last)));
  }
  function addYears(d, n) {
    const y = d.getUTCFullYear() + n, m = d.getUTCMonth();
    return new Date(Date.UTC(y, m, Math.min(d.getUTCDate(), monthEndDay(y, m))));
  }
  function yearsBetween(d0, d1) {
    d0 = D(d0); d1 = D(d1);
    if (d1 < d0) return -yearsBetween(d1, d0);
    let n = d1.getUTCFullYear() - d0.getUTCFullYear();
    if (addYears(d0, n) > d1) n -= 1;
    const a = addYears(d0, n), b = addYears(d0, n + 1);
    return n + days(a, d1) / days(a, b);
  }
  function nextBusinessDay(d) {
    let x = new Date(D(d).getTime() + DAY);
    while (x.getUTCDay() === 0 || x.getUTCDay() === 6) x = new Date(x.getTime() + DAY);
    return x;
  }
  function couponDates(maturity, settle) {
    maturity = D(maturity); settle = D(settle);
    if (settle >= maturity) throw new Error('결제일이 만기 이후입니다');
    const eom = isMonthEnd(maturity);
    let k = Math.max(Math.floor(((maturity.getUTCFullYear() - settle.getUTCFullYear()) * 12 + maturity.getUTCMonth() - settle.getUTCMonth()) / 6), 0);
    while (shiftMonths(maturity, -6 * k, eom) > settle) k += 1;
    while (k > 0 && shiftMonths(maturity, -6 * (k - 1), eom) <= settle) k -= 1;
    return { prev: shiftMonths(maturity, -6 * k, eom), next: shiftMonths(maturity, -6 * (k - 1), eom), n: k, eom };
  }
  function frame(maturity, settle) {
    const c = couponDates(maturity, settle);
    c.w = days(D(settle), c.next) / days(c.prev, c.next);   // 다음 이자일까지 남은 기간 (반기 단위)
    return c;
  }
  function accrued(coupon, maturity, settle) {
    const c = couponDates(maturity, settle);
    return coupon / 2 * days(c.prev, D(settle)) / days(c.prev, c.next);
  }
  function cashflows(coupon, maturity, settle) {
    maturity = D(maturity);
    const f = frame(maturity, settle), out = [];
    for (let k = 0; k < f.n; k++) {
      out.push({ date: ymd(shiftMonths(maturity, -6 * (f.n - 1 - k), f.eom)), t: (f.w + k) / 2,
                 coupon: coupon / 2, principal: k === f.n - 1 ? 100 : 0 });
    }
    return out;
  }
  function dirtyFromYield(coupon, maturity, settle, y) {
    const f = frame(maturity, settle), c = coupon / 2, h = y / 200;
    if (f.n === 1) return (100 + c) / (1 + f.w * h);
    const v = 1 / (1 + h);
    let s = 0;
    for (let k = 0; k < f.n; k++) s += c * Math.pow(v, f.w + k);
    return s + 100 * Math.pow(v, f.w + f.n - 1);
  }
  function yieldFromPrice(coupon, maturity, settle, clean) {
    const target = clean + accrued(coupon, maturity, settle);
    const fn = (y) => dirtyFromYield(coupon, maturity, settle, y) - target;
    let y = coupon > 0 ? coupon : 3;
    for (let i = 0; i < 60; i++) {
      const fy = fn(y);
      if (Math.abs(fy) < 1e-11) return y;
      const h = 1e-5, d = (fn(y + h) - fn(y - h)) / (2 * h);
      if (d === 0) break;
      const step = fy / d;
      if (!(y - step > -50 && y - step < 200)) break;
      y -= step;
      if (Math.abs(step) < 1e-12) return y;
    }
    let lo = -50, hi = 200;
    for (let i = 0; i < 200; i++) {
      const mid = (lo + hi) / 2;
      if (fn(mid) > 0) lo = mid; else hi = mid;
    }
    return (lo + hi) / 2;
  }
  /* 가격(clean)이나 수익률(ytm) 하나를 주면 나머지와 위험 지표를 돌려준다. dv01PerM = 액면 100만당 1bp 가격 변화(달러). */
  function analytics(coupon, maturity, settle, given) {
    const ai = accrued(coupon, maturity, settle);
    const ytm = given.ytm != null ? given.ytm : yieldFromPrice(coupon, maturity, settle, given.clean);
    const dirty = dirtyFromYield(coupon, maturity, settle, ytm);
    const clean = given.clean != null ? given.clean : dirty - ai;
    const f = frame(maturity, settle), c = coupon / 2, h = ytm / 200;
    let mac, mod, conv;
    if (f.n === 1) {
      mac = f.w / 2; mod = mac / (1 + f.w * h); conv = 2 * Math.pow(f.w / 2, 2) / Math.pow(1 + f.w * h, 2);
    } else {
      const v = 1 / (1 + h);
      let s1 = 0, s2 = 0;
      for (let k = 0; k < f.n; k++) {
        const tau = f.w + k, pv = (c + (k === f.n - 1 ? 100 : 0)) * Math.pow(v, tau);
        s1 += tau * pv; s2 += tau * (tau + 1) * pv;
      }
      mac = s1 / dirty / 2; mod = mac * v; conv = s2 * v * v / dirty / 4;
    }
    return { clean, accrued: ai, dirty, ytm, mdur: mod, mac, conv, dv01PerM: dirty * mod, nCf: f.n };
  }
  const parModDur = (years, y) => (Math.abs(y) > 1e-9 ? (1 - Math.pow(1 + y / 200, -2 * years)) / (y / 100) : years);
  function interp(xs, ys, t) {
    if (t <= xs[0]) return ys[0];
    if (t >= xs[xs.length - 1]) return ys[ys.length - 1];
    for (let j = 0; j < xs.length - 1; j++) {
      if (xs[j] <= t && t <= xs[j + 1]) return ys[j] + (ys[j + 1] - ys[j]) * (t - xs[j]) / (xs[j + 1] - xs[j]);
    }
    return ys[ys.length - 1];
  }

  const api = { D, ymd, yearsBetween, nextBusinessDay, couponDates, accrued, cashflows, dirtyFromYield, yieldFromPrice,
                analytics, parModDur, interp };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    if (require.main === module && process.argv[2] === 'check') {       // 파이썬 기준값과 비교
      const ref = JSON.parse(require('child_process').execFileSync('python3', [require('path').join(__dirname, '..', 'pipeline', 'bondmath.py'), 'json']));
      let worst = 0;
      for (const r of ref) {
        const [cpn, mat, stl, px] = r.case;
        const a = analytics(cpn, mat, stl, { clean: px });
        const diffs = { ytm: a.ytm - r.ytm, accrued: a.accrued - r.accrued, dirty: a.dirty - r.dirty, mdur: a.mdur - r.mdur,
                        mac: a.mac - r.mac, conv: a.conv - r.conv, dv01: a.dv01PerM - r.dv01_per_1m, n: a.nCf - r.n_cf };
        const m = Math.max(...Object.values(diffs).map(Math.abs));
        worst = Math.max(worst, m);
        console.log(m < 1e-8 ? 'PASS' : 'FAIL', r.case.join(' '), '최대 차이', m.toExponential(2));
      }
      console.log('전체', worst < 1e-8 ? 'PASS' : 'FAIL');
      process.exit(worst < 1e-8 ? 0 : 1);
    }
  } else {
    root.BondMath = api;
  }
})(typeof window !== 'undefined' ? window : globalThis);
