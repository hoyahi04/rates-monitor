/* 점검용. 주소 끝에 ?selftest=1 을 붙이면 지금 화면의 차트에 마우스를 올려 보고, "표" 단추와 표의 첫 줄을 눌러 보고,
   필터를 한 바퀴 돌려 본 뒤 결과를 <html data-selftest="...">에 적는다. 평소에는 불러오지 않는다. */
(function () {
  'use strict';
  const log = [], errs = [];
  window.addEventListener('error', (e) => errs.push(e.message));
  const step = (name, fn) => { try { fn(); log.push(name); } catch (e) { errs.push(name + ': ' + (e && e.message)); } };
  const fire = (el, type, x, y) => el.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y }));
  function poke(tag) {
    document.querySelectorAll('#view .chart svg rect[fill="transparent"]').forEach((r, i) => step(`${tag} 차트 ${i}`, () => {
      const b = r.getBoundingClientRect();
      fire(r, 'pointermove', b.left + b.width * 0.6, b.top + b.height * 0.5);
      fire(r, 'pointerleave', 0, 0);
    }));
    document.querySelectorAll('#view .card > header .mini').forEach((b, i) => step(`${tag} 단추 ${i}`, () => { b.click(); b.click(); }));
    document.querySelectorAll('#view table.t').forEach((t, i) => step(`${tag} 표 ${i}`, () => {
      const th = t.querySelector('th.sortable');
      if (th) { th.click(); th.click(); }
      const tr = t.querySelector('tr.click');
      if (tr) tr.click();
      const dr = document.getElementById('drawer');
      if (dr.classList.contains('open')) {
        const rng = dr.querySelector('input[type="range"]');
        if (rng) { rng.value = -50; rng.dispatchEvent(new Event('input')); }
        dr.querySelectorAll('.chart svg rect[fill="transparent"]').forEach((r) => { const b = r.getBoundingClientRect(); fire(r, 'pointermove', b.left + 20, b.top + 20); });
        dr.querySelector('header .btn').click();
      }
    }));
    document.querySelectorAll('#view select, #view input[type="number"]').forEach((el, i) => step(`${tag} 입력 ${i}`, () => {
      if (el.tagName === 'SELECT') { const keep = el.value; for (const o of el.options) { el.value = o.value; el.dispatchEvent(new Event('change')); } el.value = keep; el.dispatchEvent(new Event('change')); }
      else { el.value = 2500; el.dispatchEvent(new Event('input')); }
    }));
  }
  function setTop(label, value) {
    const el = document.querySelector(`.top select[aria-label="${label}"]`);
    el.value = value;
    el.dispatchEvent(new Event('change'));
  }
  setTimeout(() => {
    poke('기본');
    for (const [lab, vals] of [['만기', ['short', 'mid', 'long', 'all']], ['자산군', ['govt', 'credit', 'all']], ['지역', ['KR', 'US']]]) {
      for (const v of vals) step(`필터 ${lab}=${v}`, () => { setTop(lab, v); if (document.querySelector('#view .empty b') && /그리지 못했습니다/.test(document.querySelector('#view .empty b').textContent)) throw new Error('화면 오류'); });
    }
    document.querySelectorAll('.seg button[data-v]').forEach((b) => step('기간 ' + b.dataset.v, () => b.click()));
    step('기간 되돌리기', () => document.querySelector('.seg button[data-v="1Y"]').click());
    setTimeout(() => {
      poke('필터 뒤');
      step('뉴스', () => { window.DeskApp.ctx.openNews(); document.querySelectorAll('#drawer .seg button').forEach((b) => b.click()); document.querySelector('#drawer header .btn').click(); });
      document.documentElement.dataset.selftest = `steps=${log.length} errors=${errs.length}` + (errs.length ? ' :: ' + errs.slice(0, 6).join(' | ') : '');
    }, 400);
  }, 600);
})();
