// performance.js — 퍼포먼스 대시보드 (Meta 광고 × 자사몰 주문 ROAS)
(function () {
  'use strict';

  const money = v => v == null ? '-' : '₩' + Math.round(Number(v)).toLocaleString('ko-KR');
  const int   = v => v == null ? '-' : Math.round(Number(v)).toLocaleString('ko-KR');
  const pct   = (v, nd = 2) => v == null ? '-' : (v * 100).toFixed(nd) + '%';
  const roas  = v => v == null ? '-' : Number(v).toFixed(2) + 'x';
  const el    = id => document.getElementById(id);
  const set   = (id, val) => { const e = el(id); if (e) e.textContent = val; };
  const monthLabel = ym => { const [y, m] = ym.split('-'); return `${y.slice(2)}.${m}`; };

  Chart.defaults.color       = '#A8A69C';
  Chart.defaults.borderColor = '#E5E3D6';
  Chart.defaults.font.family = "'Pretendard', -apple-system, sans-serif";
  Chart.defaults.font.size   = 11;

  const C_SPEND = '#E48FB0';   // 화장품 팔레트
  const C_CLICK = '#1A1A18';
  const C_META  = '#3B6D11';
  const C_MALL  = '#C24B7A';

  let gIndex = null;
  let cur    = null;
  let _daily = null, _trend = null;
  const cache = {};

  async function fetchData(path) {
    const res = await fetch(path + '?v=' + Date.now());
    if (!res.ok) throw new Error('fetch 실패: ' + path);
    return res.json();
  }

  async function loadMonth(ym) {
    if (!cache[ym]) cache[ym] = await fetchData(`data/ads/${ym}.json`);
    return cache[ym];
  }

  // ── 월 칩 ────────────────────────────────────────────────────────────────
  function renderChips(months, active) {
    const box = el('month-chips');
    box.innerHTML = months.map(m =>
      `<button class="filter-chip${m === active ? ' active' : ''}" data-m="${m}">${monthLabel(m)}</button>`
    ).join('');
    box.querySelectorAll('.filter-chip').forEach(b => {
      b.addEventListener('click', () => selectMonth(b.dataset.m));
    });
  }

  // ── KPI ─────────────────────────────────────────────────────────────────
  function renderKpi(d, hist) {
    const t = d.totals, m = d.mall;
    const days = d.daily.length;
    set('k-spend', money(t.spend));
    set('k-spend-sub', days ? `일평균 ${money(t.spend / days)} · ${days}일` : `${d.campaigns.length}개 캠페인`);
    set('k-imp', int(t.impressions));
    set('k-imp-sub', `도달 ${int(t.reach)} · CPM ${money(t.cpm)}`);
    set('k-clk', int(t.clicks));
    set('k-clk-sub', `CTR ${pct(t.ctr)} · 링크클릭 ${int(t.link_clicks)}`);
    set('k-cpc', money(t.cpc));
    set('k-cpc-sub', t.link_clicks ? `링크 CPC ${money(t.spend / t.link_clicks)}` : '');
    set('k-purch', int(t.purchases));
    set('k-purch-sub', t.purchases ? `구매당 ${money(t.cost_per_purchase)} · 구매값 ${money(t.purchase_value)}` : '픽셀 구매 없음');
    set('k-mall', m.available ? int(m.orders) : '-');
    set('k-mall-sub', m.available ? `${int(m.units)}개 · 매출 ${money(m.gross)}` : '자사몰 집계 없음 (스냅샷 없음)');

    set('r-meta', roas(d.roas.meta));
    set('r-meta-sub', t.purchases ? `픽셀 구매 ${t.purchases}건 · 구매값 ${money(t.purchase_value)}` : '픽셀 구매 없음');
    set('r-mall', roas(d.roas.mall));
    set('r-mall-sub', m.available ? `자사몰 ${m.orders}건 · ${money(m.gross)}` : '자사몰 스냅샷 없음');

    // 화장품 전체 매출(네이버+자사몰) 대비
    const allGross = hist && hist.by_product && hist.by_product['화장품'] ? hist.by_product['화장품'].gross_revenue : null;
    if (allGross != null && t.spend) {
      set('r-all', roas(allGross / t.spend));
      set('r-all-sub', `화장품 전체 매출 ${money(allGross)} ÷ 광고비`);
    } else {
      set('r-all', '-');
      set('r-all-sub', '월 스냅샷 없음');
    }
  }

  // ── 일별 차트 ────────────────────────────────────────────────────────────
  function renderDaily(d) {
    const cv = el('daily-chart');
    if (_daily) { _daily.destroy(); _daily = null; }
    set('daily-title', `일별 광고비 · 클릭 (${monthLabel(d.month)})`);
    if (!d.daily.length) {
      cv.parentElement.classList.add('hidden');
      el('daily-none').classList.remove('hidden');
      return;
    }
    cv.parentElement.classList.remove('hidden');
    el('daily-none').classList.add('hidden');

    const labels = d.daily.map(r => r.date.slice(8));
    const purchDays = d.daily.map(r => r.purchases);
    _daily = new Chart(cv, {
      data: {
        labels,
        datasets: [
          { type: 'bar', label: '광고비', data: d.daily.map(r => r.spend), backgroundColor: C_SPEND, borderRadius: 3, yAxisID: 'y', order: 2 },
          { type: 'line', label: '클릭', data: d.daily.map(r => r.clicks), borderColor: C_CLICK, backgroundColor: C_CLICK,
            borderWidth: 1.5, pointRadius: purchDays.map(p => p ? 5 : 2),
            pointBackgroundColor: purchDays.map(p => p ? C_META : C_CLICK), tension: 0.3, yAxisID: 'y1', order: 1 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true } },
          tooltip: { callbacks: {
            label: c => c.dataset.label === '광고비' ? ` 광고비 ${money(c.raw)}` : ` 클릭 ${c.raw}`,
            afterBody: items => { const p = purchDays[items[0].dataIndex]; return p ? [`구매 ${p}건`] : []; },
          } },
        },
        scales: {
          x: { grid: { display: false } },
          y:  { position: 'left', ticks: { callback: v => (v / 1000) + 'k' }, grid: { color: '#EEEDE6' } },
          y1: { position: 'right', grid: { display: false }, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  // ── 월별 추이 ────────────────────────────────────────────────────────────
  function renderTrend(rows, active) {
    const cv = el('trend-chart');
    if (_trend) { _trend.destroy(); _trend = null; }
    const labels = rows.map(r => monthLabel(r.month));
    _trend = new Chart(cv, {
      data: {
        labels,
        datasets: [
          { type: 'bar', label: '광고비', data: rows.map(r => r.spend),
            backgroundColor: rows.map(r => r.month === active ? C_SPEND : '#F1C9D8'), borderRadius: 3, yAxisID: 'y', order: 3 },
          { type: 'line', label: 'Meta ROAS', data: rows.map(r => r.meta_roas), borderColor: C_META, backgroundColor: C_META,
            borderWidth: 1.5, pointRadius: 3, tension: 0.3, yAxisID: 'y1', spanGaps: true, order: 1 },
          { type: 'line', label: '자사몰 ROAS', data: rows.map(r => r.mall_roas), borderColor: C_MALL, backgroundColor: C_MALL,
            borderWidth: 1.5, borderDash: [4, 3], pointRadius: 3, tension: 0.3, yAxisID: 'y1', spanGaps: true, order: 2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        onClick: (_, els) => { if (els.length) selectMonth(rows[els[0].index].month); },
        plugins: {
          legend: { display: true, position: 'top', align: 'end', labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true } },
          tooltip: { callbacks: {
            label: c => c.dataset.label === '광고비' ? ` 광고비 ${money(c.raw)}` : ` ${c.dataset.label} ${roas(c.raw)}`,
          } },
        },
        scales: {
          x: { grid: { display: false } },
          y:  { position: 'left', ticks: { callback: v => (v / 10000) + '만' }, grid: { color: '#EEEDE6' } },
          y1: { position: 'right', grid: { display: false }, beginAtZero: true, ticks: { callback: v => v.toFixed(1) + 'x' } },
        },
      },
    });
  }

  // ── 캠페인 테이블 ────────────────────────────────────────────────────────
  function renderCampaigns(d) {
    const tb = el('camp-table').querySelector('tbody');
    const tf = el('camp-table').querySelector('tfoot');
    tb.innerHTML = d.campaigns.map(c => `
      <tr>
        <td>${c.name}</td>
        <td><span class="pill ${c.status === 'ACTIVE' ? 'pill-active' : 'pill-etc'}">${c.status === 'ACTIVE' ? '진행중' : '종료'}</span></td>
        <td>${money(c.spend)}</td>
        <td>${int(c.impressions)}</td>
        <td>${int(c.reach)}</td>
        <td>${int(c.clicks)}</td>
        <td>${pct(c.ctr)}</td>
        <td>${money(c.cpc)}</td>
        <td>${money(c.cpm)}</td>
        <td>${c.purchases || '-'}</td>
        <td>${c.purchases ? money(c.cost_per_purchase) : '-'}</td>
        <td>${roas(c.meta_roas)}</td>
      </tr>`).join('');
    const t = d.totals;
    tf.innerHTML = `
      <tr>
        <td>합계 (${d.campaigns.length})</td><td></td>
        <td>${money(t.spend)}</td><td>${int(t.impressions)}</td><td>${int(t.reach)}</td><td>${int(t.clicks)}</td>
        <td>${pct(t.ctr)}</td><td>${money(t.cpc)}</td><td>${money(t.cpm)}</td>
        <td>${t.purchases || '-'}</td><td>${t.purchases ? money(t.cost_per_purchase) : '-'}</td><td>${roas(d.roas.meta)}</td>
      </tr>`;
  }

  // ── 월 선택 ──────────────────────────────────────────────────────────────
  async function selectMonth(ym) {
    cur = ym;
    const months = gIndex.months.map(r => r.month);
    renderChips(months, ym);
    let d;
    try { d = await loadMonth(ym); }
    catch (e) { showError(`${ym} 광고 데이터를 불러오지 못했습니다.`); return; }

    let hist = null;
    try { hist = await fetchData(`data/history/${ym}.json`); } catch (_) { /* 스냅샷 없으면 무시 */ }

    renderKpi(d, hist);
    renderDaily(d);
    renderTrend(gIndex.months, ym);
    renderCampaigns(d);

    const w = el('warn-banner');
    if (!d.mall.available) { w.textContent = `${monthLabel(ym)} 자사몰 주문 스냅샷이 없어 자사몰 ROAS를 계산할 수 없습니다 (Meta ROAS만 표시).`; w.classList.remove('hidden'); }
    else w.classList.add('hidden');

    set('generated-at', `갱신 ${(d.updated_at || '').replace('T', ' ').slice(0, 16)} · Meta 수집 ${d.fetched_at || '-'}`);
    try { history.replaceState(null, '', '#' + ym); } catch (_) {}
  }

  function showError(msg) {
    const b = el('error-banner'); b.textContent = msg; b.classList.remove('hidden');
  }

  // ── init ────────────────────────────────────────────────────────────────
  (async function init() {
    try {
      gIndex = await fetchData('data/ads/index.json');
    } catch (e) {
      showError('광고 데이터 인덱스(data/ads/index.json)를 불러오지 못했습니다.');
      return;
    }
    if (!gIndex.months || !gIndex.months.length) { showError('수집된 광고 데이터가 없습니다.'); return; }
    const months = gIndex.months.map(r => r.month);
    const hash = (location.hash || '').replace('#', '');
    selectMonth(months.includes(hash) ? hash : months[months.length - 1]);
  })();
})();
