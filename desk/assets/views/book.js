/* 6. 포트폴리오·리스크 — 운용 Book 관리 화면.
   안쪽 탭 순서가 곧 업무 순서다: 개요 → 손익 → 포지션 → 리스크 → 매매 검토 → 시나리오 → 거래 내역 → 성과.
   주소는 #/book/<탭>. 한 번에 한 탭의 카드만 그린다. */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const SLOPE = { none: '', steepener: '스티프너', flattener: '플래트너' }, CURV = { none: '', bullet: '불릿' };
  const posTxt = (p) => {
    if (!p) return '–';
    const [d, sl, cv] = Array.isArray(p) ? p : [p.dur, p.slope, p.curv];
    return [d ? `Duration ${F.s(d, 2)}년` : 'Duration 중립', SLOPE[sl], CURV[cv]].filter(Boolean).join(' · ');
  };
  const TABS = [['overview', '개요'], ['pnl', '손익'], ['positions', '포지션'], ['risk', '리스크'], ['trade', '매매 검토'], ['scenario', '시나리오'], ['blotter', '거래 내역'], ['perf', '성과']];
  // 예전 주소(#/book/krd 등)로 들어와도 맞는 탭을 연다
  const OLD = { krd: 'positions', compose: 'positions', exposure: 'positions', limit: 'risk', adjust: 'trade', stress: 'scenario', trades: 'blotter', attribution: 'perf', months: 'perf' };
  const COST_BP = 0.25;      // 매매 검토에 쓰는 거래비용 가정: 금리 0.25bp (매수·매도 호가 차이의 절반)

  window.DeskViews.book = function (ctx) {
    const D = ctx.D, B = D.book, S = B.stats, R = B.risk, V = R.var, L = R.limits, st = ctx.st;
    const want = (location.hash.split('/')[2] || '').split('?')[0];
    const tab = TABS.some(([id]) => id === want) ? want : OLD[want] || 'overview';
    const kv = (items, cls) => h('dl', { cls: 'kv' + (cls ? ' ' + cls : '') }, items.map(([k, v, u]) => h('div', null, h('dt', null, k), h('dd', null, v, u ? h('small', null, u) : null))));
    const seg = (items, cur, pick) => h('span', { style: 'display:inline-flex;gap:4px;white-space:nowrap' }, items.map(([key, text]) => {
      const b = h('button', { cls: 'mini', type: 'button', 'aria-pressed': String(cur === key) }, text);
      b.dataset.k = String(key);
      b.addEventListener('click', () => { b.parentNode.querySelectorAll('[data-k]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); pick(key); });
      return b;
    }));
    const ex = (k) => B.perf[k].ex_bp;
    const BK = B.positions, K = B.krd, tot = (a) => a.reduce((t, v) => t + v, 0);
    const sumRow = (k) => K.keys.map((_, j) => K.rows.reduce((t, x) => t + x[k][j], 0));
    const krP = sumRow('p'), krB = sumRow('b'), krA = krP.map((v, j) => v - krB[j]);
    const ranked = K.keys.map((k, j) => [k, krA[j]]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

    // ── 위험 한도: 지표마다 현재 수준, 한도, 소진율, 남은 여유 ──
    const te = R.te_exante_bp, bud = R.budget, teLim = bud[1];
    const varLim = teLim / Math.sqrt(252) * 1.645;                       // 추적오차 한도를 하루 95% 손실로 바꾼 값
    const loss = (v) => Math.max(0, -v);
    const LIM = [
      { name: '사전 추적오차', cur: te, lim: teLim, unit: 'bp / 년', show: F.n(te, 0), note: `목표 범위 ${bud[0]}~${bud[1]}bp` },
      { name: '상대 VaR (1일, 95%)', cur: V.rel_95_bp, lim: varLim, unit: 'bp', show: F.n(V.rel_95_bp, 1), note: '추적오차 한도를 하루 손실로 바꾼 값' },
      { name: '이번 달 손실', cur: loss(ex('mtd')), lim: Math.abs(L.month_bp), unit: 'bp', show: F.bp(ex('mtd'), 1), note: '벤치마크 대비' },
      { name: '올해 손실', cur: loss(ex('ytd')), lim: Math.abs(L.year_bp), unit: 'bp', show: F.bp(ex('ytd'), 1), note: '벤치마크 대비' },
    ].map((x) => Object.assign(x, { use: x.cur / x.lim, room: Math.max(0, x.lim - x.cur) }));
    const level = (u) => (u >= 1 ? ['bad', '한도 초과', 'var(--crit)'] : u >= L.warn ? ['mid', '주의', 'var(--warn)'] : ['good', '정상', 'var(--good)']);
    const limTable = (full) => UI.table([{ label: '지표', align: 'l', get: (x) => x.name },
      { label: '현재', get: (x) => x.cur, fmt: (_, x) => x.show },
      { label: '한도', get: (x) => x.lim, fmt: (v, x) => F.n(v, x.lim < 20 ? 1 : 0) + (full ? ' ' + x.unit.replace(' / 년', '') : '') },
      { label: '소진율', align: 'l', get: (x) => x.use, fmt: (v) => [h('span', { cls: 'limbar' }, h('i', { style: `width:${Math.min(100, v * 100).toFixed(0)}%;background:${level(v)[2]}` })), F.n(v * 100, 0) + '%'] },
]
      .concat(full ? [{ label: '남은 여유', get: (x) => x.room, fmt: (v) => F.n(v, 1) + 'bp' }, { label: '금액', title: '남은 여유를 NAV에 곱한 값', get: (x) => x.room / 1e4 * B.nav, fmt: (v) => F.usd(v) }, { label: '기준', align: 'l', get: (x) => x.note }] : [])
      .concat([{ label: '상태', align: 'l', get: (x) => x.use, fmt: (v) => h('span', { cls: 'verdict ' + level(v)[0] }, h('i'), level(v)[1]) }]), { rows: LIM, dense: true });
    const worst = LIM.slice().sort((a, b) => b.use - a.use)[0];
    const limConcl = worst.use >= 1 ? `${worst.name}이 한도를 넘었습니다` : worst.use >= L.warn ? `${worst.name}이 한도의 ${F.n(worst.use * 100, 0)}%까지 찼습니다`
      : `모든 한도에 여유가 있습니다. 가장 많이 쓴 것은 ${worst.name} ${F.n(worst.use * 100, 0)}%입니다`;

    // ── 손익: 리밸런싱 이전(실현)과 이후(미실현) ──
    const ser = B.series, iAt = (d) => { let i = ser.dates.length - 1; while (i > 0 && ser.dates[i] > d) i--; return i; };
    const navDec = ser.nav_p[iAt(B.decision_date)], navYE = ser.nav_p[iAt(`${Number(B.asof.slice(0, 4)) - 1}-12-31`)];
    const unreal = B.nav - navDec, realized = navDec - navYE;

    // ── 손익 설명 자료: 하루 손익을 캐리, 롤다운, 금리 변화, 볼록성으로 ──
    const E = B.explain && B.explain.days.length ? B.explain : null;
    // 금리 변화를 수준(모든 만기가 같이 움직인 몫)과 기울기(만기가 길수록 더 움직인 몫)로: 만기 키 금리 변화를 log(만기)에 직선으로 맞춘다
    const lx = E ? E.keys.map((k) => Math.log(parseFloat(k))) : [], lxm = lx.length ? tot(lx) / lx.length : 0, lxx = lx.reduce((t, x) => t + (x - lxm) ** 2, 0);
    const lsc = (d, q) => {
      const a = tot(d.dy) / d.dy.length, b = d.dy.reduce((t, y, j) => t + (lx[j] - lxm) * y, 0) / lxx;
      const lev = -tot(q.krd) * a, slo = -q.krd.reduce((t, kd, j) => t + kd * b * (lx[j] - lxm), 0);
      return [lev, slo, tot(q.k) - lev - slo];
    };
    const explainRows = (days, mode) => {
      const acc = (f) => days.reduce((t, d) => t + f(d), 0), n = days.length;
      const row = (g, name, pick, more) => Object.assign({ g, name, usd: acc((d) => pick(d.p, d) * d.nav_p / 1e4), p: acc((d) => pick(d.p, d)), b: acc((d) => pick(d.b, d)) }, more);
      const rate = mode === 'key'
        ? E.keys.map((k, j) => row('금리가 움직여서', k, (q) => q.k[j], { dy: acc((d) => d.dy[j]), dv01: acc((d) => d.p.krd[j] * d.nav_p / 1e4) / n }))
        : [row('금리가 움직여서', '수준', (q, d) => lsc(d, q)[0]), row('금리가 움직여서', '기울기', (q, d) => lsc(d, q)[1]), row('금리가 움직여서', '그 밖의 모양 변화', (q, d) => lsc(d, q)[2])];
      return { rate, rows: [row('시간이 흘러서', '캐리', (q) => q.c), row('시간이 흘러서', '롤다운', (q) => q.r)].concat(rate, [row('금리가 움직여서', '볼록성 등', (q) => q.x)]) };
    };
    const eLast = E ? E.days[E.days.length - 1] : null;
    const WIN = E ? { d: 1, w: Math.min(5, E.days.length), m: E.days.filter((d) => d.date.slice(0, 7) === eLast.date.slice(0, 7)).length } : {};
    const pnlText = (win) => {
      const days = E.days.slice(-WIN[win]), n = days.length, { rate, rows } = explainRows(days, 'ls');
      const total = tot(rows.map((r) => r.usd)), rt = tot(rate.map((r) => r.usd)), cr = rows[0].usd + rows[1].usd, act = tot(rows.map((r) => r.p - r.b));
      const when = win === 'd' ? F.kdate(eLast.date) : win === 'w' ? `최근 ${n}영업일` : `${F.mon(eLast.date)} 들어`;
      const why = Math.abs(rt) >= Math.abs(cr) ? `대부분 금리가 ${rt > 0 ? '내려서 번' : '올라서 잃은'} 것입니다` : '금리 변화보다 캐리가 더 컸습니다';
      return { head: `${when} 손익은 ${F.usdS(total)}이고, ${why}`,
        detail: `캐리·롤다운 ${F.usdS(cr)} · 금리 수준 ${F.usdS(rate[0].usd)} · 기울기 ${F.usdS(rate[1].usd)} · 벤치마크 대비 ${F.bp(act, 1)}` };
    };

    const cards = [];
    // ════════ 개요 ════════
    if (tab === 'overview') {
      const useTe = te / teLim;
      cards.push(h('div', { cls: 'tiles c12' },
        UI.tile({ lab: '순자산 (NAV)', val: F.usd(B.nav), note: `벤치마크 ${F.usd(B.nav_bm)}`, hero: true }),
        UI.tile({ lab: '일간 손익', val: F.usdS(B.pnl_d1_usd), note: `벤치마크 대비 ${F.bp(ex('d1'), 1)}` }),
        UI.tile({ lab: '이번 달 초과수익', val: F.s(ex('mtd'), 1), unit: 'bp', note: `포트폴리오 ${F.s(B.perf.mtd.p, 2)}%` }),
        UI.tile({ lab: '올해 초과수익', val: F.s(ex('ytd'), 0), unit: 'bp', note: `포트폴리오 ${F.s(B.perf.ytd.p, 2)}%` }),
        UI.tile({ lab: '듀레이션 / BM', val: F.n(B.dur_p, 2), unit: `/ ${F.n(B.dur_b, 2)}년`, note: `액티브 ${F.s(B.active_dur, 2)}년` }),
        UI.tile({ lab: 'DV01', val: F.usd(B.dv01), unit: '/ bp', note: `벤치마크 ${F.usd(B.dv01_b)}`, title: '금리가 모두 1bp 내릴 때 포트폴리오가 버는 금액' }),
        UI.tile({ lab: '액티브 DV01', val: F.usdS(B.dv01 - B.dv01_b), unit: '/ bp', note: '포트폴리오 − 벤치마크', title: '금리가 1bp 내릴 때 벤치마크보다 더 버는 금액' }),
        UI.tile({ lab: 'VaR (1일, 95%)', val: F.usd(V.d1_95_usd), note: `NAV의 ${F.n(V.d1_95_pct, 2)}% · 상대 ${F.n(V.rel_95_bp, 1)}bp`, title: `최근 3년(${V.n}영업일) 일별 손익에서 읽은 값` }),
        UI.tile({ lab: '추적오차 (사전)', val: F.n(te, 0), unit: 'bp', note: `한도 ${teLim}bp · 1년 사후 ${F.n(S.te_1y_bp, 0)}bp` }),
        UI.tile({ lab: '위험예산 소진율', val: F.n(useTe * 100, 0), unit: '%', note: `남은 추적오차 ${F.n(teLim - te, 0)}bp`, title: '사전 추적오차 ÷ 추적오차 한도' })));
      cards.push(UI.card({ span: 'c6', title: '액티브 금리 노출', cap: '만기별 Key Rate DV01, 포트폴리오 − 벤치마크 · 달러 / bp',
        body: [UI.concl(`${ranked[0][0]} 금리 ${ranked[0][1] > 0 ? '하락' : '상승'}에 가장 크게 걸려 있습니다 (${F.usdS(ranked[0][1])} / bp)`,
          `+는 그 만기 금리가 내릴 때 벤치마크보다 더 법니다. 전체 액티브 DV01은 ${F.usdS(B.dv01 - B.dv01_b)}입니다.`),
          UI.bars({ cats: K.keys, h: 210, sign: true, unit: '', xEvery: 1, tipFmt: (v) => F.usdS(v) + ' / bp', aria: '만기별 액티브 Key Rate DV01', series: [{ name: '액티브 KR01', color: 'var(--s1)', values: krA }] })] }));
      cards.push(UI.card({ span: 'c6', title: '위험 한도', cap: '현재 · 한도 · 소진율', flush: true, body: [UI.concl(limConcl), limTable(false)] }));
      if (E) { const t = pnlText('d'); cards.push(UI.card({ span: 'c6', title: '오늘 손익', cap: '어디서 났나', body: UI.concl(t.head, t.detail + '. 자세한 내용은 손익 탭에 있습니다.') })); }
      cards.push(UI.card({ span: 'c6', title: '지금 포지션', cap: `${F.md(B.decision_date)} 리밸런싱`,
        body: kv([['규칙 포지션', posTxt(B.position)], ['리밸런싱 이후 손익', F.usdS(unreal)]], 'two') }));
    }

    // ════════ 손익 ════════
    if (tab === 'pnl' && E) {
      let eWin = 'd', eMode = 'ls', eView = 'p';
      const concl = UI.concl('', ' '), chart = h('div', { cls: 'inset' }), table = h('div');
      const draw = () => {
        const days = E.days.slice(-WIN[eWin]), { rows } = explainRows(days, eMode), t = pnlText(eWin);
        const total = { g: '합계', name: '손익 합계', usd: tot(rows.map((r) => r.usd)), p: tot(rows.map((r) => r.p)), b: tot(rows.map((r) => r.b)) };
        const uMax = Math.max(1, ...rows.map((r) => Math.abs(r.usd))), aMax = Math.max(0.1, ...rows.map((r) => Math.abs(r.p - r.b)));
        concl.firstChild.textContent = t.head; concl.lastChild.textContent = t.detail + '.';
        chart.replaceChildren(UI.bars({ cats: rows.map((r) => r.name), h: 210, sign: true, unit: '', xEvery: 1, aria: '손익 분해 막대',
          tipFmt: eView === 'p' ? (v) => F.usdS(v) : (v) => F.bp(v, 2),
          series: [{ name: eView === 'p' ? '포트폴리오 손익' : '벤치마크 대비', color: 'var(--s1)', values: rows.map((r) => (eView === 'p' ? r.usd : r.p - r.b)) }] }), h('div', { style: 'height:12px' }));
        const cols = [{ label: '항목', align: 'l', get: (r) => r.name }]
          .concat(eMode === 'key' ? [{ label: '금리 변화', get: (r) => r.dy, fmt: (v) => (ok(v) ? F.bp(v) : '') },
            { label: 'KR01 (전일)', title: '전일 기준 Key Rate DV01. 여러 날이면 평균', get: (r) => r.dv01, fmt: (v) => (ok(v) ? F.usd(v) : '') }] : [])
          .concat([{ label: '손익', get: (r) => r.usd, fmt: (v) => F.usdS(v), heat: (v, r) => (r.g === '합계' ? '' : UI.heat(v, uMax)) },
            { label: '수익률 (bp)', get: (r) => r.p, fmt: (v) => F.s(v, 2) },
            { label: '벤치마크 대비 (bp)', get: (r) => r.p - r.b, fmt: (v) => F.s(v, 2), heat: (v, r) => (r.g === '합계' ? '' : UI.heat(v, aMax)) }]);
        table.replaceChildren(UI.table(cols, { rows: rows.concat([total]), dense: true, group: (r) => r.g }));
      };
      draw();
      cards.push(UI.card({ id: 'explain', span: 'c8', title: '손익 분해', cap: '손익은 달러, 나머지는 bp', flush: true,
        tools: [seg([['d', '1일'], ['w', '1주'], ['m', '이번 달']], eWin, (k) => { eWin = k; draw(); }),
          seg([['ls', '수준·기울기'], ['key', '만기별']], eMode, (k) => { eMode = k; draw(); }),
          seg([['p', '포트폴리오'], ['a', '벤치마크 대비']], eView, (k) => { eView = k; draw(); })],
        body: [concl, chart, table],
        foot: h('details', null, h('summary', null, '계산 방법'), '전일 종가의 포지션을 그대로 들고 하루를 보냈다고 보고 나눕니다. 캐리는 금리가 그대로일 때 하루치 이자와 가격의 액면 수렴, 롤다운은 커브가 그대로일 때 만기가 하루 짧아지는 몫, 금리 변화는 전일 Key Rate DV01 × 그 만기 금리 변화, 볼록성 등은 나머지입니다. 수준은 모든 만기가 같이 움직인 몫, 기울기는 만기가 길수록 더 움직인 몫이고(만기 키 금리 변화를 log 만기에 직선으로 맞춤), 그 밖의 모양 변화에 곡률이 들어갑니다. 합은 NAV 변화와 같습니다. 여기서 쓰는 KR01은 종목을 만기 금리 하나로 값 매기는 모형 기준이라 포지션 탭의 KR01과 만기별 값이 조금 다릅니다.') }));
      cards.push(UI.card({ span: 'c4', title: '실현 · 미실현', cap: `올해 · ${F.md(B.decision_date)} 리밸런싱 기준`,
        body: [kv([['미실현 (리밸런싱 이후)', F.usdS(unreal)], ['실현 (올해, 그 이전)', F.usdS(realized)], ['올해 합계', F.usdS(unreal + realized)]], 'two'),
          h('p', { cls: 'note' }, '모형은 월말마다 보유 종목을 모두 팔고 새 종목을 사므로, 지난 리밸런싱까지의 손익을 실현으로, 그 뒤를 미실현으로 봅니다. 종목별 평가손익은 포지션 탭에 있습니다.')] }));
    }

    // ════════ 포지션 ════════
    if (tab === 'positions') {
      const pos = BK.filter((p) => ctx.matOk(p.ttm)), all = pos.length === BK.length;
      const settle = BondMath.ymd(BondMath.nextBusinessDay(B.asof));
      cards.push(UI.card({ span: 'c12', title: '액티브 금리 노출', cap: '만기별 Key Rate DV01 (KR01) · 달러 / bp',
        body: UI.bars({ cats: K.keys, h: 200, unit: '', xEvery: 1, tipFmt: (v) => F.usdS(v) + ' / bp', aria: '만기별 KR01: 포트폴리오, 벤치마크, 액티브',
          series: [{ name: '포트폴리오', color: 'var(--s1)', values: krP }, { name: '벤치마크', color: 'var(--s-mute)', values: krB }, { name: '액티브', color: 'var(--s2)', values: krA }] }) }));
      cards.push(UI.card({ id: 'blotter', span: 'c12', title: '보유 종목', cap: `${B.asof} 평가 · ${posTxt(B.position)} · 줄을 누르면 채권 상세`, flush: true,
        body: UI.table([{ label: '구간', align: 'l', get: (p) => p.label }, { label: '종목', align: 'l', get: (p) => p.maturity, fmt: (_, p) => `모형 국채 ${F.n(p.coupon, 3)}% ${p.maturity}` },
          { label: '액면', get: (p) => p.par, fmt: (v) => F.usd(v) }, { label: '매입 단가', title: '리밸런싱일의 클린가격', get: (p) => p.cost, fmt: (v) => F.n(v, 3) },
          { label: '현재가', get: (p) => p.price, fmt: (v) => F.n(v, 3) }, { label: 'YTM', get: (p) => p.ytm, fmt: (v) => F.n(v, 2) + '%' },
          { label: '수정 듀레이션', get: (p) => p.mdur, fmt: (v) => F.n(v, 2) },
          { label: 'DV01', get: (p) => p.dv01, fmt: (v) => F.usd(v) }, { label: '액티브 DV01', title: '포트폴리오 − 벤치마크', get: (p) => p.dv01 - p.dv01_b, fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 150) },
          { label: '평가금액', get: (p) => p.mv, fmt: (v) => F.usd(v) }, { label: '비중', get: (p) => p.w_p, fmt: (v) => F.n(v, 1) + '%' },
          { label: '평가손익', title: '리밸런싱 이후, 받은 이자 포함', get: (p) => p.upl, fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 10000) }],
          { rows: pos, dense: true, onRow: (p) => ctx.openBond({ title: `모형 국채 ${F.n(p.coupon, 3)}% ${p.maturity}`, sub: `${p.label} 구간 · 실제 종목이 아닌 모형 채권`, coupon: p.coupon, maturity: p.maturity, settle, ytm: p.ytm,
              tags: ['모형 종목'], source: '가격은 그날 재무부 par 커브에서 읽은 금리로 계산했습니다.' }),
            foot: all ? ['합계', '', '', '', '', '', F.n(B.dur_p, 2), F.usd(B.dv01), F.usdS(B.dv01 - B.dv01_b), F.usd(B.nav), '100%', F.usdS(tot(BK.map((p) => p.upl)))] : null }),
        foot: '구간마다 모형 국채 한 종목입니다 (실제 CUSIP 아님). 평가금액 비중은 벤치마크와 같고, 구간 안에서 만기를 옮겨 DV01을 다르게 가져갑니다.' }));
      let kMode = 'a';
      const slot = h('div');
      const drawK = () => {
        const val = (x, j) => (kMode === 'p' ? x.p[j] : kMode === 'b' ? x.b[j] : x.p[j] - x.b[j]), sg = kMode === 'a', f = (v) => (Math.abs(v) < 0.5 ? '–' : sg ? F.usdS(v) : F.usd(v));
        const rows = K.rows.map((x) => ({ g: '구간별', label: x.label, v: K.keys.map((_, j) => val(x, j)) })).concat([{ g: '합계', label: kMode === 'p' ? '포트폴리오' : kMode === 'b' ? '벤치마크' : '액티브', v: kMode === 'p' ? krP : kMode === 'b' ? krB : krA }]);
        slot.replaceChildren(UI.table([{ label: '구간 / 만기', align: 'l', get: (r) => r.label }].concat(K.keys.map((k, j) => ({ label: k, get: (r) => r.v[j], fmt: f, heat: (v) => (sg ? UI.heat(v, 150) : '') })),
          [{ label: 'DV01', get: (r) => tot(r.v), fmt: f }]), { rows, dense: true, group: (r) => r.g }));
      };
      drawK();
      cards.push(UI.card({ id: 'kr01', span: 'c12', title: 'Key Rate DV01 (KR01)', cap: '달러 / bp · 그 만기 금리만 1bp 내릴 때 손익', flush: true,
        tools: [seg([['a', '액티브'], ['p', '포트폴리오'], ['b', '벤치마크']], kMode, (k) => { kMode = k; drawK(); })], body: slot,
        foot: h('details', null, h('summary', null, '계산 방법'), `만기 하나(1·2·3·5·7·10·20·30년)의 금리만 ±1bp 움직여 다시 값을 매긴 차이를 2로 나눈 값입니다. 범프는 그 만기에서 1bp, 옆 만기에서 0인 삼각형입니다. 줄 합계가 그 종목의 DV01(${F.usd(B.dv01)} 합계)과 같도록 비율을 맞췄습니다.`) }));
    }

    // ════════ 리스크 ════════
    if (tab === 'risk') {
      cards.push(UI.card({ id: 'limits', span: 'c12', title: '위험 한도', cap: '현재 수준 · 한도 · 소진율 · 남은 여유', flush: true, body: [UI.concl(limConcl,
        `추적오차를 ${F.n(teLim - te, 0)}bp 더 쓸 수 있습니다. 지금 포지션(액티브 DV01 ${F.usdS(B.dv01 - B.dv01_b)})의 약 ${F.n(teLim / te, 1)}배까지입니다.`), limTable(true)],
        foot: `한도는 임시 기준입니다. 추적오차 한도는 위험예산 상단, 손실 한도는 연 ${F.bp(L.year_bp)}·월 ${F.bp(L.month_bp)}, 한도의 ${F.n(L.warn * 100, 0)}%를 쓰면 주의입니다. 모형 포트폴리오는 한도를 넘어도 규칙대로 운용하므로 표시만 합니다.` }));
      cards.push(UI.card({ span: 'c6', title: 'VaR', cap: `최근 3년(${V.n}영업일) 일별 손익 기준`,
        body: kv([['1일 95%', F.usd(V.d1_95_usd), `${F.n(V.d1_95_pct, 2)}%`], ['1일 99%', F.usd(V.d1_99_usd), `${F.n(V.d1_99_pct, 2)}%`], ['상대 95%', F.n(V.rel_95_bp, 1), 'bp / 일'],
          ['상대 99%', F.n(V.rel_99_bp, 1), 'bp / 일'], ['연 변동성', F.n(V.vol_ann_pct, 2), '%'], ['최대 일간 손실', F.n(V.worst_day, 2), '%']]) }));
      cards.push(UI.card({ span: 'c6', title: '추적오차', cap: 'bp / 년',
        body: kv([['사전', F.n(te, 0), 'bp'], ['사후 1년', F.n(S.te_1y_bp, 0), 'bp'], ['사후 3년', F.n(S.te_3y_bp, 0), 'bp'], ['사후 전체', F.n(S.te_all_bp, 0), 'bp'],
          ['규칙상 최대', F.n(R.te_max_bp, 0), 'bp'], ['목표 범위', `${bud[0]}~${bud[1]}`, 'bp']]) }));
      cards.push(UI.card({ span: 'c12', title: '손실 한도를 넘은 기록', cap: `${B.start.slice(0, 4)}년 말 이후`,
        body: kv([['월 한도를 넘은 달', `${L.hit_months.length}번`, `/ ${L.n_months}개월`], ['넘은 달', L.hit_months.map((m) => `${m.month} (${F.bp(m.excess_bp)})`).join(', ') || '없음'],
          ['연 한도를 넘은 해', `${L.hit_years.length}번`, `/ ${L.n_years}년 · 가장 나빴던 해 ${L.worst_year.year} (${F.bp(L.worst_year.excess_bp)})`]]) }));
    }

    // ════════ 매매 검토 (Pre-trade) ════════
    if (tab === 'trade') {
      const by = (l) => BK.find((p) => p.label === l), kr = (l) => K.rows.find((x) => x.label === l);
      const C = R.key_cov, quad = (a) => Math.sqrt(Math.max(0, a.reduce((t, x, i) => t + x * a.reduce((u, y, j) => u + C[i][j] * y, 0), 0)));
      const cr3 = (p, b) => (b ? p.carry3m_b + p.roll3m_b : p.carry3m + p.roll3m);
      const baseCR = tot(BK.map((p) => p.w_p / 100 * cr3(p))), bmCR = tot(BK.map((p) => p.w_b / 100 * cr3(p, true)));
      // 전략마다 구간별 매매를 DV01로 정한다. x는 고른 크기(달러 / bp)
      const STRAT = {
        'dur+': { name: 'Duration 확대', legs: (x) => { const s = by('1–3년'), l = by('7–10년'), m = x / ((l.mdur - s.mdur) * 1e-4); return [['7–10년', m * l.mdur * 1e-4], ['1–3년', -m * s.mdur * 1e-4]]; }, how: '1–3년을 팔고 같은 금액의 7–10년을 삽니다' },
        'dur-': { name: 'Duration 축소', legs: (x) => { const s = by('1–3년'), l = by('7–10년'), m = x / ((l.mdur - s.mdur) * 1e-4); return [['7–10년', -m * l.mdur * 1e-4], ['1–3년', m * s.mdur * 1e-4]]; }, how: '7–10년을 팔고 같은 금액의 1–3년을 삽니다' },
        steep: { name: '스티프너', legs: (x) => [['1–3년', x], ['20년+', -x]], how: '1–3년을 사고 20년+를 같은 DV01만큼 팝니다 (DV01 중립)' },
        flat: { name: '플래트너', legs: (x) => [['1–3년', -x], ['20년+', x]], how: '20년+를 사고 1–3년을 같은 DV01만큼 팝니다 (DV01 중립)' },
        belly: { name: '벨리', legs: (x) => [['5–7년', x], ['1–3년', -x / 2], ['7–10년', -x / 2]], how: '5–7년을 사고 1–3년·7–10년을 절반씩 팝니다 (DV01 중립)' },
      };
      let sKey = 'dur+', size = 500;
      const slot = h('div');
      const draw = () => {
        const sd = STRAT[sKey], after = krP.slice();
        const trades = sd.legs(size).map(([l, dv]) => {
          const p = by(l), x = kr(l), parT = dv / (p.dv01 / p.par), mvT = parT * p.mv / p.par;
          x.p.forEach((v, j) => { after[j] += v * dv / p.dv01; });
          return { l, p, side: dv > 0 ? '매수' : '매도', par: parT, mv: mvT, dv, cost: Math.abs(dv) * COST_BP };
        });
        const dDv = tot(trades.map((t) => t.dv)), cost = tot(trades.map((t) => t.cost)), aAfter = after.map((v, j) => v - krB[j]);
        const teA = te * quad(aAfter) / quad(krA), varA = V.d1_95_usd * quad(after) / quad(krP);
        const crA = baseCR + tot(trades.map((t) => t.mv / B.nav * cr3(t.p)));
        const M = [['듀레이션', B.dur_p, B.dur_p + dDv / B.nav * 1e4, (v) => F.n(v, 2) + '년', (d) => F.s(d, 2) + '년'],
          ['DV01', B.dv01, B.dv01 + dDv, (v) => F.usd(v), (d) => F.usdS(d)],
          ['액티브 DV01', B.dv01 - B.dv01_b, B.dv01 - B.dv01_b + dDv, (v) => F.usdS(v), (d) => F.usdS(d)],
          ['사전 추적오차', te, teA, (v) => F.n(v, 1) + 'bp', (d) => F.s(d, 1) + 'bp'],
          ['추적오차 한도 소진율', te / teLim * 100, teA / teLim * 100, (v) => F.n(v, 0) + '%', (d) => F.s(d, 0) + '%p'],
          ['VaR (1일, 95%)', V.d1_95_usd, varA, (v) => F.usd(v), (d) => F.usdS(d)],
          ['3개월 캐리·롤다운 (벤치마크 대비)', baseCR - bmCR, crA - bmCR, (v) => F.s(v, 1) + 'bp', (d) => F.s(d, 1) + 'bp'],
          ['거래비용', 0, cost, (v) => F.usd(v), () => `NAV의 ${F.n(cost / B.nav * 1e4, 2)}bp`]];
        slot.replaceChildren(
          UI.concl(`${sd.name} ${F.usd(size)} / bp: ${sd.how}`, `추적오차는 ${F.n(te, 1)} → ${F.n(teA, 1)}bp (한도 ${teLim}bp), 거래비용은 ${F.usd(cost)}입니다.`),
          h('div', { cls: 'inset' }, UI.bars({ cats: K.keys, h: 190, unit: '', xEvery: 1, tipFmt: (v) => F.usdS(v) + ' / bp', aria: '매매 전후 액티브 KR01',
            series: [{ name: '지금 액티브 KR01', color: 'var(--s-mute)', values: krA }, { name: '매매 뒤', color: 'var(--s1)', values: aAfter }] })),
          UI.table([{ label: '구간', align: 'l', get: (t) => t.l }, { label: '매매', align: 'l', get: (t) => t.side }, { label: '액면', get: (t) => Math.abs(t.par), fmt: (v) => F.usd(v) },
            { label: '금액', get: (t) => t.mv, fmt: (v) => F.usdS(v) }, { label: 'DV01', get: (t) => t.dv, fmt: (v) => F.usdS(v) }, { label: '거래비용', get: (t) => t.cost, fmt: (v) => F.usd(v) }],
            { rows: trades, dense: true, foot: ['합계', '', '', F.usdS(tot(trades.map((t) => t.mv))), F.usdS(dDv), F.usd(cost)] }),
          h('div', { style: 'height:10px' }),
          UI.table([{ label: '지표', align: 'l', get: (m) => m[0] }, { label: '매매 전', get: (m) => m[1], fmt: (v, m) => m[3](v) }, { label: '매매 뒤', get: (m) => m[2], fmt: (v, m) => m[3](v) },
            { label: '변화', get: (m) => m[2] - m[1], fmt: (v, m) => m[4](v) }], { rows: M, dense: true }));
      };
      draw();
      cards.push(UI.card({ id: 'pretrade', span: 'c12', title: '매매 전 위험 점검', cap: '지금 포지션에 매매를 얹으면', flush: true,
        tools: [seg(Object.entries(STRAT).map(([k, v]) => [k, v.name]), sKey, (k) => { sKey = k; draw(); }), seg([[250, '$250'], [500, '$500'], [1000, '$1,000']], size, (k) => { size = k; draw(); })],
        body: slot,
        foot: h('details', null, h('summary', null, '가정'), `예시 계산이고 리밸런싱 규칙은 바꾸지 않습니다. 각 구간의 모형 국채로 매매합니다. 추적오차와 VaR의 매매 뒤 값은 만기 키 금리의 최근 750영업일 공분산으로 본 변화율을 지금 값에 곱했습니다. 캐리는 금리 ÷ 4, 롤다운은 커브가 그대로일 때 3개월 뒤 금리 차이 × 듀레이션입니다. 거래비용은 매매한 DV01 × 금리 ${COST_BP}bp로 가정했습니다.`) }));
    }

    // ════════ 시나리오 ════════
    if (tab === 'scenario') {
      const cols = (first) => [first, { label: '2년', get: (x) => x.d2, fmt: (v) => F.bp(v) }, { label: '10년', get: (x) => x.d10, fmt: (v) => F.bp(v) }, { label: '30년', get: (x) => x.d30, fmt: (v) => F.bp(v) },
        { label: '포트폴리오 손익', get: (x) => x.p_usd, fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 700000) }, { label: '포트폴리오', get: (x) => x.p_pct, fmt: (v) => F.s(v, 2) + '%' },
        { label: '벤치마크', get: (x) => x.b_pct, fmt: (v) => F.s(v, 2) + '%' }, { label: '벤치마크 대비', get: (x) => x.active_bp, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 25) },
        { label: '상대 손익', get: (x) => x.active_usd, fmt: (v) => F.usdS(v) }];
      const wc = R.curve.slice().sort((a, b) => a.active_bp - b.active_bp)[0];
      cards.push(UI.card({ span: 'c12', title: '커브 시나리오', cap: '금리 변화는 bp · 듀레이션과 볼록성 반영', flush: true,
        body: [UI.concl(`벤치마크 대비 가장 불리한 것은 ${wc.label.split(' (')[0]}입니다 (${F.bp(wc.active_bp, 1)})`, `장기 구간을 벤치마크보다 길게 들고 있어 장기 금리가 더 오르는 쪽에서 뒤집니다.`),
          UI.table(cols({ label: '시나리오', align: 'l', get: (x) => x.label }), { rows: R.curve, dense: true })] }));
      cards.push(UI.card({ span: 'c12', title: '평행 이동', cap: '모든 만기가 같이 움직이면', flush: true, body: UI.table(cols({ label: '시나리오', align: 'l', get: (x) => x.label }), { rows: R.parallel, dense: true }) }));
      cards.push(UI.card({ id: 'stress', span: 'c12', title: '스트레스 테스트', cap: '과거 국면의 금리 변화를 지금 포트폴리오에 적용', flush: true,
        body: UI.table([{ label: '국면', align: 'l', get: (x) => x.label }, { label: '기간', align: 'l', get: (x) => x.from, fmt: (_, x) => `${x.from} ~ ${x.to}` },
          { label: '2년', get: (x) => x.d2, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) }, { label: '10년', get: (x) => x.d10, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) },
          { label: '30년', get: (x) => x.d30, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) },
          { label: '포트폴리오 손익', get: (x) => x.p_usd, fmt: (v) => F.usdS(v) }, { label: '포트폴리오', get: (x) => x.p_pct, fmt: (v) => F.s(v, 2) + '%', heat: (v) => UI.heat(v, 9) },
          { label: '벤치마크', get: (x) => x.b_pct, fmt: (v) => F.s(v, 2) + '%' }, { label: '벤치마크 대비', get: (x) => x.active_bp, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 30) }],
          { rows: R.stress, dense: true }),
        foot: '세 표 모두 지금 보유 종목에 만기별 금리 변화를 적용해 듀레이션과 볼록성으로 계산했습니다. 그 사이 받는 이자는 뺐습니다. 금리 변화 색은 오름이 빨강, 손익 색은 이익이 빨강입니다.' }));
    }

    // ════════ 거래 내역 ════════
    if (tab === 'blotter') {
      const T = B.blotter || [];
      if (T.length) {
        let ti = 0;
        const slot = h('div');
        const draw = () => {
          const t = T[ti], net = tot(t.legs.map((g) => g.dv01));
          const why = (B.rebalances.find((x) => x.date === t.date) || {}).why || '월말 정기 교체 (포지션 유지)';
          slot.replaceChildren(UI.table([{ label: '거래일', align: 'l', get: () => t.date }, { label: '종목', align: 'l', get: (g) => g.maturity, fmt: (_, g) => `모형 국채 ${F.n(g.coupon, 3)}% ${g.maturity}` },
            { label: 'CUSIP', align: 'l', get: () => '모형' }, { label: '매매', align: 'l', get: (g) => g.side }, { label: '액면', get: (g) => g.par, fmt: (v) => F.usd(v) },
            { label: '체결가', title: '클린가격', get: (g) => g.price, fmt: (v) => F.n(v, 3) }, { label: '체결 YTM', get: (g) => g.ytm, fmt: (v) => F.n(v, 3) + '%' },
            { label: '결제 금액', title: '경과이자 포함', get: (g) => (g.side === '매수' ? -g.amount : g.amount), fmt: (v) => F.usdS(v) }, { label: '거래비용', get: () => 0, fmt: () => '$0' },
            { label: 'DV01 변화', get: (g) => g.dv01, fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 2500) }, { label: '사유', align: 'l', get: () => posTxt(t.position) }],
            { rows: t.legs, dense: true, foot: ['합계', '', '', '', '', '', '', F.usdS(Math.round(tot(t.legs.map((g) => (g.side === '매수' ? -g.amount : g.amount)))) || 0), '$0', F.usdS(net), ''] }),
            h('p', { cls: 'note', style: 'padding:0 16px' }, `매매 사유: ${why}`));
        };
        draw();
        cards.push(UI.card({ id: 'fills', span: 'c12', title: '거래 내역', cap: '종목 단위 · 월말 종가 체결', flush: true,
          tools: [seg(T.map((t, i) => [i, t.date]), ti, (k) => { ti = k; draw(); })], body: slot,
          foot: '모형은 월말마다 보유 여섯 종목을 모두 팔고 그날 par 금리로 발행된 새 종목을 삽니다. 그래서 거래 금액이 실제 운용보다 크게 보입니다. 실제 종목이 아니라 CUSIP이 없고 거래비용은 0입니다.' }));
      }
      const rb = B.rebalances.slice().reverse();
      let showAll = false;
      const rbSlot = h('div');
      const drawRb = () => rbSlot.replaceChildren(UI.table([{ label: '날짜', align: 'l', get: (x) => x.date }, { label: '바꾸기 전', align: 'l', get: (x) => x.date, fmt: (_, x) => posTxt(x.frm) },
        { label: '바꾼 뒤', align: 'l', get: (x) => x.date, fmt: (_, x) => posTxt(x.to) }, { label: '이유', align: 'l', get: (x) => x.why },
        { label: '그달 초과수익', get: (x) => x.ex, fmt: (v, x) => F.s(v, 1) + (x.partial ? ' (진행 중)' : ''), heat: (v) => UI.heat(v, 25) }], { rows: showAll ? rb : rb.slice(0, 8), dense: true }));
      drawRb();
      const more = h('button', { cls: 'mini', type: 'button', 'aria-pressed': 'false' }, `전체 ${rb.length}건`);
      more.addEventListener('click', () => { showAll = !showAll; more.setAttribute('aria-pressed', String(showAll)); drawRb(); });
      cards.push(UI.card({ id: 'rules', span: 'c12', title: '포지션 변경 기록', cap: `${S.years.toFixed(0)}년 동안 ${S.n_rebal}번 · 규칙이 포지션을 바꾼 날`, flush: true, tools: [more], body: rbSlot }));
    }

    // ════════ 성과 ════════
    if (tab === 'perf') {
      const hit = (k) => `${S.hit[k][0]} / ${S.hit[k][1]}개월`;
      cards.push(h('div', { cls: 'tiles c12' },
        UI.tile({ lab: `${B.start.slice(0, 4)}년 말 이후 초과수익`, val: F.s(ex('itd'), 0), unit: 'bp', note: `연 ${F.s(S.excess_ann_bp, 1)}bp` }),
        UI.tile({ lab: '정보비율', val: F.n(S.ir, 2), note: `사후 추적오차 ${F.n(S.te_all_bp, 0)}bp` }),
        UI.tile({ lab: '적중률', val: F.n(S.months_win / S.months_active * 100, 0), unit: '%', note: `포지션을 든 ${S.months_active}개월 중 ${S.months_win}개월` }),
        UI.tile({ lab: '최대 낙폭 (MDD)', val: F.n(S.mdd_p, 1), unit: '%', note: `벤치마크 ${F.n(S.mdd_b, 1)}% · 상대 ${F.n(S.mdd_rel_bp, 0)}bp` }),
        UI.tile({ lab: '연 수익률', val: F.n(S.ann_p, 2), unit: '%', note: `벤치마크 ${F.n(S.ann_b, 2)}%` })));
      const i0 = UI.cut(ser.dates, st.period), xd = ser.dates.slice(i0), base = ser.excess_bp[i0];
      cards.push(UI.card({ id: 'cum', span: 'c7', title: '누적 초과수익', cap: `bp · ${xd[0]}부터`,
        body: UI.line({ x: xd, series: [{ name: '누적 초과수익', color: 'var(--s1)', values: ser.excess_bp.slice(i0).map((v) => v - base) }], h: 300, zero: true, legend: false, unit: 'bp', tipFmt: (v) => F.s(v, 1), aria: '누적 초과수익' }),
        alt: () => UI.seriesTable(xd, [{ name: '포트폴리오 NAV', values: ser.nav_p.slice(i0), fmt: (v) => F.usd(v) }, { name: '벤치마크 NAV', values: ser.nav_b.slice(i0), fmt: (v) => F.usd(v) },
          { name: '누적 초과수익 (bp)', values: ser.excess_bp.slice(i0).map((v) => v - base), fmt: (v) => F.s(v, 1) }], 36) }));
      cards.push(UI.card({ id: 'factors', span: 'c5', title: '전략별 기여', cap: `${B.start.slice(0, 4)}년 말 이후 · bp`, flush: true,
        body: UI.table([{ label: '요인', align: 'l', get: (x) => x[0] }, { label: '기여 (bp)', get: (x) => x[1], fmt: (v) => (ok(v) ? F.s(v, 0) : '–'), heat: (v) => UI.heat(v, 50) }, { label: '적중', align: 'l', get: (x) => x[2] }],
          { rows: [['Duration', S.c_dur, hit('dur')], ['Curve Slope', S.c_slope, hit('slope')], ['Curve Curvature', S.c_curv, hit('curv')],
            ['캐리·롤다운', null, '벤치마크와 구간 비중이 같아 나누지 않음'], ['거래비용', 0, '0으로 가정']], dense: true, foot: ['합계', F.s(ex('itd'), 0), ''] }),
        foot: '캐리·롤다운과 거래비용의 장기 기여는 실제 종목과 비용을 넣은 뒤에 나눌 수 있습니다.' }));
      const byY = {};
      for (const m of B.months) { const y = m.month.slice(0, 4); (byY[y] = byY[y] || {})[Number(m.month.slice(5))] = m; }
      const yr = Object.fromEntries(B.years.map((y) => [y.year, y]));
      const monCols = [{ label: '연도', align: 'l', get: (y) => y }];
      for (let k = 1; k <= 12; k++) monCols.push({ label: k + '월', get: (y) => (byY[y][k] ? byY[y][k].ex : null), fmt: (v) => (ok(v) ? F.s(v, 0) : ''), heat: (v) => UI.heat(v, 25) });
      monCols.push({ label: '연간', get: (y) => yr[y].excess_bp, fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 40) }, { label: '포트폴리오', get: (y) => yr[y].ret_p, fmt: (v) => F.s(v, 2) + '%' }, { label: '벤치마크', get: (y) => yr[y].ret_b, fmt: (v) => F.s(v, 2) + '%' });
      cards.push(UI.card({ id: 'monthly', span: 'c12', title: '월별 · 연도별 초과수익', cap: '벤치마크 대비 bp', flush: true, tools: [UI.scaleKey('뒤짐', '앞섬')],
        body: UI.table(monCols, { rows: Object.keys(byY).sort().reverse(), dense: true }),
        foot: `가장 좋았던 달 ${S.best.month} (${F.s(S.best.excess_bp, 0)}bp), 가장 나빴던 달 ${S.worst.month} (${F.s(S.worst.excess_bp, 0)}bp). 거래비용은 0으로 두었습니다.` }));
    }

    const act = B.active_dur, use = te / teLim;
    const posWord = Math.abs(act) < 0.03 ? '듀레이션을 벤치마크와 같게 두고 있고' : `벤치마크보다 듀레이션을 ${act > 0 ? '길게' : '짧게'} 가져가고 있고`;
    return { title: `포트폴리오는 ${posWord}, 위험 한도에는 여유가 ${worst.use < L.warn ? '있습니다' : '많지 않습니다'}`,
      lead: `액티브 듀레이션 ${F.s(act, 2)}년, DV01 ${F.usd(B.dv01)} (액티브 ${F.usdS(B.dv01 - B.dv01_b)}), 추적오차는 한도의 ${F.n(use * 100, 0)}%입니다. 일간 손익 ${F.usdS(B.pnl_d1_usd)}, 이번 달 초과수익 ${F.bp(ex('mtd'), 1)}.`,
      sub: '가상 USD 10M을 미국 국채에 규칙대로 운용하는 모형 포트폴리오입니다. 벤치마크는 공개 자료로 만든 미국 국채 대용 지수입니다.',
      usOnly: true, tab, tabs: TABS, body: cards };
  };
})();
