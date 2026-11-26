/* 2. 매크로·정책 — 왜 움직였나: 지표 일정·서프라이즈, 월별 지표 표, 정책금리 경로, 중앙은행 트래커, 인플레이션 */
(function () {
  'use strict';
  const { h, F, ok } = UI;

  window.DeskViews.macro = function (ctx) {
    const D = ctx.D, M = D.macro, P = M.policy, asof = D.meta.asof;
    const kv = (items, two) => h('dl', { cls: 'kv' + (two ? ' two' : '') }, items.map(([k, v, u]) => h('div', null, h('dt', null, k), h('dd', null, v, u ? h('small', null, u) : null))));

    // 사실 요약 (두 번째 소제목)
    const m0 = (P.meetings || [])[0];
    let lead = '정책금리 경로 자료가 없습니다';
    if (m0) {
      const mv = m0.move, word = Math.abs(mv) < 5 ? '동결' : mv > 0 ? '인상' : '인하';
      const prob = Math.min(100, Math.abs(mv) / 25 * 100);
      const peakTxt = P.peak ? `, 내재 금리의 ${P.peak > P.upper ? '정점' : '저점'}은 ${P.peak_month.slice(0, 4)}년 ${Number(P.peak_month.slice(5))}월 ${F.n(P.peak, 2)}%입니다` : '입니다';
      const how = prob >= 92 ? `25bp ${word}을 거의 다 가격했고` : `${F.bp(mv)}를 가격했고 (25bp ${word} 확률 약 ${prob.toFixed(0)}%)`;
      lead = word === '동결' ? `선물 시장은 ${F.kdate(m0.date)} FOMC를 동결로 보고 있고${peakTxt}`
        : `선물 시장은 ${F.kdate(m0.date)} FOMC의 ${how}${peakTxt}`;
    }

    // ── 지표 일정·서프라이즈 ──
    const val = (r, v) => (ok(v) ? F.n(v, r.digits) : '–');
    const relCard = UI.card({ id: 'releases', span: 'c12', title: '지표 일정·서프라이즈', cap: '우리가 신호에 쓰는 지표의 가장 최근 발표', flush: true,
      body: UI.table([
        { label: '지표', align: 'l', get: (r) => r.label, fmt: (v, r) => [v, h('span', { cls: 'sub2' }, r.ko)] },
        { label: '기준', align: 'l', get: (r) => r.ref, fmt: (v) => v || '–' },
        { label: '발표일', get: (r) => r.release, fmt: (v) => F.md(v) },
        { label: '실제', get: (r) => r.actual, fmt: (v, r) => [val(r, v), ' ', h('span', { cls: 'mute' }, r.unit)] },
        { label: '직전', get: (r) => r.prev, fmt: (v, r) => val(r, v) },
        { label: M.exp_is_proxy ? '예상 (대용치)' : '예상', title: '컨센서스가 아니라 직전 추세로 만든 대용치입니다', get: (r) => r.exp, fmt: (v, r) => val(r, v) },
        { label: '서프라이즈', get: (r) => r.sur, fmt: (v, r) => (ok(v) ? F.s(v, r.digits) : '–'), heat: (v, r) => (ok(v) ? UI.heat(v * r.dir, r.key === 'nfp' ? 120 : 0.15) : '') },
        { label: '당일 2년', get: (r) => r.d2, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) },
        { label: '당일 10년', get: (r) => r.d10, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) },
        { label: '다음 발표', get: (r) => r.next, fmt: (v) => (v ? `${F.md(v)} (D−${Math.max(0, F.days(asof, v))})` : '–') },
        { label: '참고', align: 'l', get: (r) => r.note || '' }],
        { rows: M.releases, dense: true }),
      foot: '서프라이즈 색은 금리 방향 기준입니다: 빨강은 금리가 오르는 쪽(강한 고용, 높은 물가), 파랑은 내리는 쪽. 예상은 시장 컨센서스가 아니라 직전 추세로 만든 대용치라, 실제 시장이 느낀 서프라이즈와 다를 수 있습니다.' });

    const surChart = (key, name, unit, max) => {
      const ev = M.hist[key] || [];
      return UI.card({ span: 'c6', title: `${name} 서프라이즈와 당일 10년 금리`, cap: `최근 ${ev.length}번 발표 · ${unit}`,
        body: [UI.bars({ cats: ev.map((e) => F.ym(e.ref + '-01')), sign: true, h: 150, unit: ' ' + unit, tipFmt: (v) => F.s(v, key === 'nfp' ? 0 : 1), aria: name + ' 서프라이즈',
                 series: [{ name: '서프라이즈', color: 'var(--s1)', values: ev.map((e) => e.sur) }] }),
               h('p', { cls: 'note', style: 'margin:6px 0 4px;color:var(--ink2)' }, '발표 당일 10년 금리 변화 (bp)'),
               UI.bars({ cats: ev.map((e) => F.ym(e.ref + '-01')), sign: true, h: 120, unit: 'bp', tipFmt: (v) => F.s(v), aria: '발표 당일 10년 금리 변화',
                 series: [{ name: '10년 금리', color: 'var(--s1)', values: ev.map((e) => e.d10) }] })],
        alt: () => UI.table([{ label: '기준월', align: 'l', get: (e) => e.ref }, { label: '발표일', get: (e) => e.date },
          { label: `서프라이즈 (${unit})`, get: (e) => e.sur, fmt: (v) => F.s(v, key === 'nfp' ? 0 : 1), heat: (v) => UI.heat(v, max) },
          { label: '2년', get: (e) => e.d2, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) }, { label: '10년', get: (e) => e.d10, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) }],
          { rows: ev.slice().reverse(), dense: true }) });
    };

    // ── 월별 지표 표 ──
    const H = M.heat;
    let lastGroup = null;
    const heatCols = [{ label: '기준월', align: 'l', get: (r) => r.month, fmt: (v) => F.ym(v + '-01') }].concat(H.cols.map((c) => {
      const first = c.group !== lastGroup;
      lastGroup = c.group;
      return { label: (first ? c.group + ' · ' : '') + c.label, title: `${c.group} · ${c.label}${c.unit ? ' (' + c.unit + ')' : ''}`,
        get: (r) => r.cells[c.key][0], fmt: (v) => (ok(v) ? F.n(v, c.digits) : '–'), heat: (_, r) => UI.heat(r.cells[c.key][1], 2.2) };
    }));
    const heatCard = UI.card({ id: 'cycle', span: 'c12', title: '월별 지표 표', cap: '기준월별 값 · 색은 그 지표의 지난 5년 대비 위치', flush: true,
      tools: [UI.scaleKey('금리 하락 쪽', '금리 상승 쪽')],
      body: UI.table(heatCols, { rows: H.rows, dense: true }),
      foot: '빨강은 그 지표가 지난 5년 평균보다 금리를 올리는 쪽(강한 고용, 높은 물가, 높은 금리)에 있다는 뜻이고 파랑은 반대입니다. 실업률과 실업수당은 높을수록 파랑입니다. 금리와 MOVE는 월말 값입니다.' });

    // ── 정책금리 경로 ──
    const snaps = P.snaps || [], base = snaps.find((x) => x.key === 'now') || snaps[0];
    const colors = { now: 'var(--t1)', m1: 'var(--t2)', sep: 'var(--t4)' };
    const pathCard = base ? UI.card({ id: 'policy', span: 'c7', title: '정책금리 경로', cap: '연방기금금리 선물에 내재된 월평균 금리 (%) · OIS 대용',
      body: [UI.line({ x: base.months.map((m) => F.ym(m + '-01')), date: false, xEvery: 2, h: 250, unit: '%', tipFmt: (v) => F.n(v, 3), aria: '선물 내재 정책금리 경로',
               series: snaps.map((sn) => ({ name: `${sn.label} (${F.md(sn.date)})`, color: colors[sn.key] || 'var(--t3)', width: sn.key === 'now' ? 2.5 : 1.75,
                 values: base.months.map((m) => { const k = sn.months.indexOf(m); return k < 0 ? null : sn.rates[k]; }) })),
               refs: [{ y: P.upper, label: `목표 범위 상단 ${F.n(P.upper, 2)}` }, { y: P.lower, label: `하단 ${F.n(P.lower, 2)}` }] }),
             h('p', { cls: 'note' }, `점도표 중간값 (${P.sep} 발표): ` + Object.entries(P.dots || {}).map(([y, v]) => `${y}년 말 ${F.n(v, 3)}%`).join(' · ') + ` · 장기 ${F.n(P.lr, 2)}%. ` +
               `시장이 가격한 2년 평균 금리는 점도표보다 ${F.bp(P.gap_bp)} ${P.gap_bp > 0 ? '높습니다' : '낮습니다'}.`)],
      alt: () => UI.table([{ label: '월', align: 'l', get: (i) => base.months[i] }].concat(snaps.map((sn) => ({ label: sn.label, get: (i) => { const k = sn.months.indexOf(base.months[i]); return k < 0 ? null : sn.rates[k]; }, fmt: (v) => F.n(v, 3) }))),
        { rows: base.months.map((_, i) => i), dense: true }),
      foot: '과거 시점의 선물 가격은 만기가 지나면 구할 수 없어, 비교 선은 한 달 전과 직전 점도표 발표일 두 개만 있습니다.' })
      : UI.card({ id: 'policy', span: 'c7', title: '정책금리 경로', body: UI.empty('선물 가격을 받지 못했습니다', 'Yahoo Finance의 연방기금금리 선물(ZQ) 수집이 실패했습니다.') });

    const meetCard = UI.card({ span: 'c5', title: 'FOMC 회의별 가격', cap: '선물이 가격한 회의 뒤 금리', flush: true,
      body: UI.table([{ label: '회의', align: 'l', get: (m) => m.date, fmt: (v) => `${v.slice(2, 4)}.${v.slice(5, 7)}.${v.slice(8)}` },
        { label: '회의 뒤 금리', get: (m) => m.post, fmt: (v) => F.n(v, 3) + '%' },
        { label: '이 회의', get: (m) => m.move, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 25) },
        { label: '누적', get: (m) => m.cum, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 75) },
        { label: '25bp 환산', title: '누적 변화를 25bp로 나눈 횟수', get: (m) => m.cum / 25, fmt: (v) => F.s(v, 1) + '회' }],
        { rows: P.meetings || [], dense: true }),
      foot: '빨강은 인상, 파랑은 인하 쪽 가격입니다.' });

    // ── 중앙은행 트래커 ──
    const soma = D.flows.soma;
    const fed = [['목표 범위', `${F.n(P.lower, 2)}~${F.n(P.upper, 2)}`, '%'], ['실효 연방기금금리', F.n(P.effr, 2), '%'],
                 ['마지막 변경', P.last_change ? F.bp(P.last_change.bp) : '–', P.last_change ? P.last_change.date : ''],
                 ['다음 FOMC', P.next ? F.kdate(P.next.date) : '–', P.next ? `D−${P.next.days}${P.next.sep ? ' · 점도표 발표' : ''}` : ''],
                 ['다음 회의 가격', m0 ? F.bp(m0.move, 0) : '–', m0 ? '선물 내재' : ''],
                 ['정책 기조', F.bp(P.stance_bp, 0), '1년 뒤 1년 금리 − 중립금리'],
                 ['연준 보유 국채', F.bn(soma.total_bn), soma.asof], ['3개월 변화', F.bnS(soma.chg_3m_bn), ''], ['1년 변화', F.bnS(soma.chg_1y_bn), '']];
    const K = D.kr;
    const bokBody = ctx.krOk && K.bok ? kv([['기준금리', F.n(K.bok.base, 2), '%'], ['마지막 변경', K.bok.last_change ? F.bp(K.bok.last_change.bp) : '–', K.bok.last_change ? K.bok.last_change.date : ''],
        ['국고 3년 − 기준금리', ok(K.bok.ktb3) ? F.bp((K.bok.ktb3 - K.bok.base) * 100) : '–', '시장이 보는 방향'],
        ['CD 91일', F.n(K.bok.cd91, 2), '%'], ['콜금리', F.n(K.bok.call, 2), '%'], ['소비자물가 전년비', ok(K.cpi_yoy) ? F.n(K.cpi_yoy, 1) : '–', K.cpi_date ? '% · ' + K.cpi_date : '%']], true)
      : UI.empty('한국은행 자료는 인증키가 필요합니다', '한국은행 ECOS 인증키를 넣으면 기준금리, 국고채 금리, CD 금리가 채워집니다. 금융통화위원회 일정은 공개 자료로 받는 곳을 아직 찾지 못했습니다.');
    const today = new Date().toISOString().slice(0, 10), from = today < asof ? asof : today;
    const talks = D.events.filter((e) => (e.kind === '연설' || e.kind === '의회 증언' || e.kind === 'FOMC' || e.kind === '연준 자료') && e.date >= from).slice(0, 8);
    const talkList = h('ul', { cls: 'list' }, talks.length ? talks.map((e) => h('li', null, h('span', { cls: 'when' }, `${F.md(e.date)} ${e.time || ''}`),
      h('span', { cls: 'what' }, e.title, h('small', null, [e.kind, e.note].filter(Boolean).join(' · '))))) : h('li', null, h('span'), h('span', { cls: 'mute' }, '공개된 예정 일정이 없습니다')));
    const cbCard = UI.card({ id: 'cb', span: 'c12', title: '중앙은행 트래커', cap: '연준과 한국은행',
      body: h('div', { cls: 'grid' },
        h('div', { cls: 'c4' }, h('p', { cls: 'note', style: 'margin:0 0 8px;color:var(--ink);font-weight:600' }, '연준 (Fed)'), kv(fed, true)),
        h('div', { cls: 'c4' }, h('p', { cls: 'note', style: 'margin:0 0 8px;color:var(--ink);font-weight:600' }, '한국은행 (BOK)'), bokBody),
        h('div', { cls: 'c4' }, h('p', { cls: 'note', style: 'margin:0 0 2px;color:var(--ink);font-weight:600' }, '연준 예정 일정 (미 동부 시각)'), talkList)) });

    // ── 인플레이션 ──
    const sp = Object.fromEntries(D.spreads.map((r) => [r.key, r]));
    const I = M.infl;
    const sTile = (r, lab) => (r ? UI.tile({ lab, val: F.n(r.level, 2), unit: '%', spark: r.spark, deltas: [{ k: '1달', v: F.bp(r.m1), raw: r.m1 }, { k: '1년', v: F.bp(r.y1), raw: r.y1 }], note: `3년 백분위 ${F.n(r.pct3y, 0)}` }) : null);
    const inflTiles = h('div', { cls: 'tiles' }, sTile(sp.bei10, '10년 BEI (기대 인플레이션)'), sTile(sp.f5y5y, '5y5y 선도 BEI'), sTile(sp.real10, '10년 실질금리 (TIPS)'),
      UI.tile({ lab: '근원 PCE 전년비', val: F.n(I.core_pce_yoy, 2), unit: '%', note: `${I.pce_ref} 기준 · 3개월 연율 ${F.n(I.core_pce_3m, 1)}%` }),
      UI.tile({ lab: '근원 CPI 3개월 연율', val: F.n(I.cpi_3m, 2), unit: '%', note: `${I.cpi_ref} 기준` }),
      UI.tile({ lab: '미시간 1년 기대', val: F.n(I.mich, 1), unit: '%', note: '소비자 설문' }));
    const infl = ctx.lineOf([{ key: 'y_10Y', name: '10년 명목금리', color: 'var(--s1)' }, { key: 'real10', name: '10년 실질금리', color: 'var(--s2)' }, { key: 'bei10', name: '10년 BEI', color: 'var(--s3)' }],
      { h: 240, unit: '%', tipFmt: (v) => F.n(v, 2), aria: '10년 명목금리, 실질금리, BEI' });
    // 인플레이션 결론: 실제 물가가 목표보다 높은가 + 시장의 기대는 어떤가 + 지난 1년 금리 변화를 무엇이 이끌었나
    const y10row = D.us.heat.find((r) => r.tenor === '10Y'), bei = sp.bei10, real = sp.real10;
    let inflConcl = null;
    if (bei && ok(I.core_pce_yoy)) {
      const hot = I.core_pce_yoy > 2.5, expLo = bei.pct3y <= 20, expHi = bei.pct3y >= 80;
      const a = hot ? (expLo ? '물가는 목표(2%)보다 높지만 시장의 물가 기대는 3년 가운데 가장 낮은 쪽입니다' : expHi ? '물가가 목표(2%)보다 높고 시장의 물가 기대도 3년 가운데 높은 쪽입니다' : '물가는 목표(2%)보다 높고 시장의 물가 기대는 평소 수준입니다')
        : (expLo ? '물가는 목표(2%) 근처이고 시장의 물가 기대도 3년 가운데 낮은 쪽입니다' : expHi ? '물가는 목표(2%) 근처지만 시장의 물가 기대는 3년 가운데 높은 쪽입니다' : '물가와 시장의 물가 기대 모두 안정적입니다');
      let b = '', detail = `근원 PCE 전년비 ${F.n(I.core_pce_yoy, 2)}% (3개월 연율 ${F.n(I.core_pce_3m, 1)}%, 2.5% 넘으면 목표보다 높다고 봄) · 10년 BEI ${F.n(bei.level, 2)}%는 3년 백분위 ${F.n(bei.pct3y, 0)}`;
      if (real && y10row && ok(real.y1) && ok(bei.y1) && ok(y10row.chg.y1) && Math.abs(y10row.chg.y1) >= 10) {
        const dn = y10row.chg.y1, dir = dn > 0 ? '상승' : '하락', same = (v) => Math.sign(v) === Math.sign(dn);
        const lead = same(real.y1) && Math.abs(real.y1) >= 2 * Math.abs(bei.y1) ? 'real' : same(bei.y1) && Math.abs(bei.y1) >= 2 * Math.abs(real.y1) ? 'bei' : 'both';
        b = { real: `. 지난 1년 금리 ${dir}은 물가 기대가 아니라 실질금리가 이끌었습니다`, bei: `. 지난 1년 금리 ${dir}은 실질금리가 아니라 물가 기대가 이끌었습니다`,
              both: `. 지난 1년 금리 ${dir}에는 실질금리와 물가 기대가 함께 작용했습니다` }[lead];
        detail += ` · 지난 1년 10년 금리 ${F.bp(dn)} 가운데 실질금리 ${F.bp(real.y1)}, BEI ${F.bp(bei.y1)}`;
      }
      inflConcl = UI.concl(a + b, detail + '.');
    }
    const inflCard = UI.card({ id: 'infl', span: 'c12', title: '인플레이션 (BEI·실질금리)', cap: '10년 명목금리 = 실질금리 + 기대 인플레이션(BEI)',
      body: [inflConcl, inflTiles, h('div', { style: 'height:14px' }), infl.chart], alt: infl.alt,
      foot: 'BEI는 명목 국채와 물가연동채(TIPS)의 금리 차이로, 시장이 가격한 평균 물가 상승률에 위험 보상이 섞인 값입니다.' });

    // 결론 한 줄: 금리 수준을 보는 세 신호(정책, 성장, 물가)가 지금 어느 쪽을 가리키나. +1이 금리 하락 쪽
    const L = D.score.live, three = [['s1_policy', '정책 경로'], ['s2_growth', '성장·고용'], ['s3_inflation', '물가']];
    const dn = three.filter(([k]) => L[k] > 0).map((x) => x[1]), up = three.filter(([k]) => L[k] < 0).map((x) => x[1]);
    let title;
    if (!dn.length && !up.length) title = '매크로 신호는 모두 중립이라 금리 방향을 가리키지 않습니다';
    else if (L.view_level > 0) title = `매크로 신호는 금리 하락 쪽입니다. ${F.josa(dn.join('·'), '이', '가')} 하락을 가리키고` + (up.length ? `, 반대쪽은 ${dn.length > up.length ? up.join('·') + '뿐입니다' : up.join('·') + '입니다'}` : ' 반대 신호는 없습니다');
    else if (L.view_level < 0) title = `매크로 신호는 금리 상승 쪽입니다. ${F.josa(up.join('·'), '이', '가')} 상승을 가리키고` + (dn.length ? `, 반대쪽은 ${dn.join('·')}${up.length > dn.length ? '뿐입니다' : '입니다'}` : ' 반대 신호는 없습니다');
    else title = `매크로 신호는 엇갈립니다. ${F.josa(dn.join('·'), '은', '는')} 금리 하락 쪽, ${F.josa(up.join('·'), '은', '는')} 금리 상승 쪽이라 방향은 중립입니다`;
    return { title, lead, usOnly: true,
      sub: `근거: ${F.md(L.decision_date)} 기준 점수는 ${three.map(([k, n]) => `${n} ${F.s(L[k], 0)}`).join(', ')}이고 합은 ${F.s(L.view_level, 0)}입니다 (+1이 금리 하락 쪽). 세 신호 모두 지나간 발표에 반응하는 값이라 예측이 아닙니다. 선물 가격은 ${P.asof || '–'} 기준, 정책금리 목표 범위는 ${F.n(P.lower, 2)}~${F.n(P.upper, 2)}%입니다.`,
      tabs: [['releases', '지표 일정·서프라이즈'], ['cycle', '월별 지표 표'], ['policy', '정책금리 경로'], ['cb', '중앙은행 트래커'], ['infl', '인플레이션']],
      body: [relCard, surChart('nfp', '고용', '천 명', 150), surChart('cpi', '근원 CPI', 'bp', 15), heatCard, pathCard, meetCard, cbCard, inflCard] };
  };
})();
