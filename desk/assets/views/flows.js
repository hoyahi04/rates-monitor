/* 3. 수급·펀딩 — 누가 사고, 조달비용은: 입찰·발행 캘린더, 포지셔닝, 레포·펀딩, FX 헤지 비용 */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const TERM = (t) => t.replace('-Year', '년').replace('-Month', '개월').replace('-Week', '주').replace('-Day', '일');

  window.DeskViews.flows = function (ctx) {
    const D = ctx.D, FL = D.flows, asof = D.meta.asof;
    const today = new Date().toISOString().slice(0, 10), from = today < asof ? asof : today;
    const termYears = (t) => { const m = /(\d+)-Year/.exec(t); return m ? Number(m[1]) : 0.5; };

    // ── 입찰 캘린더 ──
    const upAll = FL.auctions.upcoming || [];
    const coupons = upAll.filter((a) => a.type !== 'Bill' && a.auction_date >= from && ctx.matOk(termYears(a.term)));
    const week = coupons.filter((a) => F.days(from, a.auction_date) <= 7 && !a.tips && !a.frn);
    const weekSum = week.reduce((s0, a) => s0 + (a.offering_bn || 0), 0);
    const bills = upAll.filter((a) => a.type === 'Bill' && a.auction_date >= from && F.days(from, a.auction_date) <= 7);
    const billSum = bills.reduce((s0, a) => s0 + (a.offering_bn || 0), 0);
    const upCard = UI.card({ id: 'auctions', span: 'c5', title: '입찰 캘린더', cap: '이표채 · 재무부 잠정 일정과 공고', flush: true,
      body: coupons.length ? UI.table([
        { label: '입찰일', align: 'l', get: (a) => a.auction_date, fmt: (v) => `${F.md(v)} (${F.wd(v)})` },
        { label: '종목', align: 'l', get: (a) => a.term, fmt: (v, a) => [TERM(v), ' ', a.reopening ? h('span', { cls: 'pill' }, '리오픈') : null, a.tips ? h('span', { cls: 'pill' }, 'TIPS') : null, a.frn ? h('span', { cls: 'pill' }, 'FRN') : null] },
        { label: '규모', get: (a) => a.offering_bn, fmt: (v) => (ok(v) ? F.bn(v) : '공고 전') },
        { label: '발행일', get: (a) => a.issue_date, fmt: (v) => F.md(v) },
        { label: '상태', align: 'l', get: (a) => a.high_yield, fmt: (v, a) => (ok(v) ? `낙찰 ${F.n(v, 3)}%` : a.tentative ? '잠정' : '공고') }],
        { rows: coupons.slice(0, 16), dense: true })
        : UI.empty('예정된 이표채 입찰이 없습니다', '재무부 잠정 일정을 받지 못했거나 만기 필터에 맞는 입찰이 없습니다.'),
      foot: `앞으로 7일 T-Bill 입찰 ${bills.length}건` + (billSum ? `, 공고된 규모 합계 ${F.bn(billSum)}` : '') + '. 규모는 공고(보통 입찰 며칠 전) 뒤에 채워집니다.' });

    // ── 최근 입찰 결과 ──
    const recent = (FL.auctions.recent || []).filter((a) => ctx.matOk(Number(a.tenor.replace('Y', ''))));
    const resCard = UI.card({ span: 'c7', title: '최근 입찰 결과', cap: '수요가 평소보다 강했나', flush: true,
      body: UI.table([
        { label: '입찰일', align: 'l', get: (a) => a.date, fmt: (v) => F.md(v) },
        { label: '종목', align: 'l', get: (a) => a.tenor, fmt: (v, a) => [v.replace('Y', '년'), a.reopen ? [' ', h('span', { cls: 'pill' }, '리오픈')] : null] },
        { label: '규모', get: (a) => a.size_bn, fmt: (v) => F.bn(v) },
        { label: '낙찰 금리', get: (a) => a.hy, fmt: (v) => F.n(v, 3) + '%' },
        { label: '응찰률', title: '응찰 금액 ÷ 발행 금액', get: (a) => a.btc, fmt: (v) => F.n(v, 2) },
        { label: '평소 대비', title: '같은 만기의 직전 입찰들 평균 응찰률과의 차이. +면 수요가 강했다', get: (a) => a.btc_gap, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 0.25, true) },
        { label: 'PD 인수 비율', title: '프라이머리 딜러가 가져간 비율. 높으면 최종 수요가 약했다', get: (a) => a.dealer, fmt: (v) => F.n(v, 1) + '%' },
        { label: '평소 대비', get: (a) => a.dealer_dev, fmt: (v) => F.s(v, 1) + '%p', heat: (v) => UI.heat(v, 5) },
        { label: '당일 10년', get: (a) => a.d10, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) },
        { label: '당일 30년', get: (a) => a.d30, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 15) }],
        { rows: recent, dense: true }),
      foot: '빨강은 금리를 올리는 쪽(약한 수요)입니다: 응찰률이 평소보다 낮거나 PD(프라이머리 딜러) 인수 비율이 평소보다 높을 때. ' + FL.auctions.tail_note + '.' });

    // ── 순발행과 연준 보유 ──
    const iss = FL.issuance, n = iss.months.length, k0 = Math.max(0, n - 24);
    const out = iss.outstanding;
    const issCard = UI.card({ id: 'issuance', span: 'c6', title: '이표채 순발행', cap: '월별 · 연준 보유분 변화 제외, 민간 소화분 (십억 달러)',
      body: [UI.bars({ cats: iss.months.slice(k0).map((m) => F.ym(m + '-01')), h: 200, unit: '', tipFmt: (v) => F.bn(v), aria: '월별 이표채 순발행',
               series: [{ name: '이표채 전체', color: 'var(--s1)', values: iss.coupon_net_bn.slice(k0) }, { name: '그중 T-Bond', color: 'var(--s2)', values: iss.long_net_bn.slice(k0) }] }),
             h('p', { cls: 'note' }, `${iss.asof} 잔액: T-Bill ${F.bn(out.bills_bn)} (전체의 ${F.n(iss.bill_share_pct[n - 1], 1)}%), T-Note ${F.bn(out.notes_bn)}, T-Bond ${F.bn(out.bonds_bn)}, 시장성 국채 합계 ${F.bn(out.marketable_bn)}.`)],
      alt: () => UI.table([{ label: '월', align: 'l', get: (i) => iss.months[i] }, { label: '이표채 순발행', get: (i) => iss.coupon_net_bn[i], fmt: (v) => F.n(v, 1) },
        { label: 'T-Bond 순발행', get: (i) => iss.long_net_bn[i], fmt: (v) => F.n(v, 1) }, { label: 'T-Bill 비중 (%)', get: (i) => iss.bill_share_pct[i], fmt: (v) => F.n(v, 2) }],
        { rows: iss.months.map((_, i) => i).reverse().slice(0, 24), dense: true }) });
    const soma = FL.soma, sc = UI.cut(soma.dates, ctx.st.period), somaX = soma.dates.slice(sc), somaY = soma.total.slice(sc);
    const somaCard = UI.card({ span: 'c6', title: '연준 보유 국채 (SOMA)', cap: '주별 · 십억 달러',
      body: [UI.line({ x: somaX, series: [{ name: '연준 보유 국채', color: 'var(--s1)', values: somaY }], h: 200, legend: false, tipFmt: (v) => F.bn(v), aria: '연준 보유 국채' }),
             h('p', { cls: 'note' }, `${soma.asof} 기준 ${F.bn(soma.total_bn)}. 3개월 동안 ${F.bnS(soma.chg_3m_bn)}, 1년 동안 ${F.bnS(soma.chg_1y_bn)}. 줄면 그만큼을 민간이 받아야 합니다.`)],
      alt: () => UI.seriesTable(somaX, [{ name: '연준 보유 국채 (십억 달러)', values: somaY, fmt: (v) => F.n(v, 0) }], 36) });

    // ── 포지셔닝 ──
    const tenorY = { '2Y': 2, '5Y': 5, '10Y': 10, U10: 10, UB20: 20, UB30: 30 };
    const cf = (FL.cftc || []).filter((c) => ctx.matOk(tenorY[c.key] || 10));
    let sel = (cf.find((c) => c.key === '10Y') || cf[0] || {}).key;
    const cfSlot = h('div');
    const drawCf = () => {
      const c = cf.find((x) => x.key === sel);
      if (!c) { cfSlot.replaceChildren(); return; }
      cfSlot.replaceChildren(h('p', { cls: 'note', style: 'margin:0 0 6px;color:var(--ink2)' }, `${c.name} 순포지션 (천 계약, 최근 3년) — 표의 줄을 누르면 바뀝니다`),
        UI.line({ x: c.dates, h: 210, zero: true, tipFmt: (v) => F.s(v, 0), unit: '천', aria: c.name + ' 순포지션',
          series: [{ name: '자산운용사', color: 'var(--s1)', values: c.am_s }, { name: '레버리지 펀드', color: 'var(--s2)', values: c.lev_s }] }));
    };
    drawCf();
    const who = (key, label) => [
      { label: label + ' 순', get: (c) => c[key].net_k, fmt: (v) => F.s(v, 0) },
      { label: '1주', get: (c) => c[key].w1_k, fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 200) },
      { label: '3년 백분위', get: (c) => c[key].pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) }];
    const cfCard = UI.card({ id: 'positioning', span: 'c12', title: '포지셔닝 (CFTC 국채선물)', cap: cf.length ? `주 1회 · ${cf[0].date} 화요일 기준 · 천 계약` : '주 1회',
      tools: [UI.scaleKey('매도 쪽', '매수 쪽')],
      body: cf.length ? [UI.table([{ label: '계약', align: 'l', get: (c) => c.name }, { label: '미결제 약정', get: (c) => c.oi_k, fmt: (v) => F.n(v, 0) }]
        .concat(who('am', '자산운용사'), who('lev', '레버리지 펀드'), who('dealer', '딜러')),
        { rows: cf, dense: true, onRow: (c) => { sel = c.key; drawCf(); } }), h('div', { style: 'height:14px' }), cfSlot]
        : UI.empty('포지션 자료가 없습니다', 'CFTC 보고서를 받지 못했거나 만기 필터에 맞는 계약이 없습니다.'),
      foot: '레버리지 펀드의 순매도는 대부분 현물 국채를 사고 선물을 파는 베이시스 거래의 선물 쪽 다리입니다. 순매도가 크다는 것만으로 금리 상승에 베팅했다고 읽으면 안 됩니다.' });

    // ── 레포·펀딩 ──
    const fu = FL.funding;
    const alarm = h('span', { cls: 'status ' + (fu.alarm_on ? 'crit' : 'good') }, h('i'), fu.alarm_on ? '자금시장 경보 켜짐' : '자금시장 경보 꺼짐');
    const sofr = ctx.lineOf([{ key: 'sofr_iorb', name: 'SOFR − IORB', color: 'var(--s1)' }, { key: 'effr_iorb', name: 'EFFR − IORB', color: 'var(--s2)' }],
      { h: 210, unit: 'bp', zero: true, tipFmt: (v) => F.s(v, 0), refs: [{ y: fu.alarm_bp, label: `경보 기준 +${fu.alarm_bp}bp` }], aria: 'SOFR와 EFFR의 IORB 대비 차이' });
    const fundCard = UI.card({ id: 'funding', span: 'c6', title: '레포·펀딩', cap: '달러 단기 조달 금리와 유동성', tools: [alarm],
      body: [UI.table([{ label: '지표', align: 'l', get: (r) => r.label },
        { label: '수준', get: (r) => r.level, fmt: (v, r) => (r.unit === '%' ? F.n(v, 2) + '%' : r.unit === 'bp' ? F.s(v, 0) + 'bp' : F.bn(v)) },
        { label: '1주', get: (r) => r.w1, fmt: (v, r) => (r.chg_unit === 'bp' ? F.s(v, 0) : F.s(v * 10, 0) + '억') },
        { label: '1달', get: (r) => r.m1, fmt: (v, r) => (r.chg_unit === 'bp' ? F.s(v, 0) : F.s(v * 10, 0) + '억') },
        { label: '3년 백분위', get: (r) => r.pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) },
        { label: '기준일', get: (r) => r.date, fmt: (v) => F.md(v) }], { rows: fu.rows, dense: true }),
        h('p', { cls: 'note' }, `경보는 SOFR − IORB의 ${fu.alarm_days}영업일 평균이 +${fu.alarm_bp}bp를 넘을 때 켜집니다. 지금 평균은 ${F.s(fu.fund_avg_bp, 1)}bp입니다. 금리 변화는 bp, 잔액 변화는 억 달러입니다.`)] });
    const fundChart = UI.card({ span: 'c6', title: 'SOFR·EFFR − IORB', cap: 'bp · 0보다 크게 오르면 지급준비금이 빠듯하다는 신호', body: sofr.chart, alt: sofr.alt });

    // ── FX 헤지 비용 ──
    let fxCard;
    if (ctx.krOk && D.kr.series.cols.hedge_3m) {
      const fx = ctx.lineOf([{ key: 'hedge_3m', name: '미국 3개월 국채 − 한국 CD 91일', color: 'var(--s1)' }], { src: D.kr.series, h: 210, unit: '%p', zero: true, legend: false, tipFmt: (v) => F.s(v, 2) });
      fxCard = UI.card({ id: 'fx', span: 'c12', title: 'FX 헤지 비용 (근사)', cap: '원화 투자자가 달러 채권을 3개월 환헤지할 때 드는 비용의 금리차 부분 (연율 %p)', body: fx.chart, alt: fx.alt,
        foot: '실제 헤지 비용은 여기에 통화스왑 베이시스가 더해집니다. 베이시스는 무료로 받을 수 있는 자료가 없어 빠져 있으므로, 실제 비용은 이 값보다 대체로 큽니다.' });
    } else {
      fxCard = UI.card({ id: 'fx', span: 'c12', title: 'FX 헤지 비용 (통화스왑 베이시스)',
        body: UI.empty('자료 없음', '통화스왑 베이시스와 FX 스왑 포인트는 무료로 받을 수 있는 출처가 없습니다 (인포맥스·Bloomberg 영역). 한국은행 ECOS 인증키를 넣으면 미국 3개월 금리와 한국 CD 금리의 차이로 헤지 비용의 금리차 부분만 근사해 보여 줍니다.') });
    }

    // 사실 요약 (두 번째 소제목)
    const sofrRow = fu.rows.find((r) => r.key === 'sofr_minus_rr_bp');
    const aucTxt = week.length ? `앞으로 7일 이표채 입찰은 ${week.map((a) => TERM(a.term)).join('·')}` + (weekSum ? ` 합계 ${F.bn(weekSum)}` : '') + '이고' : '앞으로 7일 안에 이표채 입찰은 없고';
    const fundTxt = sofrRow ? `SOFR는 IORB(지급준비금 이자율)보다 ${Math.abs(sofrRow.level).toFixed(0)}bp ${sofrRow.level >= 0 ? '높아' : '낮아'} 경보 기준(+${fu.alarm_bp}bp) ${fu.alarm_on ? '을 넘었습니다' : '아래입니다'}` : '';

    // 결론 한 줄: 공급(점수표의 수급 점수) + 최근 입찰 수요 → 장기 금리에 어느 쪽인가, 그리고 자금시장
    const s4 = D.score.live.s4_supply, dm = FL.demand || {}, sec4 = D.score.sections.find((x) => x.key === 's4_supply');
    const sup = s4 > 0 ? 'up' : s4 < 0 ? 'down' : 'flat', dem = dm.state || 'normal';
    const stem = {
      'up/weak': '장기물 공급이 늘고 입찰 수요도 약해 수급은 장기 금리를 올리는 쪽', 'up/normal': '장기물 공급이 늘고 있어 수급은 장기 금리를 올리는 쪽',
      'up/strong': '장기물 공급은 늘지만 입찰 수요가 강해 수급은 금리에 중립', 'down/weak': '장기물 공급은 줄지만 최근 입찰 수요가 약해 수급은 금리에 중립',
      'down/normal': '장기물 공급이 줄고 있어 수급은 장기 금리를 내리는 쪽', 'down/strong': '장기물 공급이 줄고 입찰 수요도 강해 수급은 장기 금리를 내리는 쪽',
      'flat/weak': '최근 입찰 수요가 약해 수급은 장기 금리를 올리는 쪽', 'flat/strong': '최근 입찰 수요가 강해 수급은 장기 금리를 내리는 쪽',
      'flat/normal': '공급과 입찰 수요 모두 평소 수준이라 수급은 금리에 중립' }[sup + '/' + dem];
    const tight = sofrRow && sofrRow.pct3y >= 80;
    const fundVerdict = fu.alarm_on ? '자금시장은 경보 기준을 넘었습니다' : tight ? '자금시장은 지난 3년 가운데 빠듯한 편입니다' : '자금시장은 조용합니다';
    const why = [`장기물 공급 점수 ${F.s(s4, 0)}${sec4 && sec4.live ? ' (' + sec4.live.word_ko + ')' : ''}`,
      ok(dm.avg_gap) ? `최근 입찰 ${dm.n}건의 응찰률이 평소보다 평균 ${F.n(Math.abs(dm.avg_gap), 2)} ${dm.avg_gap < 0 ? '낮음' : '높음'} (2010년 이후 ${dm.avg_gap < 0 ? '하위 ' + F.n(dm.pct_hist, 0) : '상위 ' + F.n(100 - dm.pct_hist, 0)}%, 하위 25%부터 약함·상위 25%부터 강함으로 봄)` : null,
      sofrRow ? `SOFR − IORB의 3년 백분위 ${F.n(sofrRow.pct3y, 0)} (80부터 빠듯한 편으로 봄)` : null].filter(Boolean).join(' · ');
    return { title: `${stem}이고, ${fundVerdict}`, lead: `${aucTxt}, ${fundTxt}`, usOnly: true,
      sub: `근거: ${why}. 수급 신호는 과거에 커브 방향을 잘 맞히지 못했으므로 예측이 아니라 지금 상태의 요약으로 읽으세요. 입찰은 재무부, 포지션은 CFTC(주 1회), 조달 금리는 뉴욕 연준과 FRED 자료입니다.`,
      tabs: [['auctions', '입찰·발행 캘린더'], ['issuance', '순발행'], ['positioning', '포지셔닝'], ['funding', '레포·펀딩'], ['fx', 'FX 헤지 비용']],
      body: [upCard, resCard, issCard, somaCard, cfCard, fundCard, fundChart, fxCard] };
  };
})();
