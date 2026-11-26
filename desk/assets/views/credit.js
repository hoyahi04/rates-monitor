/* 5. 크레딧·소버린 — 발행자는 안전한가: 지수 스프레드 보드, 국가 스코어카드, 등급 트래커, CDS, 발행자 프로파일 */
(function () {
  'use strict';
  const { h, F, ok } = UI;

  window.DeskViews.credit = function (ctx) {
    const D = ctx.D, C = D.credit;

    // ── 스프레드 보드 (지수 OAS) ──
    const rows = C.ladder;
    let sel = 'oas_hy';
    const slot = h('div');
    const draw = () => {
      const r = rows.find((x) => x.key === sel) || rows[0];
      if (!r || !C.series) { slot.replaceChildren(); return; }
      const made = ctx.lineOf([{ key: r.key, name: r.label, color: 'var(--s1)' }], { src: C.series, h: 230, legend: false, unit: 'bp', tipFmt: (v) => F.n(v, 0), aria: r.label + ' OAS' });
      slot.replaceChildren(h('p', { cls: 'note', style: 'margin:0 0 6px;color:var(--ink2)' }, `${r.label} OAS (bp) — 표의 줄을 누르면 바뀝니다`), made.chart);
    };
    draw();
    const chg = (label, key, max) => ({ label, get: (r) => r[key], fmt: (v) => F.s(v), heat: (v, r) => UI.heat(v, r.group === 'IG' ? max : max * 4) });
    // 카드 결론: 한 달 사이 몇 개 등급이 벌어졌나 + 스프레드 대비 비율로 보면 어느 쪽이 더 벌어졌나
    const grades = rows.filter((r) => !['oas_ig', 'oas_hy', 'oas_em'].includes(r.key) && ok(r.m1) && ok(r.level) && r.level - r.m1 > 0);
    let ladderConcl = null;
    if (grades.length >= 5) {
      const rel = (r) => r.m1 / (r.level - r.m1) * 100, avg = (xs) => (xs.length ? xs.reduce((t, x) => t + x, 0) / xs.length : null);
      const nW = grades.filter((r) => r.m1 > 0).length, nT = grades.filter((r) => r.m1 < 0).length, n = grades.length;
      const ig = avg(grades.filter((r) => r.group === 'IG').map(rel)), hy = avg(grades.filter((r) => r.group === 'HY').map(rel));
      const hiAll = grades.every((r) => r.pct3y >= 80), loAll = grades.every((r) => r.pct3y <= 20);
      let text;
      if (nW === n || nT === n) {
        const dirW = nW === n, a = Math.abs(ig), b = Math.abs(hy);
        const where = !ok(ig) || !ok(hy) ? '' : b >= 1.5 * a ? ` 하이일드가 훨씬 크게 ${dirW ? '벌어져, 위험 회피가 낮은 등급에 몰려 있습니다' : '좁아져, 낮은 등급으로 돈이 돌아오고 있습니다'}`
          : a >= 1.5 * b ? ` 투자등급이 더 크게 ${dirW ? '벌어져, 높은 등급까지 불안이 번졌습니다' : '좁아졌습니다'}`
          : dirW ? ' 등급을 가리지 않고 비슷한 비율이라, 특정 등급의 문제가 아니라 시장 전체의 위험 회피입니다' : ' 등급을 가리지 않고 비슷한 비율로 좁아져, 시장 전체의 심리가 풀리고 있습니다';
        text = `한 달 사이 모든 등급의 스프레드가 ${dirW ? '벌어졌습니다' : '좁아졌습니다'}.${where}`;
      } else if (nW >= n - 2) text = '한 달 사이 대부분의 등급에서 스프레드가 벌어졌습니다';
      else if (nT >= n - 2) text = '한 달 사이 대부분의 등급에서 스프레드가 좁아졌습니다';
      else text = '한 달 사이 스프레드는 등급마다 엇갈려 뚜렷한 방향이 없습니다';
      const lvl = hiAll ? ` · ${n}개 등급 모두 3년 백분위 80 이상` : loAll ? ` · ${n}개 등급 모두 3년 백분위 20 이하` : '';
      ladderConcl = UI.concl(text, `한 달 변화를 한 달 전 스프레드에 대한 비율로 보면 투자등급 ${F.s(ig, 0)}%, 하이일드 ${F.s(hy, 0)}% (등급별 평균, 1.5배 넘게 차이 나면 한쪽에 몰렸다고 봄)${lvl}.`);
    }
    const ladderCard = UI.card({ id: 'ladder', span: 'c7', title: '스프레드 보드', cap: 'ICE BofA 지수 OAS (bp) · 달러 회사채', flush: true,
      tools: [UI.scaleKey('좁아짐', '벌어짐')],
      body: rows.length ? [ladderConcl, UI.table([{ label: '등급', align: 'l', get: (r) => r.label }, { label: 'OAS', get: (r) => r.level, fmt: (v) => F.n(v, 0) },
        chg('1주', 'w1', 8), chg('1달', 'm1', 12), chg('3달', 'm3', 20), chg('1년', 'y1', 30),
        { label: '3년 백분위', title: '지난 3년 가운데 지금보다 낮았던 날의 비율. 100이면 3년 중 가장 넓음', get: (r) => r.pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) }],
        { rows, dense: true, group: (r) => ({ IG: '투자등급', HY: '하이일드', EM: '신흥국' }[r.group]), onRow: (r) => { sel = r.key; draw(); } })]
        : UI.empty('스프레드 자료가 없습니다', 'FRED에서 ICE BofA 지수를 받지 못했습니다.'),
      foot: `종목이 아니라 지수 단위입니다. FRED는 이 지수를 최근 3년치(${C.oas_from || '–'}부터)만 제공합니다. 색의 진하기는 투자등급과 하이일드에 다른 눈금을 씁니다.` });
    const chartCard = UI.card({ span: 'c5', title: '스프레드 추이', cap: '기간 필터 적용', body: slot });

    // ── 만기별, 등급 간 ──
    const mat = C.maturity || [];
    const matCard = UI.card({ id: 'curve', span: 'c6', title: '투자등급 만기별 OAS', cap: '신용 스프레드 커브 (bp)',
      body: mat.length ? UI.bars({ cats: mat.map((m) => m.label), h: 210, unit: 'bp', labels: true, labFmt: (v) => F.n(v, 0), tipFmt: (v) => F.n(v, 0), aria: '만기별 투자등급 OAS',
        series: [{ name: '지금', color: 'var(--s1)', values: mat.map((m) => m.now) }, { name: '1년 전', color: 'var(--s-mute)', values: mat.map((m) => m.y1) }] }) : UI.empty('자료 없음', ''),
      alt: () => UI.table([{ label: '만기', align: 'l', get: (m) => m.label }, { label: '지금', get: (m) => m.now }, { label: '1달 전', get: (m) => m.m1 }, { label: '1년 전', get: (m) => m.y1 },
        { label: '3년 백분위', get: (m) => m.pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) }], { rows: mat, dense: true }) });
    const qCard = UI.card({ span: 'c6', title: '등급 간 스프레드', cap: '낮은 등급이 얼마나 더 받나 (bp)', flush: true,
      body: UI.table([{ label: '구분', align: 'l', get: (q) => q.label }, { label: '수준', get: (q) => q.level, fmt: (v) => F.n(v, 0) },
        { label: '1달', get: (q) => q.m1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 40) }, { label: '1년', get: (q) => q.y1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 100) },
        { label: '3년 백분위', get: (q) => q.pct3y, fmt: (v) => F.n(v, 0), heat: (v) => UI.heatPct(v) },
        { label: '1년 추이', align: 'c', sort: false, get: (q) => q.label, fmt: (_, q) => UI.spark(q.spark) }], { rows: C.quality || [], dense: true }),
      foot: '등급 간 스프레드가 벌어지면 시장이 약한 발행자를 가려서 피하기 시작했다는 뜻입니다.' });

    // ── 한국 크레딧 (키가 있으면) ──
    const krRows = ctx.krOk ? D.kr.spreads.filter((r) => r.group === '크레딧') : [];
    const krCard = krRows.length ? UI.card({ span: 'c12', title: '한국 회사채 스프레드', cap: '회사채 3년 − 국고채 3년 (bp) · 한국은행 ECOS', flush: true,
      body: UI.table([{ label: '스프레드', align: 'l', get: (r) => r.label }, { label: '수준', get: (r) => r.level, fmt: (v) => F.n(v, 0) + 'bp' },
        { label: '1주', get: (r) => r.w1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 10) }, { label: '1달', get: (r) => r.m1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 20) },
        { label: '1년', get: (r) => r.y1, fmt: (v) => F.s(v), heat: (v) => UI.heat(v, 50) }, { label: 'z-score (3년)', get: (r) => r.z3y, fmt: (v) => F.s(v, 2), heat: (v) => UI.heat(v, 2.5) },
        { label: '1년 추이', align: 'c', sort: false, get: (r) => r.key, fmt: (_, r) => UI.spark(r.spark) }], { rows: krRows, dense: true }) }) : null;

    // ── 국가 스코어카드 ──
    const sov = C.sovereign || [];
    const colHeat = (key, invert) => {
      const vals = sov.map((r) => r[key]).filter(ok).sort((a, b) => a - b);
      if (vals.length < 3) return () => '';
      const med = vals[Math.floor(vals.length / 2)], max = Math.max(...vals.map((v) => Math.abs(v - med))) || 1;
      return (v) => (ok(v) ? UI.heat(v - med, max, invert) : '');
    };
    const rate = {};
    for (const x of C.ratings || []) { (rate[x.issuer] = rate[x.issuer] || []).push(`${x.agency} ${x.rating}`); }
    const VERDICT = { good: '양호', mid: '보통', bad: '주의' };
    const names = (v) => sov.filter((r) => r.verdict === v).sort((a, b) => b.score - a.score).map((r) => r.name);
    const gd = names('good'), bd = names('bad').reverse();
    const sovConcl = sov.some((r) => ok(r.score)) ? UI.concl(
      (gd.length ? `재정·경제 여건은 ${F.josa(gd.join('·'), '이', '가')} 양호하고` : '양호한 나라는 없고') + (bd.length ? `, ${F.josa(bd.join('·'), '은', '는')} 주의가 필요합니다` : ', 주의가 필요한 나라는 없습니다'),
      '아홉 나라 안에서의 상대 비교입니다. 재정(정부부채), 경제(실업률), 시장(10년 금리 수준과 1년 변화)을 순위로 점수화해 같은 무게로 평균했고(모두 낮을수록 좋다고 봄), 60점 이상 양호 · 40점 미만 주의입니다.') : null;
    const sovCard = UI.card({ id: 'sov', span: 'c12', title: '국가 스코어카드', cap: 'OECD 월별 자료 (FRED 경유) · 색은 아홉 나라 중간값과의 차이', flush: true,
      tools: [UI.scaleKey('중간값보다 낮음', '높음')],
      body: sov.length ? [sovConcl, UI.table([{ label: '나라', align: 'l', get: (r) => r.name },
        { label: '10년 금리', title: '월평균', get: (r) => r.y10, fmt: (v, r) => [F.n(v, 2) + '%', h('span', { cls: 'sub2' }, r.y10_date || '')], heat: colHeat('y10') },
        { label: '1달 변화', get: (r) => r.y10_m1, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 50) },
        { label: '1년 변화', get: (r) => r.y10_y1, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) },
        { label: '미국 대비', get: (r) => r.vs_us, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 250) },
        { label: '3개월 금리', get: (r) => r.r3m, fmt: (v) => (ok(v) ? F.n(v, 2) + '%' : '자료 끊김'), heat: colHeat('r3m') },
        { label: '10년 − 3개월', get: (r) => r.slope, fmt: (v) => F.bp(v), heat: colHeat('slope') },
        { label: '실업률', get: (r) => r.unemp, fmt: (v, r) => (ok(v) ? [F.n(v, 1) + '%', h('span', { cls: 'sub2' }, r.unemp_date || '')] : '자료 끊김'), heat: colHeat('unemp') },
        { label: '정부부채 / GDP', get: (r) => r.debt_gdp, fmt: (v, r) => (ok(v) ? [F.n(v, 0) + '%', h('span', { cls: 'sub2' }, r.debt_year || '')] : '–'), heat: colHeat('debt_gdp') },
        { label: '신용등급', align: 'l', sort: false, get: (r) => r.name, fmt: (v) => (rate[v] ? rate[v].join(' · ') : h('span', { cls: 'mute' }, '입력 전')) },
        { label: '10년 금리 3년 추이', align: 'c', sort: false, get: (r) => r.code, fmt: (_, r) => UI.spark(r.spark, { w: 84 }) },
        { label: '종합', align: 'c', title: '재정(정부부채), 경제(실업률), 시장(10년 금리 수준과 1년 변화) 세 갈래를 나라들 안의 순위로 점수화해 평균 (100점이 가장 좋음)', get: (r) => r.score,
          fmt: (v, r) => (ok(v) ? h('span', { cls: 'verdict ' + r.verdict, title: Object.entries(r.pillars || {}).map(([k, x]) => `${k} ${x}점`).join(' · ') },
            h('i'), VERDICT[r.verdict], h('small', null, v + '점')) : h('span', { cls: 'mute' }, '자료 부족')) }],
        { rows: sov, dense: true, sortable: true })] : UI.empty('자료 없음', 'FRED에서 나라별 자료를 받지 못했습니다.'),
      foot: '종합은 신용등급이 아니라 이 표 안에서 매긴 상대 점수이고, 칸에 마우스를 올리면 재정·경제·시장 점수가 보입니다. 금리가 높아 투자 매력이 있는지는 RV·전략에서 따로 봅니다. 10년 금리와 3개월 금리는 그달 평균이라 시장 모니터의 일별 값과 다릅니다. 물가 상승률은 OECD 시리즈가 나라마다 끊겨 있어 싣지 않았습니다. 정부부채는 IMF 연간 값으로 한두 해 늦습니다. 유로존 세 나라의 3개월 금리는 같은 값(Euribor)입니다.' });

    // ── 자료가 없는 칸 ──
    const ratingCard = UI.card({ id: 'ratings', span: 'c4', title: '등급 트래커',
      body: (C.ratings || []).length
        ? UI.table([{ label: '발행자', align: 'l', get: (x) => x.issuer }, { label: '평가사', align: 'l', get: (x) => x.agency }, { label: '등급', align: 'l', get: (x) => x.rating },
            { label: '전망', align: 'l', get: (x) => x.outlook }, { label: '날짜', get: (x) => x.date }], { rows: C.ratings, dense: true })
        : UI.empty('직접 적어야 하는 칸입니다', '신용등급은 자동으로 받을 수 있는 무료 출처가 없습니다. data/ratings.csv에 발행자, 평가사, 등급, 전망, 날짜를 적으면 여기와 국가 스코어카드에 나타납니다.') });
    const cdsCard = UI.card({ id: 'cds', span: 'c4', title: 'CDS 모니터', body: UI.empty('자료 없음', '개별 CDS 호가는 무료 출처가 사실상 없습니다 (Bloomberg, Markit 영역). 부도 위험의 방향은 위의 지수 OAS로 대신 봅니다.') });
    const issuerCard = UI.card({ id: 'issuer', span: 'c4', title: '발행자 프로파일', body: UI.empty('아직 만들지 않았습니다', '공시(DART, EDGAR)에서 재무제표를 읽어 올 수는 있지만 발행자마다 손이 많이 갑니다. 볼 발행자가 정해지면 추가합니다.') });

    // 결론 한 줄
    const ig = rows.find((r) => r.key === 'oas_ig'), hy = rows.find((r) => r.key === 'oas_hy');
    let lead = '신용 스프레드 자료가 없습니다', title = lead, basis = '';
    if (ig && hy) {
      const where = (p) => (p >= 80 ? '3년 범위의 위쪽' : p <= 20 ? '3년 범위의 아래쪽' : '3년 범위의 가운데');
      const tail = Math.abs(hy.w1) >= 15 ? `이고, 한 주 사이 하이일드가 ${Math.abs(hy.w1).toFixed(0)}bp ${hy.w1 > 0 ? '벌어졌습니다' : '좁아졌습니다'}` : '입니다';
      lead = `투자등급 OAS ${F.n(ig.level, 0)}bp, 하이일드 ${F.n(hy.level, 0)}bp로 ${where(hy.pct3y)}(백분위 ${F.n(ig.pct3y, 0)}, ${F.n(hy.pct3y, 0)})${tail}`;
    }
    // 결론 한 줄: 하이일드 스프레드가 3년 가운데 높은가 낮은가 + 한 달 사이 벌어지는가 좁아지는가
    if (ig && hy) {
      const lvl = hy.pct3y >= 80 ? 'high' : hy.pct3y <= 20 ? 'low' : 'mid', mom = hy.m1 >= 30 ? 'wide' : hy.m1 <= -30 ? 'tight' : 'flat';
      title = { 'high/wide': '신용 시장이 불안합니다. 스프레드가 3년 가운데 높은 수준이고 계속 벌어지고 있습니다',
        'high/flat': '신용 스프레드는 3년 가운데 높은 수준이지만 더 벌어지지는 않고 있습니다', 'high/tight': '신용 스프레드는 아직 높지만 좁아지며 진정되고 있습니다',
        'mid/wide': '신용 스프레드가 벌어지고 있습니다. 아직 3년 범위의 가운데입니다', 'mid/flat': '신용 시장은 평소 수준으로 조용합니다',
        'mid/tight': '신용 스프레드가 좁아지고 있습니다', 'low/wide': '신용 스프레드는 아직 낮지만 벌어지기 시작했습니다',
        'low/flat': '신용 시장은 안정적입니다. 다만 스프레드가 얇아 위험을 지는 보상은 작습니다', 'low/tight': '신용 스프레드가 3년 가운데 가장 얇은 쪽으로 더 좁아지고 있습니다' }[lvl + '/' + mom];
      basis = `근거: 하이일드 OAS의 3년 백분위 ${F.n(hy.pct3y, 0)} (80 이상 높음, 20 이하 낮음), 한 달 변화 ${F.bp(hy.m1)} (±30bp부터 벌어짐·좁아짐으로 봄). `;
    }
    return { title, lead: ig && hy ? lead : null, usOnly: !ctx.krOk,
      sub: basis + '이 화면은 "발행자가 안전한가"를 봅니다. 종목 단위 자료(개별 회사채, CDS)는 무료로 구할 수 없어 지수와 나라 단위로만 채웠습니다.',
      tabs: [['ladder', '스프레드 보드'], ['curve', '만기별·등급 간'], ['sov', '국가 스코어카드'], ['ratings', '등급 트래커'], ['cds', 'CDS 모니터'], ['issuer', '발행자 프로파일']],
      body: [ladderCard, chartCard, matCard, qCard, krCard, sovCard, ratingCard, cdsCard, issuerCard] };
  };
})();
