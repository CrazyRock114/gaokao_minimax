/* 高考数学真题题库 — front-end
   Data layout:  data/manifest.json  (facets + taxonomy)
                 data/index.json     (light record per problem)
                 data/p/<year>.json  (full records, lazy-loaded per year)  */
(function () {
  'use strict';

  var M = null, IDX = [], SHARDS = {}, CART = [];
  var PAGE = 1, PER = 20, VIEW = 'browse';
  var F = { y0: null, y1: null, decade: null, region: null, track: null,
            type: null, diff: null, chapter: null, point: null, fig: false, sol: false };

  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); };

  /* ---------------------------------------------------------- bootstrap */
  function boot() {
    Promise.all([
      fetch('data/manifest.json').then(function (r) { return r.json(); }),
      fetch('data/index.json').then(function (r) { return r.json(); })
    ]).then(function (res) {
      M = res[0]; IDX = res[1];
      $('#brandsub').textContent =
        M.years[0] + '–' + M.years[M.years.length - 1] + ' · ' + M.total.toLocaleString() + ' 题';
      loadCart();
      buildFacets();
      bindUI();
      render();
      renderPaper();
    }).catch(function (e) {
      console.error('[gk] boot failed', e);
      document.body.insertAdjacentHTML('afterbegin',
        '<div class="note" style="margin:14px">数据加载失败：' + esc(e.message) +
        '<br>请通过 HTTP 方式打开（不要直接双击 index.html）。</div>');
    });
  }

  // Exports used to read findRec() synchronously; if a year shard had not
  // finished loading the record was null and the export silently shipped
  // empty content with answer_status "ok". Always await this first.
  function ensureShards(ids) {
    var years = {};
    ids.forEach(function (id) { years[id.split('|')[0]] = 1; });
    var keys = Object.keys(years);
    if (!keys.length) return Promise.resolve();
    return Promise.all(keys.map(shard));
  }

  function shard(year) {
    if (SHARDS[year]) return Promise.resolve(SHARDS[year]);
    return fetch(M.shards[year]).then(function (r) { return r.json(); })
      .then(function (a) { SHARDS[year] = a; return a; });
  }

  /* ------------------------------------------------------------ filters */
  function matches(r) {
    if (F.y0 != null && r.y < F.y0) return false;
    if (F.y1 != null && r.y > F.y1) return false;
    if (F.decade != null && Math.floor(r.y / 10) * 10 !== Number(F.decade)) return false;
    if (F.region && r.r !== F.region) return false;
    if (F.track && r.t !== F.track) return false;
    // facet values are the Chinese labels (manifest keys off section_type_cn)
    if (F.type && r.tyc !== F.type) return false;
    if (F.diff && r.d !== F.diff) return false;
    if (F.chapter && !(r.k || []).some(function (c) { return ptChap[c] === F.chapter; })) return false;
    if (F.point && (r.k || []).indexOf(F.point) < 0) return false;
    if (F.fig && !r.f) return false;
    if (F.sol && !r.s) return false;
    if (Q) {
      // r.pl is the full stem+options+solution projection; r.tx is only the
      // 110-char preview used for display
      var hay = (r.p + ' ' + r.r + ' ' + r.t + ' ' + r.tyc + ' ' +
                 (r.kn || []).join(' ') + ' ' + (r.pl || r.tx || '')).toLowerCase();
      if (hay.indexOf(Q) < 0) return false;
    }
    return true;
  }

  var Q = '';
  var ptChap = {};      // point code -> chapter code
  var ptName = {};      // point code -> name
  var chapName = {};    // chapter code -> cn name

  function results() {
    var out = [];
    for (var i = 0; i < IDX.length; i++) if (matches(IDX[i])) out.push(IDX[i]);
    return out;
  }

  /* ------------------------------------------------------------- facets */
  function fillFacet(el, items, key, label) {
    el.innerHTML = items.map(function (it) {
      return '<li data-k="' + esc(it.v) + '" data-key="' + key + '">' +
             '<span>' + esc(it.n) + '</span><span class="c">' + it.c.toLocaleString() + '</span></li>';
    }).join('');
  }

  function buildFacets() {
    (M.chapters || []).forEach(function (c) {
      chapName[c.chapter] = c.chapter_cn;
      (c.points || []).forEach(function (p) {
        // the point object carries code/name/count; the chapter comes from
        // the enclosing block, so read it from there rather than p.chapter
        ptChap[p.code] = c.chapter;
        ptName[p.code] = p.name;
      });
    });

    var f = M.facets;
    // decades
    var dec = {};
    IDX.forEach(function (r) { var d = Math.floor(r.y / 10) * 10; dec[d] = (dec[d] || 0) + 1; });
    fillFacet($('#f-decade'), Object.keys(dec).sort().map(function (d) {
      return { v: d, n: d + 's', c: dec[d] };
    }), 'decade');

    ['region', 'track', 'type', 'diff', 'chapter', 'point'].forEach(function (k) {
      var el = $('#f-' + k); if (!el) return;
      var items = Object.keys(f[k]).map(function (kk) {
        return { v: (k === 'diff') ? Number(kk) : kk, n: nameOf(k, kk), c: f[k][kk] };
      });
      items.sort(function (a, b) {
        if (k === 'diff') return a.v - b.v;
        if (k === 'point' || k === 'chapter') return b.c - a.c;
        return b.c - a.c;
      });
      // every region must be reachable: 17 of 33 were silently hidden,
      // making thousands of questions unfilterable by province
      fillFacet(el, items, k);
      if (k === 'region' && items.length > 16) {
        Array.prototype.forEach.call(el.children, function (li, i) {
          if (i >= 16) li.hidden = true;
        });
        el.insertAdjacentHTML('beforeend',
          '<li class="more" data-more="1" data-expanded="0">展开其余 ' +
          (items.length - 16) + ' 个地区 ▾</li>');
      }
    });
    $('#c-fig').textContent = IDX.filter(function (r) { return r.f; }).length.toLocaleString();
    $('#c-sol').textContent = IDX.filter(function (r) { return r.s; }).length.toLocaleString();
  }

  function nameOf(k, v) {
    if (k === 'diff') return ['', '易', '较易', '中等', '较难', '难'][Number(v)] || v;
    if (k === 'chapter') return chapName[v] || v;
    if (k === 'point') return ptName[v] || v;
    if (k === 'type') return v;
    return v;
  }

  /* -------------------------------------------------------------- render */
  function render() {
    var res = results();
    $('#nres').textContent = res.length.toLocaleString();
    var pages = Math.max(1, Math.ceil(res.length / PER));
    if (PAGE > pages) PAGE = pages;
    var slice = res.slice((PAGE - 1) * PER, PAGE * PER);

    $('#cards').innerHTML = slice.length ? slice.map(cardHTML).join('')
      : '<div class="empty"><b>没有匹配的题目</b>试试放宽年份或清除部分筛选条件</div>';
    renderPager(pages);
    renderSelInfo();
  }

  var GAP_LABEL = {
    answer_conflicted: '原卷题面缺陷',
    options_missing: '原卷缺选项',
    answer_missing: '无答案',
    answer_derived: '答案取自解析'
  };

  function cardHTML(r) {
    var pk = (r.k || [])[0];
    var kpills = (r.kn || []).slice(0, 3).map(function (n, i) {
      var code = (r.k || [])[i];
      return '<span class="pill k" data-kp="' + esc(code) + '">' + esc(n) + '</span>';
    }).join('');
    var inCart = CART.indexOf(r.id) >= 0;
    var gap = (r.dg || []).map(function (g) {
      return '<span class="pill gap" title="数据质量标记">' + esc(GAP_LABEL[g] || g) + '</span>';
    }).join('');
    return '<article class="card' + (inCart ? ' sel' : '') + '" data-id="' + esc(r.id) + '">' +
      '<div class="meta">' +
        '<span class="y">' + r.y + '</span>' +
        '<span>' + esc(r.r) + '</span>' +
        '<span class="pill ' + (r.t === '理科' ? 'sc' : r.t === '文科' ? 'li' : 'hi') + '">' + esc(r.t) + '</span>' +
        '<span class="pill q">' + esc(r.tyc) + '</span>' +
        '<span class="pill d' + r.d + '">' + ['', '易', '较易', '中等', '较难', '难'][r.d] + '</span>' +
        (r.f ? '<span class="pill fb">图</span>' : '') +
        (r.s ? '' : '<span class="pill">无解析</span>') +
        gap +
        kpills +
      '</div>' +
      '<div class="stem clamp">' + esc(r.tx) + '</div>' +
      '<div class="acts">' +
        '<button class="btn mini" data-act="open">展开 / 收起</button>' +
        '<button class="btn mini' + (inCart ? ' on' : '') + '" data-act="cart">' +
          (inCart ? '已在试卷中 ✓' : '加入试卷') + '</button>' +
        '<button class="btn mini" data-act="json">导出本题</button>' +
        '<span class="hint">' + esc(r.p) + ' · ' + esc(r.sec || '') +
          ' 第' + r.n + '题</span>' +
      '</div>' +
      '<div class="full" hidden></div>' +
    '</article>';
  }

  function renderPager(pages) {
    if (pages <= 1) { $('#pager').innerHTML = ''; return; }
    var h = '<button data-p="1"' + (PAGE === 1 ? ' class="on"' : '') + '>首页</button>';
    h += '<button data-p="' + (PAGE - 1) + '"' + (PAGE === 1 ? ' disabled' : '') + '>上一页</button>';
    var s = Math.max(1, PAGE - 3), e = Math.min(pages, PAGE + 3);
    for (var i = s; i <= e; i++)
      h += '<button data-p="' + i + '"' + (i === PAGE ? ' class="on"' : '') + '>' + i + '</button>';
    h += '<button data-p="' + (PAGE + 1) + '"' + (PAGE === pages ? ' disabled' : '') + '>下一页</button>';
    h += '<button data-p="' + pages + '"' + (PAGE === pages ? ' class="on"' : '') + '>末页</button>';
    h += '<span style="margin-left:8px;font-size:12px;color:var(--ink-3)">' +
         PAGE + ' / ' + pages + ' 页 · 每页 ' + PER + ' 题</span>';
    $('#pager').innerHTML = h;
  }

  function renderSelInfo() {
    var t = [];
    function add(k, label) { t.push('<span class="tag" data-clear="' + k + '">' + esc(label) + ' ×</span>'); }
    if (F.y0 != null || F.y1 != null) add('yr', (F.y0 || 1952) + '–' + (F.y1 || 2026));
    if (F.decade != null) add('decade', F.decade + 's');
    if (F.region) add('region', F.region);
    if (F.track) add('track', F.track);
    if (F.type) add('type', F.type);
    if (F.diff) add('diff', ['', '易', '较易', '中等', '较难', '难'][F.diff]);
    if (F.chapter) add('chapter', chapName[F.chapter]);
    if (F.point) add('point', ptName[F.point]);
    if (F.fig) add('fig', '含题图');
    if (F.sol) add('sol', '含解析');
    if (Q) add('q', '搜索：' + Q);
    $('#selinfo').innerHTML = t.join('');
  }

  /* ------------------------------------------------------------- detail */
  function openCard(card) {
    var box = card.querySelector('.full');
    if (!box.hidden) { box.hidden = true; return; }
    var id = card.dataset.id, year = +id.split('|')[0];
    box.hidden = false;
    if (box.dataset.loaded === '1') { return; }
    box.innerHTML = '<div class="loading">载入中…</div>';
    shard(year).then(function (arr) {
      var rec = null;
      for (var i = 0; i < arr.length; i++) if (arr[i].id === id) { rec = arr[i]; break; }
      if (!rec) { box.innerHTML = '<div class="hint">未找到该题记录</div>'; return; }
      box.dataset.loaded = '1';
      var h = '';
      if ((rec.dg || []).length) {
        h += '<div class="gapbox">' + (rec.dg || []).map(function (g) {
          var t = {
            answer_conflicted: '原卷题面本身存在问题（整理者已标注，答案并非本系统臆造）',
            options_missing: '原卷未收录该题选项',
            answer_missing: '该题无答案',
            answer_derived: '原卷答案为空，答案取自解析原文'
          }[g] || g;
          return '<div>· ' + esc(t) + '</div>';
        }).join('') + (rec.anote ? '<div class="hint">' + esc(rec.anote) + '</div>' : '') + '</div>';
      }
      h += '<div class="stem">' + (rec.ph || '') + '</div>';
      if (rec.ch && rec.ch.length) {
        h += '<div class="opts">' + rec.ch.map(function (c, i) {
          return '<div class="opt"><b>' + 'ABCDEF'.charAt(i) + '.</b>' + c + '</div>';
        }).join('') + '</div>';
      } else if (rec.ty && /^choice/.test(rec.ty)) {
        h += '<div class="hint">（原卷未收录选项）</div>';
      }
      if (rec.ah) h += '<div class="lbl">答案</div><div class="ansbox">' + rec.ah + '</div>';
      else if (/^choice/.test(rec.ty)) h += '<div class="lbl">答案</div><div class="ansbox none">（原卷未给出答案）</div>';
      if (rec.sh) h += '<div class="lbl">解析</div><div class="solbox">' + rec.sh + '</div>';
      else h += '<div class="lbl">解析</div><div class="hint">该题暂无解析文本</div>';
      box.innerHTML = h;
      if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([box]);
    }).catch(function () { box.innerHTML = '<div class="hint">载入失败</div>'; });
  }

  /* --------------------------------------------------------------- cart */
  function loadCart() {
    try { CART = JSON.parse(localStorage.getItem('gk_cart') || '[]'); }
    catch (e) { CART = []; }
    if (!Array.isArray(CART)) CART = [];
    // sync the badge immediately; otherwise it reads 0 on reload even though
    // the stored paper is intact
    $('#cartn').textContent = CART.length;
  }
  function saveCart() {
    try { localStorage.setItem('gk_cart', JSON.stringify(CART)); } catch (e) {}
    $('#cartn').textContent = CART.length;
  }
  function toggleCart(id) {
    var i = CART.indexOf(id);
    if (i >= 0) CART.splice(i, 1); else CART.push(id);
    saveCart();
  }

  /* -------------------------------------------------------------- paper */
  var paperWithAns = true;
  function renderPaper() {
    var el = $('#paper');
    if (!CART.length) {
      el.innerHTML = '<h2>组卷</h2><div class="sub">试卷还是空的</div>' +
        '<div class="empty">在「题库」页筛选题目后，点击卡片上的「加入试卷」</div>';
      $('#pstat').textContent = '';
      return;
    }
    var byYear = {};
    CART.forEach(function (id) {
      var y = +id.split('|')[0];
      (byYear[y] = byYear[y] || []).push(id);
    });
    var years = Object.keys(byYear).map(Number).sort(function (a, b) { return a - b; });

    var h = '<h2>模拟试卷</h2><div class="sub">共 ' + CART.length +
            ' 题 · 涵盖 ' + years.length + ' 份试卷 · 来源 1952–2026 全国高考真题</div>';
    years.forEach(function (y) {
      h += '<div class="psect">' + y + ' 年（' + byYear[y].length + ' 题）</div>';
      byYear[y].forEach(function (id) {
        var li = findLight(id); if (!li) return;
        h += '<div class="pitem" data-id="' + esc(id) + '">' +
             '<div class="m">' + y + ' · ' + esc(li.r) + ' ' + esc(li.t) + ' · ' +
               esc(li.tyc) + ' · ' + ['', '易', '较易', '中等', '较难', '难'][li.d] +
               (li.k && li.k.length ? ' · ' + esc(ptName[li.k[0]] || '') : '') + '</div>' +
             '<div><span class="n">' + li.n + '.</span><span class="ph-slot" data-id="' + esc(id) + '">' +
               esc(li.tx) + '</span></div>' +
             '<div class="s" data-sol="' + esc(id) + '" style="display:none"></div>' +
             '<div class="pgap"></div>' +
             '<button class="btn mini" data-rm="' + esc(id) + '" style="margin-top:5px">移除</button>' +
           '</div>';
      });
    });
    el.innerHTML = h;
    hydratePaper();
    renderPaperStats();
  }

  function findLight(id) {
    for (var i = 0; i < IDX.length; i++) if (IDX[i].id === id) return IDX[i];
    return null;
  }

  function hydratePaper() {
    var years = {};
    CART.forEach(function (id) { years[+id.split('|')[0]] = 1; });
    var need = Object.keys(years);
    if (!need.length) return;
    Promise.all(need.map(shard)).then(function () {
      $$('#paper .pitem').forEach(function (it) {
        var id = it.dataset.id;
        var rec = findRec(id);
        if (!rec) return;
        var slot = it.querySelector('.ph-slot');
        var h = rec.ph || '';
        if (rec.ch && rec.ch.length) {
          h += '<div class="opts">' + rec.ch.map(function (c, i) {
            return '<div class="opt"><b>' + 'ABCDEF'.charAt(i) + '.</b>' + c + '</div>';
          }).join('') + '</div>';
        }
        slot.innerHTML = h;
        var sb = it.querySelector('.s');
        var gap = it.querySelector('.pgap');
        if (paperWithAns) {
          sb.style.display = 'block';
          sb.innerHTML = (rec.ah ? '<b>答案：</b>' + rec.ah : (rec.ty && /^choice/.test(rec.ty)
            ? '<b>答案：</b>（原卷未给出答案）' : '')) +
                         (rec.sh ? '<div style="margin-top:4px"><b>解析：</b>' + rec.sh + '</div>' : '');
        } else { sb.style.display = 'none'; sb.innerHTML = ''; }
        // carry the upstream data-gap caveat into the assembled paper
        if (gap) {
          var dgs = rec.dg || [];
          gap.innerHTML = dgs.length ? '<div class="gapbox" style="margin-top:6px">' +
            dgs.map(function (g) {
              var t = {
                answer_conflicted: '原卷题面本身存在问题（整理者已标注，答案并非本系统臆造）',
                options_missing: '原卷未收录该题选项',
                answer_missing: '该题无答案',
                answer_derived: '原卷答案为空，答案取自解析原文'
              }[g] || g;
              return '<div>· ' + esc(t) + '</div>';
            }).join('') + '</div>' : '';
        }
      });
      if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([$('#paper')]);
    });
  }

  function findRec(id) {
    var y = id.split('|')[0];
    var arr = SHARDS[y]; if (!arr) return null;
    for (var i = 0; i < arr.length; i++) if (arr[i].id === id) return arr[i];
    return null;
  }

  function renderPaperStats() {
    var cnt = {}, yrs = {};
    CART.forEach(function (id) {
      var li = findLight(id); if (!li) return;
      yrs[li.y] = 1;
      (li.k || []).slice(0, 2).forEach(function (c) { cnt[c] = (cnt[c] || 0) + 1; });
    });
    var top = Object.keys(cnt).sort(function (a, b) { return cnt[b] - cnt[a]; }).slice(0, 8);
    var st = ['题数 ' + CART.length, '年份跨度 ' + Object.keys(yrs).length];
    if (top.length) st.push('主要知识点：' + top.map(function (c) {
      return (ptName[c] || c) + '×' + cnt[c];
    }).join('、'));
    $('#pstat').innerHTML = st.map(function (x) { return esc(x); }).join('<br>');
  }

  /* ------------------------------------------------------------ exports */
  function exportJSON() {
    return ensureShards(CART).then(function () {
    var out = CART.map(function (id) {
      var r = findRec(id) || {}, li = findLight(id) || {};
      return {
        id: id, year: li.y, region: li.r, track: li.t, question_type: li.tyc,
        difficulty: li.d, difficulty_label: ['', '易', '较易', '中等', '较难', '难'][li.d],
        knowledge: r.k || [], source_paper: li.p, number: li.n,
        answer_status: r.as || 'ok', answer_note: r.anote || '',
        data_gaps: r.dg || [],
        problem_latex: r.pt || '', problem_html: r.ph || '',
        choices_html: r.ch || [], answer_latex: r.af || '', answer_html: r.ah || '',
        solution_latex: r.sf || '', solution_html: r.sh || '',
        figures: (r.fi || []).concat(r.fs || [])
      };
    });
    dl(new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' }), 'gaokao_paper.json');
    });
  }

  function exportTEX() {
    return ensureShards(CART).then(function () {
    var out = '\\documentclass[12pt]{article}\n\\usepackage{amsmath,amssymb,ctex}\n' +
      '\\begin{document}\n';
    CART.forEach(function (id) {
      var r = findRec(id) || {}, li = findLight(id) || {};
      out += '\\noindent ' + li.y + ' ' + (li.r || '') + (li.t || '') +
             ' \\quad 第' + (li.n || '') + '题\n\n';
      out += (r.pt || '') + '\n\n';
      if (r.ch && r.ch.length) {
        out += '\\begin{enumerate}\n' + r.ch.map(function (c) {
          return '  \\item ' + c.replace(/^\\\\\(|\\\\\)$/g, '$');
        }).join('\n') + '\n\\end{enumerate}\n\n';
      }
      if (paperWithAns) {
        var note = (r.dg || []).length
          ? '%% 本题数据说明：' + (r.dg || []).map(function (g) {
              return {
                answer_conflicted: '原卷题面本身存在问题，整理者已标注，未臆造答案',
                options_missing: '原卷未收录该题选项',
                answer_missing: '该题无答案',
                answer_derived: '原卷答案为空，答案取自解析原文'
              }[g] || g;
            }).join('；') + '\n'
          : '';
        out += note;
        out += '{\\bf 答案：}' + (r.af || '（原卷未给出答案）') + '\n\n';
        out += '{\\bf 解析：}' + (r.sf || '') + '\n\n';
      }
    });
    out += '\\end{document}\n';
    dl(new Blob([out], { type: 'text/plain' }), 'gaokao_paper.tex');
    });
  }

  function dl(blob, name) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
  }

  /* --------------------------------------------------------------- wire */
  function setView(v) {
    VIEW = v;
    ['browse', 'paper', 'stats'].forEach(function (x) {
      $('#view-' + x).style.display = (x === v) ? '' : 'none';
    });
    $$('.tabs button').forEach(function (b) {
      b.classList.toggle('on', b.dataset.view === v);
    });
    if (v === 'stats' && !$('#report').dataset.loaded) {
      $('#report').innerHTML = '<div class="loading">载入分析报告…</div>';
      fetch('report/index.html').then(function (r) { return r.text(); })
        .then(function (h) {
          var m = h.match(/<div class="rep">([\s\S]*)<\/div>\s*<\/div>\s*<\/body>/);
          $('#report').innerHTML = (m ? m[1] : h)
            .replace(/<script[\s\S]*?<\/script>/g, '')
            .replace(/<link[^>]*>/g, '');
          $('#report').dataset.loaded = '1';
          if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise([$('#report')]);
        })
        .catch(function () { $('#report').innerHTML = '<div class="note">报告载入失败</div>'; });
    }
    if (v === 'paper') renderPaper();
  }

  function bindUI() {
    $$('.tabs button').forEach(function (b) {
      b.addEventListener('click', function () { setView(b.dataset.view); });
    });
    $('#cartbtn').addEventListener('click', function () { setView('paper'); });

    var qt;
    $('#q').addEventListener('input', function (e) {
      clearTimeout(qt);
      var v = e.target.value.trim().toLowerCase();
      $('#searchWrap').classList.toggle('has', !!v);
      qt = setTimeout(function () { Q = v; PAGE = 1; render(); }, 220);
    });
    $('#qclr').addEventListener('click', function () {
      $('#q').value = ''; Q = ''; $('#searchWrap').classList.remove('has'); render();
    });

    ['y0', 'y1'].forEach(function (k) {
      $('#' + k).addEventListener('change', function (e) {
        F[k] = e.target.value === '' ? null : Number(e.target.value);
        F.decade = null; PAGE = 1; syncFacet(); render();
      });
    });

    document.addEventListener('click', function (e) {
      var t = e.target;

      var fli = t.closest('.frow[data-flag]');
      if (fli) {
        var k = fli.dataset.flag;
        F[k] = !F[k]; fli.classList.toggle('on', F[k]);
        PAGE = 1; render(); return;
      }
      var more = t.closest('.facet li[data-more]');
      if (more) {
        var list = more.parentNode;
        var items = Array.prototype.filter.call(list.children, function (li) {
          return !li.dataset.more; });
        // dataset.expanded === '1' means "currently showing all"
        var expanded = more.dataset.expanded === '1';
        items.forEach(function (li, i) { li.hidden = expanded ? i >= 16 : false; });
        more.dataset.expanded = expanded ? '0' : '1';
        more.textContent = expanded
          ? '展开其余 ' + (items.length - 16) + ' 个地区 ▾'
          : '收起 ▴';
        return;
      }
      var fac = t.closest('.facet li');
      if (fac) {
        var key = fac.dataset.key, v = fac.dataset.k;
        if (key === 'diff') v = Number(v);
        if (key === 'point') {
          // a chapter and a point are mutually exclusive selections
          F.chapter = null;
          F.point = (F.point === v) ? null : v;
        } else if (key === 'chapter') {
          F.point = null;
          F.chapter = (F.chapter === v) ? null : v;
        } else {
          F[key] = (F[key] === v) ? null : v;
        }
        PAGE = 1; syncFacet(); render(); return;
      }
      var tag = t.closest('.selinfo .tag');
      if (tag) {
        var ck = tag.dataset.clear;
        if (ck === 'yr') { F.y0 = F.y1 = null; $('#y0').value = ''; $('#y1').value = ''; }
        else if (ck === 'q') { Q = ''; $('#q').value = ''; $('#searchWrap').classList.remove('has'); }
        else { F[ck] = (ck === 'diff') ? null : null; }
        PAGE = 1; syncFacet(); render(); return;
      }
      var kp = t.closest('.pill.k');
      if (kp && kp.dataset.kp) {
        F.chapter = null; F.point = kp.dataset.kp; PAGE = 1;
        setView('browse'); syncFacet(); render(); return;
      }
      var pb = t.closest('.pager button');
      if (pb && !pb.disabled && pb.dataset.p) {
        PAGE = Number(pb.dataset.p); render();
        window.scrollTo({ top: 0, behavior: 'smooth' }); return;
      }
      var act = t.closest('.acts button');
      if (act) {
        var card = act.closest('.card'), id = card.dataset.id;
        if (act.dataset.act === 'open') openCard(card);
        else if (act.dataset.act === 'cart') {
          toggleCart(id);
          var inCart = CART.indexOf(id) >= 0;
          act.classList.toggle('on', inCart);
          act.textContent = inCart ? '已在试卷中 ✓' : '加入试卷';
          card.classList.toggle('sel', inCart);
          renderPaper();
        } else if (act.dataset.act === 'json') {
          shard(+id.split('|')[0]).then(function () {
            var r = findRec(id), li = findLight(id);
            dl(new Blob([JSON.stringify({
              id: id, year: li.y, region: li.r, track: li.t, type: li.tyc,
              difficulty: li.d, knowledge: r.k, source: li.p, number: li.n,
              problem_latex: r.pt, choices_latex: r.ch, answer_latex: r.af,
              solution_latex: r.sf, figures: (r.fi || []).concat(r.fs || [])
            }, null, 2)], { type: 'application/json' }), id.replace(/[|\\]/g, '_') + '.json');
          });
        }
        return;
      }
      var rm = t.closest('[data-rm]');
      if (rm) { toggleCart(rm.dataset.rm); renderPaper(); render(); return; }
    });

    $('#reset').addEventListener('click', function () {
      F = { y0: null, y1: null, decade: null, region: null, track: null,
            type: null, diff: null, chapter: null, point: null, fig: false, sol: false };
      Q = ''; $('#q').value = ''; $('#searchWrap').classList.remove('has');
      $('#y0').value = ''; $('#y1').value = '';
      PAGE = 1; syncFacet(); render();
    });

    $('#p-print').addEventListener('click', function () { window.print(); });
    $('#p-json').addEventListener('click', exportJSON);
    $('#p-tex').addEventListener('click', exportTEX);
    $('#p-clear').addEventListener('click', function () { CART = []; saveCart(); renderPaper(); render(); });
    $('#p-noans').addEventListener('click', function () {
      paperWithAns = !paperWithAns;
      $('#p-noans').textContent = paperWithAns ? '切换：只含题目 / 含答案' : '切换：含答案（当前：只题目）';
      renderPaper();
    });
  }

  function syncFacet() {
    $$('.facet li').forEach(function (li) {
      var k = li.dataset.key, v = li.dataset.k;
      if (k === 'diff') v = Number(v);
      li.classList.toggle('on',
        (k === 'point' ? F.point === v :
         k === 'chapter' ? F.chapter === v : F[k] === v));
    });
    $$('.frow[data-flag]').forEach(function (r) {
      r.classList.toggle('on', !!F[r.dataset.flag]);
    });
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
