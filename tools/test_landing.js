/* Runs the hero drawing against a recording stub of CanvasRenderingContext2D, so
   the geometry is checked by counting what it actually painted rather than by
   trusting the maths. */
const fs = require('fs');
const calls = { arc: [], stroke: 0, fills: {}, strokes: {}, drawImage: 0, moveTo: 0,
                inkPaths: [], inkWidths: [] };
let fill = '', stroke = '', lw = 1, path = [];

function mkCtx() {
  return {
    set fillStyle(v){ fill = v; }, get fillStyle(){ return fill; },
    set strokeStyle(v){ stroke = v; }, get strokeStyle(){ return stroke; },
    set lineWidth(v){ lw = v; }, get lineWidth(){ return lw; },
    lineCap: '', lineJoin: '', globalAlpha: 1,
    setTransform(){}, clearRect(){}, beginPath(){ path = []; }, closePath(){},
    arc(x, y, r){ calls.arc.push({ x, y, r, fill }); },
    fill(){ calls.fills[fill] = (calls.fills[fill] || 0) + 1; },
    moveTo(x, y){ calls.moveTo++; path.push([x, y]); },
    lineTo(x, y){ path.push([x, y]); },
    stroke(){
      calls.stroke++;
      calls.strokes[stroke] = (calls.strokes[stroke] || 0) + 1;
      /* Ink is set as a hex literal, flag edges as rgba(): that is the
         discriminator between a pole and a flag edge. */
      if (/^#/.test(String(stroke)) && path.length > 2) {
        calls.inkPaths.push(path.slice());
        calls.inkWidths.push(lw);
      }
      path = [];
    },
    drawImage(){ calls.drawImage++; },
  };
}
const canvasEl = (w, h) => ({ width: w, height: h, clientWidth: w, clientHeight: h,
  getContext: () => mkCtx(), addEventListener(){} });

const hero = canvasEl(1024, 300);
global.document = {
  getElementById: (id) => id === 'hoist' ? hero : ({ value:'', textContent:'', hidden:false,
    style:{}, addEventListener(){}, classList:{toggle(){}} }),
  createElement: () => canvasEl(1024, 300),
  querySelectorAll: () => [], addEventListener(){}, body:{}, documentElement:{}, hidden:false,
};
global.window = { innerWidth:1280, innerHeight:800, addEventListener(){}, matchMedia: () => ({ matches:false, addEventListener(){} }),
  devicePixelRatio: 1, location:{ href:'' } };
global.matchMedia = window.matchMedia;
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
global.fetch = async () => ({ ok:false, status:0, json:async()=>({}), text:async()=>'' });
let frames = 0;
global.requestAnimationFrame = (f) => { if (frames++ < 3) f(frames * 40); return frames; };
global.cancelAnimationFrame = () => {};
global.clearTimeout = () => {}; global.setTimeout = () => 0;
process.on('unhandledRejection', () => {});

const html = fs.readFileSync(__dirname + '/../web/landing.html', 'utf8');
const m = /<script>\s*\n/.exec(html);
new Function(html.slice(m.index + m[0].length, html.indexOf('</script', m.index)))();

let fails = 0;
const t = (name, cond, extra) => { if (!cond) { fails++; console.log('FAIL  ' + name + (extra ? '  ' + extra : '')); } else console.log('PASS  ' + name); };

const red = calls.arc.filter(a => /212,0,0/.test(a.fill));
const grey = calls.arc.filter(a => /210,212,213/.test(a.fill));
const dark = calls.arc.filter(a => /^rgba\(10,10,10/.test(a.fill));


t('mast prerendered and composited', calls.drawImage > 0);
/* Lower bound only. The count has come down deliberately three times now, so this
   is here to catch the flags vanishing, not to police the density. */
t('red pennant nodes drawn', red.length > 25, red.length + ' nodes');
t('few nodes, not a solid block', red.length < 400, red.length + ' nodes');
t('nodes are large circles', red.every(function (a) { return a.r > 4; }),
  'radii ' + [...new Set(red.map(a => a.r))].join(','));
t('grey lattice drawn', grey.length + dark.length > 500, (grey.length + dark.length) + ' nodes');
/* The pole leans: it starts near 13.5% of the width and ends near 3%. The matrix
   must cover the whole page, so there are dots to the left of it at every height. */
t('matrix covers the page, including left of the pole',
  grey.concat(dark).filter(function (a) { return a.x < 0.03 * 1280; }).length > 20,
  grey.concat(dark).filter(function (a) { return a.x < 0.03 * 1280; }).length + ' dots in the left 3%');
/* Flags hang off the curved pole, so the lower one must start further left than
   the upper one. This is the detail the earlier drafts got wrong. */
(function () {
  var upper = red.filter(function (a) { return /,1\)$/.test(a.fill); });
  var lower = red.filter(function (a) { return !/,1\)$/.test(a.fill); });
  if (!upper.length || !lower.length) { t('two flags on the pole', false); return; }
  var uMin = Math.min.apply(null, upper.map(function (a) { return a.x; }));
  var lMin = Math.min.apply(null, lower.map(function (a) { return a.x; }));
  t('lower flag hoists further left, because the pole leans', lMin < uMin - 20,
    'upper starts ' + uMin.toFixed(0) + ', lower starts ' + lMin.toFixed(0));
  var uMax = Math.max.apply(null, upper.map(function (a) { return a.x; }));
  var lMax = Math.max.apply(null, lower.map(function (a) { return a.x; }));
  t('upper flag is the longer one', uMax > lMax + 100,
    'upper reaches ' + uMax.toFixed(0) + ', lower reaches ' + lMax.toFixed(0));
})();
/* Two bands rather than one block: there must be a clear horizontal gap between
   them. Derived from the drawing rather than from a hardcoded y, so it survives a
   change of proportions. */
(function () {
  var ys = red.map(function (a) { return a.y; }).sort(function (a, b) { return a - b; });
  var biggest = 0;
  for (var i = 1; i < ys.length; i++) biggest = Math.max(biggest, ys[i] - ys[i - 1]);
  t('two pennant bands, not one', biggest > 25, 'largest vertical gap ' + biggest.toFixed(0) + 'px');
})();
t('flag deflects (fly moves off the grid)',
  red.some(a => Math.abs(a.y % 12 - 6) > 1.5));
t('focus enlarges some dots', dark.some(a => a.r > 1.5), 'max r ' + Math.max(...dark.map(a => a.r)).toFixed(2));
t('two red alpha levels for the two flags',
  new Set(red.map(a => a.fill)).size === 2, [...new Set(red.map(a => a.fill))].join(' '));
/* Nodes and the edges between them, Neo4j-ish. The count is low now by design -
   COARSE=3 means far fewer links - so this checks there are some, not many. */
t('edges stroked between nodes', calls.stroke > 0 && calls.moveTo > 30,
  calls.moveTo + ' moveTo, ' + calls.stroke + ' stroke');
t('flags have no black border',
  Object.keys(calls.strokes).filter(function (k) { return /^rgba\(10,10,10/.test(k); }).length === 0,
  Object.keys(calls.strokes).join(' | '));

/* Swallowtail: the fly is notched, so the flag reaches further at its top and
   bottom edges than at mid height. */
(function () {
  var upper = red.filter(function (a) { return /,1\)$/.test(a.fill); });
  if (!upper.length) { t('swallowtail notch', false, 'no solid-red nodes found'); return; }
  var ys = upper.map(function (a) { return a.y; });
  var mid = (Math.min.apply(null, ys) + Math.max.apply(null, ys)) / 2;
  var atMid = upper.filter(function (a) { return Math.abs(a.y - mid) < 14; });
  var maxAll = Math.max.apply(null, upper.map(function (a) { return a.x; }));
  var maxMid = Math.max.apply(null, atMid.map(function (a) { return a.x; }));
  t('swallowtail notch cuts the fly back at mid height', maxMid < maxAll - 40,
    'mid reaches ' + maxMid.toFixed(0) + ', edges reach ' + maxAll.toFixed(0));
})();
/* Poles: more than one, they cross, and the primary is bold. */
(function () {
  var wide = calls.inkWidths.filter(function (w) { return w >= 10; });
  t('primary pole is bold', wide.length >= 1,
    'weights ' + calls.inkWidths.map(function (w) { return w.toFixed(1); }).join(','));

  /* Each pole is drawn in three passes with the same point count, so counting
     distinct lengths counts poles rather than brush strokes. */
  var byLen = {};
  calls.inkPaths.forEach(function (p) { if (p.length > 60) byLen[p.length] = p; });
  var main = Object.keys(byLen).map(function (k) { return byLen[k]; });
  t('more than one pole drawn', main.length >= 2,
    main.length + ' distinct poles, point counts ' + Object.keys(byLen).join(','));

  /* Two poles cross if one is left of the other at one height and right of it at
     another. Cheaper and more honest than a segment intersection test. */
  function xAt(p, y) {
    for (var i = 1; i < p.length; i++) {
      if ((p[i - 1][1] - y) * (p[i][1] - y) <= 0) return p[i][0];
    }
    return null;
  }
  if (main.length >= 2) {
    var a = main[0], b = main[main.length - 1], flips = 0, prev = null;
    for (var y = 100; y < 700; y += 20) {
      var xa = xAt(a, y), xb = xAt(b, y);
      if (xa === null || xb === null) continue;
      var sign = xa < xb ? -1 : 1;
      if (prev !== null && sign !== prev) flips++;
      prev = sign;
    }
    t('the poles cross', flips >= 1, flips + ' side changes down the page');
  }

  /* Detached: no flag node may come within GAP of any pole. */
  var minDist = Infinity;
  red.forEach(function (n) {
    calls.inkPaths.forEach(function (p) {
      p.forEach(function (q) {
        var d = Math.hypot(q[0] - n.x, q[1] - n.y);
        if (d < minDist) minDist = d;
      });
    });
  });
  t('flag nodes stand clear of the poles', minDist > 15,
    'closest node is ' + minDist.toFixed(1) + 'px from a stroke');
})();

t('frame ran more than once', frames > 1);

console.log(fails ? '\n' + fails + ' FAILURE(S)' : '\nall assertions passed');
process.exit(fails ? 1 : 0);
