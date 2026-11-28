/* 크로스에셋 — 다른 시장은 뭐라 하나: 국면 보드, 관계 자세히, 해외 수요, 원자재·인플레, 변동성 지도, 전략 연결, 자산별 등락
   계산은 pipeline/desk/xasset.py가 한다(desk_data의 xa). 긴 설명은 <?> 단추 안에 둔다(views/xasset_text.js). */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const TONE = { good: '유리', bad: '불리', mid: '중립' };
  const tone = (t, text) => h('span', { cls: 'tone ' + t }, text || TONE[t]);
  const sgn = (v) => F.s(v, 2);

  /* 보드 한 줄의 60일 상관 1년 추이: ±0.2 띠 위에 선 */
  function corrSpark(vals) {
    const v = vals.filter(ok).slice(-52), w = 96, hh = 22;
    if (v.length < 2) return h('span', { cls: 'mute' }, '–');
    const X = (i) => 2 + (i / (v.length - 1)) * (w - 6), Y = (x) => 2 + (1 - (Math.max(-0.8, Math.min(0.8, x)) + 0.8) / 1.6) * (hh - 4);
    return UI.s('svg', { width: w, height: hh, viewBox: `0 0 ${w} ${hh}`, role: 'img', 'aria-label': '60일 상관 최근 1년' },
      UI.s('rect', { x: 0, y: Y(0.2), width: w, height: Y(-0.2) - Y(0.2), fill: 'var(--wash)' }),
      UI.s('line', { x1: 0, x2: w, y1: Y(0), y2: Y(0), stroke: 'var(--axis)' }),
      UI.s('path', { d: v.map((x, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(x).toFixed(1)).join(''), fill: 'none', stroke: 'var(--s1)', 'stroke-width': 1.4 }),
      UI.s('circle', { cx: X(v.length - 1), cy: Y(v[v.length - 1]), r: 2.5, fill: 'var(--ink)' }));
  }
  const names = (ps) => ps.map((p) => p.label.replace(/ \(.*\)$/, '')).join('·');

  window.DeskViews.xasset = function (ctx) {
    const D = ctx.D, X = D.xa, T = window.DeskXaText;
    if (!X || !X.pairs || !X.pairs.length) {
      return { title: '크로스에셋 자료가 아직 없습니다', usOnly: true, body: [UI.card({ span: 'c12', title: '크로스에셋', body: UI.empty('자료 없음', 'pipeline/desk/build_data.py를 다시 돌리면 채워집니다.') })] };
    }
    const P = Object.fromEntries(X.pairs.map((p) => [p.key, p])), xa = Object.fromEntries(D.xasset.map((r) => [r.key, r]));
    const sp = Object.fromEntries(D.spreads.map((r) => [r.key, r]));
    const good = X.pairs.filter((p) => p.tone === 'good'), bad = X.pairs.filter((p) => p.tone === 'bad');
    const tally = `국채에 유리 ${X.tally.good} · 불리 ${X.tally.bad} · 중립 ${X.tally.mid}`;
    if (!ctx.st.xaSel || !P[ctx.st.xaSel]) ctx.st.xaSel = 'sp';

    // ── 1. 국면 보드 ──
    const heatC = (v) => UI.heat(v, 0.8);
    const board = UI.card({ id: 'board', span: 'c12', title: '국면 보드', cap: '자산마다 국채와 어떤 짝으로 움직이는지 · 줄을 누르면 아래에서 자세히', flush: true,
      tools: [UI.scaleKey('−', '+'), UI.help('국면 보드 읽는 법', [
        ['무엇을 재나', '자산의 일별 변화와 국채 쪽 짝의 일별 변화가 얼마나 같이 움직였는지(상관, −1~+1)를 최근 60영업일과 250영업일(약 1년)로 잽니다. 국채 가격은 10년 금리 변화에 −를 붙인 값이라 +면 국채 강세입니다. 유가는 10년 기대인플레(BEI), 금은 실질금리 하락과 짝을 짓습니다.'],
        ['국면 이름', '상관이 ±0.2 안이면 불분명, 밖이면 부호에 따라 이름을 붙입니다(60개 표본의 상관은 우연만으로도 ±0.13쯤 흔들리기 때문). 이름은 60일 쪽을 따르고, 1년이 다른 칸이면 ‘전환 중’ 표시가 붙습니다.'],
        ['국채에 유리·불리', '국면이 지금 국채를 들고 있는 쪽에 유리한지입니다. 서로 겹치는 정보라 점수로 더하지 않고 개수만 셉니다.'],
        ['2016~21 → 2022~', '2022년 인플레 충격 앞뒤로 관계가 어떻게 바뀌었는지 보여 줍니다.']])],
      body: UI.table([
        { label: '자산', align: 'l', get: (p) => p.label, fmt: (v, p) => h('span', null, h('b', null, v), h('br'), h('small', { cls: 'mute' }, p.pair)) },
        { label: '60일', get: (p) => p.r60, fmt: sgn, heat: heatC },
        { label: '1년', get: (p) => p.r250, fmt: sgn, heat: heatC },
        { label: '2016~21 → 2022~', align: 'c', sort: false, get: (p) => p.post, fmt: (_, p) => `${sgn(p.pre)} → ${sgn(p.post)}` },
        { label: '60일 상관 1년 추이', align: 'c', sort: false, get: (p) => p.key, fmt: (_, p) => corrSpark(p.hist.r60) },
        { label: '지금 국면', align: 'c', sort: false, get: (p) => p.regime, fmt: (_, p) => h('span', null, tone(p.tone, p.regime.split(' · ')[0]), p.turn ? h('small', { cls: 'mute' }, ' 전환 중') : null) },
        { label: '국채에', align: 'c', sort: false, get: (p) => p.tone, fmt: (_, p) => tone(p.tone) }],
        { rows: X.pairs, dense: true, rowCls: (p) => (p.key === ctx.st.xaSel ? 'sel' : ''), onRow: (p) => { ctx.st.xaSel = p.key; if (location.hash === '#/xasset/detail') ctx.rerender(); else ctx.go('xasset', 'detail'); } }),
      foot: `상관은 일별 변화 기준, ${X.pairs[0].date} 종가까지. 구리는 Yahoo HG=F, MOVE는 Yahoo ^MOVE, 나머지는 FRED입니다.` });

    // ── 2. 관계 자세히 ──
    const p = P[ctx.st.xaSel], t = T[p.key] || {};
    const chips = h('div', { cls: 'chips', role: 'group', 'aria-label': '자산 고르기' }, X.pairs.map((q) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(q.key === p.key) }, q.label.replace(/ \(.*\)$/, ''));
      b.addEventListener('click', () => { ctx.st.xaSel = q.key; ctx.rerender('keep'); });
      return b;
    }));
    const marks = (t.marks || []).map(([d, label]) => ({ i: p.hist.d.findIndex((x) => x >= d), label })).filter((m) => m.i >= 0);
    const chart = UI.line({ x: p.hist.d, h: 230, unit: '', tipFmt: sgn, yFmt: (v) => F.s(v, 1), aria: p.pair + ' 상관 추이', marks,
      refs: [{ y: X.th }, { y: -X.th }], zero: true,
      series: [{ name: '60일 상관', color: 'var(--s1)', values: p.hist.r60, width: 1.6 }, { name: '1년 상관', color: 'var(--s-mute)', values: p.hist.r250 }] });
    const tiles = [
      UI.tile({ lab: '60일 상관', val: sgn(p.r60), note: `한 달 전 ${sgn(p.r60_1m)}` }),
      UI.tile({ lab: '1년 상관', val: sgn(p.r250) }),
      UI.tile({ lab: '2016~21 → 2022~', val: `${sgn(p.pre)} → ${sgn(p.post)}` })];
    if (p.key === 'sp') tiles.push(UI.tile({ lab: '‘둘 다 손실’ 날', val: X.stockbond.both_loss, unit: `/${X.stockbond.n}일`, note: '주가↓·금리↑' }),
      UI.tile({ lab: '‘헤지 성공’ 날', val: X.stockbond.hedge, unit: `/${X.stockbond.n}일`, note: '주가↓·금리↓' }));
    const detail = UI.card({ id: 'detail', span: 'c12', title: '관계 자세히 · ' + p.label, cap: p.pair + ' · 2016년부터, 점선은 과거 사례',
      tools: [UI.help(p.label + ' — 국채와의 관계', [['작동 원리', t.how], ['과거 사례', h('span', null, (t.past || []).map((x) => h('span', { style: 'display:block' }, '· ' + x)))],
        ['전략에 주는 의미', t.strat], ['보는 지표 · 경보', t.watch]])],
      body: [chips, UI.concl(h('span', null, '지금 ', tone(p.tone, p.regime), p.turn ? h('small', { cls: 'mute' }, ' (1년 기준과 달라 전환 중)') : null),
        (window.DeskXaMean[p.regime] || '') + '. 설명은 오른쪽 위 ? 단추에 있습니다.'),
        h('div', { cls: 'xgrid' }, chart, h('div', { cls: 'tiles', style: 'grid-template-columns:repeat(auto-fill,minmax(150px,1fr))' }, tiles))] });

    // ── 3. 해외 수요 ──
    const pk = X.pickup, lastOk = (a) => { for (let i = a.length - 1; i >= 0; i--) if (ok(a[i])) return [a[i], pk.d[i]]; return [null, null]; };
    const [jp, jpD] = lastOk(pk.jp), [de, deD] = lastOk(pk.de);
    const fx = UI.card({ id: 'fx', span: 'c6', title: '해외 수요', cap: '환헤지 후 미 10년 금리 − 자국 10년 금리 (%p, 월)',
      tools: [UI.help('환헤지 후 금리란', [['왜 보나', '일본은 미 국채 최대 해외 보유국이고, 일본·유럽 기관은 환위험을 없애려 환헤지를 하고 삽니다. 헤지 비용은 대략 두 나라 단기금리 차이입니다.'],
        ['계산', '환헤지 후 미 10년 금리 = 미 10년 − (미 3개월 − 자국 3개월). 여기서 자국 10년 금리를 뺀 값(픽업)이 0보다 작으면, 헤지까지 하면 자국 국채보다 덜 벌어 미 국채를 살 이유가 약합니다.'],
        ['채권에 주는 의미', '픽업이 음수로 오래가면 장기물 해외 수요가 줄어 기간 프리미엄을 밀어 올립니다(수급·기간프리미엄 필라). OECD 월별 금리라 1~2달 늦고, 정확한 선물환 비용이 아니라 근사치입니다.']])],
      body: [UI.concl(ok(jp) ? `일본 투자자: 환헤지한 미 국채가 일본 국채보다 ${F.n(Math.abs(jp), 2)}%p ${jp < 0 ? '덜' : '더'} 줍니다` : '일본 자료가 없습니다',
        ok(jp) && jp < 0 ? '일본 자금이 미 국채를 살 이유가 약합니다' : null),
        UI.line({ x: pk.d, h: 190, unit: '%p', zero: true, tipFmt: (v) => F.s(v, 2), aria: '환헤지 후 픽업',
          series: [{ name: '일본 투자자', color: 'var(--s2)', values: pk.jp }, { name: '독일(유로) 투자자', color: 'var(--s3)', values: pk.de }] }),
        h('div', { cls: 'tiles', style: 'margin-top:8px' },
          UI.tile({ lab: `일본 (${F.ym(jpD)})`, val: F.s(jp, 2), unit: '%p' }), UI.tile({ lab: `독일 (${F.ym(deD)})`, val: F.s(de, 2), unit: '%p' }),
          xa.usdjpy ? UI.tile({ lab: '엔/달러', val: F.n(xa.usdjpy.level, 1), deltas: [{ k: '1주', v: F.s(xa.usdjpy.w1, 1) + '%', raw: xa.usdjpy.w1 }] }) : null)] });

    // ── 4. 원자재·인플레 ──
    const O = X.oil, G = X.gold;
    const oilTxt = O.shock ? `유가 충격 (${O.wti_m1 > 0 ? '상승 · 국채에 불리' : '하락 · 국채에 유리'})` : '유가 충격 없음';
    const cmdty = UI.card({ id: 'cmdty', span: 'c6', title: '원자재·인플레', cap: '유가 → 기대인플레, 금 → 실질금리, 구리 → 경기',
      tools: [UI.help('원자재와 국채', [['유가', T.wti.how], ['금', T.gold.how], ['구리', T.cu.how],
        ['유가 충격 기준', '유가 1달 ±15% 그리고 5년 BEI가 같은 방향으로 ±10bp 이상.']])],
      body: [UI.concl(oilTxt, `유가 1달 ${F.s(O.wti_m1, 1)}%, 5년 BEI 1달 ${F.bp(O.bei5_m1)}`),
        h('div', { cls: 'xgrid', style: 'grid-template-columns:1fr 1fr' },
          h('div', null, h('p', { cls: 'note' }, 'WTI (달러, 1년)'), UI.line({ x: O.d, h: 110, legend: false, series: [{ name: 'WTI', color: 'var(--s4)', values: O.wti }], tipFmt: (v) => F.n(v, 1) }),
            h('p', { cls: 'note' }, '10년 BEI (%)'), UI.line({ x: O.d, h: 110, legend: false, series: [{ name: '10년 BEI', color: 'var(--s1)', values: O.bei10 }], tipFmt: (v) => F.n(v, 2) })),
          h('div', null, h('p', { cls: 'note' }, `금 × 10년 실질금리 (월말) · 수준 상관 ${sgn(G.lvl_pre)} → ${sgn(G.lvl_post)}`),
            UI.scatter({ h: 250, xLabel: '실질금리 %', yFmt: (v) => F.n(v / 1000, 1) + 'k', aria: '금과 실질금리',
              points: G.pts.map(([x, y, yr]) => ({ x, y, r: 3, color: yr >= 2022 ? 'var(--s2)' : 'var(--s-mute)', tipTitle: String(yr), tipRows: [{ name: '실질금리', value: F.n(x, 2) + '%' }, { name: '금', value: F.n(y, 0) }] })),
              labels: [{ text: '회색 2016~21 · 주황 2022~', top: true }] }))),
        X.cg ? h('p', { cls: 'note' }, `구리/금 비율이 말하는 10년 금리 ${F.n(X.cg.y10_fair, 2)}% (실제 ${F.n(X.cg.y10, 2)}%) · 3년 상관 ${F.n(X.cg.corr3y, 2)}${Math.abs(X.cg.corr3y) < 0.3 ? ', 설명력이 낮아 참고만' : ''}`) : null] });

    // ── 5. 변동성 지도 ──
    const V = X.vol, hiV = V.now[0] >= V.p80[0], hiM = V.now[1] >= V.p80[1];
    const quad = hiV && hiM ? '동반 스트레스' : hiV ? '주식만 불안' : hiM ? '채권만 불안' : '평온';
    const vol = UI.card({ id: 'vol', span: 'c6', title: '변동성 지도', cap: 'VIX × MOVE · 최근 3년 · 선은 각각 3년 80%분위',
      tools: [UI.help('변동성 지도 읽는 법', [['네 칸', '평온(둘 다 낮음): 캐리·RV가 잘 되는 환경. 주식만 불안: 보통 국채 강세. 채권만 불안: 금리 경로가 불확실해 듀레이션·캐리 축소. 동반 스트레스: 유동성 경색, 국채도 팔릴 수 있어 신규 RV 중단.'],
        ['VIX', T.vix.how], ['MOVE', T.move.how], ['MOVE 대체값', `MOVE가 끊기면 10년 금리 20일 실현변동성(지금 ${F.n(V.rv20, 0)}bp)으로 대신합니다. 둘의 상관 ${F.n(V.rv_corr, 2)}.`]])],
      body: [UI.concl(`지금은 ‘${quad}’ 칸입니다`, `VIX ${F.n(V.now[0], 1)} (3년 ${F.n(V.pct[0], 0)}%분위) · MOVE ${F.n(V.now[1], 0)} (${F.n(V.pct[1], 0)}%분위, 경계 ${F.n(V.p80[1], 0)})`),
        UI.scatter({ h: 260, xLabel: 'VIX', aria: 'VIX와 MOVE', xRefs: [V.p80[0]], yRefs: [V.p80[1]],
          labels: [{ text: '채권만 불안', top: true }, { text: '동반 스트레스', top: true, right: true }, { text: '평온' }, { text: '주식만 불안', right: true }],
          points: V.pts.map(([x, y]) => ({ x, y, r: 2.5, color: 'var(--s-mute)', op: 0.6, tipTitle: 'VIX · MOVE', tipRows: [{ name: 'VIX', value: F.n(x, 1) }, { name: 'MOVE', value: F.n(y, 0) }] }))
            .concat([{ x: V.now[0], y: V.now[1], r: 6, color: 'var(--s2)', op: 1, ring: true, tipTitle: '오늘 ' + V.date, tipRows: [{ name: 'VIX', value: F.n(V.now[0], 1) }, { name: 'MOVE', value: F.n(V.now[1], 0) }] }]) })] });

    // ── 6. 전략 연결 ──
    const act = D.book.active_dur, eqM = xa.sp500 ? xa.sp500.m1 : null, hyM = sp.oas_hy ? sp.oas_hy.m1 : null;
    const support = P.sp && P.sp.tone === 'good' && ((ok(eqM) && eqM <= -5) || (ok(hyM) && hyM >= 50));
    const against = P.sp && P.sp.tone === 'bad' && ok(eqM) && eqM <= -5;
    const caution = [P.wti, P.move, P.gold].filter((q) => q && q.tone === 'bad').map((q) => q.label.replace(/ \(.*\)$/, ''));
    const long = act > 0.03, short = act < -0.03;
    let dur;
    if (long && against || short && support) dur = ['bad', '충돌', '크기 절반 검토 (방향은 그대로)'];
    else if (long && support) dur = caution.length ? ['mid', '부분 일치', `롱 유지, 늘리지 않음 (${caution.join('·')} 불리)`] : ['good', '일치', '롱 유지'];
    else dur = ['mid', '중립', support ? '크로스에셋은 롱 쪽' : against ? '크로스에셋은 숏 쪽' : '뚜렷한 신호 없음'];
    const fund = (ok(jp) && jp < 0) || (P.gold && P.gold.tone === 'bad');
    const curve = O.shock && O.wti_m1 > 0 ? ['bad', '주의', '유가 충격: 벨리 비중확대 절반'] : ['mid', '참고', (O.shock ? '유가 급락은 벨리에 유리. ' : '') + (fund ? '재원은 20~30년에서 (장기 수요 약함)' : '특이 신호 없음')];
    const carry = hiM || quad === '동반 스트레스' ? ['bad', '축소', 'MOVE 80%분위 이상'] : ['good', '유지', `MOVE ${F.n(V.now[1], 0)} < 경계 ${F.n(V.p80[1], 0)}`];
    const liq = quad === '동반 스트레스' && ((xa.dxy && xa.dxy.m1 >= 3) || (xa.usdjpy && xa.usdjpy.w1 <= -3));
    const rv = liq ? ['bad', '신규 중단', '동반 스트레스 + 달러·엔 급변'] : ['good', '허용', '유동성 경색 신호 없음'];
    const strat = UI.card({ id: 'strategy', span: 'c6', title: '전략 연결', cap: '크로스에셋은 방향을 정하지 않고, 하우스 뷰를 확인하고 크기를 조절합니다', flush: true,
      tools: [UI.help('전략 연결 규칙', [
        ['듀레이션', '지금 포트폴리오의 액티브 듀레이션과 비교합니다. 주식-국채가 성장 주도이면서 주가 1달 −5% 이하나 하이일드 1달 +50bp 이상이면 롱 지지. 인플레 주도이면서 주가 −5% 이하면 롱에 반대(충돌 → 크기 절반 검토). 유가·MOVE·금이 불리하면 롱을 늘리지 않습니다.'],
        ['커브', '유가 상승 충격이면 벨리 비중확대 절반. 일본 픽업이 음수이거나 금이 실질금리와 분리되면 재원을 20~30년에서.'],
        ['캐리 & 롤다운', 'MOVE가 3년 80%분위 이상이거나 동반 스트레스면 축소.'],
        ['상대가치', '동반 스트레스이면서 달러 1달 +3% 이상이나 엔/달러 1주 −3% 이하면 신규 진입 중단.']])],
      body: UI.table([{ label: '전략', align: 'l', get: (r) => r[0], fmt: (v) => h('b', null, v) },
        { label: '판정', align: 'c', sort: false, get: (r) => r[1][1], fmt: (_, r) => tone(r[1][0], r[1][1]) },
        { label: '이유·제안', align: 'l', sort: false, get: (r) => r[1][2] }],
        { rows: [['듀레이션', dur], ['커브', curve], ['캐리 & 롤다운', carry], ['상대가치', rv]], dense: true }),
      foot: `지금 액티브 듀레이션 ${F.s(act, 2)}년 기준.` });

    // ── 7. 자산별 등락 (시장 모니터에서 옮겨 옴) ──
    const pc = (label, key, max) => ({ label, get: (r) => r[key], fmt: (v, r) => (r.pct ? F.s(v, 2) + '%' : F.s(v, 1)), heat: (v, r) => UI.heat(v, r.pct ? max : max * 3) });
    const table = UI.card({ id: 'table', span: 'c12', title: '자산별 등락', cap: '주식·통화·원자재는 등락률(%), 변동성 지수는 포인트 변화', flush: true,
      tools: [UI.scaleKey('내림', '오름')],
      body: UI.table([{ label: '자산', align: 'l', get: (r) => r.label },
        { label: '수준', get: (r) => r.level, fmt: (v, r) => F.n(v, v >= 1000 ? 0 : 2) + (r.unit ? ' ' + r.unit : '') },
        pc('1일', 'd1', 2.5), pc('1주', 'w1', 5), pc('1달', 'm1', 8), pc('연초 이후', 'ytd', 20), pc('1년', 'y1', 25),
        { label: '국채 가격과의 상관 (60일)', title: '최근 60영업일 일별 변화의 상관. +면 국채 가격과 같은 방향(금리가 내리는 날 오름)', get: (r) => (ok(r.corr60) ? -r.corr60 : null), fmt: sgn, heat: (v) => UI.heat(v, 0.8) },
        { label: '1년 추이', align: 'c', sort: false, get: (r) => r.key, fmt: (_, r) => UI.spark(r.spark) },
        { label: '기준일', get: (r) => r.date, fmt: (v) => F.md(v) }],
        { rows: D.xasset, dense: true, group: (r) => r.group }),
      foot: '원/달러, 엔/달러가 오르면 달러 강세입니다. 금·구리·KOSPI·MOVE는 Yahoo Finance, 나머지는 FRED 값입니다.' });

    const title = good.length && bad.length ? `${F.josa(names(good), '은', '는')} 국채에 유리하게, ${F.josa(names(bad), '은', '는')} 불리하게 움직이고 있습니다`
      : bad.length ? `${F.josa(names(bad), '이', '가')} 국채에 불리한 국면입니다` : good.length ? `${F.josa(names(good), '이', '가')} 국채에 유리한 국면입니다` : '크로스에셋에서 뚜렷한 신호가 없습니다';
    return { title, usOnly: true,
      lead: `${X.pairs.length}개 관계 중 ${tally}. 주식-국채 60일 상관 ${sgn(P.sp && P.sp.r60)}, 1년 ${sgn(P.sp && P.sp.r250)}`,
      sub: `상관은 일별 변화 기준이고 ±${X.th}를 넘어야 국면 이름이 붙습니다. 자세한 설명은 카드마다 오른쪽 위 ? 단추에 있습니다. 숫자는 ${X.pairs[0].date} 종가 기준입니다.`,
      tabs: [['board', '국면 보드'], ['detail', '관계 자세히'], ['fx', '해외 수요'], ['cmdty', '원자재·인플레'], ['vol', '변동성'], ['strategy', '전략 연결'], ['table', '자산별 등락']],
      body: [board, detail, fx, cmdty, vol, strat, table] };
  };
})();
