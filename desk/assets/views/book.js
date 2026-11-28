/* 6. 포트폴리오·리스크 — 내 포트폴리오는 어떤가: 일별 손익 설명, 손실 한도, KRD, 구성, 보유 종목·거래 내역, 익스포저, 성과 분해, 리스크·시나리오 */
(function () {
  'use strict';
  const { h, F, ok } = UI;
  const SLOPE = { none: '', steepener: '스티프너', flattener: '플래트너' }, CURV = { none: '', bullet: '불릿' };
  const posTxt = (p) => {
    if (!p) return '–';
    const [d, sl, cv] = Array.isArray(p) ? p : [p.dur, p.slope, p.curv];
    const parts = [d ? `Duration ${F.s(d, 2)}년` : 'Duration 중립', SLOPE[sl], CURV[cv]].filter(Boolean);
    return parts.join(' · ');
  };

  window.DeskViews.book = function (ctx) {
    const D = ctx.D, B = D.book, S = B.stats, R = B.risk, st = ctx.st;
    const V = R.var;
    const kv = (items) => h('dl', { cls: 'kv' }, items.map(([k, v, u, cls]) => h('div', null, h('dt', null, k), h('dd', { cls: cls || null }, v, u ? h('small', null, u) : null))));

    // ── 요약 타일 ──
    const ex = (k) => B.perf[k].ex_bp;
    const tiles = h('div', { cls: 'tiles c12' },
      UI.tile({ lab: '순자산 (NAV)', val: F.usd(B.nav), note: `벤치마크 ${F.usd(B.nav_bm)}`, hero: true }),
      UI.tile({ lab: '일간 손익', val: F.usdS(B.pnl_d1_usd), note: `포트폴리오 ${F.s(B.perf.d1.p, 2)}% · 벤치마크 ${F.s(B.perf.d1.b, 2)}%` }),
      UI.tile({ lab: '이번 달 초과수익', val: F.s(ex('mtd'), 1), unit: 'bp', note: `포트폴리오 ${F.s(B.perf.mtd.p, 2)}%` }),
      UI.tile({ lab: '올해 초과수익', val: F.s(ex('ytd'), 0), unit: 'bp', note: `포트폴리오 ${F.s(B.perf.ytd.p, 2)}%` }),
      UI.tile({ lab: `${B.start.slice(0, 4)}년 말 이후`, val: F.s(ex('itd'), 0), unit: 'bp', note: `연 ${F.s(S.excess_ann_bp, 1)}bp · 정보비율 ${F.n(S.ir, 2)}` }),
      UI.tile({ lab: '듀레이션 / BM', val: F.n(B.dur_p, 2), unit: `/ ${F.n(B.dur_b, 2)}년`, note: `액티브 듀레이션 ${F.s(B.active_dur, 2)}년` }),
      UI.tile({ lab: '액티브 DV01', val: F.usdS(B.dv01 - B.dv01_b), unit: '/ bp', note: `포트폴리오 ${F.usd(B.dv01)} · 벤치마크 ${F.usd(B.dv01_b)}`,
        title: '금리가 1bp 내릴 때 포트폴리오가 벤치마크보다 더 버는 금액 (달러)' }));

    // ── 일별 손익 설명: 전일 포지션을 그대로 들고 하루를 보냈을 때 손익이 어디서 났나 (캐리, 롤다운, 만기별 금리 변화, 볼록성) ──
    const E = B.explain && B.explain.days.length ? B.explain : null;
    let pnlCard = null;
    if (E) {
      const eAll = E.days, eLast = eAll[eAll.length - 1];
      const WIN = { d: 1, w: Math.min(5, eAll.length), m: eAll.filter((d) => d.date.slice(0, 7) === eLast.date.slice(0, 7)).length };
      let eWin = 'd', eMode = 'p';
      const pnlConcl = UI.concl('', ' '), pnlChart = h('div', { cls: 'inset' }), pnlTable = h('div');
      const drawPnl = () => {
        const n = WIN[eWin], days = eAll.slice(-n);
        const acc = (f) => days.reduce((t, d) => t + f(d), 0);
        // 줄마다 포트폴리오 손익(달러), 포트폴리오·벤치마크 수익률 기여(bp). 만기 줄에는 금리 변화(bp)와 키레이트 DV01(달러 / bp, 기간 평균)도
        const row = (g, name, pick, more) => Object.assign({ g, name, usd: acc((d) => pick(d.p) * d.nav_p / 1e4), p: acc((d) => pick(d.p)), b: acc((d) => pick(d.b)) }, more);
        const keyRows = E.keys.map((k, j) => row('금리가 움직여서', k, (q) => q.k[j], { dy: acc((d) => d.dy[j]), dv01: acc((d) => d.p.krd[j] * d.nav_p / 1e4) / n }));
        const rows = [row('시간이 흘러서', '캐리', (q) => q.c), row('시간이 흘러서', '롤다운', (q) => q.r)].concat(keyRows, [row('금리가 움직여서', '볼록성 등', (q) => q.x)]);
        const sum = (k) => rows.reduce((t, r) => t + r[k], 0);
        const total = { g: '합계', name: '손익 합계', usd: sum('usd'), p: sum('p'), b: sum('b') };
        const rate = keyRows.reduce((t, r) => t + r.usd, 0), conv = rows[rows.length - 1].usd, cr = rows[0].usd + rows[1].usd;
        const top = keyRows.slice().sort((a, b) => Math.abs(b.usd) - Math.abs(a.usd))[0];
        const when = eWin === 'd' ? F.kdate(eLast.date) : eWin === 'w' ? `최근 ${n}영업일(${F.md(days[0].date)}~${F.md(eLast.date)})` : `${F.mon(eLast.date)} 들어 ${n}영업일`;
        const why = Math.abs(rate + conv) >= Math.abs(cr) ? `대부분 금리가 ${rate > 0 ? '내려서 번' : '올라서 잃은'} 것입니다` : '금리 변화보다 캐리가 더 컸습니다';
        const usdMax = Math.max(1, ...rows.map((r) => Math.abs(r.usd))), actMax = Math.max(0.1, ...rows.map((r) => Math.abs(r.p - r.b)));
        pnlConcl.firstChild.textContent = `${when} 손익은 ${F.usdS(total.usd)}이고, ${why}`;
        pnlConcl.lastChild.textContent = `금리 변화 ${F.usdS(rate)} (가장 큰 만기는 ${top.name}: ${F.bp(top.dy)} 움직여 ${F.usdS(top.usd)}) · 캐리 ${F.usdS(rows[0].usd)} · 롤다운 ${F.usdS(rows[1].usd)} · 볼록성 등 ${F.usdS(conv)}. 벤치마크 대비로는 ${F.bp(total.p - total.b, 1)}입니다 (포트폴리오 ${F.bp(total.p, 1)}, 벤치마크 ${F.bp(total.b, 1)}).`;
        pnlChart.replaceChildren(UI.bars({ cats: rows.map((r) => r.name), h: 200, sign: true, unit: '', xEvery: 1, aria: '손익을 캐리, 롤다운, 만기별 금리 변화, 볼록성으로 나눈 막대',
            tipFmt: eMode === 'p' ? (v) => F.usdS(v) : (v) => F.bp(v, 2),
            series: [{ name: eMode === 'p' ? '포트폴리오 손익' : '벤치마크 대비', color: 'var(--s1)', values: rows.map((r) => (eMode === 'p' ? r.usd : r.p - r.b)) }] }), h('div', { style: 'height:12px' }));
        pnlTable.replaceChildren(UI.table([{ label: '항목', align: 'l', get: (r) => r.name },
            { label: '금리 변화', title: '그 만기 재무부 par 금리의 변화 (bp)', get: (r) => r.dy, fmt: (v) => (ok(v) ? F.bp(v) : '') },
            { label: '키레이트 DV01', title: '그 만기 금리만 1bp 내릴 때 포트폴리오가 버는 금액. 전일 기준이고, 여러 날이면 평균', get: (r) => r.dv01, fmt: (v) => (ok(v) ? F.usd(v) : '') },
            { label: '손익', get: (r) => r.usd, fmt: (v) => F.usdS(v), heat: (v, r) => (r.g === '합계' ? '' : UI.heat(v, usdMax)) },
            { label: '수익률', title: '전일 NAV 대비 bp', get: (r) => r.p, fmt: (v) => F.s(v, 2) },
            { label: '벤치마크 대비', title: '포트폴리오 수익률 − 벤치마크 수익률 (bp)', get: (r) => r.p - r.b, fmt: (v) => F.s(v, 2), heat: (v, r) => (r.g === '합계' ? '' : UI.heat(v, actMax)) }],
            { rows: rows.concat([total]), dense: true, group: (r) => r.g }));
      };
      drawPnl();
      const seg = (items, cur, pick) => h('span', { style: 'display:inline-flex;gap:4px;white-space:nowrap' }, items.map(([key, text]) => {
        const b = h('button', { cls: 'mini', type: 'button', 'aria-pressed': String(cur === key) }, text);
        b.dataset.k = key;
        b.addEventListener('click', () => { pick(key); b.parentNode.querySelectorAll('[data-k]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.k === key))); drawPnl(); });
        return b;
      }));
      pnlCard = UI.card({ id: 'pnl', span: 'c8', title: '일별 손익 설명', cap: '어디서 벌고 잃었나 · 손익은 달러, 나머지는 bp', flush: true,
        tools: [seg([['d', '1일'], ['w', '1주'], ['m', '이번 달']], eWin, (k) => { eWin = k; }), seg([['p', '포트폴리오'], ['a', '벤치마크 대비']], eMode, (k) => { eMode = k; })],
        body: [pnlConcl, pnlChart, pnlTable],
        foot: '전일 종가의 포지션을 그대로 들고 하루를 보냈다고 보고 나눈 값입니다. 캐리는 금리가 그대로일 때 하루치 이자와 가격이 액면으로 돌아가는 몫, 롤다운은 커브가 그대로일 때 만기가 하루 짧아져 금리가 달라지는 몫입니다. 금리 변화는 전일 키레이트 DV01 × 그 만기 금리 변화이고, 볼록성 등은 나머지(금리 변화의 2차 효과)입니다. 네 갈래의 합은 NAV 변화와 같습니다. 모형은 종목을 그 만기의 금리 하나로 값을 매기므로 키레이트 DV01을 좌우 두 만기에 나눠 붙였고, 그래서 현금흐름마다 할인율을 움직이는 아래 KRD 표와 만기별 값이 조금 다릅니다. 여러 날을 고르면 하루 값들을 더하므로, 손익이 금리 변화 × 평균 키레이트 DV01과 조금 다를 수 있습니다.' });
    }

    // ── 손실 한도: 벤치마크 대비 이번 달·올해 초과수익이 한도를 얼마나 썼나 ──
    const L = R.limits;
    let limitCard = null;
    if (L) {
      const used = (cur, lim) => Math.max(0, -cur) / Math.abs(lim);
      const level = (u) => (u >= 1 ? ['bad', '한도 초과', 'var(--crit)'] : u >= L.warn ? ['mid', '주의', 'var(--warn)'] : ['good', '정상', 'var(--good)']);
      const gauge = (label, cur, lim) => {
        const u = used(cur, lim), [cls, word, col] = level(u), room = Math.max(0, Math.abs(lim) - Math.max(0, -cur));
        return h('div', { cls: 'limit' },
          h('div', { cls: 'limit-h' }, label, h('span', { cls: 'verdict ' + cls }, h('i'), word)),
          h('div', { cls: 'limit-v' }, F.bp(cur, 1), h('small', null, `한도 ${F.bp(lim)}`)),
          h('span', { cls: 'bar', role: 'img', 'aria-label': `${label} 한도 사용률 ${F.n(u * 100, 0)}%` }, h('i', { style: `width:${Math.min(100, u * 100).toFixed(1)}%;background:${col}` })),
          h('small', null, `한도의 ${F.n(u * 100, 0)}% 사용 · 남은 여유 ${F.n(room, 1)}bp (${F.usd(room / 1e4 * B.nav)})`));
      };
      const uM = used(ex('mtd'), L.month_bp), uY = used(ex('ytd'), L.year_bp), uTop = Math.max(uM, uY), which = uM >= uY ? '이번 달' : '올해';
      const roomM = Math.max(0, Math.abs(L.month_bp) - Math.max(0, -ex('mtd')));
      const head = uTop >= 1 ? `${which} 손실이 한도를 넘었습니다` : uTop >= L.warn ? `${which} 손실이 한도의 ${F.n(uTop * 100, 0)}%까지 찼습니다`
        : uTop > 0 ? '이번 달과 올해 모두 손실 한도에 여유가 있습니다' : '이번 달과 올해 모두 벤치마크를 앞서고 있어 손실 한도를 쓰지 않았습니다';
      const hitM = L.hit_months.map((m) => `${m.month} (${F.bp(m.excess_bp)})`).join(', ');
      limitCard = UI.card({ id: 'limit', span: 'c4', title: '손실 한도', cap: '벤치마크 대비 초과수익',
        body: [UI.concl(head, `이번 달 여유 ${F.n(roomM, 1)}bp는 하루 상대 VaR(95%) ${F.n(V.rel_95_bp, 1)}bp의 ${F.n(roomM / V.rel_95_bp, 0)}일치입니다.`),
          gauge(`${F.mon(B.asof)} (이번 달)`, ex('mtd'), L.month_bp), gauge(`${B.asof.slice(0, 4)}년 (올해)`, ex('ytd'), L.year_bp),
          h('dl', { cls: 'kv two' }, [['월 한도를 넘은 달', `${L.hit_months.length}번`, `/ ${L.n_months}개월`], ['연 한도를 넘은 해', `${L.hit_years.length}번`, `/ ${L.n_years}년`]]
            .map(([k, v, u]) => h('div', null, h('dt', null, k), h('dd', null, v, h('small', null, u))))),
          h('p', { cls: 'note' }, `${B.start.slice(0, 4)}년 말 이후 기록입니다.${hitM ? ` 월 한도를 넘은 달은 ${hitM}입니다.` : ''} 가장 나빴던 해는 ${L.worst_year.year}년 (${F.bp(L.worst_year.excess_bp)})으로 연 한도의 ${F.n(used(L.worst_year.excess_bp, L.year_bp) * 100, 0)}%였습니다.`)],
        foot: `임시 기준입니다. 연 한도는 위험예산 하단(${L.budget_bp}bp)만큼, 월 한도는 그 절반으로 두었고, 한도의 ${F.n(L.warn * 100, 0)}%를 쓰면 주의로 표시합니다. 모형 포트폴리오는 한도를 넘어도 규칙대로 운용을 계속하므로, 이 카드는 표시만 합니다.` });
    }

    // ── 구성: 만기별 금리 위험(키레이트 DV01)을 벤치마크와 나란히. 금액 비중이 아니라 1bp당 손익으로 본다 ──
    const BK = B.positions;
    const K = B.krd || { keys: [], rows: [] }, nk = K.keys.length;
    const sumRow = (k) => K.keys.map((_, j) => K.rows.reduce((t, x) => t + x[k][j], 0));
    const krdP = sumRow('p'), krdB = sumRow('b'), krdA = krdP.map((v, j) => v - krdB[j]);
    const tot = (a) => a.reduce((t, v) => t + v, 0);
    const dvTot = BK.reduce((t, p) => t + p.dv01, 0), dvTotB = BK.reduce((t, p) => t + p.dv01_b, 0);
    const composeCard = UI.card({ id: 'compose', span: 'c5', title: '내 포트폴리오', cap: '만기별 금리 위험 · 달러 / bp',
      body: [UI.bars({ cats: K.keys, h: 230, unit: '', tipFmt: (v) => F.usd(v) + ' / bp', aria: '만기별 키레이트 DV01, 포트폴리오와 벤치마크',
               series: [{ name: '포트폴리오', color: 'var(--s1)', values: krdP }, { name: '벤치마크', color: 'var(--s-mute)', values: krdB }] }),
        h('div', { style: 'height:6px' }),
        UI.table([{ label: '만기 구간', align: 'l', get: (p) => p.label },
          { label: 'DV01', title: '금리 1bp 하락 때 이 구간에서 버는 금액', get: (p) => p.dv01, fmt: (v) => F.usd(v) },
          { label: 'DV01 비중', title: '포트폴리오 전체 DV01 가운데 이 구간이 차지하는 몫', get: (p) => p.dv01 / dvTot * 100, fmt: (v) => F.n(v, 1) + '%' },
          { label: '벤치마크', title: '벤치마크 DV01 가운데 이 구간의 몫', get: (p) => p.dv01_b / dvTotB * 100, fmt: (v) => F.n(v, 1) + '%' },
          { label: '평가금액 비중', get: (p) => p.w_p, fmt: (v) => F.n(v, 1) + '%' }],
          { rows: BK, dense: true, foot: ['합계', F.usd(dvTot), '100%', '100%', '100%'] })],
      foot: `${B.asof} 평가. 막대는 그 만기 금리만 1bp 내릴 때 버는 금액(키레이트 DV01)이고, 포트폴리오와 벤치마크의 차이가 액티브 포지션입니다. 표는 보유 구간별 DV01입니다. 평가금액 비중은 벤치마크와 같지만 구간 안에서 만기를 옮겨 DV01이 달라집니다. 국채만 보유하고 현금은 없습니다.` });

    // ── 키레이트 듀레이션 (KRD) 행렬: 종목 × 만기, 그 만기 금리만 ±1bp 움직였을 때 손익 ──
    let kMode = 'p';
    const krdSlot = h('div');
    const drawKrd = () => {
      const val = (x, j) => (kMode === 'p' ? x.p[j] : kMode === 'b' ? x.b[j] : x.p[j] - x.b[j]);
      const rows = K.rows.map((x) => ({ g: '보유 종목 (구간별 모형 국채)', label: x.label, v: K.keys.map((_, j) => val(x, j)), act: kMode === 'a' }))
        .concat([{ g: '합계', label: '포트폴리오', v: krdP }, { g: '합계', label: '벤치마크', v: krdB }, { g: '합계', label: '액티브 (포트폴리오 − 벤치마크)', v: krdA, act: true }]);
      const cols = [{ label: '종목 / 만기', align: 'l', get: (r) => r.label }]
        .concat(K.keys.map((k, j) => ({ label: k, get: (r) => r.v[j], fmt: (v, r) => (r.act ? F.usdS(v) : F.usd(v)), heat: (v, r) => (r.act ? UI.heat(v, 150) : '') })))
        .concat([{ label: '합계', get: (r) => tot(r.v), fmt: (v, r) => (r.act ? F.usdS(v) : F.usd(v)), heat: (v, r) => (r.act ? UI.heat(v, 300) : '') }]);
      krdSlot.replaceChildren(UI.table(cols, { rows, dense: true, group: (r) => r.g }));
    };
    drawKrd();
    const kBtn = (key, text) => {
      const b = h('button', { cls: 'mini', type: 'button', 'aria-pressed': String(kMode === key) }, text);
      b.dataset.k = key;
      b.addEventListener('click', () => { kMode = key; b.parentNode.querySelectorAll('[data-k]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.k === key))); drawKrd(); });
      return b;
    };
    const krdCard = UI.card({ id: 'krd', span: 'c12', title: '키레이트 듀레이션 (KRD)', cap: '달러 / bp · 그 만기 금리만 1bp 내릴 때 손익', flush: true,
      tools: [h('span', { style: 'display:inline-flex;gap:4px;white-space:nowrap' }, kBtn('p', '포트폴리오'), kBtn('b', '벤치마크'), kBtn('a', '액티브'))],
      body: krdSlot,
      foot: `만기 하나(1·2·3·5·7·10·20·30년)의 금리만 1bp 올린 값과 1bp 내린 값의 차이를 2로 나눈 것입니다 (중앙 차분). 범프는 그 만기에서 1bp, 옆 만기에서 0인 삼각형이라 이웃 만기 사이의 현금흐름은 두 칸에 나뉩니다. 할인율은 ${B.asof} 재무부 par 금리에 오늘 가격과 맞추는 일정한 스프레드를 더해 썼습니다. 그래서 줄 합계가 DV01(${F.usd(B.dv01)})과 조금 다릅니다. 액티브 줄이 +이면 그 만기 금리가 내릴 때 벤치마크보다 더 법니다.` });

    // ── 앞으로: 지금 포지션을 그대로 두고 무엇을 조정할지 ──
    const kIdx = (k) => K.keys.indexOf(k);
    const ranked = K.keys.map((k, j) => [k, krdA[j]]).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const belly = (kIdx('5Y') >= 0 ? krdA[kIdx('5Y')] : 0) + (kIdx('7Y') >= 0 ? krdA[kIdx('7Y')] : 0);
    const big = ranked.slice(0, 3).map(([k, v]) => `${k} ${F.usdS(v)}`).join(', ');
    // 벨리 비중확대 예시: 5–7년을 사고 1–3년과 7–10년을 DV01 절반씩 판다 (DV01 중립 버터플라이)
    const byLab = (l) => BK.find((p) => p.label === l), rowOf = (l) => K.rows.find((x) => x.label === l);
    const legs = [['5–7년', 1], ['1–3년', -0.5], ['7–10년', -0.5]].filter(([l]) => byLab(l) && rowOf(l));
    let flyAmt = 0;
    const flySlot = h('div');
    const drawFly = () => {
      const after = krdA.slice();
      const trades = legs.map(([l, wgt]) => {
        const p = byLab(l), x = rowOf(l), dv = flyAmt * wgt, parT = dv / (p.dv01 / p.par);
        x.p.forEach((v, j) => { after[j] += v * parT / p.par; });
        return { l, side: dv > 0 ? '매수' : dv < 0 ? '매도' : '–', par: parT, dv };
      });
      const kCols = [{ label: '', align: 'l', get: (r) => r.n }].concat(K.keys.map((k, j) => ({ label: k, get: (r) => r.v[j], fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 150) })))
        .concat([{ label: '합계', get: (r) => tot(r.v), fmt: (v) => F.usdS(v) }]);
      flySlot.replaceChildren(
        UI.table([{ label: '구간', align: 'l', get: (t) => t.l }, { label: '매매', align: 'l', get: (t) => t.side }, { label: '액면', get: (t) => t.par, fmt: (v) => F.usdS(v) },
          { label: 'DV01', get: (t) => t.dv, fmt: (v) => F.usdS(v) }], { rows: trades, dense: true }),
        h('div', { style: 'height:8px' }),
        UI.table(kCols, { rows: [{ n: '지금 액티브', v: krdA }, { n: '조정 뒤 액티브', v: after }], dense: true }),
        h('p', { cls: 'note' }, flyAmt ? `벨리(5·7년) 금리가 양쪽 윙보다 10bp 더 내리면 약 ${F.usdS(flyAmt * 10)}를 법니다. 전체 DV01은 거의 그대로라 금리 수준 전체가 움직일 때의 손익은 크게 바뀌지 않습니다.` : '위 단추로 벨리 비중확대 크기를 고르면 필요한 매매와 조정 뒤 KRD가 나옵니다.'));
    };
    drawFly();
    const fBtn = (amt, text) => {
      const b = h('button', { cls: 'mini', type: 'button', 'aria-pressed': String(flyAmt === amt) }, text);
      b.dataset.k = String(amt);
      b.addEventListener('click', () => { flyAmt = amt; b.parentNode.querySelectorAll('[data-k]').forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.k === String(amt)))); drawFly(); });
      return b;
    };
    const adjustCard = UI.card({ id: 'adjust', span: 'c12', title: '앞으로 무엇을 조정할까', cap: '지금 보유 포지션을 그대로 두고, 액티브 KRD로 본 위험과 벨리 비중확대 예시',
      tools: [h('span', { style: 'display:inline-flex;gap:4px;white-space:nowrap' }, fBtn(0, '그대로'), fBtn(250, '벨리 +$250'), fBtn(500, '+$500'), fBtn(1000, '+$1,000'))],
      body: [UI.bars({ cats: K.keys, h: 190, sign: true, unit: '', tipFmt: (v) => F.usdS(v) + ' / bp', aria: '만기별 액티브 KRD',
               series: [{ name: '액티브 KRD', color: 'var(--s1)', values: krdA }] }),
             h('p', { cls: 'note' }, `지금 벤치마크와 가장 다르게 걸린 만기는 ${big}입니다 (달러 / bp). 벨리(5·7년) 액티브는 ${F.usdS(belly)}${Math.abs(belly) < 150 ? '로 작아서, 벨리 비중확대 관점은 아직 포트폴리오에 거의 들어가 있지 않습니다' : belly > 0 ? '로 벨리를 이미 비중확대하고 있습니다' : '로 벨리를 비중축소하고 있습니다'}. 오른쪽 위 단추로 DV01 중립 버터플라이(5–7년 매수, 1–3년·7–10년 매도)를 넣어 보면 매매 규모와 바뀐 KRD가 나옵니다.`),
             flySlot],
      foot: '예시 계산일 뿐 실제 리밸런싱 규칙을 바꾸지는 않습니다. 각 구간의 모형 국채로 매매한다고 보고, 1bp당 손익(DV01)을 맞춰 액면을 정했습니다. 거래비용은 뺐습니다.' });

    // ── 성과 ──
    const ser = B.series, i0 = UI.cut(ser.dates, st.period), xd = ser.dates.slice(i0);
    const base = ser.excess_bp[i0];
    const perfCard = UI.card({ id: 'perf', span: 'c7', title: '벤치마크 대비 누적 초과수익', cap: `bp · ${xd[0]}부터 · 0보다 위면 벤치마크를 앞섬`,
      body: UI.line({ x: xd, series: [{ name: '누적 초과수익', color: 'var(--s1)', values: ser.excess_bp.slice(i0).map((v) => v - base) }], h: 470, zero: true, legend: false, unit: 'bp', tipFmt: (v) => F.s(v, 1), aria: '누적 초과수익' }),
      alt: () => UI.seriesTable(xd, [{ name: '포트폴리오 NAV', values: ser.nav_p.slice(i0), fmt: (v) => F.usd(v) }, { name: '벤치마크 NAV', values: ser.nav_b.slice(i0), fmt: (v) => F.usd(v) },
        { name: '누적 초과수익 (bp)', values: ser.excess_bp.slice(i0).map((v) => v - base), fmt: (v) => F.s(v, 1) }], 36),
      foot: `전체 기간 연 수익률은 포트폴리오 ${F.n(S.ann_p, 2)}%, 벤치마크 ${F.n(S.ann_b, 2)}%입니다. 최대 낙폭(MDD)은 포트폴리오 ${F.n(S.mdd_p, 1)}% (${S.mdd_p_from} ~ ${S.mdd_p_to}), 벤치마크 ${F.n(S.mdd_b, 1)}%입니다. 거래비용은 0으로 두었습니다.` });
    const yearCard = UI.card({ span: 'c4', title: '연도별 성과', cap: '%, 초과수익은 bp', flush: true,
      body: UI.table([{ label: '연도', align: 'l', get: (y) => y.year, fmt: (v, y) => v + (y.partial ? ' (진행 중)' : '') }, { label: '포트폴리오', get: (y) => y.ret_p, fmt: (v) => F.s(v, 2) },
        { label: '벤치마크', get: (y) => y.ret_b, fmt: (v) => F.s(v, 2) }, { label: '초과', get: (y) => y.excess_bp, fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 40) }],
        { rows: B.years.slice().reverse(), dense: true }) });

    // ── 포지션 ──
    const pos = B.positions.filter((p) => ctx.matOk(p.ttm));
    const settle = BondMath.ymd(BondMath.nextBusinessDay(B.asof));
    const posCard = UI.card({ id: 'blotter', span: 'c12', title: '보유 종목', cap: `${B.asof} 평가 · ${F.md(B.decision_date)} 리밸런싱 · ${posTxt(B.position)} · 줄을 누르면 채권 상세`, flush: true,
      body: UI.table([{ label: '구간', align: 'l', get: (p) => p.label }, { label: '종목', align: 'l', get: (p) => p.maturity, fmt: (_, p) => `모형 국채 ${F.n(p.coupon, 3)}% ${p.maturity}` },
        { label: 'DV01', title: '금리 1bp 하락 때 버는 금액', get: (p) => p.dv01, fmt: (v) => F.usd(v) }, { label: '벤치마크 DV01', get: (p) => p.dv01_b, fmt: (v) => F.usd(v) },
        { label: '듀레이션', get: (p) => p.mdur, fmt: (v) => F.n(v, 2) }, { label: '벤치마크 듀레이션', get: (p) => p.dur_b, fmt: (v) => F.n(v, 2) },
        { label: '액티브 듀레이션 기여도', title: '비중 × 듀레이션의 포트폴리오와 벤치마크 차이 (년)', get: (p) => p.active, fmt: (v) => F.s(v, 3), heat: (v) => UI.heat(v, 0.1) },
        { label: 'YTM', get: (p) => p.ytm, fmt: (v) => F.n(v, 2) + '%' }, { label: '가격', get: (p) => p.price, fmt: (v) => F.n(v, 3) },
        { label: '액면', get: (p) => p.par, fmt: (v) => F.usd(v) }, { label: '평가금액', get: (p) => p.mv, fmt: (v) => F.usd(v) },
        { label: '비중', title: '평가금액 비중. 벤치마크와 같게 둔다', get: (p) => p.w_p, fmt: (v) => F.n(v, 1) + '%' }],
        { rows: pos, dense: true, onRow: (p) => ctx.openBond({ title: `모형 국채 ${F.n(p.coupon, 3)}% ${p.maturity}`, sub: `${p.label} 구간 · 실제 종목이 아닌 모형 채권`, coupon: p.coupon, maturity: p.maturity, settle, ytm: p.ytm,
            tags: ['모형 종목'], source: '가격은 그날 재무부 par 커브에서 읽은 금리로 계산했습니다.' }),
          foot: pos.length === B.positions.length ? ['합계', '', F.usd(B.dv01), F.usd(B.dv01_b), F.n(B.dur_p, 2), F.n(B.dur_b, 2), F.s(B.active_dur, 3), '', '', '', F.usd(B.nav), '100%'] : null }),
      foot: B.model_note + ` 비중은 벤치마크와 같게 두고, 구간 안에서 만기를 옮겨 포지션을 만듭니다. 액티브 듀레이션은 오늘 금리로 다시 계산한 값이라 리밸런싱일의 ${F.s(B.rule_active_dur, 2)}년과 조금 다릅니다. 평균 매입가와 실현·미실현 손익은 실제 종목으로 바꾼 뒤에 채울 수 있습니다.` });

    // ── 거래 내역 ──
    const rb = B.rebalances.slice().reverse();
    let showAll = false;
    const rbSlot = h('div');
    const drawRb = () => rbSlot.replaceChildren(UI.table([{ label: '날짜', align: 'l', get: (x) => x.date }, { label: '적용 월', align: 'l', get: (x) => x.month },
      { label: '바꾸기 전', align: 'l', get: (x) => x.date, fmt: (_, x) => posTxt(x.frm) }, { label: '바꾼 뒤', align: 'l', get: (x) => x.date, fmt: (_, x) => posTxt(x.to) },
      { label: '이유', align: 'l', get: (x) => x.why }, { label: '그달 초과수익', get: (x) => x.ex, fmt: (v, x) => F.s(v, 1) + (x.partial ? ' (진행 중)' : ''), heat: (v) => UI.heat(v, 25) }],
      { rows: showAll ? rb : rb.slice(0, 10), dense: true }));
    drawRb();
    const more = h('button', { cls: 'mini', type: 'button', 'aria-pressed': 'false' }, `전체 ${rb.length}건`);
    more.addEventListener('click', () => { showAll = !showAll; more.setAttribute('aria-pressed', String(showAll)); drawRb(); });
    const rbCard = UI.card({ id: 'trades', span: 'c12', title: '거래 내역 (리밸런싱)', cap: `${S.years.toFixed(0)}년 동안 ${S.n_rebal}번 · 바꾼 이유는 모두 점수 변화`, flush: true, tools: [more], body: rbSlot,
      foot: '규칙이 낸 포지션을 매달 마지막 영업일 종가에 그대로 실행한 기록입니다. 재량 거래는 없습니다.' });

    // ── 익스포저 ──
    const expCard = UI.card({ id: 'exposure', span: 'c6', title: '익스포저', cap: '만기 구간별 DV01 (달러 / bp)',
      body: [UI.bars({ cats: B.positions.map((p) => p.label), h: 210, unit: '', tipFmt: (v) => F.usd(v), aria: '구간별 DV01',
        series: [{ name: '포트폴리오', color: 'var(--s1)', values: B.positions.map((p) => p.dv01) }, { name: '벤치마크', color: 'var(--s-mute)', values: B.positions.map((p) => p.dv01_b) }] }),
        kv([['DV01 차이', F.usdS(B.dv01 - B.dv01_b), '/ bp'], ['CS01 (신용)', '$0', '국채만 보유'], ['통화', 'USD 100%', '환 위험 없음']])],
      alt: () => UI.table([{ label: '구간', align: 'l', get: (p) => p.label }, { label: '포트폴리오 DV01', get: (p) => p.dv01, fmt: (v) => F.n(v, 0) }, { label: '벤치마크 DV01', get: (p) => p.dv01_b, fmt: (v) => F.n(v, 0) },
        { label: '차이', get: (p) => p.dv01 - p.dv01_b, fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 100) }], { rows: B.positions, dense: true }),
      foot: '구간별 DV01은 구간에 든 종목의 금리 위험입니다. 만기별(1~30년) 금리 위험은 위의 키레이트 듀레이션 표에서 봅니다.' });

    // ── 성과 분해 ──
    const cum = B.cum, cx = cum.month.map((m) => m + '-01'), c0 = UI.cut(cx, st.period);
    const reb = (arr) => { const b0 = c0 > 0 ? arr[c0 - 1] : 0; return arr.slice(c0).map((v) => v - b0); };
    const attrCard = UI.card({ id: 'attribution', span: 'c6', title: '성과 분해', cap: '초과수익의 전략별 기여도 누적 (bp)',
      body: [UI.line({ x: cx.slice(c0), h: 210, zero: true, unit: 'bp', tipFmt: (v) => F.s(v, 1), aria: '전략별 누적 기여',
        series: [{ name: 'Duration (수준)', color: 'var(--s1)', values: reb(cum.dur) }, { name: 'Curve Slope (기울기)', color: 'var(--s2)', values: reb(cum.slope) }, { name: 'Curve Curvature (곡률)', color: 'var(--s3)', values: reb(cum.curv) }] }),
        UI.table([{ label: '요인', align: 'l', get: (x) => x[0] }, { label: '2015년 이후 (bp)', get: (x) => x[1], fmt: (v) => (ok(v) ? F.s(v, 0) : '–'), heat: (v) => UI.heat(v, 50) }, { label: '설명', align: 'l', get: (x) => x[2] }],
          { rows: [['Duration', S.c_dur, `포지션을 든 ${S.hit.dur[1]}개월 중 ${S.hit.dur[0]}개월 적중`], ['Curve Slope', S.c_slope, `${S.hit.slope[1]}개월 중 ${S.hit.slope[0]}개월 적중`],
                   ['Curve Curvature', S.c_curv, `${S.hit.curv[1]}개월 중 ${S.hit.curv[0]}개월 적중`], ['캐리·롤다운', null, '벤치마크와 같은 구간 비중이라 따로 나누지 않음'],
                   ['스프레드', 0, '국채만 보유'], ['FX', 0, 'USD만 보유'], ['거래비용', 0, '0으로 가정']], dense: true })],
      foot: '뒤진 것은 대부분 Duration에서 나왔습니다.' });

    // ── 월별 초과수익 ──
    const byY = {};
    for (const m of B.months) { const y = m.month.slice(0, 4); (byY[y] = byY[y] || {})[Number(m.month.slice(5))] = m; }
    const yrs = Object.keys(byY).sort().reverse(), yearEx = Object.fromEntries(B.years.map((y) => [y.year, y.excess_bp]));
    const monCols = [{ label: '연도', align: 'l', get: (y) => y }];
    for (let k = 1; k <= 12; k++) monCols.push({ label: k + '월', get: (y) => (byY[y][k] ? byY[y][k].ex : null), fmt: (v) => (ok(v) ? F.s(v, 0) : ''), heat: (v) => UI.heat(v, 25) });
    monCols.push({ label: '연간', get: (y) => yearEx[y], fmt: (v) => F.s(v, 0), heat: (v) => UI.heat(v, 40) });
    const monCard = UI.card({ id: 'months', span: 'c8', title: '월별 초과수익', cap: '벤치마크 대비 bp', flush: true, tools: [UI.scaleKey('뒤짐', '앞섬')],
      body: UI.table(monCols, { rows: yrs, dense: true }),
      foot: `${S.months}개월 가운데 포지션이 있던 ${S.months_active}개월 중 ${S.months_win}개월을 앞섰습니다. 가장 좋았던 달 ${S.best.month} (${F.s(S.best.excess_bp, 0)}bp), 가장 나빴던 달 ${S.worst.month} (${F.s(S.worst.excess_bp, 0)}bp).` });

    // ── 리스크 ──
    const te = R.te_exante_bp, bud = R.budget;
    const riskCard = UI.card({ id: 'risk', span: 'c5', title: '리스크', cap: '추적오차(TE)와 VaR',
      body: [kv([['사전 추적오차', F.n(te, 0), 'bp / 년'], ['위험예산 (TE)', `${bud[0]}~${bud[1]}`, 'bp'], ['위험예산 소진율', F.n(te / bud[0] * 100, 0), '% (하단 기준)'],
                 ['사후 추적오차 1년', F.n(S.te_1y_bp, 0), 'bp'], ['사후 추적오차 3년', F.n(S.te_3y_bp, 0), 'bp'], ['사후 추적오차 전체', F.n(S.te_all_bp, 0), 'bp'],
                 ['1일 VaR 95%', F.usd(V.d1_95_usd), `${F.n(V.d1_95_pct, 2)}%`], ['1일 VaR 99%', F.usd(V.d1_99_usd), `${F.n(V.d1_99_pct, 2)}%`], ['상대 VaR 95%', F.n(V.rel_95_bp, 1), 'bp / 일'],
                 ['연 변동성', F.n(V.vol_ann_pct, 2), '%'], ['최대 일간 손실', F.n(V.worst_day, 2), '%'], ['규칙상 최대 추적오차', F.n(R.te_max_bp, 0), 'bp']]),
             h('p', { cls: 'note' }, `VaR는 최근 3년(${V.n}영업일) 일별 손익을 크기순으로 늘어놓고 5%, 1% 자리의 값을 읽은 것입니다. 상대 VaR는 벤치마크 대비 하루 손실입니다. 규칙이 낼 수 있는 가장 큰 포지션에서도 추적오차가 위험예산 하단에 못 미칩니다.`)] });
    const scenCard = UI.card({ id: 'scenario', span: 'c7', title: '시나리오', cap: '금리가 한 번에 움직이면', flush: true,
      body: [UI.table([{ label: '평행 이동', align: 'l', get: (x) => x.bp, fmt: (v) => F.bp(v) }, { label: '포트폴리오 손익', get: (x) => x.p_usd, fmt: (v) => F.usdS(v), heat: (v) => UI.heat(v, 700000) },
        { label: '수익률', get: (x) => x.p_pct, fmt: (v) => F.s(v, 2) + '%' }, { label: '벤치마크 대비', get: (x) => x.active_bp, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 25) }],
        { rows: R.parallel, dense: true }),
        h('div', { style: 'height:10px' }),
        UI.table([{ label: '커브 모양 변화', align: 'l', get: (x) => x.label }, { label: '벤치마크 대비', get: (x) => x.bp, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 15) }],
          { rows: R.scenarios.filter((x) => !x.label.startsWith('평행')), dense: true })],
      foot: '듀레이션만으로 계산한 근사입니다 (볼록성과 그동안 받는 이자는 뺌).' });
    const stressCard = UI.card({ id: 'stress', span: 'c12', title: '스트레스 테스트', cap: '과거 국면의 금리 변화를 지금 포트폴리오에 그대로 적용하면', flush: true,
      body: UI.table([{ label: '국면', align: 'l', get: (x) => x.label }, { label: '기간', align: 'l', get: (x) => x.from, fmt: (_, x) => `${x.from} ~ ${x.to}` },
        { label: '2년', get: (x) => x.d2, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) }, { label: '10년', get: (x) => x.d10, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) },
        { label: '30년', get: (x) => x.d30, fmt: (v) => F.bp(v), heat: (v) => UI.heat(v, 150) },
        { label: '포트폴리오 손익', get: (x) => x.p_usd, fmt: (v) => F.usdS(v) }, { label: '포트폴리오', get: (x) => x.p_pct, fmt: (v) => F.s(v, 2) + '%', heat: (v) => UI.heat(v, 9) },
        { label: '벤치마크', get: (x) => x.b_pct, fmt: (v) => F.s(v, 2) + '%' }, { label: '벤치마크 대비', get: (x) => x.active_bp, fmt: (v) => F.bp(v, 1), heat: (v) => UI.heat(v, 30) }],
        { rows: R.stress, dense: true }),
      foot: '금리 변화 색은 오름이 빨강이고, 손익 색은 이익이 빨강입니다. 듀레이션만으로 계산한 근사라 금리가 크게 움직인 국면에서는 손실이 실제보다 조금 크게 나옵니다.' });

    const act = B.active_dur;
    const lead = `포트폴리오 듀레이션은 벤치마크보다 ${Math.abs(act).toFixed(2)}년 ${act >= 0 ? '길고' : '짧고'} DV01은 ${F.usd(B.dv01)}입니다. ${B.start.slice(0, 4)}년 말 이후 초과수익은 ${F.bp(ex('itd'), 0)}, 올해는 ${F.bp(ex('ytd'), 0)}입니다.${ranked.length ? ` 액티브 KRD가 가장 큰 만기는 ${ranked[0][0]} (${F.usdS(ranked[0][1])} / bp)입니다` : ''}`;
    // 결론 한 줄: 듀레이션을 어느 쪽으로 얼마나 가져갔나 + 지금까지 성과가 벤치마크와 구분되나
    const use = te / bud[0], tStat = S.ir * Math.sqrt(S.years);
    const posWord = Math.abs(act) < 0.03 ? '듀레이션을 벤치마크와 같게 두고 있고' : `벤치마크보다 듀레이션을 ${use < 0.6 ? '소폭 ' : use > 1 ? '크게 ' : ''}${act > 0 ? '확대' : '축소'}했고`;
    const since = `${B.start.slice(0, 4)}년 말 이후 성과는`;
    const perfWord = Math.abs(tStat) < 2 ? `${since} 벤치마크와 사실상 같습니다` : tStat > 0 ? `${since} 벤치마크를 꾸준히 앞섰습니다` : `${since} 벤치마크에 꾸준히 뒤졌습니다`;
    const title = `포트폴리오는 ${posWord}, ${perfWord}`;
    return { title, lead, usOnly: true,
      sub: `근거: 사전 추적오차 ${F.n(te, 0)}bp는 위험예산 하단 ${bud[0]}bp의 ${F.n(use * 100, 0)}% (60% 미만이면 소폭으로 봄). 정보비율 ${F.n(S.ir, 2)} × √${F.n(S.years, 1)}년 = t ${F.n(tStat, 2)} (절댓값이 2에 못 미치면 우연과 구분되지 않는다고 봄). 가상 USD 10M을 미국 국채에 규칙대로 운용한 모형 포트폴리오이고, 벤치마크는 공개 자료로 만든 미국 국채 대용 지수입니다.`,
      tabs: [...(pnlCard ? [['pnl', '손익 설명']] : []), ...(limitCard ? [['limit', '손실 한도']] : []), ['krd', 'KRD'], ['adjust', '조정'], ['compose', '구성'], ['perf', '성과'], ['blotter', '보유 종목'], ['trades', '거래 내역'], ['exposure', '익스포저'], ['attribution', '성과 분해'], ['months', '월별 초과수익'], ['risk', '리스크·시나리오'], ['stress', '스트레스 테스트']],
      body: [tiles, pnlCard, limitCard, krdCard, adjustCard, composeCard, perfCard, posCard, rbCard, expCard, attrCard, yearCard, monCard, riskCard, scenCard, stressCard] };
  };
})();
