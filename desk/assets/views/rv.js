/* 4. RV·전략 — 어디에 투자할까: 커브 밸류에이션, 종목 상대가치, 전략 스크리너, Trade Builder, 백테스터 */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const BM = window.BondMath;
  const BUCKETS = [['1-3', 0, 3], ['3-5', 3, 5], ['5-7', 5, 7], ['7-10', 7, 10], ['10-20', 10, 20], ['20+', 20, 1e9]];
  const bucketOf = (t) => (BUCKETS.find(([, lo, hi]) => t >= lo && t < hi) || BUCKETS[0])[0];
  const TY = { '2Y': 2, '3Y': 3, '5Y': 5, '7Y': 7, '10Y': 10, '20Y': 20, '30Y': 30 };

  window.DeskViews.rv = function (ctx) {
    const D = ctx.D, R = D.rv, S = R.screener, B = D.bonds, book = D.book;

    // ── 기간 프리미엄 ──
    const tp = ctx.lineOf([{ key: 'tp10', name: '10년', color: 'var(--s1)' }, { key: 'tp5', name: '5년', color: 'var(--s2)' }, { key: 'tp2', name: '2년', color: 'var(--s3)' }],
      { h: 230, unit: '%', zero: true, tipFmt: (v) => F.n(v, 2), aria: '만기별 기간 프리미엄' });
    const tp10 = R.tp.rows.find((r) => r.key === 'tp10');
    const y10 = D.us.heat.find((r) => r.tenor === '10Y');
    const tpCard = UI.card({ id: 'value', span: 'c6', title: '커브 밸류에이션 — 기간 프리미엄', cap: `${R.tp.source} · %`,
      body: [tp.chart, UI.table([{ label: '만기', align: 'l', get: (r) => r.label }, { label: '기간 프리미엄', get: (r) => r.level, fmt: (v) => F.n(v, 2) + '%' },
        { label: '1달', get: (r) => r.m1, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 25) }, { label: '1년', get: (r) => r.y1, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 50) },
        { label: 'z-score (3년)', get: (r) => r.z3y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) },
        { label: '3년 백분위', get: (r) => r.pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) }], { rows: R.tp.rows, dense: true })],
      alt: tp.alt,
      foot: tp10 && ok(R.tp.rn10) ? `모형은 10년 금리를 "앞으로 10년 단기금리 평균 예상 ${F.n(R.tp.rn10, 2)}%"와 "기간 프리미엄 ${F.n(tp10.level, 2)}%"로 나눕니다. 기간 프리미엄이 높을수록 장기채를 드는 보상이 크다는 뜻이지만, 모형 추정치라 수준보다 변화를 보는 편이 안전합니다.` : null });

    // ── 종목 상대가치 ──
    let rvCard, listCard = null;
    const arg = (b) => window.DeskBondArg(B, b);
    if (B.status === 'ok') {
      const list = B.list.filter((b) => ctx.matOk(b.ttm));
      const pts = list.map((b) => ({ x: b.ttm, y: b.ytm, r: b.otr ? 5 : 3, ring: !!b.otr, op: b.otr ? 1 : 0.6,
        color: b.otr ? 'var(--s2)' : b.old ? 'var(--s-mute)' : 'var(--s1)', data: b,
        tipTitle: `UST ${F.n(b.coupon, 3)}% ${b.maturity}${b.otr ? ' · 지표물' : ''}`,
        tipRows: [{ name: 'YTM', value: F.n(b.ytm, 3) + '%' }, { name: '커브 대비', value: F.bp(b.fit_bp, 1) }, { name: '수정듀레이션', value: F.n(b.mdur, 2) }] }));
      const ranked = list.filter((b) => !b.old && b.ttm >= 1 && ok(b.fit_bp)).sort((a, b) => b.fit_bp - a.fit_bp);
      const mini = (rows, label) => UI.table([{ label, align: 'l', get: (b) => b.maturity, fmt: (_, b) => `${F.n(b.coupon, 3)}% ${b.maturity}` },
        { label: 'YTM', get: (b) => b.ytm, fmt: (v) => F.n(v, 3) }, { label: '커브 대비', get: (b) => b.fit_bp, fmt: (v) => F.s(v, 1), heat: (v) => UI.heat(v, 8) }],
        { rows, dense: true, onRow: (b) => ctx.openBond(arg(b)) });
      rvCard = UI.card({ id: 'bonds', span: 'c6', title: '종목 상대가치', cap: `적합 커브 대비 금리차 (저평가·고평가) · 재무부 종가 ${B.price_date} · ${list.length}종목`,
        body: [UI.legend([{ name: '지표물', color: 'var(--s2)' }, { name: '2010년 이후 발행', color: 'var(--s1)' }, { name: '2010년 이전 발행', color: 'var(--s-mute)' }, { name: '적합 커브', color: 'var(--ink2)' }]),
               UI.scatter({ points: pts, curve: B.fit.curve, h: 250, xLabel: '잔존만기 (년)', yFmt: (v) => F.n(v, 2), xFmt: (v) => F.n(v, 0), onClick: (p) => ctx.openBond(arg(p.data)), aria: '잔존만기와 만기수익률' }),
               h('div', { cls: 'grid', style: 'margin-top:10px' }, h('div', { cls: 'c6' }, mini(ranked.slice(0, 5), '저평가 종목 (금리가 높음)')), h('div', { cls: 'c6' }, mini(ranked.slice(-5).reverse(), '고평가 종목 (금리가 낮음)')))],
        foot: `적합 커브는 ${B.fit.method}입니다. 점이나 줄을 누르면 채권 상세가 열립니다. 재무부 종가는 정부 계정용 공시 가격이라 시장 호가와 다를 수 있고, 쿠폰 차이에서 오는 금리 차이는 걸러내지 않았습니다.` });

      const all = B.list.filter((b) => ctx.matOk(b.ttm));
      const tbl = UI.table([{ label: '만기일', align: 'l', get: (b) => b.maturity }, { label: '쿠폰', get: (b) => b.coupon, fmt: (v) => F.n(v, 3) + '%' },
        { label: 'CUSIP', align: 'l', get: (b) => b.cusip, fmt: (v, b) => [v, b.otr ? [' ', h('span', { cls: 'pill acc' }, b.otr.replace('Y', '년'))] : null] },
        { label: '잔존만기', get: (b) => b.ttm, fmt: (v) => F.n(v, 2) }, { label: '가격', get: (b) => b.price, fmt: (v) => F.n(v, 3) },
        { label: 'YTM', get: (b) => b.ytm, fmt: (v) => F.n(v, 3) }, { label: '수정듀레이션', get: (b) => b.mdur, fmt: (v) => F.n(v, 2) },
        { label: '볼록성', get: (b) => b.conv, fmt: (v) => F.n(v, 1) }, { label: 'DV01', get: (b) => b.dv01, fmt: (v) => F.n(v, 0) },
        { label: '커브 대비', get: (b) => b.fit_bp, fmt: (v) => F.s(v, 1), heat: (v) => UI.heat(v, 8) },
        { label: '3개월 캐리', get: (b) => b.carry3m, fmt: (v) => F.s(v, 0) }, { label: '롤다운', get: (b) => b.roll3m, fmt: (v) => F.s(v, 0) }],
        { rows: all, dense: true, sortable: true, onRow: (b) => ctx.openBond(arg(b)) });
      tbl.style.maxHeight = '420px';
      tbl.style.overflowY = 'auto';
      listCard = UI.card({ id: 'list', span: 'c12', title: '종목 표', cap: `미국 이표 국채 ${all.length}종목 · 머리글을 누르면 정렬 · 줄을 누르면 채권 상세`, flush: true, body: tbl,
        foot: 'DV01은 액면 100만 달러당 달러, 캐리와 롤다운은 3개월 동안의 가격 기준 bp입니다.' });
    } else {
      rvCard = UI.card({ id: 'bonds', span: 'c6', title: '종목 상대가치', body: UI.empty('종목 종가를 받지 못했습니다', '재무부 FedInvest에서 종가를 받지 못해 종목별 비교를 만들지 못했습니다.') });
    }

    // ── 전략 스크리너 ──
    const out = S.outright.filter((o) => ctx.matOk(o.years));
    const legOk = (t) => t.legs.some((l) => ctx.matOk(TY[l] || 10));
    const spreadCols = (kindLabel) => [
      { label: kindLabel, align: 'l', get: (t) => t.label, fmt: (v, t) => [v, h('span', { cls: 'sub2' }, t.hint)] },
      { label: '수준', get: (t) => t.level, fmt: (v) => F.n(v, 0) + 'bp' },
      { label: '1주', get: (t) => t.w1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 15) }, { label: '1달', get: (t) => t.m1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 25) },
      { label: 'z-score (1년)', get: (t) => t.z1y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) }, { label: 'z-score (3년)', get: (t) => t.z3y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) },
      { label: '3년 범위 안 위치', align: 'c', sort: false, get: (t) => t.pct3y, fmt: (_, t) => UI.range(t.lo3y, t.hi3y, t.level, `3년 범위 ${F.n(t.lo3y, 0)} ~ ${F.n(t.hi3y, 0)}bp`) },
      { label: '3개월 캐리+롤다운', title: '금리가 그대로일 때 3개월 동안 벌거나 잃는 크기를 스프레드 bp로 나타낸 값', get: (t) => t.cr3m, fmt: (v) => F.s(v, 1) + 'bp', heat: (v) => UI.heat(v, 10) },
      { label: '1년 추이', align: 'c', sort: false, get: (t) => t.key, fmt: (_, t) => UI.spark(t.spark) }];
    const scrCard = UI.card({ id: 'screener', span: 'c12', title: '전략 스크리너', cap: `금리가 지금 그대로라면 ${S.horizon} 동안 · 조달 금리 SOFR ${F.n(S.repo, 2)}%`,
      body: [
        h('p', { cls: 'note', style: 'margin:0 0 4px;color:var(--ink);font-weight:600' }, '매수 (캐리·롤다운)'),
        UI.table([{ label: '전략', align: 'l', get: (o) => o.years, fmt: (_, o) => o.tenor.replace('Y', '년') + ' 매수' }, { label: '금리', get: (o) => o.yield, fmt: (v) => F.n(v, 2) + '%' },
          { label: '1달', get: (o) => o.m1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 30) }, { label: 'z-score (3년)', get: (o) => o.z3y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) },
          { label: '캐리', title: '(금리 − SOFR) × 3개월', get: (o) => o.carry, fmt: (v) => F.s(v, 1) }, { label: '롤다운', title: '3개월 짧아진 만기의 금리로 내려올 때의 가격 효과', get: (o) => o.roll, fmt: (v) => F.s(v, 1) },
          { label: '합계 (가격 bp)', get: (o) => o.total, fmt: (v) => F.s(v, 1), heat: (v) => UI.heat(v, 50) },
          { label: '손익분기 (금리 bp)', title: '금리가 이만큼 올라도 3개월 손익이 0', get: (o) => o.be, fmt: (v) => F.s(v, 1), heat: (v) => UI.heat(v, 12) }],
          { rows: out, dense: true, sortable: true }),
        h('p', { cls: 'note', style: 'margin:16px 0 4px;color:var(--ink);font-weight:600' }, '커브 (DV01 중립 스티프너 기준)'),
        UI.table(spreadCols('스프레드'), { rows: S.curves.filter(legOk), dense: true, sortable: true }),
        h('p', { cls: 'note', style: 'margin:16px 0 4px;color:var(--ink);font-weight:600' }, '버터플라이 (벨리 매수 기준, 윙은 DV01 절반씩)'),
        UI.table(spreadCols('버터플라이'), { rows: S.flies.filter(legOk), dense: true, sortable: true })],
      foot: '재무부 par 커브로 계산한 근사입니다. 버터플라이 수준은 2 × 벨리 − 두 윙이고, z-score가 높으면 벨리가 윙보다 싸다(금리가 높다)는 뜻입니다. 캐리+롤다운이 +면 그 포지션을 들고만 있어도 버는 쪽입니다. 지난 값이 싸 보인다고 해서 되돌아온다는 보장은 없습니다.' });

    // ── Trade Builder ──
    const settle = B.status === 'ok' ? B.settle : BM.ymd(BM.nextBusinessDay(D.meta.asof));
    let inst;
    if (B.status === 'ok') {
      inst = B.list.filter((b) => b.otr).map((b) => ({ key: b.otr, label: `${b.otr.replace('Y', '년')} · UST ${F.n(b.coupon, 3)}% ${b.maturity}`, coupon: b.coupon, maturity: b.maturity, price: b.price, accrued: b.accrued,
        ytm: b.ytm, mdur: b.mdur, dv01: b.dv01, ttm: b.ttm, cr: (b.carry3m || 0) + (b.roll3m || 0) }));
    } else {                                   // 종가가 없으면 par 금리로 만든 모형 종목
      inst = S.outright.map((o) => {
        const d0 = BM.D(settle), mat = BM.ymd(new Date(Date.UTC(d0.getUTCFullYear() + o.years, d0.getUTCMonth(), d0.getUTCDate())));
        const a = BM.analytics(o.yield, mat, settle, { ytm: o.yield });
        return { key: o.tenor, label: `${o.tenor.replace('Y', '년')} · 모형 종목 (쿠폰 ${F.n(o.yield, 2)}%)`, coupon: o.yield, maturity: mat, price: a.clean, accrued: a.accrued, ytm: o.yield, mdur: a.mdur, dv01: a.dv01PerM, ttm: o.years, cr: o.total };
      });
    }
    inst.sort((a, b) => a.ttm - b.ttm);
    const byKey = Object.fromEntries(inst.map((x) => [x.key, x]));
    const tb = { type: 'steep', a: byKey['2Y'] ? '2Y' : inst[0].key, b: byKey['10Y'] ? '10Y' : inst[inst.length - 1].key, c: byKey['30Y'] ? '30Y' : inst[inst.length - 1].key, size: 500 };
    const STRATS = { long: ['매수 (아웃라이트)', 1], steep: ['스티프너 (단기 매수 · 장기 매도)', 2], flat: ['플래트너 (단기 매도 · 장기 매수)', 2],
                     fly_long: ['버터플라이 · 벨리 매수', 3], fly_short: ['버터플라이 · 벨리 매도', 3] };
    const tbOut = h('div');
    const selOf = (key, label) => {
      const el = h('select', null, inst.map((x) => h('option', { value: x.key }, x.label)));
      el.value = tb[key];
      el.addEventListener('change', () => { tb[key] = el.value; drawTb(); });
      const lab = h('label', null, label, el);
      lab.dataset.leg = key;
      return lab;
    };
    const typeSel = h('select', null, Object.entries(STRATS).map(([k, v]) => h('option', { value: k }, v[0])));
    typeSel.value = tb.type;
    const sizeIn = h('input', { type: 'number', min: 100, step: 100, value: tb.size });
    const legA = selOf('a', '레그 1'), legB = selOf('b', '레그 2'), legC = selOf('c', '레그 3');
    typeSel.addEventListener('change', () => { tb.type = typeSel.value; drawTb(); });
    sizeIn.addEventListener('input', () => { tb.size = Math.max(0, Number(sizeIn.value) || 0); drawTb(); });

    function legsOf() {
      const A = byKey[tb.a], Bq = byKey[tb.b], C = byKey[tb.c];
      if (tb.type === 'long') return [[A, 1, '매수']];
      if (tb.type === 'steep' || tb.type === 'flat') {
        const [sh, lg] = A.ttm <= Bq.ttm ? [A, Bq] : [Bq, A], sgn = tb.type === 'steep' ? 1 : -1;
        return [[sh, sgn, sgn > 0 ? '매수' : '매도'], [lg, -sgn, sgn > 0 ? '매도' : '매수']];
      }
      const three = [A, Bq, C].sort((x, y) => x.ttm - y.ttm), sgn = tb.type === 'fly_long' ? 1 : -1;
      return [[three[0], -0.5 * sgn, sgn > 0 ? '매도' : '매수'], [three[1], sgn, sgn > 0 ? '매수' : '매도'], [three[2], -0.5 * sgn, sgn > 0 ? '매도' : '매수']];
    }
    function drawTb() {
      const nLeg = STRATS[tb.type][1];
      legA.firstChild.textContent = nLeg === 1 ? '종목' : nLeg === 2 ? '레그 1' : '레그 1 (윙)';
      legB.style.display = nLeg >= 2 ? '' : 'none';
      legB.firstChild.textContent = nLeg === 3 ? '레그 2 (벨리)' : '레그 2';
      legC.style.display = nLeg === 3 ? '' : 'none';
      legC.firstChild.textContent = '레그 3 (윙)';
      const legs = legsOf();
      const uniq = new Set(legs.map((l) => l[0].key));
      if (uniq.size < legs.length) { tbOut.replaceChildren(UI.empty('레그마다 다른 만기를 고르세요', '같은 종목이 두 번 들어가면 포지션이 상쇄됩니다.')); return; }
      const rows = legs.map(([x, w, side]) => {
        const par = Math.round((w * tb.size / x.dv01) * 1e6 / 1000) * 1000;
        const dirty = x.price + x.accrued;
        return { x, w, side, par, mv: par * dirty / 100, dv01: par / 1e6 * x.dv01, cr: par * dirty / 100 * x.cr / 1e4 };
      });
      const sum = (k) => rows.reduce((t, r0) => t + r0[k], 0);
      const reprice = (shifts) => rows.reduce((t, r0, i) => t + (BM.dirtyFromYield(r0.x.coupon, r0.x.maturity, settle, r0.x.ytm + shifts[i] / 100) - BM.dirtyFromYield(r0.x.coupon, r0.x.maturity, settle, r0.x.ytm)) / 100 * r0.par, 0);
      const tmin = Math.min(...rows.map((r0) => r0.x.ttm)), tmax = Math.max(...rows.map((r0) => r0.x.ttm));
      const slope = (bp) => rows.map((r0) => (tmax > tmin ? bp * (r0.x.ttm - tmin) / (tmax - tmin) : 0));
      const scen = [['평행 +25bp', rows.map(() => 25)], ['평행 −25bp', rows.map(() => -25)]];
      if (rows.length >= 2) scen.push(['스티프닝: 만기가 가장 긴 레그 +10bp', slope(10)], ['플래트닝: 만기가 가장 긴 레그 −10bp', slope(-10)]);
      if (rows.length === 3) scen.push(['벨리만 −5bp', [0, -5, 0]], ['벨리만 +5bp', [0, 5, 0]]);

      // 포트폴리오에 편입하면
      const add = {};
      rows.forEach((r0) => { const k = bucketOf(r0.x.ttm); add[k] = add[k] || { dv01: 0, mv: 0 }; add[k].dv01 += r0.dv01; add[k].mv += r0.mv; });
      const net = sum('dv01'), before = book.active_dur, after = (book.dv01 + net - book.dv01_b) / book.nav * 1e4;
      const shortBad = book.positions.filter((p) => add[p.id] && -add[p.id].mv > p.mv);
      const cash = sum('mv');
      const checks = [];
      checks.push(shortBad.length
        ? h('p', { cls: 'status crit' }, h('i'), `${shortBad.map((p) => p.label).join(', ')} 구간은 매도 금액이 보유액보다 커서 공매도가 필요합니다. 포트폴리오 운용 규칙(공매도 금지)으로는 이 규모로 편입할 수 없습니다.`)
        : h('p', { cls: 'status good' }, h('i'), '매도 레그는 그 구간 보유를 줄이는 것으로 충분합니다 (공매도 없음).'));
      if (cash > 1000) checks.push(h('p', { cls: 'status warn' }, h('i'), `순매수 금액 ${F.usd(cash)}만큼 다른 보유를 팔아야 합니다 (포트폴리오에는 현금과 레버리지가 없습니다).`));

      tbOut.replaceChildren(h('div', { cls: 'grid' },
        h('div', { cls: 'c7' },
          UI.table([{ label: '종목', align: 'l', get: (r0) => r0.x.label }, { label: '방향', align: 'c', get: (r0) => r0.side },
            { label: '액면', get: (r0) => r0.par, fmt: (v) => F.usd(Math.abs(v)) }, { label: '평가금액', get: (r0) => r0.mv, fmt: (v) => F.usdS(v) },
            { label: 'DV01', get: (r0) => r0.dv01, fmt: (v) => F.usdS(v) }, { label: '3개월 캐리+롤다운', get: (r0) => r0.cr, fmt: (v) => F.usdS(v) }],
            { rows, dense: true, onRow: (r0) => ctx.openBond({ title: r0.x.label, sub: 'Trade Builder에서 고른 종목', coupon: r0.x.coupon, maturity: r0.x.maturity, settle, price: r0.x.price, source: B.status === 'ok' ? `가격은 미 재무부 FedInvest ${B.price_date} 종가입니다.` : 'par 금리로 만든 모형 종목입니다.' }),
              foot: ['합계', '', '', F.usdS(cash), F.usdS(net), F.usdS(sum('cr'))] }),
          h('p', { cls: 'note' }, '액면은 1,000달러 단위로 맞췄습니다. 평가금액 +는 매수, −는 매도 금액입니다. 합계 DV01이 0에 가까우면 금리가 나란히 움직일 때 손익이 거의 없습니다.'),
          h('p', { cls: 'note', style: 'margin-top:12px;color:var(--ink);font-weight:600' }, '금리가 이렇게 움직이면'),
          UI.table([{ label: '시나리오', align: 'l', get: (x) => x[0] }, { label: '손익 (달러)', get: (x) => reprice(x[1]), fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, tb.size * 12) }], { rows: scen, dense: true })),
        h('div', { cls: 'c5' },
          h('p', { cls: 'note', style: 'margin:0 0 6px;color:var(--ink);font-weight:600' }, '포트폴리오에 편입하면'),
          UI.table([{ label: '구간', align: 'l', get: (p) => p.label }, { label: '포트폴리오 DV01', get: (p) => p.dv01, fmt: (v) => F.n(v, 0) }, { label: '벤치마크', get: (p) => p.dv01_b, fmt: (v) => F.n(v, 0) },
            { label: '거래', get: (p) => (add[p.id] ? add[p.id].dv01 : null), fmt: (v) => (ok(v) ? F.s(v, 0) : '') , heat: (v) => UI.heat(v, tb.size) },
            { label: '편입 후 BM 대비', get: (p) => p.dv01 + (add[p.id] ? add[p.id].dv01 : 0) - p.dv01_b, fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 600) }],
            { rows: book.positions, dense: true, foot: ['합계', F.n(book.dv01, 0), F.n(book.dv01_b, 0), F.s(net, 0), F.s(book.dv01 + net - book.dv01_b, 0)] }),
          h('p', { cls: 'note' }, `액티브 듀레이션: 지금 ${F.s(before, 2)}년 → 편입 후 ${F.s(after, 2)}년. DV01은 금리 1bp에 대한 달러 손익입니다.`), checks,
          h('p', { cls: 'note' }, '계산만 하고 저장하지 않습니다. 포트폴리오는 매달 말 판정 규칙대로만 움직입니다.'))));
    }
    drawTb();
    const tbCard = UI.card({ id: 'builder', span: 'c12', title: 'Trade Builder', cap: `DV01 기준 물량 계산 · 지표물 · 결제일 ${settle}`,
      body: [h('div', { cls: 'form' }, h('label', null, '전략', typeSel), legA, legB, legC, h('label', null, '리스크 규모: DV01 (달러 / bp)', sizeIn)), h('div', { style: 'height:14px' }), tbOut] });

    // ── 백테스터 ──
    const ser = book.series, i0 = UI.cut(ser.dates, ctx.st.period), xd = ser.dates.slice(i0);
    const rebase = (arr) => { if (!arr) return null; const b0 = arr[i0]; return arr.slice(i0).map((v) => (ok(v) ? v - b0 : null)); };
    const alt = book.alt || {};
    const btSeries = [{ name: '지금 규칙 (매크로 점수 5개)', color: 'var(--s1)', values: rebase(ser.excess_bp) }];
    if (ser.alt_excess_bp) btSeries.push({ name: `개선안 (${alt.name})`, color: 'var(--s2)', values: rebase(ser.alt_excess_bp) });
    const st = book.stats, rec = R.backtest.record;
    const seg = (x) => (x ? `${F.s(x.sum_bp, 0)}bp (t ${F.n(x.t, 2)}, ${x.win}/${x.on}개월 적중)` : '–');
    const rulesRows = [{ name: '지금 규칙', cum: st.excess_cum_bp, ann: st.excess_ann_bp, te: st.te_all_bp, ir: st.ir, train: alt.train && alt.train.cur, test: alt.test && alt.test.cur }];
    if (alt.name) rulesRows.push({ name: `개선안: ${alt.name}`, cum: alt.excess_cum_bp, ann: alt.excess_ann_bp, te: alt.te_bp, ir: alt.ir, train: alt.train && alt.train.alt, test: alt.test && alt.test.alt });
    const hitRows = [['Duration', rec.duration], ['Curve Slope', rec.slope], ['Curve Curvature', rec.curvature]].map(([name, x]) => ({ name, on: x.on, hits: x.hits, off: x.off, y: x.yardstick_ko }));
    const btCard = UI.card({ id: 'backtest', span: 'c12', title: '백테스터', cap: `규칙대로 운용했다면 · 벤치마크 대비 누적 초과수익 (bp) · ${xd[0]}부터`,
      body: [UI.line({ x: xd, series: btSeries, h: 240, zero: true, unit: 'bp', tipFmt: (v) => F.s(v, 1), aria: '규칙별 누적 초과수익' }),
        UI.table([{ label: '규칙', align: 'l', get: (x) => x.name }, { label: '누적 (2015~)', get: (x) => x.cum, fmt: (v) => F.bp(v, 0), heat: (v) => UI.heat(v, 100) },
          { label: '연율', get: (x) => x.ann, fmt: (v) => F.bp(v, 1) }, { label: '추적오차', get: (x) => x.te, fmt: (v) => F.n(v, 0) + 'bp' }, { label: '정보비율', get: (x) => x.ir, fmt: (v) => F.n(v, 2) },
          { label: `표본 내 (${R.backtest.split.start.slice(0, 4)}~${Number(R.backtest.split.test_start.slice(0, 4)) - 1})`, align: 'l', get: (x) => x.train, fmt: seg, sort: false },
          { label: `표본 외 (${R.backtest.split.test_start.slice(0, 4)}~)`, align: 'l', get: (x) => x.test, fmt: seg, sort: false }], { rows: rulesRows, dense: true }),
        h('p', { cls: 'note', style: 'margin:14px 0 4px;color:var(--ink);font-weight:600' }, '전략별 방향 적중 (다음 달 금리가 포지션 방향으로 움직였나)'),
        UI.table([{ label: '전략', align: 'l', get: (x) => x.name }, { label: '재는 잣대', align: 'l', get: (x) => x.y }, { label: '포지션을 든 달', get: (x) => x.on },
          { label: '맞힌 달', get: (x) => x.hits }, { label: '적중률', get: (x) => (x.on ? x.hits / x.on * 100 : null), fmt: (v, x) => (x.on >= 20 ? F.n(v, 0) + '%' : '표본 부족') },
          { label: '포지션 없던 달', get: (x) => x.off }], { rows: hitRows, dense: true })],
      alt: () => UI.seriesTable(xd, btSeries.map((s0) => ({ name: s0.name, values: s0.values, fmt: (v) => F.s(v, 1) })), 36),
      foot: [`t값이 2에 못 미치면 우연과 구분되지 않습니다. 두 규칙 모두 아직 그 수준입니다. 개선안은 결과를 본 뒤에 고른 규칙이라 표본 외 숫자도 온전한 검증이 아닙니다. 거래비용은 0으로 두었습니다. ${alt.rule || ''} `,
        h('a', { href: '../pipeline/model/combined.html' }, '2페이지 버전에서 자세히 보기')] });

    // 사실 요약 (두 번째 소제목)
    const bestCarry = out.slice().sort((a, b) => b.be - a.be)[0];
    const ext = S.curves.concat(S.flies).filter((t) => ok(t.z3y)).sort((a, b) => Math.abs(b.z3y) - Math.abs(a.z3y))[0];
    const extTxt = ext ? `${ext.label}${ext.kind === 'fly' ? ' Fly' : ''}가 3년 평균에서 가장 멀리(z ${F.s(ext.z3y, 1)}) 있습니다` : '';
    const lead = (bestCarry ? `금리가 그대로일 때 손익분기 금리폭이 가장 큰 구간은 ${bestCarry.tenor.replace('Y', '년')}(${F.s(bestCarry.be, 0)}bp)이고, ` : '') + extTxt;

    // 결론 한 줄: 평균에서 가장 먼 자리가 눈에 띄는가, 그리고 되돌아오길 기다리는 동안 벌거나 잃는가
    const yr = (l) => l.replace('Y', '년');
    let title;
    if (!ext || Math.abs(ext.z3y) < 1) title = '커브 모양은 지난 3년 평균 근처라, 눈에 띄게 싸거나 비싼 자리가 없습니다';
    else {
      const deg = Math.abs(ext.z3y) >= 2 ? '크게 ' : Math.abs(ext.z3y) >= 1.5 ? '' : '조금 ';
      let what, carry;
      if (ext.kind === 'fly') {                       // legs = [벨리, 윙, 윙]. z가 +면 벨리 금리가 높다(싸다)
        what = `${yr(ext.legs[0])}이 양옆(${yr(ext.legs[1])}·${yr(ext.legs[2])})보다 ${deg}${ext.z3y > 0 ? '싼' : '비싼'} 편입니다`;
        carry = ext.z3y > 0 ? ext.cr3m : -ext.cr3m;   // cr3m은 벨리 매수 기준
      } else {                                        // legs = [긴 만기, 짧은 만기]. cr3m은 스티프너 기준
        what = `${yr(ext.legs[1])}과 ${yr(ext.legs[0])} 사이 커브가 평소보다 ${deg}${ext.z3y > 0 ? '가파릅니다' : '평평합니다'}`;
        carry = ext.z3y > 0 ? -ext.cr3m : ext.cr3m;
      }
      const wait = carry > 0.5 ? `기다리는 동안에도 법니다 (3개월 ${F.s(carry, 1)}bp)` : carry < -0.5 ? `기다리는 동안은 잃습니다 (3개월 ${F.s(carry, 1)}bp)` : '기다리는 비용은 거의 없습니다';
      title = `${what}. 평균으로 되돌아오는 쪽에 걸면 ${wait}`;
    }
    return { title, lead, usOnly: true,
      sub: `근거: 커브 스프레드 6개와 버터플라이 6개 가운데 3년 z-score가 평균에서 가장 먼 것을 골랐습니다 (1 미만이면 눈에 띄는 자리가 없다고 봄). 싸 보인다고 되돌아온다는 보장은 없습니다. 10년 금리 ${y10 ? F.n(y10.level, 2) : '–'}% 가운데 기간 프리미엄은 ${tp10 ? F.n(tp10.level, 2) : '–'}%입니다.`,
      tabs: [['value', '커브 밸류에이션'], ['bonds', '종목 상대가치'], ['screener', '전략 스크리너'], ['builder', 'Trade Builder'], ['backtest', '백테스터'], ['list', '종목 표']],
      body: [tpCard, rvCard, scrCard, tbCard, btCard, listCard] };
  };
})();
