/* 1. 시장 모니터 — 무엇이 움직였나: 커브 모니터, 금리 히트맵, 스프레드 보드, 크로스에셋, 지표물 */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const SNAP_COLOR = { now: 'var(--t1)', w1: 'var(--t2)', m1: 'var(--t3)', y1: 'var(--t4)' };   // 시간 순서 색 (가까운 날이 진함)

  function headline(blk, name) {
    const by = Object.fromEntries(blk.heat.map((r) => [r.tenor, r]));
    const a = by['2Y'] || by['3Y'], b = by['10Y'];
    if (!a || !b) return `${name} 금리 현황입니다`;
    const da = a.chg.w1, db = b.chg.w1, ds = db - da, avg = (da + db) / 2;
    const dir = Math.abs(avg) < 1.5 ? '거의 움직이지 않았고' : avg < 0 ? '내렸고' : '올랐고';
    let shape;
    if (Math.abs(ds) < 3) shape = '장단기가 나란히 움직여 커브 모양은 그대로입니다';
    else if (ds > 0) shape = `장기가 ${Math.abs(ds).toFixed(0)}bp ${avg < 0 ? '덜 내려' : '더 올라'} 커브가 가팔라졌습니다 (${avg < 0 ? '불' : '베어'} 스티프닝)`;
    else shape = `장기가 ${Math.abs(ds).toFixed(0)}bp ${avg < 0 ? '더 내려' : '덜 올라'} 커브가 평평해졌습니다 (${avg < 0 ? '불' : '베어'} 플래트닝)`;
    return `한 주 동안 ${name} 금리는 ${a.tenor.replace('Y', '년')} ${F.bp(da)}, 10년 ${F.bp(db)}로 ${dir}, ${shape}`;
  }

  /* 결론: 이번 주가 어떤 장이었나 (주가와 견준 방향) + 움직임이 평소보다 컸나 */
  function conclusion(blk, eq) {
    const by = Object.fromEntries(blk.heat.map((r) => [r.tenor, r]));
    const a = by['2Y'] || by['3Y'], b = by['10Y'];
    if (!a || !b || !ok(b.chg.w1)) return { title: '이번 주 금리 움직임을 계산하지 못했습니다', why: '' };
    const avg = (a.chg.w1 + b.chg.w1) / 2, dir = Math.abs(avg) < 3 ? 0 : Math.sign(avg);
    const sd = (blk.wk_sd || {})['10Y'], ratio = sd ? Math.abs(b.chg.w1) / sd : null;
    const e = eq && ok(eq.w1) ? eq.w1 : null;
    let what;
    if (dir === 0) what = '금리가 거의 움직이지 않은 한 주';
    else if (e != null && e <= -3) what = dir < 0 ? '주가가 내리고 국채 금리도 내린 위험 회피 장세' : '주식과 채권이 함께 약했던 한 주';
    else if (e != null && e >= 3) what = dir > 0 ? '주가가 오르고 국채 금리도 오른 위험 선호 장세' : '주식과 채권이 함께 강했던 한 주';
    else what = dir < 0 ? '국채가 강했던(금리 하락) 한 주' : '국채가 약했던(금리 상승) 한 주';
    const size = ratio == null || dir === 0 ? '' : ratio >= 2 ? `, 금리 움직임은 평소 한 주의 ${F.n(ratio, 1)}배로 컸습니다` : ratio >= 1.2 ? ', 금리 움직임은 평소보다 컸습니다'
      : ratio >= 0.6 ? ', 금리 움직임은 평소 수준이었습니다' : ', 금리 움직임은 평소보다 작았습니다';
    const why = `10년 금리의 한 주 변화 ${F.bp(b.chg.w1)}` + (sd ? `는 최근 1년 주간 변화 표준편차(${F.n(sd, 0)}bp)의 ${F.n(ratio, 1)}배` : '') + (e != null ? `, ${eq.label} 한 주 ${F.s(e, 1)}% (±3%부터 주가 방향을 함께 봄)` : '');
    return { title: size ? `이번 주는 ${what}였고${size}` : `이번 주는 ${what}였습니다`, why };
  }

  window.DeskViews.market = function (ctx) {
    const D = ctx.D, st = ctx.st, kr = st.region === 'KR' && ctx.krOk;
    const blk = kr ? D.kr : D.us, name = kr ? '한국 국고채' : '미국 국채';
    const keep = blk.tenors.map((t, i) => ctx.matOk(blk.years[i]));
    const tenors = blk.tenors.filter((_, i) => keep[i]);
    const pick = (arr) => arr.filter((_, i) => keep[i]);

    // ── 커브 모니터 ──
    const snaps = blk.snaps.filter((sn) => SNAP_COLOR[sn.key]);
    const curveSeries = snaps.map((sn) => ({ name: sn.key === 'now' ? `오늘 (${F.md(sn.date)})` : `${sn.label} (${F.md(sn.date)})`, color: SNAP_COLOR[sn.key], values: pick(sn.y), width: sn.key === 'now' ? 2.5 : 1.75 }));
    const now = blk.snaps.find((x) => x.key === 'now'), w1 = blk.snaps.find((x) => x.key === 'w1'), m1 = blk.snaps.find((x) => x.key === 'm1');
    const diff = (ref) => pick(now.y.map((v, i) => (ok(v) && ref && ok(ref.y[i]) ? Math.round((v - ref.y[i]) * 100) : null)));
    const curveCard = UI.card({ id: 'curve', span: 'c5', title: '커브 모니터', cap: `${name} · 만기별 금리 (%)`,
      body: [UI.line({ x: tenors, series: curveSeries, date: false, dots: true, h: 250, unit: '%', tipFmt: (v) => F.n(v, 2), aria: '수익률 커브' }),
             h('p', { cls: 'note', style: 'margin:10px 0 4px;color:var(--ink2)' }, '만기별 변화 (bp)'),
             UI.bars({ cats: tenors, h: 150, unit: 'bp', labels: true, labFmt: (v) => F.s(v), tipFmt: (v) => F.s(v), aria: '만기별 금리 변화',
               series: [{ name: '1주 전 대비', color: 'var(--t2)', values: diff(w1) }, { name: '1달 전 대비', color: 'var(--t3)', values: diff(m1) }] })],
      alt: () => UI.table([{ label: '만기', align: 'l', get: (i) => tenors[i] }].concat(blk.snaps.map((sn) => ({ label: `${sn.label} ${F.md(sn.date)}`, get: (i) => pick(sn.y)[i], fmt: (v) => F.n(v, 2) }))),
        { rows: tenors.map((_, i) => i), dense: true }) });

    // ── 금리 히트맵 (기간별) ──
    const hrows = blk.heat.filter((r) => ctx.matOk(r.years));
    const bpCol = (label, key, max) => ({ label, get: (r) => r.chg[key], fmt: (v) => F.s(v), heat: (v) => UI.heat(v, max) });
    const heatCard = UI.card({ id: 'heat', span: 'c7', title: '금리 히트맵', cap: '기간별 변화 (bp)', flush: true,
      tools: [UI.scaleKey('내림', '오름')],
      body: UI.table([{ label: '만기', align: 'l', get: (r) => r.tenor }, { label: '금리', get: (r) => r.level, fmt: (v) => F.n(v, 2) },
        bpCol('1일', 'd1', 15), bpCol('1주', 'w1', 30), bpCol('1달', 'm1', 45), bpCol('3달', 'm3', 70), bpCol('연초 이후', 'ytd', 120), bpCol('1년', 'y1', 120),
        { label: '3년 백분위', title: '지난 3년 일별 값 가운데 지금보다 낮았던 날의 비율', get: (r) => r.pct3y, fmt: (v) => (ok(v) ? F.n(v, 0) : '–'), heat: (v) => UI.heatPct(v) },
        { label: '1년 추이', align: 'c', sort: false, get: (r) => r.tenor, fmt: (_, r) => UI.spark(r.spark) }],
        { rows: hrows, dense: true }),
      foot: '3년 백분위가 100에 가까우면 지난 3년 가운데 가장 높은 수준입니다.' });

    // ── 금리 히트맵 (월별) ──
    const mo = blk.monthly, mrows = mo.months.map((m, i) => i).reverse().slice(0, 24);
    const monthCard = UI.card({ id: 'months', span: 'c12', title: '월별 금리 변화', cap: '그달 마지막 영업일 금리 − 전달 마지막 영업일 금리 (bp)', flush: true,
      tools: [UI.scaleKey('내림', '오름')],
      body: UI.table([{ label: '월', align: 'l', get: (i) => mo.months[i], fmt: (v, i) => F.ym(v + '-01') + (i === mo.months.length - 1 && mo.partial_last ? ' (진행 중)' : '') }]
        .concat(tenors.map((t) => ({ label: t, get: (i) => mo.chg[t][i], fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 50) })))
        .concat([{ label: '10년 금리', get: (i) => (mo.level['10Y'] || [])[i], fmt: (v) => F.n(v, 2) }]), { rows: mrows, dense: true }) });

    // ── 스프레드 보드 ──
    const groupsFor = { all: null, govt: ['커브', '물가·실질', '펀딩', '금리'], credit: ['크레딧'] }[st.asset] || null;
    const srows = (kr ? D.kr.spreads : D.spreads).filter((r) => !groupsFor || groupsFor.includes(r.group));
    const src = kr ? D.kr.series : D.series;
    let selKey = (srows[0] || {}).key;
    const chartSlot = h('div');
    const drawSel = () => {
      const r = srows.find((x) => x.key === selKey);
      if (!r) { chartSlot.replaceChildren(); return; }
      const scale = 1;
      const made = ctx.lineOf([{ key: r.key, name: r.label, color: 'var(--s1)', scale }], { src, h: 200, legend: false, unit: r.unit === 'bp' ? 'bp' : '%', tipFmt: (v) => F.n(v, r.unit === 'bp' ? 0 : 2) });
      chartSlot.replaceChildren(h('p', { cls: 'note', style: 'margin:0 0 6px;color:var(--ink2)' }, `${r.label} (${r.unit}) — 표의 줄을 누르면 바뀝니다`), made.chart);
    };
    const chgCol = (label, key, max) => ({ label, get: (r) => r[key], fmt: (v) => F.s(v), heat: (v) => UI.heat(v, max) });
    const spreadTable = () => UI.table([
      { label: '스프레드', align: 'l', get: (r) => r.label },
      { label: '수준', get: (r) => r.level, fmt: (v, r) => F.n(v, r.unit === 'bp' ? 0 : 2) + (r.unit === 'bp' ? 'bp' : '%') },
      chgCol('1일', 'd1', 10), chgCol('1주', 'w1', 20), chgCol('1달', 'm1', 30), chgCol('3달', 'm3', 50), chgCol('1년', 'y1', 80),
      { label: 'z-score (3년)', title: '지난 3년 평균에서 표준편차 몇 개만큼 떨어져 있는지', get: (r) => r.z3y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) },
      { label: '3년 범위 안 위치', align: 'c', sort: false, get: (r) => r.pct3y, fmt: (_, r) => UI.range(r.lo3y, r.hi3y, r.level) },
      { label: '1년 추이', align: 'c', sort: false, get: (r) => r.key, fmt: (_, r) => UI.spark(r.spark) },
      { label: '기준일', get: (r) => r.date, fmt: (v) => F.md(v) }],
      { rows: srows, dense: true, group: (r) => r.group, onRow: (r) => { selKey = r.key; drawSel(); }, rowCls: (r) => '' });
    drawSel();
    const spreadCard = UI.card({ id: 'spreads', span: 'c12', title: '스프레드 보드', cap: '변화는 모두 bp · 자산군 필터가 적용됩니다',
      tools: [UI.scaleKey('좁아짐·내림', '벌어짐·오름')],
      body: srows.length ? [spreadTable(), h('div', { style: 'height:14px' }), chartSlot] : UI.empty('이 조건에 맞는 스프레드가 없습니다', '자산군이나 지역 필터를 바꿔 보세요.'),
      foot: '신용 스프레드(ICE BofA 지수)는 FRED가 최근 3년치만 제공합니다. 기준일이 금리보다 하루 늦을 수 있습니다.' });

    // ── 크로스에셋 ──
    const pc = (label, key, max) => ({ label, get: (r) => r[key], fmt: (v, r) => (r.pct ? F.s(v, 2) + '%' : F.s(v, 1)), heat: (v, r) => UI.heat(v, r.pct ? max : max * 3) });
    const xCard = UI.card({ id: 'xasset', span: 'c12', title: '크로스에셋', cap: '주식·통화·원자재는 등락률(%), 변동성 지수는 포인트 변화', flush: true,
      tools: [UI.scaleKey('내림', '오름')],
      body: UI.table([{ label: '자산', align: 'l', get: (r) => r.label },
        { label: '수준', get: (r) => r.level, fmt: (v, r) => F.n(v, v >= 1000 ? 0 : 2) + (r.unit ? ' ' + r.unit : '') },
        pc('1일', 'd1', 2.5), pc('1주', 'w1', 5), pc('1달', 'm1', 8), pc('연초 이후', 'ytd', 20), pc('1년', 'y1', 25),
        { label: '10년 금리와의 상관 (60일)', title: '최근 60영업일 일별 변화의 상관계수. +면 금리가 오르는 날 같이 오름', get: (r) => r.corr60, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 0.8) },
        { label: '1년 추이', align: 'c', sort: false, get: (r) => r.key, fmt: (_, r) => UI.spark(r.spark) },
        { label: '기준일', get: (r) => r.date, fmt: (v) => F.md(v) }],
        { rows: D.xasset, dense: true, group: (r) => r.group }),
      foot: '원/달러, 엔/달러가 오르면 달러 강세입니다. 금과 KOSPI는 Yahoo Finance, 나머지는 FRED 값입니다.' });

    // ── 지표물 ──
    let bondCard;
    if (kr) {
      bondCard = UI.card({ id: 'bonds', span: 'c12', title: '종목', body: UI.empty('한국 종목 자료는 아직 없습니다', '국고채 종목별 가격은 금융투자협회 채권정보센터에서 받아야 하는데 아직 연결하지 않았습니다. 지금은 만기별 금리만 있습니다.') });
    } else if (D.bonds.status === 'ok') {
      const otr = D.bonds.list.filter((b) => b.otr && ctx.matOk(b.ttm));
      bondCard = UI.card({ id: 'bonds', span: 'c12', title: '지표물 (on-the-run)', cap: `재무부 종가 ${D.bonds.price_date} · 줄을 누르면 채권 상세가 열립니다`, flush: true,
        body: UI.table([{ label: '구분', align: 'l', get: (b) => b.otr, fmt: (v) => v.replace('Y', '년') },
          { label: '종목', align: 'l', get: (b) => b.maturity, fmt: (_, b) => `UST ${F.n(b.coupon, 3)}% ${b.maturity}` },
          { label: 'CUSIP', align: 'l', get: (b) => b.cusip }, { label: '가격', get: (b) => b.price, fmt: (v) => F.n(v, 3) },
          { label: 'YTM', get: (b) => b.ytm, fmt: (v) => F.n(v, 3) + '%' }, { label: '수정듀레이션', get: (b) => b.mdur, fmt: (v) => F.n(v, 2) },
          { label: '볼록성', get: (b) => b.conv, fmt: (v) => F.n(v, 1) }, { label: 'DV01 (액면 100만)', get: (b) => b.dv01, fmt: (v) => F.usd(v) },
          { label: '커브 대비', title: '잔존만기가 비슷한 종목들로 만든 적합 커브보다 금리가 얼마나 높은지 (bp). +면 저평가', get: (b) => b.fit_bp, fmt: (v) => F.s(v, 1), heat: (v) => UI.heat(v, 8) },
          { label: '3개월 캐리+롤다운', get: (b) => (ok(b.carry3m) && ok(b.roll3m) ? b.carry3m + b.roll3m : null), fmt: (v) => F.s(v, 0) + 'bp' }],
          { rows: otr, dense: true, onRow: (b) => ctx.openBond(bondArg(D.bonds, b)) }),
        foot: [`전체 ${D.bonds.n}종목은 `, h('a', { href: '#/rv/value' }, 'RV·전략'), '에서 볼 수 있습니다. 종가는 다음 영업일에 공시되어 금리 기준일보다 하루 이를 수 있습니다.'] });
    } else {
      bondCard = UI.card({ id: 'bonds', span: 'c12', title: '지표물', body: UI.empty('종목 종가를 받지 못했습니다', '재무부 FedInvest에서 종가를 받지 못했습니다. 다음 갱신 때 다시 시도합니다.') });
    }

    const con = conclusion(blk, D.xasset.find((x) => x.key === (kr ? 'kospi' : 'sp500')));
    return { title: con.title, lead: headline(blk, name), usOnly: false,
      sub: `${con.why ? '근거: ' + con.why + '. ' : ''}${blk.asof} 종가이고, 상단의 지역·만기·자산군 필터가 이 화면의 표와 차트에 적용됩니다.`,
      tabs: [['curve', '커브 모니터'], ['heat', '금리 히트맵'], ['months', '월별 변화'], ['spreads', '스프레드 보드'], ['xasset', '크로스에셋'], ['bonds', '지표물']],
      body: [curveCard, heatCard, monthCard, spreadCard, xCard, bondCard] };
  };

  /* 종목 표의 한 줄 → 채권 상세에 넘길 값 */
  function bondArg(B, b) {
    return { title: `UST ${F.n(b.coupon, 3)}% ${b.maturity}`, sub: `${b.type === 'Bond' ? 'Treasury Bond' : 'Treasury Note'} · CUSIP ${b.cusip}`,
      coupon: b.coupon, maturity: b.maturity, settle: B.settle, price: b.price, cusip: b.cusip,
      tags: [b.otr ? `${b.otr.replace('Y', '년')} 지표물` : null, b.old ? '2010년 이전 발행' : null].filter(Boolean),
      rv: { fit_bp: b.fit_bp, par_gap_bp: b.par_gap_bp, carry3m: b.carry3m, roll3m: b.roll3m },
      source: `가격은 미 재무부 FedInvest ${B.price_date} 종가입니다.` };
  }
  window.DeskBondArg = bondArg;
})();
