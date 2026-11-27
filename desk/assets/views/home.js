/* 홈 (Desk Overview): 주요 금리·커브·변동성, 내 포트폴리오, 일정, 이번 달 판정, 뉴스 */
(function () {
  'use strict';
  const { h, F, ok } = UI;

  window.DeskViews.home = function (ctx) {
    const D = ctx.D, B = D.book, heat = Object.fromEntries(D.us.heat.map((r) => [r.tenor, r]));
    const sp = Object.fromEntries(D.spreads.map((r) => [r.key, r])), xa = Object.fromEntries(D.xasset.map((r) => [r.key, r]));
    const y10 = heat['10Y'];

    // 사실 요약 (두 번째 소제목)
    const w = y10.chg.w1;
    const move = !ok(w) || Math.abs(w) < 0.5 ? '한 주 전과 같고' : `한 주 동안 ${Math.abs(w).toFixed(0)}bp ${w < 0 ? '내렸고' : '올랐고'}`;
    const act = B.active_dur;
    const stance = Math.abs(act) < 0.03 ? '포트폴리오 듀레이션은 벤치마크와 같습니다' : `포트폴리오 듀레이션은 벤치마크보다 ${Math.abs(act).toFixed(2)}년 ${act > 0 ? '깁니다' : '짧습니다'}`;
    const lead = `10년 금리는 ${F.n(y10.level, 2)}%로 ${move}, ${stance}`;

    // 결론 한 줄: 이번 주 금리 움직임이 포트폴리오에 유리했나 (실제 초과수익으로 확인)
    const exW = B.perf.w1 ? B.perf.w1.ex_bp : null;
    const rateDir = !ok(w) || Math.abs(w) < 2 ? 0 : Math.sign(w), posDir = Math.abs(act) < 0.03 ? 0 : Math.sign(act);
    let title;
    if (!ok(exW)) title = '포트폴리오의 이번 주 성과를 계산하지 못했습니다';
    else if (Math.abs(exW) < 0.5) title = '이번 주 포트폴리오는 벤치마크와 거의 같게 움직였습니다';
    else {
      const res = `벤치마크를 ${F.n(Math.abs(exW), Math.abs(exW) < 10 ? 1 : 0)}bp ${exW > 0 ? '앞섰습니다' : '뒤졌습니다'}`;
      const fits = Math.sign(exW) === -rateDir * posDir;        // 금리가 내리고 듀레이션을 확대했으면 앞서는 것이 맞다
      title = rateDir && posDir && fits ? `금리가 ${rateDir < 0 ? '내려' : '올라'}, 듀레이션을 ${posDir > 0 ? '확대' : '축소'}한 포트폴리오가 이번 주 ${res}` : `이번 주 포트폴리오는 ${res}`;
    }

    // 금리·커브·변동성 타일
    const rateTile = (t, label) => {
      const r = heat[t];
      return UI.tile({ lab: label, val: F.n(r.level, 2), unit: '%', spark: r.spark, hero: t === '10Y', onClick: () => ctx.go('market', 'heat'),
        deltas: [{ k: '1일', v: F.bp(r.chg.d1), raw: r.chg.d1 }, { k: '1주', v: F.bp(r.chg.w1), raw: r.chg.w1 }] });
    };
    const spTile = (r, label, digits, unit, anchor) => UI.tile({ lab: label, val: F.n(r.level, digits), unit, spark: r.spark,
      onClick: () => ctx.go('market', anchor || 'spreads'),
      deltas: [{ k: '1일', v: F.bp(r.d1), raw: r.d1 }, { k: '1주', v: F.bp(r.w1), raw: r.w1 }] });
    const move_ = xa.move;
    const tiles = h('div', { cls: 'tiles c12' },
      rateTile('2Y', '미국 2년'), rateTile('10Y', '미국 10년'), rateTile('30Y', '미국 30년'),
      spTile(sp.s2s10s, '2s10s', 0, 'bp'), sp.real10 ? spTile(sp.real10, '10년 실질금리', 2, '%') : null,
      move_ ? UI.tile({ lab: 'MOVE (채권 변동성)', val: F.n(move_.level, 0), spark: move_.spark, onClick: () => ctx.go('market', 'xasset'),
        deltas: [{ k: '1일', v: F.s(move_.d1, 1), raw: move_.d1 }, { k: '1주', v: F.s(move_.w1, 1), raw: move_.w1 }] }) : null,
      sp.oas_hy ? spTile(sp.oas_hy, '하이일드 OAS', 0, 'bp') : null);

    // 내 포트폴리오
    const te = B.risk.te_exante_bp, bud = B.risk.budget;
    const pos = B.position;
    const posText = [`Duration ${pos.dur ? F.s(pos.dur, 2) + '년' : '중립'}`, `Slope ${{ none: '없음', steepener: '스티프너', flattener: '플래트너' }[pos.slope] || pos.slope}`,
                     `Curvature ${{ none: '없음', bullet: '불릿' }[pos.curv] || pos.curv}`, 'Carry 유지'].join(' · ');
    const kv = (items) => h('dl', { cls: 'kv' }, items.map(([k, v, u, cls]) => h('div', null, h('dt', null, k), h('dd', { cls: cls || null }, v, u ? h('small', null, u) : null))));
    const bookCard = UI.card({ span: 'c7', title: '내 포트폴리오', cap: `모형 포트폴리오 · ${B.start.slice(0, 4)}년 말 USD 10M으로 시작해 규칙대로 운용`,
      tools: [h('a', { href: '#/book', cls: 'cap' }, '포트폴리오·리스크 →')],
      body: [
        kv([['순자산 (NAV)', F.usd(B.nav)], ['일간 손익', F.usdS(B.pnl_d1_usd), null, UI.dirCls(B.pnl_d1_usd)],
            ['이번 달 초과수익', F.bp(B.perf.mtd.ex_bp, 1), '벤치마크 대비', UI.dirCls(B.perf.mtd.ex_bp)],
            ['DV01', F.usd(B.dv01), '/ bp'], ['DV01 차이', F.usdS(B.dv01 - B.dv01_b), '벤치마크 대비', UI.dirCls(B.dv01 - B.dv01_b)],
            ['액티브 듀레이션', F.s(B.active_dur, 2), '년 (전체 ' + F.n(B.dur_p, 2) + ')'],
            ['사전 추적오차', F.n(te, 0), `bp · 위험예산 ${bud[0]}~${bud[1]}`], ['올해 초과수익', F.bp(B.perf.ytd.ex_bp, 0), null, UI.dirCls(B.perf.ytd.ex_bp)],
            [`${B.start.slice(0, 4)}년 말 이후`, F.bp(B.perf.itd.ex_bp, 0), null, UI.dirCls(B.perf.itd.ex_bp)]]),
        h('p', { cls: 'note' }, `${F.mon(B.apply_month + '-01')} 포지션: ${posText} (${F.md(B.decision_date)} 판정). 실제 종목이 아니라 만기 구간마다 모형 국채 한 종목을 든 계산입니다.`)] });

    // 일정: 오늘부터 열흘
    const today = new Date().toISOString().slice(0, 10);
    const from = today < D.meta.asof ? D.meta.asof : today;
    const evs = D.events.filter((e) => e.date >= from && F.days(from, e.date) <= 10 && e.imp >= 2).slice(0, 12);
    const evList = h('ul', { cls: 'list' });
    let lastDay = null;
    for (const e of evs) {
      if (e.date !== lastDay) { lastDay = e.date; evList.appendChild(h('li', { cls: 'day' }, `${F.kdate(e.date)} (${F.wd(e.date)})${e.date === today ? ' · 오늘' : ''}`)); }
      evList.appendChild(h('li', null, h('span', { cls: 'when' }, e.time || '–'),
        h('span', { cls: 'what' }, h('i', { cls: 'imp ' + (e.imp >= 3 ? 'h' : 'm') }), e.title, h('small', null, [e.kind, e.note].filter(Boolean).join(' · ')))));
    }
    if (!evs.length) evList.appendChild(h('li', null, h('span'), h('span', { cls: 'mute' }, '열흘 안에 잡힌 주요 일정이 없습니다')));
    const evCard = UI.card({ span: 'c5', title: '일정', cap: '오늘부터 열흘 · 미 동부 시각 · 주요 일정만', body: evList,
      tools: [h('a', { href: '#/macro/releases', cls: 'cap' }, '지표 →')] });

    // 이번 달 판정
    const S = D.score, O = S.official, L = S.live;
    const scoreRow = (rec) => h('dl', { cls: 'scorerow' }, S.sections.map((sec) => {
      const v = rec[sec.key], part = rec === O ? sec.official : sec.live;
      return h('div', null, h('dt', null, sec.name), h('dd', { cls: UI.dirCls(v) }, F.s(v, 0)), h('small', { title: part && part.value_ko }, part ? part.word_ko : ''));
    }));
    const scoreCard = UI.card({ span: 'c7', title: '이번 달 판정', cap: `매크로 신호 5개 → 포지션 · ${F.md(O.decision_date)} 판정, ${F.mon(O.apply_month + '-01')} 적용`,
      body: [scoreRow(O), h('p', { cls: 'note', style: 'color:var(--ink)' }, O.position_ko),
        h('p', { cls: 'note' }, `${F.mon(L.apply_month + '-01')} 잠정 (${F.md(L.decision_date)} 기준): ${L.position_ko}` +
          ((S.changes || []).length ? ' — 바뀐 것: ' + S.changes.map((c) => `${c.name} ${c.from_ko} → ${c.to_ko}`).join(', ') : ' — 그대로')),
        h('p', { cls: 'note' }, '+1은 금리 하락 쪽 신호입니다. 다섯 신호 모두 지나간 발표에 반응하는 값이라 예측이 아닙니다. 규칙과 근거는 ',
          h('a', { href: '../macro/scoreboard_rules.html' }, '점수 규칙'), ', ', h('a', { href: '../pipeline/model/combined.html' }, '2페이지 버전'), '에 있습니다.')] });

    // 뉴스
    const news = h('ul', { cls: 'list' });
    for (const n of D.news.slice(0, 6)) {
      const safe = /^https?:\/\//.test(n.link) ? n.link : null;
      news.appendChild(h('li', null, h('span', { cls: 'when' }, F.md(n.ts)),
        h('span', { cls: 'what' }, safe ? h('a', { href: safe, target: '_blank', rel: 'noopener noreferrer' }, n.title) : n.title, h('small', null, `${n.src} · ${n.kind}`))));
    }
    const more = h('button', { cls: 'mini', type: 'button' }, '전체 보기');
    more.addEventListener('click', ctx.openNews);
    const newsCard = UI.card({ span: 'c5', title: '뉴스', cap: '연준·한국은행 · 하루 한 번 갱신', body: news, tools: [more] });

    // 이 데스크가 하는 일 (정보 화면이 아니라 운용 화면이라는 것을 먼저 밝힌다)
    const steps = [['1 · Monitor', '시장 파악', 'market', '무엇이 움직였나'], ['2 · Analyze', '원인 분석', 'macro', '왜 움직였나'],
                   ['3 · Identify', '기회 탐색', 'rv', '어디가 싸고 비싼가'], ['4 · Trade', '포지션 구성', 'rv/builder', 'DV01 기준 물량'],
                   ['5 · Manage', '위험·성과', 'book', '내 포트폴리오는 어떤가']];
    const flow = h('div', { cls: 'flow5' }, steps.map(([en, ko, to, q]) => h('a', { href: '#/' + to }, h('em', null, en), h('b', null, ko), h('span', null, q))));
    const purpose = h('section', { cls: 'purpose c12', 'aria-label': '이 데스크가 하는 일' },
      h('p', null, h('b', null, '이 데스크는 운용 화면입니다. '),
        `USD 10M 가상 미국채 포트폴리오를 자체 벤치마크(미국채 대용 지수) 대비 운용합니다. ` +
        '시장·매크로·수급·RV·크레딧 화면은 매달 말 포지션을 정하는 재료이고, 정한 포지션의 위험은 만기별 키레이트 듀레이션(KRD)으로, 결과는 벤치마크 대비 초과수익으로 봅니다.'),
      flow);

    // 지금 할 일: 지금 포지션, 만기별 액티브 KRD, 다음 판정에서 바뀌는 것
    const fmtYr = (v) => (Math.abs(v) < 0.005 ? '중립' : F.s(v, 2) + '년');
    const monthEnd = L.month_end || null, dLeft = monthEnd ? F.days(from, monthEnd) : null;
    const posChg = (S.changes || []).filter((c) => c.kind === 'position'), whyChg = (S.changes || []).filter((c) => c.kind !== 'position');
    const todo = posChg.length
      ? `${monthEnd ? F.md(monthEnd) + ' 종가에 ' : '다음 리밸런싱에서 '}${posChg.map((c) => `${c.name} ${c.from_ko} → ${c.to_ko}`).join(', ')}` +
        (posChg.some((c) => c.key === 'duration_active_yr') ? ` (DV01 차이 ${F.usdS(B.dv01 - B.dv01_b)} → ${F.usdS(B.dv01_b * L.duration_active_yr / B.dur_b)} / bp)` : '')
      : '포지션을 그대로 둡니다. 월말에 규칙값으로 다시 맞추기만 합니다';
    // KRD: 포트폴리오 스레드가 book.krd({labels, active_dv01, active_yr})를 넣으면 그것을 쓰고, 없으면 구간별 DV01 차이로 대신한다
    // (모형 채권이 구간마다 하나라 구간별 DV01이 곧 KRD)
    const K = B.krd && B.krd.labels ? B.krd : {
      labels: B.positions.map((p) => p.label),
      active_dv01: B.positions.map((p) => p.dv01 - p.dv01_b),
      active_yr: B.positions.map((p) => ok(p.active) ? p.active : (p.c_p - p.c_b)),
      note: '구간마다 모형 채권이 하나라 구간별 DV01 차이를 KRD로 씁니다' };
    const kmax = Math.max(1, ...K.active_dv01.map((v) => Math.abs(v || 0)));
    const krdStrip = h('div', { cls: 'krdstrip', role: 'img', 'aria-label': '만기별 액티브 KRD: ' + K.labels.map((l, i) => `${l} ${F.usdS(K.active_dv01[i])}`).join(', ') },
      K.labels.map((l, i) => {
        const v = K.active_dv01[i], y = K.active_yr ? K.active_yr[i] : null;
        return h('div', null, h('dt', null, l),
          h('span', { cls: 'bar' }, h('i', { cls: v < 0 ? 'neg' : 'pos', style: `width:${Math.round(Math.abs(v || 0) / kmax * 100)}%` })),
          h('dd', { cls: UI.dirCls(v) }, F.usdS(v)), ok(y) ? h('small', null, F.s(y, 2) + '년') : null);
      }));
    const actCard = UI.card({ span: 'c12', title: '지금 할 일', cap: `${F.mon(O.apply_month + '-01')} 포지션과 다음 판정 · ${D.meta.asof} 종가 기준`,
      tools: [h('a', { href: '#/book/exposure', cls: 'cap' }, '익스포저 →')],
      body: [
        kv([['지금 포지션', O.position_ko.replace(/ · Carry 유지$/, '')],
            ['액티브 듀레이션', fmtYr(act), `규칙 ${fmtYr(B.rule_active_dur)}`, UI.dirCls(act)],
            ['다음 판정', monthEnd ? F.md(monthEnd) : '월말', dLeft != null && dLeft >= 0 ? `${dLeft}일 남음 · 월말 종가` : null]]),
        h('p', { cls: 'todo' }, h('b', null, '할 일 '), todo + '.',
          whyChg.length ? h('small', null, ' 이유: ' + whyChg.map((c) => `${c.name} ${c.from_ko} → ${c.to_ko}`).join(', ') + ` (${F.md(L.decision_date)} 잠정 점수)`) : null),
        h('h3', { cls: 'mini-h' }, '만기별 액티브 KRD', h('small', null, ' 벤치마크보다 더 든 DV01 ($/bp) · 아래는 액티브 듀레이션 기여 (년)')),
        krdStrip,
        h('p', { cls: 'note' }, K.note || '포트폴리오·리스크 화면의 KRD 표와 같은 값입니다.')] });

    return { q: 'Desk Overview', title, lead, usOnly: true,
      sub: `근거: 한 주 동안 10년 금리 ${F.bp(w)}, 액티브 듀레이션 ${F.s(act, 2)}년, 벤치마크 대비 ${F.bp(exW, 1)}. ${D.meta.asof} 종가 기준이고, 숫자의 빨강은 오름, 파랑은 내림입니다.`,
      body: [purpose, actCard, tiles, h('div', { cls: 'stack c7' }, bookCard, scoreCard), h('div', { cls: 'stack c5' }, evCard, newsCard)] };
  };
})();
