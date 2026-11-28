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

    // 점도표 분포 (SEP 그림 2): 위원별 점, 이번 중간값(파란 선)과 직전 중간값(회색 선)
    const dotPlot = (DT) => {
      if (!DT || !DT.dist) return null;
      const cols = Object.keys(DT.dist), lv = [...new Set(cols.flatMap((c) => Object.keys(DT.dist[c])).map(Number))];
      const lo = Math.min(...lv) - 0.125, hi = Math.max(...lv) + 0.125, W = 900, H = 300, cw = (W - 60) / cols.length;
      const Y = (v) => 16 + (hi - v) / (hi - lo) * (H - 46);
      const kids = [];
      for (let v = Math.ceil(lo * 4) / 4; v <= hi; v += 0.25) kids.push(UI.s('line', { x1: 50, x2: W, y1: Y(v), y2: Y(v), stroke: 'var(--grid)' }), UI.s('text', { x: 44, y: Y(v) + 4, 'font-size': 11, 'text-anchor': 'end', fill: 'var(--mute)' }, v.toFixed(2)));
      cols.forEach((c, i) => {
        const cx = 60 + cw * i + cw / 2;
        kids.push(UI.s('text', { x: cx, y: H - 8, 'font-size': 12, 'text-anchor': 'middle', fill: 'var(--ink)' }, c === 'LR' ? '장기' : c));
        for (const [lvl, n] of Object.entries(DT.dist[c])) for (let j = 0; j < n; j++) kids.push(UI.s('circle', { cx: cx + (j - (n - 1) / 2) * 9, cy: Y(Number(lvl)), r: 3.6, fill: 'var(--ink)' }));
        const m = DT.median && DT.median[c], pm = DT.prev_median && DT.prev_median[c];
        if (pm != null) kids.push(UI.s('line', { x1: cx - cw * 0.42, x2: cx + cw * 0.42, y1: Y(pm), y2: Y(pm), stroke: 'var(--mute)', 'stroke-width': 2, 'stroke-dasharray': '4 3' }));
        if (m != null) kids.push(UI.s('line', { x1: cx - cw * 0.42, x2: cx + cw * 0.42, y1: Y(m), y2: Y(m), stroke: 'var(--s1)', 'stroke-width': 2 }));
      });
      const chg = cols.filter((c) => DT.median && DT.prev_median && DT.median[c] != null && DT.prev_median[c] != null).map((c) => `${c === 'LR' ? '장기' : c} ${F.bp((DT.median[c] - DT.prev_median[c]) * 100, 0)}`).join(' · ');
      return h('div', null, h('p', { cls: 'note', style: 'margin:14px 0 4px;color:var(--ink);font-weight:600' }, `점도표 분포 (${DT.date} SEP, 점 하나 = 위원 한 명)`),
        UI.s('svg', { viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img', 'aria-label': '점도표 분포' }, ...kids),
        h('p', { cls: 'note' }, `파란 선 = 이번 중간값, 회색 점선 = 직전(${DT.prev_label || '직전 SEP'}) 중간값. 중간값 변화: ${chg || '–'}. 표 1의 중간값은 소수 첫째 자리로 반올림된 값입니다.`));
    };

    // FOMC 성명 리뷰: 직전 성명 대비 바뀐 단어(레드라인), 회의별 반대표와 2년 금리 당일 반응 (±5bp 이상 = 서프라이즈)
    const FO = P.fomc;
    let fomcCard = null;
    if (FO && FO.redline) {
      const red = h('p', { style: 'line-height:1.75;margin:0 0 10px' }, FO.redline.map(([k, t]) =>
        k === 'eq' ? t + ' ' : k === 'del' ? h('del', { style: 'color:var(--up-ink)' }, t) : h('ins', { style: 'color:var(--down-ink);font-weight:600' }, t)).flatMap((x) => [x, ' ']));
      const m0 = FO.meetings[0], ds = m0.dissent;
      const sideKo = { hawk: '매파(더 긴축)', dove: '비둘기파(더 완화)', other: '기타' };
      const dTxt = ds.names.length ? ds.names.map((x) => `${x.name} ${sideKo[x.side]}`).join(', ') : '없음';
      const reac = m0.d_y2 == null ? '당일 금리 자료가 아직 없습니다' : `2년 금리 ${F.bp(m0.d_y2, 0)}, 10년 ${F.bp(m0.d_y10, 0)}` + (m0.surprise ? ` → 시장에는 ${m0.surprise} 서프라이즈였습니다` : ' → 예상 범위 안(±5bp)이었습니다');
      fomcCard = UI.card({ id: 'fomc', span: 'c12', title: 'FOMC 성명 리뷰', cap: `${F.kdate(FO.latest)} 성명 vs ${F.kdate(FO.prev)} 성명`,
        body: [UI.concl(`이번 성명은 ${FO.total_words}단어 가운데 ${FO.changed_words}단어가 새로 들어갔고, 표결은 ${m0.vote ? m0.vote.join(' 대 ') : '–'}입니다`,
            `반대표: ${dTxt}. 시장 반응: ${reac}.`),
          h('p', { cls: 'note', style: 'margin:0 0 4px;color:var(--ink);font-weight:600' }, '레드라인 ',
            h('small', null, h('del', { style: 'color:var(--up-ink)' }, '지운 표현'), ' · ', h('ins', { style: 'color:var(--down-ink);font-weight:600' }, '새 표현'))), red,
          UI.table([{ label: '회의', align: 'l', get: (x) => x.date, fmt: (v) => F.kdate(v) }, { label: '표결', get: (x) => (x.vote ? x.vote.join('–') : null) },
            { label: '매파 반대', get: (x) => x.dissent.hawk }, { label: '비둘기 반대', get: (x) => x.dissent.dove },
            { label: '2년 당일', get: (x) => x.d_y2, fmt: (v) => F.bp(v, 0) }, { label: '10년 당일', get: (x) => x.d_y10, fmt: (v) => F.bp(v, 0) },
            { label: '2s10s 당일', get: (x) => x.d_2s10s, fmt: (v) => F.bp(v, 0) },
            { label: '서프라이즈 (±5bp)', get: (x) => x.surprise || '–' }, { label: '우리 기울기', get: (x) => x.tilt, fmt: (v) => F.bp(v, 1) },
            { label: '○/×', get: (x) => x.ox || '–' }], { rows: FO.meetings, dense: true }),
          h('p', { cls: 'note' }, `○/× = 회의가 있던 달 적용 중이던 우리 기울기 방향과 회의 당일 2년 금리 방향이 같았나 (기울기 0이면 채점 안 함). 최근 ${FO.meetings.length}회 중 채점 ${FO.ox_n}회, 적중 ${FO.ox_hits}회.`),
          dotPlot(FO.dots)],
        foot: h('span', null, '성명은 연준 홈페이지에서 자동으로 받습니다. 금리 반응은 재무부 CMT 종가 기준 성명 당일 변화(성명은 오후 2시, 종가에 반영). 반대표는 성명의 "Voting against" 문장을 규칙으로 읽습니다 (인상·완화 편향 반대 = 매파). 원문: ',
          h('a', { href: FO.url, target: '_blank', rel: 'noopener noreferrer' }, '최신 성명'), '.') });
    }

    // 시장 가격 vs 컨센서스: 선물 내재 금리 − 뉴욕 연은 SME 중간값 (±25bp 넘으면 시장이 컨센서스와 다르게 가격)
    const S = P.sme;
    let consCard = null;
    if (S && S.rows && S.rows.length) {
      const hd = S.head, g = hd ? hd.gap_bp : null;
      const word = g == null ? null : g >= 25 ? '컨센서스보다 매파적으로(금리를 높게) 가격하고 있습니다' : g <= -25 ? '컨센서스보다 비둘기적으로(금리를 낮게) 가격하고 있습니다' : '컨센서스와 비슷하게 가격하고 있습니다';
      // 컨센서스 + 우리 기울기 = 우리 경로 → 괴리 B (우리 − 선물) → 듀레이션 신호
      const V = P.view, vc = V && V.current, vl = V && V.live;
      const tiltWhy = (x) => `P2 성장·고용 ${F.s(x.p2, 0)}, P3 물가 ${F.s(x.p3, 0)} → −25bp × (${F.s(x.p2, 0)} ${x.p3 < 0 ? '−' : '+'} ${Math.abs(x.p3)}) ÷ 2 = ${F.bp(x.tilt_raw, 1)}` + (x.tilt !== x.tilt_raw ? ` → 한도에서 잘라 ${F.bp(x.tilt, 1)}` : '');
      const capKo = { start: '시작 한도', wide: '확대 한도 (적중률 55% 이상)', off: '0 (적중률 45% 미만, 컨센서스만 사용)' };
      const viewPart = vc ? [
        UI.concl(`우리 기울기는 ${F.bp(vc.tilt, 1)}라서 1년 뒤(${V.target.slice(0, 4)}년 ${Number(V.target.slice(5))}월) 우리 경로는 ${F.n(vc.ours, 2)}%, 선물은 ${F.n(V.futures, 2)}%입니다. 괴리 B ${F.bp(vc.gap_b, 0)} → ${vc.signal.ko}`,
          `${vc.label} 점수(${F.mon(vc.apply_month + '-01')} 적용, ${vc.decision_date} 판정) 기준. ` + (vl ? `잠정 점수(${F.mon(vl.apply_month + '-01')})로 바꾸면 기울기 ${F.bp(vl.tilt, 1)}, 괴리 B ${F.bp(vl.gap_b, 0)} → ${vl.signal.ko}.` : '')),
        UI.table([{ label: '줄', align: 'l', get: (x) => x[0] }, { label: '1년 뒤 금리', get: (x) => x[1], fmt: (v) => (v == null ? '' : F.n(v, 2) + '%') }, { label: '내용', align: 'l', get: (x) => x[2] }],
          { rows: [['① 컨센서스 (SME 중간값)', V.consensus, `뉴욕 연은 시장참가자 설문 ${S.survey}, 1년 뒤 시점은 월 단위 보간`],
            ['② 우리 기울기', null, `${F.bp(vc.tilt, 1)} (한도 ±${V.cap}bp, ${capKo[V.cap_key]}) · 근거: ${tiltWhy(vc)}`],
            ['③ 우리 경로 = ① + ②', vc.ours, ''],
            ['④ 선물 가격', V.futures, '연방기금금리 선물 월평균'],
            ['⑤ 괴리 B = ③ − ④', null, `${F.bp(vc.gap_b, 0)} → ${vc.signal.ko} (${vc.signal.why}). 기준 ±${V.rules.gapb_th[0]}bp 약, ±${V.rules.gapb_th[1]}bp 강`]], dense: true }),
        h('p', { cls: 'note' }, `한도를 정하는 적중률: 최근 12개월 동안 기울기가 있었던 ${V.hit.n12}개월 중 ${V.hit.hits12}번 적중(${V.hit.rate12 == null ? '–' : F.n(V.hit.rate12 * 100, 0) + '%'}). ` +
          `2015년부터 전체 ${V.hit.n_all}개월 적중률 ${V.hit.rate_all == null ? '–' : F.n(V.hit.rate_all * 100, 0) + '%'}. 적중 = 기울기 방향과 다음 달 2년 금리 변화 방향이 같음. 과거 기록은 팀 스코어보드 월별 점수로 거꾸로 계산한 값입니다.`),
        h('p', { cls: 'note', style: 'margin:14px 0 4px;color:var(--ink);font-weight:600' }, '참고: 시장 가격 vs 컨센서스 (시점별)')] : [];
      consCard = UI.card({ id: 'cons', span: 'c12', title: '컨센서스 vs 우리', cap: `컨센서스(SME ${S.survey}) + 우리 기울기 → 우리 경로 vs 선물 → 듀레이션 신호`,
        body: [...viewPart, hd ? (vc ? (a, b) => h('p', { cls: 'note' }, a + '. ' + b) : UI.concl)(`약 1년 뒤(${hd.label}) 기준으로 선물은 ${F.n(hd.fut, 2)}%, SME 중간값은 ${F.n(hd.sme, 2)}%라서 시장은 ${word}`,
            `갭 ${F.bp(g, 0)}. 기준: ±25bp 안이면 비슷, 넘으면 시장과 컨센서스가 갈린 것으로 봅니다. SME 장기 금리 ${F.n(S.lr, 2)}%, 향후 10년 평균 ${F.n(S.avg10, 2)}%.`) : null,
          UI.table([{ label: '시점', align: 'l', get: (x) => x.label }, { label: '선물 내재', get: (x) => x.fut, fmt: (v) => F.n(v, 2) },
            { label: 'SME 중간값', get: (x) => x.sme, fmt: (v) => F.n(v, 2) }, { label: 'SME 25~75%', get: (x) => `${F.n(x.p25, 2)}~${F.n(x.p75, 2)}` },
            { label: '점도표', get: (x) => x.dot, fmt: (v) => F.n(v, 3) }, { label: '선물 − SME', get: (x) => x.gap_bp, fmt: (v) => F.bp(v, 0) }],
            { rows: S.rows.filter((x) => x.fut != null), dense: true })],
        foot: h('span', null, '선물은 월평균 금리라 회의가 있는 달은 다음 달 평균(회의 뒤 수준)과 비교합니다. SME는 목표 범위 중간값, 점도표는 연말 값입니다. 원자료: ',
          h('a', { href: S.url, target: '_blank', rel: 'noopener noreferrer' }, 'SME 결과 PDF'), '.') });
    }

    // 기조 판정표 (확장안 ③): S1~S5 → 기조 점수·등급, 괴리 A, 교차 점검
    const ST = P.stance;
    let stanceCard = null;
    if (ST && ST.score != null) {
      const keys = ['S1', 'S2', 'S3', 'S4', 'S5'];
      const gA = ST.gap_a;
      const aTxt = gA == null ? '괴리 A 자료 없음' : `괴리 A(점도표 − 선물, ${ST.target.slice(0, 4)}년 ${Number(ST.target.slice(5))}월) ${F.bp(gA, 0)}: ` +
        (gA >= 25 ? '시장이 연준보다 인하를 더 기대합니다' : gA <= -25 ? '시장이 연준보다 금리를 더 높게 봅니다 (연준 점도표보다 매파적 가격)' : '시장과 연준이 비슷합니다');
      stanceCard = UI.card({ id: 'stance', span: 'c12', title: '기조 판정표', cap: '연준은 얼마나 매파인가, 시장은 그걸 얼마나 믿나',
        body: [UI.concl(`연준 기조 점수 ${F.s(ST.score, 2)} → ${ST.grade}` + (ST.chg != null ? ` (지난달 ${F.s(ST.prev.score, 2)}에서 ${F.s(ST.chg, 2)})` : ''),
            aTxt + '.' + (ST.distrust ? ' ⚠ 시장이 연준을 안 믿는 중: 기조는 매파인데 시장은 인하를 더 가격하고 있습니다.' : '') + (ST.shift_alert ? ' ⚠ 기조 전환 경고: 지난달보다 0.5 넘게 움직였습니다.' : '')),
          UI.table([{ label: '항목', align: 'l', get: (k) => `${k} ${ST.parts[k] ? ST.parts[k].name : ''}` }, { label: '가중치', get: (k) => ST.weights[k], fmt: (v) => Math.round(v * 100) + '%' },
            { label: '점수 (−2~+2)', get: (k) => (ST.parts[k] ? ST.parts[k].score : null), fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 2) },
            { label: '근거', align: 'l', get: (k) => (ST.parts[k] ? ST.parts[k].basis : '자료 없음') }], { rows: keys, dense: true }),
          h('p', { cls: 'note' }, '등급: −1.0 이하 비둘기파 강 · −1.0~−0.3 비둘기파 · ±0.3 중립 · +0.3~+1.0 매파 · +1.0 이상 매파 강. 빠진 항목이 있으면 나머지 가중치로 다시 나눕니다.')],
        foot: `S1·S3·S4는 FOMC-RoBERTa 문장 분류 성향에서 모델 기준선(최근 1년 정책 발언 성향 중간값 ${F.s(ST.baseline, 2)})을 뺀 값으로 매깁니다: ±${ST.tone_step[0]} 넘으면 ±1, ±${ST.tone_step[1]} 넘으면 ±2 (잠정 문턱). ` +
          `S2는 SEP 내년 말 중간값의 직전 대비 변화(±25bp = ±1, ±50bp = ±2). S5는 최근 회의 반대표. 점도표 경로는 오늘 정책금리에서 연말 중간값까지 월 단위 선형.` });
    }

    // 연준 기조 브리핑 (확장안 ②): 매달 같은 틀, 모든 칸 자동
    const BR = P.brief;
    let briefCard = null;
    if (BR) {
      const T3 = BR.three;
      briefCard = UI.card({ id: 'brief', span: 'c12', title: '연준 기조 브리핑', cap: `${BR.asof} 기준 · 매달 같은 틀로 자동 작성`,
        body: [UI.concl(BR.headline, `현재 진단: ${BR.diagnosis}.`),
          h('p', { cls: 'note', style: 'margin:10px 0 4px;color:var(--ink);font-weight:600' }, '매크로 요소'),
          UI.table([{ label: '요소', align: 'l', get: (x) => x.factor }, { label: '현재 값', align: 'l', get: (x) => x.now }, { label: '3개월', get: (x) => x.dir || '' },
            { label: '연준 전망', align: 'l', get: (x) => x.cons || '' }, { label: '우리 점수', align: 'l', get: (x) => x.score },
], { rows: BR.factors, dense: true }),
          h('p', { cls: 'note', style: 'margin:10px 0 4px;color:var(--ink);font-weight:600' }, '미리 정한 확인 신호'),
          UI.table([{ label: '요소', align: 'l', get: (x) => x.factor }, { label: '맞았다는 신호', align: 'l', get: (x) => x.confirm }, { label: '틀렸다는 신호', align: 'l', get: (x) => x.refute }], { rows: BR.factors, dense: true }),
          h('p', { cls: 'note', style: 'margin:10px 0 4px;color:var(--ink);font-weight:600' }, '컨센서스 vs 우리'),
          h('ul', { cls: 'note', style: 'margin:0 0 8px 18px' },
            h('li', null, `컨센서스: SME 중간값 ${F.n(T3.consensus, 2)}% (1년 뒤), 선물 ${F.n(T3.futures, 2)}%`),
            h('li', null, `우리 기울기: ${F.bp(T3.tilt, 1)} (한도 ±${T3.cap}bp) · 근거 P2 ${F.s(T3.p2, 0)}, P3 ${F.s(T3.p3, 0)}`),
            h('li', null, `결과: 우리 경로 ${F.n(T3.ours, 2)}% − 선물 = 괴리 B ${F.bp(T3.gap_b, 0)} → ${T3.signal}`)),
          h('p', { cls: 'note', style: 'margin:10px 0 4px;color:var(--ink);font-weight:600' }, '주의할 점'),
          BR.flags.length ? h('ul', { style: 'margin:0 0 0 18px;color:var(--up-ink)' }, BR.flags.map((t) => h('li', null, t)))
            : h('p', { cls: 'note' }, '켜진 경고 없음 (물가·실업률이 연준 전망에서 크게 벗어나지 않았고, 시장과 연준의 괴리 경고도 없음)')],
        foot: '한 줄 결론은 기조 판정표와 우리 기울기에서, 현재 진단은 SEP 전망 대비 실제 값에서, 매크로 요소 점수는 팀 5필라 스코어보드(적용 중인 달)에서 가져옵니다. 맞았다/틀렸다는 신호는 미리 정한 규칙입니다.' });
    }

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
    const today = new Date().toISOString().slice(0, 10), from = today < asof ? asof : today;
    const talks = D.events.filter((e) => (e.kind === '연설' || e.kind === '의회 증언' || e.kind === 'FOMC' || e.kind === '연준 자료') && e.date >= from).slice(0, 8);
    const talkList = h('ul', { cls: 'list' }, talks.length ? talks.map((e) => h('li', null, h('span', { cls: 'when' }, `${F.md(e.date)} ${e.time || ''}`),
      h('span', { cls: 'what' }, e.title, h('small', null, [e.kind, e.note].filter(Boolean).join(' · '))))) : h('li', null, h('span'), h('span', { cls: 'mute' }, '공개된 예정 일정이 없습니다')));
    // 연준 커뮤니케이션 로그: 연설·증언·성명·기자회견(성향은 FOMC-RoBERTa 문장 분류, fed_tone.py) + 의사록(RSS)
    const TN = P.tone;
    const cut = new Date(new Date(asof).getTime() - 45 * 864e5).toISOString().slice(0, 10);
    const minutes = (D.news || []).filter((n) => n.src === '연준' && n.kind === '보도자료' && /minutes of the federal open/i.test(n.title) && n.ts.slice(0, 10) >= cut)
      .map((n) => ({ date: n.ts.slice(0, 10), kind: '의사록', speaker: 'FOMC', title: n.title, url: n.link, policy: true, voter: false }));
    const logAll = (TN ? TN.items.filter((x) => x.date >= cut) : []).concat(minutes).sort((x, y) => (x.date < y.date ? 1 : -1));
    const grp = { all: '전체', stmt: '성명·의사록', chair: '의장', member: '위원' };
    const inGrp = (x, g) => g === 'all' || (g === 'stmt' ? (x.kind === '성명' || x.kind === '의사록') : g === 'chair' ? x.chair : !x.chair && (x.kind === '연설' || x.kind === '의회 증언'));
    const tagCls = { 매: 'up', 비: 'down', 중: 'mute' };
    const commsList = h('ul', { cls: 'list' });
    const logState = { g: 'all', noise: false };
    const drawLog = () => {
      commsList.replaceChildren();
      const rows = logAll.filter((x) => inGrp(x, logState.g) && (logState.noise || x.policy));
      for (const x of rows.slice(0, 10)) {
        const safe = /^https?:\/\//.test(x.url || '') ? x.url : null;
        commsList.appendChild(h('li', null, h('span', { cls: 'when' }, F.md(x.date)),
          h('span', { cls: 'what' }, safe ? h('a', { href: safe, target: '_blank', rel: 'noopener noreferrer' }, x.title) : x.title,
            h('small', null, `${x.speaker}${x.voter ? ' ●' : ''} · ${x.kind}`, x.tag ? h('span', { cls: tagCls[x.tag], style: 'margin-left:6px;font-weight:600' }, `${x.tag} ${F.s(x.net, 2)}`) : null,
              x.policy ? null : h('span', { cls: 'mute', style: 'margin-left:6px' }, '정책 무관')))));
      }
      if (!rows.length) commsList.appendChild(h('li', null, h('span'), h('span', { cls: 'mute' }, '해당하는 발언이 없습니다')));
    };
    const gBtns = Object.entries(grp).map(([k, lab]) => { const b = h('button', { cls: 'mini', type: 'button' }, lab); b.addEventListener('click', () => { logState.g = k; drawLog(); }); return b; });
    const noiseBtn = h('button', { cls: 'mini', type: 'button' }, '정책 무관 포함');
    noiseBtn.addEventListener('click', () => { logState.noise = !logState.noise; noiseBtn.textContent = logState.noise ? '정책 관련만' : '정책 무관 포함'; drawLog(); });
    drawLog();
    // 위원 성향 띠: 최근 90일 정책 발언 평균 (−0.5 비둘기 ~ +0.5 매파)
    let band = null;
    if (TN && TN.members.length) {
      const W = 900, H0 = 44 + TN.members.length * 18, X = (v) => 20 + (Math.max(-0.5, Math.min(0.5, v)) + 0.5) * (W - 40);
      const svg = UI.s('svg', { viewBox: `0 0 ${W} ${H0}`, width: '100%', role: 'img', 'aria-label': '위원 성향 띠' },
        UI.s('line', { x1: X(-0.5), x2: X(0.5), y1: 14, y2: 14, stroke: 'var(--grid)', 'stroke-width': 6, 'stroke-linecap': 'round' }),
        UI.s('line', { x1: X(0), x2: X(0), y1: 6, y2: H0 - 4, stroke: 'var(--mute)', 'stroke-dasharray': '2 3' }),
        UI.s('text', { x: X(-0.5), y: H0 - 2, 'font-size': 10, fill: 'var(--mute)' }, '← 비둘기파'),
        UI.s('text', { x: X(0.5), y: H0 - 2, 'font-size': 10, fill: 'var(--mute)', 'text-anchor': 'end' }, '매파 →'),
        ...TN.members.flatMap((m, i) => [
          UI.s('circle', { cx: X(m.avg), cy: 14, r: m.chair ? 6 : 4.5, fill: m.chair ? 'var(--s1)' : 'var(--ink)', 'fill-opacity': m.voter ? 0.9 : 0.35 }),
          UI.s('line', { x1: X(m.avg), x2: X(m.avg), y1: 19, y2: 30 + i * 18 - 4, stroke: 'var(--axis)' }),
          UI.s('text', { x: X(m.avg) + 6, y: 30 + i * 18 + 4, 'font-size': 11, fill: 'var(--ink)' }, `${m.name}${m.chair ? ' (의장)' : ''} ${F.s(m.avg, 2)} · ${m.n}건`)]));
      band = svg;
    }
    const chairList = TN && TN.chair_recent.length ? h('ul', { cls: 'list' }, TN.chair_recent.map((x) => h('li', null, h('span', { cls: 'when' }, F.md(x.date)),
      h('span', { cls: 'what' }, h('a', { href: x.url, target: '_blank', rel: 'noopener noreferrer' }, x.title), h('small', null, x.kind, h('span', { cls: tagCls[x.tag], style: 'margin-left:6px;font-weight:600' }, `${x.tag} ${F.s(x.net, 2)}`)),
        x.ex_h[0] ? h('small', { style: 'display:block' }, `매파 문장 예: “${x.ex_h[0].slice(0, 90)}…”`) : null)))) : h('p', { cls: 'mute' }, '의장 발언 성향 자료가 없습니다 (fed_tone.py 실행 필요)');
    const sub = (t) => h('p', { cls: 'note', style: 'margin:0 0 6px;color:var(--ink);font-weight:600' }, t);
    const cbCard = UI.card({ id: 'cb', span: 'c12', title: '연준 트래커', cap: '정책 현황 · 커뮤니케이션 로그 · 위원 성향 · 예정 일정',
      body: [h('div', { cls: 'grid' },
        h('div', { cls: 'c4' }, sub('정책 현황'), kv(fed, true)),
        h('div', { cls: 'c4' }, sub('커뮤니케이션 로그 (45일)'), h('div', { style: 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px' }, ...gBtns, noiseBtn), commsList),
        h('div', { cls: 'c4' }, sub('연준 예정 일정 (미 동부 시각)'), talkList)),
        h('div', { cls: 'grid', style: 'margin-top:14px' },
          h('div', { cls: 'c8' }, sub(`위원 성향 띠 (최근 ${TN ? TN.band_days : 90}일 정책 발언 평균, 진한 점 = 투표권자)`), band || h('p', { cls: 'mute' }, '성향 자료가 없습니다')),
          h('div', { cls: 'c4' }, sub(`의장${TN && TN.chair ? ' ' + TN.chair : ''} 최근 발언`), chairList))],
      foot: `성향 = (매파 문장 − 비둘기파 문장) ÷ 전체 문장, −1~+1. 문장마다 FOMC-RoBERTa(Shah et al. 2023)로 분류합니다. 한 발언은 ±${TN ? TN.tag_th : 0.1} 넘으면 매·비로 표시하고, 판정에는 한 달 평균만 씁니다. ` +
        `정책 키워드 문장이 ${TN && TN.policy_th ? Math.round(TN.policy_th * 100) : 20}% 미만이면 '정책 무관'으로 가립니다. ● = 올해 투표권자. 연준 이사회 RSS 기준이라 지역 연은 총재 연설은 아직 빠져 있습니다.` });

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
      tabs: [['releases', '지표 일정·서프라이즈'], ['cycle', '월별 지표 표'], ['policy', '정책금리 경로'], ['brief', '기조 브리핑'], ['cons', '컨센서스 vs 우리'], ['stance', '기조 판정표'], ['fomc', 'FOMC 성명 리뷰'], ['cb', '연준 트래커'], ['infl', '인플레이션']],
      body: [relCard, surChart('nfp', '고용', '천 명', 150), surChart('cpi', '근원 CPI', 'bp', 15), heatCard, pathCard, meetCard, briefCard, consCard, stanceCard, fomcCard, cbCard, inflCard].filter(Boolean) };
  };
})();
