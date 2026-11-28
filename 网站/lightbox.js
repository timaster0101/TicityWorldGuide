/* 图集放大查看：点击缩略图开大图，← →（或手机左右滑）翻页，Esc 关闭，滚轮/双击缩放，拖动平移。 */
(function () {
  'use strict';

  var TILE_SEL = 'button.tile[data-full]';
  var tiles = Array.prototype.slice.call(document.querySelectorAll(TILE_SEL));
  var box = document.getElementById('lb');
  if (!tiles.length || !box) return;

  var img = box.querySelector('.lb__img');
  var nameEl = box.querySelector('.lb__name');
  var idEl = box.querySelector('.lb__id');
  var countEl = box.querySelector('.lb__count');
  var orig = box.querySelector('.lb__orig');
  var fig = box.querySelector('.lb__fig');

  var index = 0;
  var scale = 1;
  var tx = 0;
  var ty = 0;
  var lastFocus = null;

  function clampScale(v) {
    return Math.min(6, Math.max(1, v));
  }

  function applyTransform() {
    img.style.transform = 'translate3d(' + tx + 'px,' + ty + 'px,0) scale(' + scale + ')';
  }

  function resetZoom() {
    scale = 1;
    tx = 0;
    ty = 0;
    applyTransform();
    fig.classList.toggle('is-zoomed', false);
  }

  function show(i) {
    index = (i + tiles.length) % tiles.length;
    var tile = tiles[index];
    var full = tile.getAttribute('data-full') || '';
    var name = tile.getAttribute('data-cap') || '';
    var id = tile.getAttribute('data-id') || '';
    img.src = full;
    img.alt = name;
    nameEl.textContent = name;
    idEl.textContent = id;
    countEl.textContent = (index + 1) + ' / ' + tiles.length;
    orig.href = full;
    resetZoom();
    // 预取相邻两张，翻页不空窗
    [index + 1, index - 1].forEach(function (n) {
      var t = tiles[(n + tiles.length) % tiles.length];
      var pre = new Image();
      pre.src = t.getAttribute('data-full');
    });
  }

  function open(i) {
    lastFocus = document.activeElement;
    box.hidden = false;
    document.body.classList.add('is-locked');
    show(i);
    box.querySelector('[data-lb="close"]').focus();
  }

  function close() {
    box.hidden = true;
    document.body.classList.remove('is-locked');
    img.removeAttribute('src');
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function openByTile(tile) {
    open(tiles.indexOf(tile));
  }

  tiles.forEach(function (tile) {
    tile.addEventListener('click', function () {
      openByTile(tile);
    });
  });

  box.addEventListener('click', function (e) {
    var act = e.target.getAttribute && e.target.getAttribute('data-lb');
    if (act === 'prev') show(index - 1);
    else if (act === 'next') show(index + 1);
    else if (act === 'close') close();
    else if (e.target === box || e.target === fig) close();
  });

  document.addEventListener('keydown', function (e) {
    if (box.hidden) return;
    if (e.key === 'Escape') {
      close();
    } else if (e.key === 'ArrowLeft') {
      show(index - 1);
    } else if (e.key === 'ArrowRight') {
      show(index + 1);
    } else if (e.key === '0') {
      resetZoom();
    } else {
      return;
    }
    e.preventDefault();
  });

  // 滚轮缩放：以指针位置为中心
  box.addEventListener(
    'wheel',
    function (e) {
      if (box.hidden) return;
      e.preventDefault();
      var before = scale;
      var next = clampScale(scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12));
      if (next === before) return;
      var rect = img.getBoundingClientRect();
      var cx = e.clientX - (rect.left + rect.width / 2);
      var cy = e.clientY - (rect.top + rect.height / 2);
      var k = next / before;
      tx = cx - (cx - tx) * k;
      ty = cy - (cy - ty) * k;
      scale = next;
      if (scale === 1) {
        tx = 0;
        ty = 0;
      }
      fig.classList.toggle('is-zoomed', scale > 1);
      applyTransform();
    },
    { passive: false }
  );

  // 双击缩放
  img.addEventListener('dblclick', function () {
    if (scale > 1) {
      resetZoom();
    } else {
      scale = 2.2;
      fig.classList.add('is-zoomed');
      applyTransform();
    }
  });

  // 拖动平移（放大后）
  var dragging = false;
  var startX = 0;
  var startY = 0;
  var baseX = 0;
  var baseY = 0;

  img.addEventListener('pointerdown', function (e) {
    if (scale <= 1) return;
    dragging = true;
    startX = e.clientX;
    startY = e.clientY;
    baseX = tx;
    baseY = ty;
    img.setPointerCapture(e.pointerId);
    fig.classList.add('is-dragging');
  });

  img.addEventListener('pointermove', function (e) {
    if (!dragging) return;
    tx = baseX + (e.clientX - startX);
    ty = baseY + (e.clientY - startY);
    applyTransform();
  });

  function endDrag(e) {
    if (!dragging) return;
    dragging = false;
    fig.classList.remove('is-dragging');
    if (e && e.pointerId != null && img.hasPointerCapture(e.pointerId)) {
      img.releasePointerCapture(e.pointerId);
    }
  }

  img.addEventListener('pointerup', endDrag);
  img.addEventListener('pointercancel', endDrag);

  // 手机左右滑翻页（未放大时）
  var touchX = null;
  var touchY = null;

  box.addEventListener(
    'touchstart',
    function (e) {
      if (scale > 1) return;
      touchX = e.touches[0].clientX;
      touchY = e.touches[0].clientY;
    },
    { passive: true }
  );

  box.addEventListener(
    'touchend',
    function (e) {
      if (touchX === null) return;
      var dx = e.changedTouches[0].clientX - touchX;
      var dy = e.changedTouches[0].clientY - touchY;
      touchX = null;
      touchY = null;
      if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy)) return;
      show(dx > 0 ? index - 1 : index + 1);
    },
    { passive: true }
  );
})();
