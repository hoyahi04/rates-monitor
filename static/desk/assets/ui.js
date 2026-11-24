/* 공통 도구: DOM, 숫자 표기, 히트맵 색, 표, 카드, 차트(SVG).
   자료에서 온 글자는 모두 textContent로만 넣는다 (innerHTML을 쓰지 않는다). */
(function () {
  'use strict';
  const SVGNS = 'http://www.w3.org/2000/svg';

  function put(el, kids) {
    for (const k of kids) {
      if (k == null || k === false) continue;
      if (Array.isArray(k)) put(el, k);
      else el.appendChild(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  function setAttrs(el, attrs) {
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'text') el.textContent = v;
      else el.setAttribute(k === 'cls' ? 'class' : k, v === true ? '' : v);
    }
    return el;
  }
  const h = (tag, attrs, ...kids) => put(setAttrs(document.createElement(tag), attrs), kids);
  const s = (tag, attrs, ...kids) => put(setAttrs(document.createElementNS(SVGNS, tag), attrs), kids);

  // ───────── 숫자 표기 ─────────
  const ok = (v) => v != null && isFinite(v);
  const F = {
    n(v, d = 2) { return ok(v) ? Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }).replace('-', '−') : '–'; },
    s(v, d = 0) {                                   // 부호 붙은 숫자
      if (!ok(v)) return '–';
      const r = Number(Number(v).toFixed(d));
      const body = Math.abs(r).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
      return r > 0 ? '+' + body : r < 0 ? '−' + body : body;
    },
    pct(v, d = 2) { return ok(v) ? F.n(v, d) + '%' : '–'; },
    bp(v, d = 0) { return ok(v) ? F.s(v, d) + 'bp' : '–'; },
    usd(v) { return ok(v) ? (v < 0 ? '−$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US') : '–'; },
    usdS(v) { return ok(v) ? (v > 0 ? '+$' : v < 0 ? '−$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US') : '–'; },
    bn(v, d) {                                       // 십억 달러 단위 값 → '690억 달러', '2.98조 달러'
      if (!ok(v)) return '–';
      const a = Math.abs(v), sign = v < 0 ? '−' : '';
      return a >= 1000 ? sign + F.n(a / 1000, d == null ? 2 : d) + '조 달러' : sign + F.n(a * 10, 0) + '억 달러';
    },
    bnS(v) { return !ok(v) ? '–' : (v > 0 ? '+' : '') + F.bn(v); },
    md(d) { return d ? d.slice(5, 10) : '–'; },
    ym(d) { return d ? d.slice(2, 4) + '.' + d.slice(5, 7) : '–'; },
    mon(d) { return d ? Number(d.slice(5, 7)) + '월' : '–'; },
    kdate(d) { return d ? Number(d.slice(5, 7)) + '월 ' + Number(d.slice(8, 10)) + '일' : '–'; },
    wd(d) { return '일월화수목금토'[new Date(d + 'T00:00:00Z').getUTCDay()]; },
    days(a, b) { return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000); },
  };
  const dirCls = (v) => (!ok(v) || Math.abs(v) < 1e-9 ? '' : v > 0 ? 'up' : 'down');

  // ───────── 히트맵 색: + 빨강, − 파랑. 0에 가까우면 색 없음 ─────────
  function heat(v, max, invert) {
    if (!ok(v) || !max) return '';
    const a = Math.min(Math.abs(v) / max, 1), pct = Math.round(a * 50);
    if (pct < 4) return '';
    const c = (v > 0) !== !!invert ? 'var(--up)' : 'var(--down)';
    return `color-mix(in srgb, ${c} ${pct}%, transparent)`;
  }
  const heatPct = (p) => (ok(p) ? heat(p - 50, 50) : '');           // 백분위(0~100): 50에서 멀수록 진하게

  // ───────── 말풍선 ─────────
  const tipEl = () => document.getElementById('tip');
  const tip = {
    show(evt, title, rows) {
      const el = tipEl();
      el.replaceChildren();
      if (title) el.appendChild(h('div', { cls: 'tt' }, title));
      for (const r of rows || []) {
        el.appendChild(h('div', { cls: 'tr' },
          h('span', null, r.color ? h('i', { style: `background:${r.color}` }) : null, r.name),
          h('b', null, r.value)));
      }
      el.style.display = 'block';
      const pad = 14, w = el.offsetWidth, hh = el.offsetHeight;
      let x = evt.clientX + pad, y = evt.clientY + pad;
      if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
      if (y + hh > window.innerHeight - 8) y = evt.clientY - hh - pad;
      el.style.left = Math.max(8, x) + 'px';
      el.style.top = Math.max(8, y) + 'px';
    },
    hide() { tipEl().style.display = 'none'; },
  };

  // ───────── 표 ─────────
  /* cols: [{label, get(row), fmt(v,row) → 글자|Node, align:'l'|'c', heat(v,row) → 배경색, title, sort:false, w}]
     opts: {rows, dense, onRow(row), group(row) → 묶음 이름, sortable, rowCls(row), foot: [셀...]} */
  function table(cols, opts) {
    const o = opts || {};
    let rows = o.rows.slice(), sortBy = null, sortDir = -1;
    const tb = h('tbody');
    const draw = () => {
      tb.replaceChildren();
      let last = null;
      for (const row of rows) {
        if (o.group && !sortBy) {
          const g = o.group(row);
          if (g !== last) { last = g; tb.appendChild(h('tr', { cls: 'grp' }, h('td', { colspan: cols.length }, g))); }
        }
        const tr = h('tr', { cls: [o.onRow ? 'click' : '', o.rowCls ? o.rowCls(row) : ''].join(' ').trim() || null,
                             tabindex: o.onRow ? 0 : null });
        if (o.onRow) {
          tr.addEventListener('click', () => o.onRow(row));
          tr.addEventListener('keydown', (e) => { if (e.key === 'Enter') o.onRow(row); });
        }
        for (const c of cols) {
          const v = c.get ? c.get(row) : null;
          const out = c.fmt ? c.fmt(v, row) : v;
          const bg = c.heat ? c.heat(v, row) : '';
          const td = h('td', { cls: [c.align || '', c.heat ? 'hc' : ''].join(' ').trim() || null });
          if (c.heat) td.appendChild(h('span', { style: bg ? `background:${bg}` : null }, out == null ? '–' : out));
          else put(td, [out == null ? '–' : out]);
          tr.appendChild(td);
        }
        tb.appendChild(tr);
      }
    };
    const head = h('tr');
    cols.forEach((c) => {
      const canSort = o.sortable && c.get && c.sort !== false;
      const th = h('th', { cls: [c.align || '', canSort ? 'sortable' : ''].join(' ').trim() || null, title: c.title,
                           style: c.w ? `width:${c.w}` : null }, c.label);
      if (canSort) th.addEventListener('click', () => {
        sortDir = sortBy === c ? -sortDir : -1; sortBy = c;
        rows.sort((a, b) => {
          const x = c.get(a), y = c.get(b);
          if (x == null) return 1; if (y == null) return -1;
          return (typeof x === 'string' ? x.localeCompare(y) : x - y) * sortDir;
        });
        draw();
      });
      head.appendChild(th);
    });
    draw();
    const t = h('table', { cls: 't' + (o.dense ? ' dense' : '') }, h('thead', null, head), tb);
    if (o.foot) t.appendChild(h('tfoot', null, h('tr', null, o.foot.map((x, i) => h('td', { cls: cols[i] && cols[i].align }, x == null ? '' : x)))));
    return h('div', { cls: 'tw' }, t);
  }

  // ───────── 카드 ─────────
  /* {id, span, title, cap, body, foot, flush, tools:[Node], alt: () => Node}  alt가 있으면 "표" 단추로 바꿔 볼 수 있다 */
  function card(o) {
    const body = h('div', { cls: 'body' + (o.flush ? ' flush' : '') }, o.body);
    const head = h('header', null, h('h2', null, o.title), o.cap ? h('span', { cls: 'cap' }, o.cap) : null, h('span', { cls: 'sp' }), o.tools || null);
    if (o.alt) {
      let on = false;
      const main = Array.from(body.childNodes);
      const btn = h('button', { cls: 'mini', type: 'button', 'aria-pressed': 'false', title: '차트의 값을 표로 봅니다' }, '표');
      btn.addEventListener('click', () => {
        on = !on;
        btn.setAttribute('aria-pressed', String(on));
        body.replaceChildren(...(on ? [o.alt()] : main));
        body.classList.toggle('flush', on || !!o.flush);
      });
      head.appendChild(btn);
    }
    return h('section', { cls: 'card ' + (o.span || 'c12'), id: o.id }, head, body, o.foot ? h('footer', null, o.foot) : null);
  }
  const empty = (title, text) => h('div', { cls: 'empty' }, h('b', null, title), text);

  function tile(o) {
    const el = h('div', { cls: 'tile' + (o.hero ? ' hero' : '') + (o.onClick ? ' link' : ''), title: o.title, tabindex: o.onClick ? 0 : null },
      h('div', { cls: 'lab' }, o.lab),
      h('div', { cls: 'val' + (String(o.val).length >= 10 ? ' long' : '') }, o.val, o.unit ? h('small', null, o.unit) : null),   // 긴 값은 모양 파일이 글자를 줄일 수 있게 표시
      o.deltas && o.deltas.length ? h('div', { cls: 'del num' }, o.deltas.map((d) => h('span', null, d.k + ' ', h('span', { cls: dirCls(d.raw) }, d.v)))) : null,
      o.note ? h('div', { cls: 'del' }, o.note) : null,
      o.spark && o.spark.length > 2 ? h('div', { cls: 'spark' }, spark(o.spark, { w: 132, h: 26 })) : null);
    if (o.onClick) {
      el.addEventListener('click', o.onClick);
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter') o.onClick(); });
    }
    return el;
  }

  // ───────── 작은 그림 ─────────
  function spark(vals, o) {
    const w = (o && o.w) || 72, hh = (o && o.h) || 20, v = (vals || []).filter(ok);
    if (v.length < 2) return h('span', { cls: 'mute' }, '–');
    const lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
    const X = (i) => 2 + (i / (v.length - 1)) * (w - 6), Y = (x) => hh - 3 - ((x - lo) / sp) * (hh - 6);
    const dpath = v.map((x, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(x).toFixed(1)).join('');
    return s('svg', { width: w, height: hh, viewBox: `0 0 ${w} ${hh}`, role: 'img', 'aria-label': '최근 1년 추이' },
      s('path', { d: dpath, fill: 'none', stroke: 'var(--s-mute)', 'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }),
      s('circle', { cx: X(v.length - 1), cy: Y(v[v.length - 1]), r: 2.5, fill: 'var(--ink)' }));
  }
  function range(lo, hi, v, title) {
    if (!ok(lo) || !ok(hi) || !ok(v) || hi <= lo) return h('span', { cls: 'mute' }, '–');
    const p = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    return h('span', { cls: 'range', title: title || `3년 범위 ${F.n(lo, 2)} ~ ${F.n(hi, 2)}` }, h('i', { style: `left:${(p * 100).toFixed(1)}%` }));
  }
  function legend(items, box) {
    return h('div', { cls: 'legend' }, items.map((it) => h('span', null, h('i', { cls: box ? 'box' : null, style: `background:${it.color}` }), it.name)));
  }
  const scaleKey = (lo, hi) => h('span', { cls: 'scale' }, lo, h('i'), hi);

  // ───────── 차트 공통 ─────────
  function chartBox(height, draw) {
    const el = h('div', { cls: 'chart', style: `height:${height}px` });
    let seen = 0;
    const run = () => {
      const w = Math.floor(el.clientWidth);
      if (w > 40 && w !== seen) { seen = w; el.replaceChildren(); draw(el, w, height); }
    };
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(run).observe(el);
    requestAnimationFrame(run);
    return el;
  }
  function niceTicks(lo, hi, n) {
    if (!(hi > lo)) { hi = lo + 1; lo = lo - 1; }
    const raw = (hi - lo) / (n || 4), mag = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / mag;
    const step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * mag;
    const out = [];
    for (let t = Math.ceil(lo / step - 1e-9) * step; t <= hi + step * 1e-9; t += step) out.push(Number(t.toFixed(10)));
    return { ticks: out, step };
  }
  const tickFmt = (step) => (v) => F.n(v, step >= 1 ? 0 : step >= 0.1 ? 1 : step >= 0.01 ? 2 : 3);
  function dateTicks(dates) {
    const n = dates.length;
    if (n < 2) return [];
    const span = F.days(dates[0], dates[n - 1]);
    const stepM = span <= 130 ? 1 : span <= 400 ? 2 : span <= 800 ? 3 : span <= 1500 ? 6 : span <= 3200 ? 12 : 24;
    const out = [];
    let last = dates[0].slice(0, 7);
    for (let i = 1; i < n; i++) {
      const ym = dates[i].slice(0, 7);
      if (ym === last) continue;
      last = ym;
      const y = +ym.slice(0, 4), m = +ym.slice(5, 7);
      if ((y * 12 + m - 1) % stepM === 0) out.push({ i, label: stepM >= 12 ? String(y) : ym.slice(2, 4) + '.' + ym.slice(5, 7) });
    }
    return out;
  }
  function cut(dates, period) {                    // 기간 필터 → 시작 위치
    if (!dates.length || period === 'ALL') return 0;
    const end = new Date(dates[dates.length - 1] + 'T00:00:00Z');
    const months = { '3M': 3, '1Y': 12, '3Y': 36, '5Y': 60 }[period] || 12;
    end.setUTCMonth(end.getUTCMonth() - months);
    const from = end.toISOString().slice(0, 10);
    let lo = 0, hi = dates.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (dates[mid] < from) lo = mid + 1; else hi = mid; }
    return lo;
  }

  /* 선 차트. o: {x:[날짜 또는 이름], series:[{name,color,values,width,dash}], h, yFmt, date:true, zero, refs:[{y,label}],
               step, dots, legend:false, xEvery, marks:[{i,label}]} */
  function line(o) {
    const series = o.series.filter((sr) => sr.values && sr.values.some(ok));
    const wrap = h('div');
    if (series.length > 1 && o.legend !== false) wrap.appendChild(legend(series));
    if (!series.length) { wrap.appendChild(empty('그릴 값이 없습니다', '이 기간에는 자료가 없습니다.')); return wrap; }
    const n = o.x.length, isDate = o.date !== false;
    wrap.appendChild(chartBox(o.h || 220, (el, W, H) => {
      const m = { l: 44, r: 14, t: 8, b: 22 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
      let lo = Infinity, hi = -Infinity;
      for (const sr of series) for (const v of sr.values) if (ok(v)) { if (v < lo) lo = v; if (v > hi) hi = v; }
      for (const rf of o.refs || []) { lo = Math.min(lo, rf.y); hi = Math.max(hi, rf.y); }
      if (o.zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
      const padY = (hi - lo || Math.abs(hi) || 1) * 0.07;
      lo -= padY; hi += padY;
      const { ticks, step } = niceTicks(lo, hi, Math.max(2, Math.round(ph / 46)));
      const yf = o.yFmt || tickFmt(step);
      const X = (i) => m.l + (n > 1 ? (i / (n - 1)) * pw : pw / 2), Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * ph;
      const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || '선 차트' });
      for (const t of ticks) {
        svg.appendChild(s('line', { cls: 'gl', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
        svg.appendChild(s('text', { x: m.l - 7, y: Y(t) + 3.5, 'text-anchor': 'end' }, yf(t)));
      }
      if (lo < 0 && hi > 0) svg.appendChild(s('line', { cls: 'ax', x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0) }));
      const xt = isDate ? dateTicks(o.x) : o.x.map((lab, i) => ({ i, label: lab })).filter((_, i) => i % (o.xEvery || 1) === 0);
      let lastX = -99;
      for (const t of xt) {
        const x = X(t.i);
        if (x - lastX < 34) continue;
        lastX = x;
        svg.appendChild(s('text', { x, y: H - 6, 'text-anchor': 'middle' }, t.label));
      }
      for (const rf of o.refs || []) {
        svg.appendChild(s('line', { cls: 'ref', x1: m.l, x2: W - m.r, y1: Y(rf.y), y2: Y(rf.y) }));
        if (rf.label) svg.appendChild(s('text', { cls: 'lab', x: W - m.r, y: Y(rf.y) - 4, 'text-anchor': 'end' }, rf.label));
      }
      for (const mk of o.marks || []) {
        svg.appendChild(s('line', { cls: 'ax', x1: X(mk.i), x2: X(mk.i), y1: m.t, y2: m.t + ph }));
        if (mk.label) svg.appendChild(s('text', { cls: 'lab', x: X(mk.i) + 4, y: m.t + 10 }, mk.label));
      }
      const skip = Math.max(1, Math.floor(n / (pw * 1.5)));
      for (const sr of series) {
        let dd = '', pen = false, prevY = null;
        for (let i = 0; i < n; i++) {
          const v = sr.values[i];
          if (!ok(v)) continue;
          if (skip > 1 && i % skip && i !== n - 1) continue;
          const x = X(i).toFixed(1), y = Y(v).toFixed(1);
          if (!pen) { dd += `M${x} ${y}`; pen = true; }
          else dd += o.step ? `L${x} ${prevY}L${x} ${y}` : `L${x} ${y}`;
          prevY = y;
        }
        svg.appendChild(s('path', { d: dd, fill: 'none', stroke: sr.color, 'stroke-width': sr.width || 2, 'stroke-linejoin': 'round',
                                    'stroke-linecap': 'round', 'stroke-dasharray': sr.dash || null }));
        if (o.dots) for (let i = 0; i < n; i++) if (ok(sr.values[i])) svg.appendChild(s('circle', { cx: X(i), cy: Y(sr.values[i]), r: 3.5, fill: sr.color, stroke: 'var(--surface)', 'stroke-width': 2 }));
      }
      // 십자선과 말풍선
      const vl = s('line', { cls: 'ax', y1: m.t, y2: m.t + ph, visibility: 'hidden' });
      const dots = series.map((sr) => s('circle', { r: 4, fill: sr.color, stroke: 'var(--surface)', 'stroke-width': 2, visibility: 'hidden' }));
      svg.appendChild(vl);
      dots.forEach((dt) => svg.appendChild(dt));
      const hit = s('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent', tabindex: 0, 'aria-label': '값 읽기' });
      const at = (i, evt) => {
        vl.setAttribute('x1', X(i)); vl.setAttribute('x2', X(i)); vl.setAttribute('visibility', 'visible');
        const rows = [];
        series.forEach((sr, k) => {
          let j = i;
          if (isDate) while (j >= 0 && !ok(sr.values[j]) && i - j < 6) j--;
          const v = sr.values[j];
          if (ok(v)) { dots[k].setAttribute('cx', X(i)); dots[k].setAttribute('cy', Y(v)); dots[k].setAttribute('visibility', 'visible'); }
          else dots[k].setAttribute('visibility', 'hidden');
          rows.push({ name: sr.name, color: sr.color, value: ok(v) ? (o.tipFmt || yf)(v) + (o.unit || '') : '–' });
        });
        tip.show(evt, o.x[i], rows);
      };
      const off = () => { vl.setAttribute('visibility', 'hidden'); dots.forEach((dt) => dt.setAttribute('visibility', 'hidden')); tip.hide(); };
      let cur = n - 1;
      hit.addEventListener('pointermove', (e) => {
        const r = svg.getBoundingClientRect();
        cur = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - r.left - m.l) / pw) * (n - 1))));
        at(cur, e);
      });
      hit.addEventListener('pointerleave', off);
      hit.addEventListener('blur', off);
      hit.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        cur = Math.max(0, Math.min(n - 1, cur + (e.key === 'ArrowLeft' ? -1 : 1) * Math.max(1, Math.round(n / 60))));
        const r = svg.getBoundingClientRect();
        at(cur, { clientX: r.left + X(cur), clientY: r.top + m.t + 10 });
      });
      svg.appendChild(hit);
      el.appendChild(svg);
    }));
    return wrap;
  }

  /* 막대 차트. o: {cats:[이름], series:[{name,color,values}], h, yFmt, sign:true(부호로 색), labels, refs, unit, xEvery} */
  function bars(o) {
    const wrap = h('div');
    if (o.series.length > 1) wrap.appendChild(legend(o.series, true));
    const n = o.cats.length, k = o.series.length;
    wrap.appendChild(chartBox(o.h || 200, (el, W, H) => {
      const m = { l: 44, r: 10, t: 14, b: 22 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
      let lo = 0, hi = 0;
      for (const sr of o.series) for (const v of sr.values) if (ok(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      for (const rf of o.refs || []) { lo = Math.min(lo, rf.y); hi = Math.max(hi, rf.y); }
      const padY = (hi - lo || 1) * 0.1;
      if (hi > 0) hi += padY; if (lo < 0) lo -= padY;
      const { ticks, step } = niceTicks(lo, hi, Math.max(2, Math.round(ph / 46)));
      const yf = o.yFmt || tickFmt(step);
      const band = pw / n, gap = 2, bw = Math.max(2, Math.min(24, (band * 0.72 - gap * (k - 1)) / k));
      const Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * ph, y0 = Y(0);
      const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || '막대 차트' });
      for (const t of ticks) {
        svg.appendChild(s('line', { cls: 'gl', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
        svg.appendChild(s('text', { x: m.l - 7, y: Y(t) + 3.5, 'text-anchor': 'end' }, yf(t)));
      }
      for (const rf of o.refs || []) {
        svg.appendChild(s('line', { cls: 'ref', x1: m.l, x2: W - m.r, y1: Y(rf.y), y2: Y(rf.y) }));
        if (rf.label) svg.appendChild(s('text', { cls: 'lab', x: W - m.r, y: Y(rf.y) - 4, 'text-anchor': 'end' }, rf.label));
      }
      const every = o.xEvery || Math.ceil(n / Math.max(1, Math.floor(pw / 46)));
      for (let i = 0; i < n; i++) {
        const cx = m.l + band * (i + 0.5);
        if (i % every === 0) svg.appendChild(s('text', { x: cx, y: H - 6, 'text-anchor': 'middle' }, o.cats[i]));
        const g = s('g');
        o.series.forEach((sr, j) => {
          const v = sr.values[i];
          if (!ok(v)) return;
          const x = cx - (k * bw + (k - 1) * gap) / 2 + j * (bw + gap), y = Y(v), hh = Math.abs(y - y0), rr = Math.min(4, bw / 2, hh);
          const fill = o.sign ? (v >= 0 ? 'var(--up)' : 'var(--down)') : sr.color;
          const dd = v >= 0
            ? `M${x} ${y0}V${y + rr}Q${x} ${y} ${x + rr} ${y}H${x + bw - rr}Q${x + bw} ${y} ${x + bw} ${y + rr}V${y0}Z`
            : `M${x} ${y0}V${y - rr}Q${x} ${y} ${x + rr} ${y}H${x + bw - rr}Q${x + bw} ${y} ${x + bw} ${y - rr}V${y0}Z`;
          g.appendChild(s('path', { d: dd, fill }));
          if (o.labels && n * k <= 16) g.appendChild(s('text', { cls: 'lab', x: x + bw / 2, y: v >= 0 ? y - 4 : y + 12, 'text-anchor': 'middle' }, (o.labFmt || yf)(v)));
        });
        const hitR = s('rect', { x: m.l + band * i, y: m.t, width: band, height: ph, fill: 'transparent', tabindex: 0 });
        const show = (e) => { g.setAttribute('opacity', '.72'); tip.show(e, o.cats[i], o.series.map((sr) => ({ name: sr.name, color: o.sign ? null : sr.color, value: ok(sr.values[i]) ? (o.tipFmt || yf)(sr.values[i]) + (o.unit || '') : '–' }))); };
        const hide = () => { g.removeAttribute('opacity'); tip.hide(); };
        hitR.addEventListener('pointermove', show);
        hitR.addEventListener('pointerleave', hide);
        hitR.addEventListener('focus', () => { const r = hitR.getBoundingClientRect(); show({ clientX: r.left + r.width / 2, clientY: r.top + 10 }); });
        hitR.addEventListener('blur', hide);
        svg.appendChild(g);
        svg.appendChild(hitR);
      }
      svg.appendChild(s('line', { cls: 'ax', x1: m.l, x2: W - m.r, y1: y0, y2: y0 }));
      el.appendChild(svg);
    }));
    return wrap;
  }

  /* 산점도 + 선. o: {points:[{x,y,color,r,tipTitle,tipRows,data}], curve:[[x,y]], h, xFmt, yFmt, xLabel, onClick(point)} */
  function scatter(o) {
    return chartBox(o.h || 260, (el, W, H) => {
      const m = { l: 44, r: 14, t: 10, b: 30 }, pw = W - m.l - m.r, ph = H - m.t - m.b;
      const xs = o.points.map((p) => p.x), ys = o.points.map((p) => p.y).concat((o.curve || []).map((c) => c[1]));
      if (!xs.length) { el.appendChild(empty('그릴 종목이 없습니다', '만기 필터를 바꿔 보세요.')); return; }
      let x0 = o.xMin != null ? o.xMin : Math.min(...xs), x1 = o.xMax != null ? o.xMax : Math.max(...xs);
      let lo = Math.min(...ys), hi = Math.max(...ys);
      const padY = (hi - lo || 1) * 0.08;
      lo -= padY; hi += padY;
      if (x1 <= x0) x1 = x0 + 1;
      const X = (v) => m.l + ((v - x0) / (x1 - x0)) * pw, Y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * ph;
      const svg = s('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || '산점도' });
      const yt = niceTicks(lo, hi, 4), yf = o.yFmt || tickFmt(yt.step);
      for (const t of yt.ticks) {
        svg.appendChild(s('line', { cls: 'gl', x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
        svg.appendChild(s('text', { x: m.l - 7, y: Y(t) + 3.5, 'text-anchor': 'end' }, yf(t)));
      }
      const xt = niceTicks(x0, x1, Math.max(3, Math.round(pw / 90)));
      for (const t of xt.ticks) svg.appendChild(s('text', { x: X(t), y: H - 14, 'text-anchor': 'middle' }, (o.xFmt || tickFmt(xt.step))(t)));
      if (o.xLabel) svg.appendChild(s('text', { x: W - m.r, y: H - 1, 'text-anchor': 'end' }, o.xLabel));
      if (o.curve && o.curve.length) {
        const cv = o.curve.filter((c) => c[0] >= x0 && c[0] <= x1);
        svg.appendChild(s('path', { d: cv.map((c, i) => (i ? 'L' : 'M') + X(c[0]).toFixed(1) + ' ' + Y(c[1]).toFixed(1)).join(''), fill: 'none', stroke: 'var(--ink2)', 'stroke-width': 1.5 }));
      }
      const marks = o.points.map((p) => {
        const c = s('circle', { cx: X(p.x), cy: Y(p.y), r: p.r || 3, fill: p.color || 'var(--s1)', 'fill-opacity': p.op || 0.75, stroke: p.ring ? 'var(--surface)' : null, 'stroke-width': p.ring ? 2 : null });
        svg.appendChild(c);
        return c;
      });
      let cur = -1;
      const hit = s('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent', style: o.onClick ? 'cursor:pointer' : null });
      const nearest = (e) => {
        const r = svg.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
        let best = -1, bd = 26 * 26;
        o.points.forEach((p, i) => { const dx = X(p.x) - px, dy = Y(p.y) - py, d2 = dx * dx + dy * dy; if (d2 < bd) { bd = d2; best = i; } });
        return best;
      };
      hit.addEventListener('pointermove', (e) => {
        const i = nearest(e);
        if (cur >= 0 && cur !== i) marks[cur].setAttribute('r', o.points[cur].r || 3);
        cur = i;
        if (i < 0) { tip.hide(); return; }
        marks[i].setAttribute('r', (o.points[i].r || 3) + 2.5);
        tip.show(e, o.points[i].tipTitle, o.points[i].tipRows);
      });
      hit.addEventListener('pointerleave', () => { if (cur >= 0) marks[cur].setAttribute('r', o.points[cur].r || 3); cur = -1; tip.hide(); });
      if (o.onClick) hit.addEventListener('click', (e) => { const i = nearest(e); if (i >= 0) o.onClick(o.points[i]); });
      svg.appendChild(hit);
      el.appendChild(svg);
    });
  }

  /* 시계열을 표로: 달마다 마지막 값 (최근 maxRows개). cols: [{name, values, fmt}] */
  function seriesTable(dates, cols, maxRows) {
    const rows = [];
    for (let i = dates.length - 1; i >= 0 && rows.length < (maxRows || 36); i--) {
      if (i === dates.length - 1 || dates[i].slice(0, 7) !== dates[i + 1].slice(0, 7)) rows.push(i);
    }
    return table([{ label: '날짜', align: 'l', get: (i) => dates[i] }].concat(cols.map((c) => ({
      label: c.name, get: (i) => { let j = i; while (j > 0 && !ok(c.values[j]) && i - j < 6) j--; return c.values[j]; }, fmt: (v) => (c.fmt || ((x) => F.n(x, 2)))(v) }))),
      { rows, dense: true });
  }

  window.UI = { h, s, F, ok, dirCls, heat, heatPct, tip, table, card, empty, tile, spark, range, legend, scaleKey, line, bars, scatter,
                seriesTable, cut, chartBox };
})();
