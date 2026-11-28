/* 틀: 왼쪽 메뉴, 상단 필터, 화면 전환, 뉴스 서랍, 채권 상세 서랍.
   화면 하나는 window.DeskViews[이름](ctx) → {q, title, lead, sub, tabs, body} 를 돌려주는 함수다.
   title은 결론 한 줄, lead는 그 아래 두 번째 소제목(사실 요약), sub는 근거와 출처다. */
(function () {
  'use strict';
  const { h, s, F, ok } = UI;
  const D = window.DESK;
  const BM = window.BondMath;
  window.DeskViews = window.DeskViews || {};

  const MENU = [
    { id: 'home', name: '홈', q: 'Desk Overview', icon: 'M3 11l9-7 9 7M5 10v10h14V10' },
    { sep: true },
    { id: 'market', name: '시장 모니터', q: '무엇이 움직였나', icon: 'M3 12h4l3-8 4 16 3-8h4' },
    { id: 'macro', name: '매크로·정책', q: '왜 움직였나', icon: 'M3 21h18M5 21V10M19 21V10M9 21V10M15 21V10M2 10l10-6 10 6' },
    { id: 'xasset', name: '크로스에셋', q: '다른 시장은 뭐라 하나', icon: 'M4 17l5-5 4 4 7-8M15 8h5v5' },
    { id: 'flows', name: '수급·펀딩', q: '누가 사고, 조달비용은', icon: 'M4 7h13l-3-3M20 17H7l3 3' },
    { id: 'rv', name: 'RV·전략', q: '어디에 투자할까', icon: 'M12 3v4M12 17v4M3 12h4M17 12h4M7 12a5 5 0 1 0 10 0a5 5 0 1 0-10 0' },
    { id: 'credit', name: '크레딧·소버린', q: '발행자는 안전한가', icon: 'M12 3l8 3v6c0 5-3.5 8-8 9c-4.5-1-8-4-8-9V6l8-3z' },
    { id: 'book', name: '포트폴리오·리스크', q: '내 포트폴리오는 어떤가', icon: 'M3 8h18v12H3zM9 8V5h6v3M3 13h18' },
  ];
  const PERIODS = [['3M', '3달'], ['1Y', '1년'], ['3Y', '3년'], ['5Y', '5년'], ['ALL', '전체']];
  const krOk = D.kr && D.kr.status === 'ok';

  // ───────── 상태 (필터는 이 브라우저에만 기억) ─────────
  const st = { route: 'home', asset: 'all', region: 'US', mat: 'all', period: '1Y' };
  try { Object.assign(st, JSON.parse(localStorage.getItem('desk.filters') || '{}')); } catch (e) { /* 저장소를 못 쓰면 기본값 */ }
  {                                       // 주소의 ?region=KR&mat=long&asset=credit&period=3Y 가 저장된 값보다 먼저다
    const qs0 = new URLSearchParams(location.search);
    const allow = { asset: ['all', 'govt', 'credit'], region: ['US', 'KR'], mat: ['all', 'short', 'mid', 'long'], period: ['3M', '1Y', '3Y', '5Y', 'ALL'] };
    for (const k of Object.keys(allow)) {
      const v = qs0.get(k);
      if (v && allow[k].includes(v)) st[k] = v;
      else if (!allow[k].includes(st[k])) st[k] = allow[k][0];
    }
  }
  const save = () => { try { localStorage.setItem('desk.filters', JSON.stringify({ asset: st.asset, region: st.region, mat: st.mat, period: st.period })); } catch (e) { /* 무시 */ } };
  const matGroup = (y) => (y <= 2.5 ? 'short' : y <= 8 ? 'mid' : 'long');

  const ctx = {
    D, st, F, UI, krOk,
    go(route, anchor) { location.hash = '#/' + route + (anchor ? '/' + anchor : ''); },
    /* 같은 화면을 다시 그린다 (scroll: 'keep'이면 제자리, 아니면 주소의 카드로) */
    rerender(scroll) { render(scroll === 'keep'); },
    matOk: (years) => st.mat === 'all' || matGroup(years) === st.mat,
    /* 일별 시계열을 기간 필터에 맞춰 잘라 선 차트로. defs: [{key,name,color,scale}] */
    lineOf(defs, o) {
      const src = (o && o.src) || D.series, i0 = UI.cut(src.dates, st.period), x = src.dates.slice(i0);
      const series = defs.map((df) => ({ name: df.name, color: df.color, width: df.width, dash: df.dash,
        values: (src.cols[df.key] || []).slice(i0).map((v) => (ok(v) ? v * (df.scale || 1) : null)) }));
      return { chart: UI.line(Object.assign({ x, series }, o || {})),
               alt: () => UI.seriesTable(x, series.map((sr) => ({ name: sr.name, values: sr.values, fmt: o && o.tblFmt })), 36) };
    },
    openBond, openNews,
  };

  // ───────── 틀 그리기 ─────────
  function icon(d) { return s('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true' }, s('path', { d })); }
  function buildShell() {
    const nav = h('nav', { cls: 'nav', 'aria-label': '메뉴' }, MENU.map((m) => (m.sep ? h('div', { cls: 'sep' })
      : h('a', { href: '#/' + m.id, 'data-route': m.id }, icon(m.icon), h('span', null, m.name, h('small', null, m.q))))));
    // 버전은 2 하나뿐이다 (2026-11-28 버전 1 정리). index.html이 data-version="2"로 theme-v2.css를 켠다.
    const ver = '2';
    const side = h('aside', { cls: 'side' },
      h('div', { cls: 'brand' }, h('b', null, 'Rates Desk'), h('span', null, '채권 데스크 대시보드'), h('span', { cls: 'ver' }, 'v' + ver)),
      nav,
      h('div', { cls: 'foot' }, h('span', null, `금리 기준일 ${D.meta.asof}`), h('span', null, `자료 갱신 ${D.meta.generated.slice(5)} UTC`),
        h('span', null, '일별 종가 · 실시간 아님')));

    const sel = (key, label, opts) => {
      const el = h('select', { 'aria-label': label }, opts.map(([v, t, off]) => h('option', { value: v, disabled: off || null }, t)));
      el.value = st[key];
      el.addEventListener('change', () => { setFilter(key, el.value); });
      return h('label', { cls: 'flt' }, label, el);
    };
    const seg = h('div', { cls: 'seg', role: 'group', 'aria-label': '기간' }, PERIODS.map(([v, t]) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(st.period === v) }, t);
      b.addEventListener('click', () => { setFilter('period', v); });
      b.dataset.v = v;
      return b;
    }));
    const newest = (D.news[0] || {}).ts || '';
    let seen = '';
    try { seen = localStorage.getItem('desk.newsSeen') || ''; } catch (e) { /* 무시 */ }
    const newsBtn = h('button', { cls: 'btn', type: 'button' }, icon('M4 5h13v14H6a2 2 0 0 1-2-2zM17 9h3v8a2 2 0 0 1-2 2M8 9h5M8 13h5'), '뉴스',
      newest > seen ? h('span', { cls: 'dot', title: '새 소식' }) : null);
    newsBtn.addEventListener('click', () => { openNews(); const d = newsBtn.querySelector('.dot'); if (d) d.remove(); });
    const themeBtn = h('button', { cls: 'btn', type: 'button', title: '밝은 화면 / 어두운 화면', 'aria-label': '화면 밝기 바꾸기' }, icon('M12 3a9 9 0 1 0 9 9c-5 1-9-3-9-9z'));
    themeBtn.addEventListener('click', () => {
      const dark = getComputedStyle(document.documentElement).colorScheme.includes('dark');
      document.documentElement.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem('desk.theme', document.documentElement.dataset.theme); } catch (e) { /* 무시 */ }
    });
    const top = h('div', { cls: 'top' },
      sel('asset', '자산군', [['all', '전체'], ['govt', '국채'], ['credit', '크레딧 지수'], ['_c', '회사채 종목 (자료 없음)', true], ['_d', '금리 파생 (자료 없음)', true]]),
      sel('region', '지역', [['US', '미국'], ['KR', krOk ? '한국' : '한국 (키 필요)']]),
      sel('mat', '만기', [['all', '전체'], ['short', '단기 · 2년 이하'], ['mid', '중기 · 3~7년'], ['long', '장기 · 10년 이상']]),
      sel('ccy', '통화', [['USD', 'USD'], ['KRW', 'KRW']]),
      seg, h('span', { cls: 'grow' }),
      h('span', { cls: 'asof num' }, `${D.meta.asof} 종가`), newsBtn, themeBtn);
    top.querySelector('select[aria-label="통화"]').value = st.region === 'KR' ? 'KRW' : 'USD';

    document.body.appendChild(h('div', { cls: 'app' }, side, h('div', { cls: 'main' }, top, h('main', { cls: 'view', id: 'view' }))));
    document.body.appendChild(h('div', { cls: 'scrim', id: 'scrim' }));
    document.body.appendChild(h('aside', { cls: 'drawer', id: 'drawer', 'aria-hidden': 'true' }));
    document.body.appendChild(h('div', { id: 'tip', role: 'tooltip' }));
    document.getElementById('scrim').addEventListener('click', closeDrawer);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawer(); });
  }
  function setFilter(key, value) {
    if (key === 'ccy') { key = 'region'; value = value === 'KRW' ? 'KR' : 'US'; }
    st[key] = value;
    save();
    document.querySelectorAll('.top select').forEach((el) => {
      const lab = el.getAttribute('aria-label');
      if (lab === '지역') el.value = st.region;
      if (lab === '통화') el.value = st.region === 'KR' ? 'KRW' : 'USD';
    });
    document.querySelectorAll('.seg button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === st.period)));
    render(true);
  }

  function render(keepScroll) {
    const parts = location.hash.replace(/^#\/?/, '').split('/');
    const route = MENU.some((m) => m.id === parts[0]) ? parts[0] : 'home';
    st.route = route;
    document.querySelectorAll('.nav a').forEach((a) => {
      if (a.dataset.route === route) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    const view = document.getElementById('view'), y = window.scrollY;
    const fn = window.DeskViews[route];
    UI.tip.hide();
    let v;
    try { v = fn(ctx); } catch (err) {
      console.error(err);
      view.replaceChildren(UI.empty('이 화면을 그리지 못했습니다', String(err && err.message || err)));
      document.documentElement.dataset.error = (document.documentElement.dataset.error || '') + route + ';';
      return;
    }
    const m = MENU.find((x) => x.id === route);
    const notes = [];
    if (st.region === 'KR' && !krOk) notes.push(h('div', { cls: 'banner' }, '한국 자료는 아직 없습니다. 한국은행 ECOS 인증키를 ', h('code', null, '4. desk/.env'), '에 넣고 ', h('code', null, 'pipeline/fetch_korea.py'), '를 돌리면 시장 모니터와 크레딧 화면의 한국 칸이 채워집니다. 지금은 미국 자료를 보여 줍니다.'));
    else if (st.region === 'KR' && v.usOnly) notes.push(h('div', { cls: 'banner' }, '이 화면은 미국 자료만 있습니다. 한국 자료는 시장 모니터, 매크로·정책의 중앙은행, 크레딧·소버린에 있습니다.'));
    view.replaceChildren(
      h('div', { cls: 'vhead' }, h('p', { cls: 'q' }, m.name + ' · ' + (v.q || m.q)), h('h1', null, v.title), v.lead ? h('p', { cls: 'lead', role: 'doc-subtitle' }, v.lead) : null, v.sub ? h('p', { cls: 'sub' }, v.sub) : null,
        v.tabs ? h('div', { cls: 'tabs' }, v.tabs.map(([id, t]) => h('a', { href: '#/' + route + '/' + id, 'aria-current': v.tab === id ? 'page' : null }, t))) : null),
      notes, h('div', { cls: 'grid' }, v.body));
    document.title = m.name + ' · Rates Desk';
    if (keepScroll) window.scrollTo(0, y);
    else if (parts[1]) requestAnimationFrame(() => { const el = document.getElementById(parts[1]); if (el) el.scrollIntoView(); });
    else window.scrollTo(0, 0);
  }

  // ───────── 서랍 ─────────
  function openDrawer(title, sub, bodyNodes) {
    const dr = document.getElementById('drawer');
    const close = h('button', { cls: 'btn', type: 'button', 'aria-label': '닫기' }, '닫기');
    close.addEventListener('click', closeDrawer);
    dr.replaceChildren(h('header', null, h('div', null, h('h2', null, title), sub ? h('p', null, sub) : null), h('span', { cls: 'sp' }), close),
      h('div', { cls: 'dbody' }, bodyNodes));
    dr.classList.add('open');
    dr.setAttribute('aria-hidden', 'false');
    document.getElementById('scrim').classList.add('open');
    close.focus();
  }
  function closeDrawer() {
    const dr = document.getElementById('drawer');
    if (!dr) return;
    dr.classList.remove('open');
    dr.setAttribute('aria-hidden', 'true');
    document.getElementById('scrim').classList.remove('open');
    UI.tip.hide();
  }

  function openNews() {
    let src = '전체';
    const list = h('ul', { cls: 'list' });
    const fmtKst = (ts) => new Date(ts).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
    const draw = () => {
      list.replaceChildren();
      const items = D.news.filter((n) => src === '전체' || n.src === src);
      for (const n of items) {
        const safe = /^https?:\/\//.test(n.link) ? n.link : null;
        list.appendChild(h('li', null, h('span', { cls: 'when' }, fmtKst(n.ts)),
          h('span', { cls: 'what' }, safe ? h('a', { href: safe, target: '_blank', rel: 'noopener noreferrer' }, n.title) : n.title,
            h('small', null, `${n.src} · ${n.kind}${n.cat && n.cat !== n.kind ? ' · ' + n.cat : ''}`))));
      }
      if (!items.length) list.appendChild(h('li', null, h('span'), h('span', { cls: 'mute' }, '받은 소식이 없습니다')));
    };
    const seg = h('div', { cls: 'seg', role: 'group', 'aria-label': '출처' }, ['전체', '연준', '한국은행'].map((t) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(t === src) }, t);
      b.addEventListener('click', () => { src = t; seg.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); draw(); });
      return b;
    }));
    draw();
    openDrawer('뉴스', '연준과 한국은행의 보도자료·연설 · 하루 한 번 갱신 (실시간 속보 아님) · 시각은 한국 시간', [seg, h('div', { style: 'height:8px' }), list]);
    try { localStorage.setItem('desk.newsSeen', (D.news[0] || {}).ts || ''); } catch (e) { /* 무시 */ }
  }

  /* 채권 상세. b: {title, sub, coupon, maturity, settle, price(클린) | ytm, cusip, tags:[글자], rv:{fit_bp,par_gap_bp,carry3m,roll3m}, model:bool, source} */
  function openBond(b) {
    const a = BM.analytics(b.coupon, b.maturity, b.settle, b.price != null ? { clean: b.price } : { ytm: b.ytm });
    const ttm = BM.yearsBetween(b.settle, b.maturity);
    const kv = (items) => h('dl', { cls: 'kv' }, items.map(([k, v, u]) => h('div', null, h('dt', null, k), h('dd', null, v, u ? h('small', null, u) : null))));
    const nodes = [];
    if (b.tags && b.tags.length) nodes.push(h('p', { style: 'margin:0 0 10px' }, b.tags.map((t) => [h('span', { cls: 'pill acc' }, t), ' '])));
    nodes.push(kv([['클린가격', F.n(a.clean, 3)], ['경과이자', F.n(a.accrued, 4)], ['더티가격', F.n(a.dirty, 3)],
                   ['만기수익률 (YTM)', F.n(a.ytm, 3), '%'], ['수정듀레이션', F.n(a.mdur, 2), '년'], ['볼록성', F.n(a.conv, 1)],
                   ['DV01', F.usd(a.dv01PerM), '/ 액면 100만'], ['맥컬리 듀레이션', F.n(a.mac, 2), '년'], ['잔존만기', F.n(ttm, 2), '년']]));
    nodes.push(h('p', { cls: 'note' }, `결제일 ${b.settle} 기준. ${b.source || ''}`));

    nodes.push(h('h3', null, '상대가치'));
    if (b.rv) {
      nodes.push(kv([['적합 커브 대비', F.bp(b.rv.fit_bp, 1)], ['재무부 par 커브 대비', F.bp(b.rv.par_gap_bp, 1)],
                     ['3개월 캐리+롤다운', ok(b.rv.carry3m) && ok(b.rv.roll3m) ? F.bp(b.rv.carry3m + b.rv.roll3m, 0) : '–']]));
      nodes.push(h('p', { cls: 'note' }, '+ 는 잔존만기가 비슷한 종목들로 만든 적합 커브보다 금리가 높다(저평가)는 뜻입니다. 캐리는 금리에서 SOFR를 뺀 값, 롤다운은 커브를 따라 3개월 내려올 때의 가격 효과입니다.'));
    }
    nodes.push(h('p', { cls: 'note' }, 'Z-스프레드와 OAS는 회사채를 국채·스왑 커브와 비교하는 지표라 국채 자체에는 쓰지 않습니다. 회사채 종목 자료는 아직 없습니다.'));

    // 금리가 움직이면
    nodes.push(h('h3', null, '금리가 움직이면'));
    const out = h('div');
    const rng = h('input', { type: 'range', min: -150, max: 150, step: 5, value: 25, 'aria-label': '금리 변화 (bp)' });
    const calc = () => {
      const bp = Number(rng.value), dy = bp / 100;
      const d1 = BM.dirtyFromYield(b.coupon, b.maturity, b.settle, a.ytm + dy);
      const tot = d1 - a.dirty, durEff = -a.mdur * (dy / 100) * a.dirty, convEff = 0.5 * a.conv * Math.pow(dy / 100, 2) * a.dirty;
      out.replaceChildren(kv([['금리 변화', F.bp(bp)], ['새 금리', F.n(a.ytm + dy, 3), '%'], ['새 클린가격', F.n(d1 - a.accrued, 3)],
                              ['손익', F.usdS(tot * 10000)], ['듀레이션 효과', F.usdS(durEff * 10000)], ['볼록성 효과', F.usdS(convEff * 10000)]]),
        h('p', { cls: 'note' }, '손익과 두 효과는 액면 100만 달러를 들고 있을 때의 달러 금액입니다.'));
    };
    rng.addEventListener('input', calc);
    calc();
    nodes.push(h('div', { cls: 'form' }, h('label', null, '금리 변화: −150bp ~ +150bp', rng)), h('div', { style: 'height:8px' }), out);
    const shifts = [];
    for (let k = -200; k <= 200; k += 25) shifts.push(k);
    nodes.push(h('div', { style: 'height:10px' }), UI.line({
      x: shifts.map((k) => F.s(k)), date: false, xEvery: 2, h: 170, legend: false, unit: '', aria: '금리 변화에 따른 가격',
      series: [{ name: '클린가격', color: 'var(--s1)', values: shifts.map((k) => BM.dirtyFromYield(b.coupon, b.maturity, b.settle, a.ytm + k / 100) - a.accrued) },
               { name: '듀레이션만으로 본 가격', color: 'var(--s-mute)', width: 1.5, values: shifts.map((k) => a.clean - a.mdur * (k / 10000) * a.dirty) }],
      marks: [{ i: 8, label: '지금' }], tipFmt: (v) => F.n(v, 2) }));
    nodes.push(h('p', { cls: 'note' }, '가로축은 금리 변화(bp)입니다. 회색 선(듀레이션만)보다 실제 가격이 늘 위에 있는 만큼이 볼록성입니다.'));

    // 현금흐름
    const cfs = BM.cashflows(b.coupon, b.maturity, b.settle);
    nodes.push(h('h3', null, `현금흐름 (액면 100 기준, 이자 ${cfs.length}회와 만기 원금)`));
    const v = 1 / (1 + a.ytm / 200);
    nodes.push(UI.table([{ label: '지급일', align: 'l', get: (c) => c.date }, { label: '이자', get: (c) => c.coupon, fmt: (x) => F.n(x, 4) },
                         { label: '원금', get: (c) => c.principal, fmt: (x) => (x ? F.n(x, 0) : '') },
                         { label: '현재가치', get: (c) => (c.coupon + c.principal) * Math.pow(v, c.t * 2), fmt: (x) => F.n(x, 3) }],
      { rows: cfs.length > 14 ? cfs.slice(0, 6).concat(cfs.slice(-6)) : cfs, dense: true }));
    if (cfs.length > 14) nodes.push(h('p', { cls: 'note' }, `처음 6회와 마지막 6회만 표에 실었습니다 (전체 ${cfs.length}회).`));
    openDrawer(b.title, b.sub, nodes);
  }

  // ───────── 시작 ─────────
  try { const t = localStorage.getItem('desk.theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* 무시 */ }
  const q = new URLSearchParams(location.search).get('theme');
  if (q === 'dark' || q === 'light') document.documentElement.dataset.theme = q;
  window.addEventListener('DOMContentLoaded', () => {
    buildShell();
    render();
    window.addEventListener('hashchange', () => render());
    // 주소에 ?bond=CUSIP 이나 ?panel=news 가 있으면 그 서랍을 연 채로 시작한다
    const qs = new URLSearchParams(location.search), cusip = qs.get('bond');
    if (cusip && D.bonds.status === 'ok') {
      const b = D.bonds.list.find((x) => x.cusip === cusip);
      if (b && window.DeskBondArg) openBond(window.DeskBondArg(D.bonds, b));
    }
    if (qs.get('panel') === 'news') openNews();
    if (qs.get('selftest')) document.head.appendChild(Object.assign(document.createElement('script'), { src: 'assets/selftest.js' }));
  });
  window.DeskApp = { ctx, render };
})();
