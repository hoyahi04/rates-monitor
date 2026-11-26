/* 화면이 열리거나 탭을 바꿀 때 한 번 도는 짧은 애니메이션.
   기기에서 "동작 줄이기"를 켜 두면 아무것도 하지 않는다. */
window.__anim = function (root) {
  if (!root || root.hidden || root.classList.contains('anim')) return;
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  root.querySelectorAll('.chart polyline').forEach(p => p.setAttribute('pathLength', '1'));
  root.classList.add('anim');
  setTimeout(() => root.classList.remove('anim'), 1500);
  // 큰 숫자를 0에서 올리기
  root.querySelectorAll('.num, .hl .big').forEach(el => {
    const node = [...el.childNodes].find(n => n.nodeType === 3 && /\d/.test(n.nodeValue));
    if (!node || node.nodeValue.includes('/')) return;
    const full = node.nodeValue, m = full.match(/^(\D*?)([+−]?)(\d[\d,]*)(?:\.(\d+))?([\s\S]*)$/);
    if (!m) return;
    const [, pre, sign, int, dec = '', post] = m, target = parseFloat(int.replace(/,/g, '') + (dec ? '.' + dec : ''));
    const comma = int.includes(','), dur = 700; let t0 = null;
    const step = function (t) {
      if (t0 === null) t0 = t; const k = Math.max(0, Math.min(1, (t - t0) / dur)), e = 1 - Math.pow(1 - k, 3), v = target * e;
      let s = v.toFixed(dec.length); if (comma) s = Number(s).toLocaleString('en-US', { minimumFractionDigits: dec.length });
      node.nodeValue = k < 1 ? pre + sign + s + post : full;
      if (k < 1) requestAnimationFrame(step);
    }; node.nodeValue = pre + sign + (0).toFixed(dec.length) + post; requestAnimationFrame(step);
    setTimeout(() => { node.nodeValue = full; }, dur + 400);
  });
};
