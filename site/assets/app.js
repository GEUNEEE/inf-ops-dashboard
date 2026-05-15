// app.js — 인플루언서 대시보드 메인 스크립트
(function () {
  'use strict';

  const money = v => v == null ? '-' : '₩' + Number(v).toLocaleString('ko-KR');
  const pct   = v => v == null ? '-' : (v * 100).toFixed(1) + '%';
  const el    = id => document.getElementById(id);
  const set   = (id, val) => { const e = el(id); if (e) e.textContent = val; };

  Chart.defaults.color       = '#A8A69C';
  Chart.defaults.borderColor = '#E5E3D6';
  Chart.defaults.font.family = "'Pretendard', -apple-system, sans-serif";
  Chart.defaults.font.size   = 11;

  let gData  = null;
  let _donut = null;
  const hCache = {};  // month → history JSON 캐시

  // ── 구간 단가 ─────────────────────────────────────────────────────────────
  function tierPrice(cumQty) {
    if (cumQty >= 100) return 25000;
    if (cumQty  >= 30) return 22000;
    return 20000;
  }

  // 누적 수량 전체에 대한 구간별 정산액 (1~29: 2만 / 30~99: 2.2만 / 100+: 2.5만)
  function calcTieredAmount(n) {
    if (n <= 0)  return 0;
    if (n < 30)  return n * 20000;
    if (n < 100) return 29 * 20000 + (n - 29) * 22000;
    return 29 * 20000 + 70 * 22000 + (n - 99) * 25000;
  }

  // prevCum ~ cum 구간에 걸치는 티어별 {qty, price} 배열
  function tierBreakdownRange(prevCum, cum) {
    const tiers = [];
    const t1 = Math.min(cum, 29)                       - Math.min(prevCum, 29);
    const t2 = Math.min(Math.max(cum, 29), 99)         - Math.min(Math.max(prevCum, 29), 99);
    const t3 = Math.max(cum, 99)                       - Math.max(prevCum, 99);
    if (t1 > 0) tiers.push({ qty: t1, price: 20000 });
    if (t2 > 0) tiers.push({ qty: t2, price: 22000 });
    if (t3 > 0) tiers.push({ qty: t3, price: 25000 });
    return tiers;
  }

  // ── 유틸 ──────────────────────────────────────────────────────────────────
  async function fetchData(path) {
    const res = await fetch(path + '?v=' + Date.now());
    if (!res.ok) throw new Error('fetch 실패: ' + path);
    return res.json();
  }

  function statusPill(status) {
    if (!status) return `<span class="pill pill-etc">-</span>`;
    let cls = 'pill-etc';
    if      (status.includes('체험'))          cls = 'pill-exp';
    else if (status.includes('광고완료'))      cls = 'pill-addone';
    else if (status.includes('광고예정'))      cls = 'pill-adplan';
    else if (status.includes('미팅진행'))      cls = 'pill-meeting-active';
    else if (status.includes('미팅예정'))      cls = 'pill-meeting-plan';
    else if (status.includes('미팅'))          cls = 'pill-meeting';
    else if (status.includes('거절'))          cls = 'pill-reject';
    return `<span class="pill ${cls}">${status}</span>`;
  }

  function monthLabel(ym) {
    return parseInt(ym.slice(5), 10) + '월';
  }

  // ── KPI 업데이트 ───────────────────────────────────────────────────────────
  function updateKPIs(r, f) {
    set('kpi-revenue',    money(r.gross_revenue));
    set('kpi-orders',     (r.order_count || 0) + '건');
    set('kpi-reply-rate', pct(f.reply_rate));
    set('kpi-ad-rate',    pct(f.ad_rate));
    set('kpi-exp-rate',   pct(f.exp_rate));

    const profit = r.net_profit;
    set('kpi-profit', money(profit));
    const pe = el('kpi-profit');
    if (pe) pe.style.color = profit > 0 ? '#3B6D11' : profit < 0 ? '#A32D2D' : '';
  }

  function setKPISubs(r, f) {
    set('kpi-revenue-sub', r.unit_count != null ? r.unit_count + '개 판매' : '');
    set('kpi-orders-sub',  r.unit_count != null ? r.unit_count + '개 단위' : '');
    set('kpi-profit-sub',  r.net_profit > 0 ? '흑자' : r.net_profit < 0 ? '적자' : '');
    set('kpi-reply-sub',   f.total_sent    ? Number(f.total_sent).toLocaleString() + '건 발송 기준' : '');
    set('kpi-ad-sub',      f.meeting_total ? Number(f.meeting_total).toLocaleString() + '건 미팅 기준' : '');
  }

  function clearKPISubs() {
    ['kpi-revenue-sub','kpi-orders-sub','kpi-profit-sub','kpi-reply-sub','kpi-ad-sub']
      .forEach(id => set(id, ''));
  }

  // ── 전체 기간 집계 ─────────────────────────────────────────────────────────
  async function buildAllTimeData() {
    const months = (gData.trends || {}).months || [];

    // 병렬로 모든 history 로드 (캐시 우선)
    await Promise.all(months.map(async m => {
      if (!hCache[m]) {
        try { hCache[m] = await fetchData('data/history/' + m + '.json'); }
        catch (e) { console.warn('[전체] 로드 실패:', m); }
      }
    }));

    const histories = months.map(m => hCache[m]).filter(Boolean);

    // 매출·수익 합산
    const revenue = { gross_revenue: 0, net_profit: 0, order_count: 0, unit_count: 0 };
    for (const h of histories) {
      revenue.gross_revenue += h.gross_revenue || 0;
      revenue.net_profit    += h.net_profit    || 0;
      revenue.order_count   += h.order_count   || 0;
      revenue.unit_count    += h.unit_count    || 0;
    }

    // 인플루언서별 합산
    const infMap = {};
    for (const h of histories) {
      for (const [name, d] of Object.entries(h.influencers || {})) {
        if (!infMap[name]) {
          infMap[name] = { order_count: 0, qty: 0, amount: 0, is_general: d.is_general };
        }
        infMap[name].order_count += d.order_count || 0;
        infMap[name].qty         += d.qty || 0;
        if (!d.is_general && d.amount != null) infMap[name].amount += d.amount;
      }
    }

    // 누적 수량 기반으로 구간 단가 + 정산액 재계산
    for (const d of Object.values(infMap)) {
      if (!d.is_general) {
        d.cumulative_qty = d.qty;
        d.unit_price     = tierPrice(d.qty);
        d.amount         = calcTieredAmount(d.qty);  // 누적 기준으로 재계산
      } else {
        d.cumulative_qty = null;
        d.unit_price     = null;
        d.amount         = null;
      }
    }

    return { revenue, infMap };
  }

  // 전체 기간 집계 → settlement_summary 형식
  function buildAllTimeSummary(infMap, currentSummary) {
    const result = {};
    for (const [name, d] of Object.entries(infMap)) {
      result[name] = {
        '건수':     d.order_count,
        '수량':     d.qty,
        '누적수량': d.cumulative_qty,
        '현재단가': d.unit_price,
        '금액':     d.is_general ? null : d.amount,
        '정산대상': !d.is_general,
        '현재상태': (currentSummary[name] || {})['현재상태'] || '',
      };
    }
    // history에 없으나 현재 관리 중인 인플루언서 포함
    for (const [name, d] of Object.entries(currentSummary)) {
      if (!result[name] && d['정산대상']) {
        result[name] = {
          '건수': 0, '수량': 0, '누적수량': 0,
          '현재단가': tierPrice(0), '금액': 0,
          '정산대상': true, '현재상태': d['현재상태'] || '',
        };
      }
    }
    return result;
  }

  // 월 필터 → settlement_summary 형식 (누적수량 기반 차등 단가 + 해당 월 금액)
  function historyToSummary(influencers) {
    const s = {};
    for (const [name, d] of Object.entries(influencers)) {
      const cum = d.cumulative_qty;
      s[name] = {
        '건수':     d.order_count ?? 0,
        '수량':     d.qty ?? 0,
        '누적수량': cum ?? null,
        '현재단가': d.is_general ? null : tierPrice(cum || 0),
        // 이번 달 정산액 = 누적 기준 총액 - 이전 누적 기준 총액
        '금액':     d.is_general ? null : calcTieredAmount(cum || 0) - calcTieredAmount((cum || 0) - (d.qty || 0)),
        '정산대상': !d.is_general,
        '현재상태': '',
      };
    }
    return s;
  }

  // ── 월별 필터 버튼 ─────────────────────────────────────────────────────────
  function renderFilterButtons(months) {
    const c = el('month-filter');
    if (!c) return;
    const sorted = months.slice().sort().reverse();
    c.innerHTML = [''].concat(sorted).map((m, i) =>
      `<button class="filter-chip${i === 0 ? ' active' : ''}" data-month="${m}">${m ? monthLabel(m) : '전체'}</button>`
    ).join('');
    c.addEventListener('click', e => {
      const btn = e.target.closest('.filter-chip');
      if (btn) selectMonth(btn);
    });
  }

  async function selectMonth(btn) {
    document.querySelectorAll('#month-filter .filter-chip').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const month = btn.dataset.month;

    if (!month) {
      // 전체 — 모든 history 합산
      const { revenue, infMap } = await buildAllTimeData();
      updateKPIs(revenue, gData.mail_funnel || {});
      setKPISubs(revenue, gData.mail_funnel || {});
      renderDonutChart(gData.inf_status || {});
      renderInfluencerGrid(buildAllTimeSummary(infMap, gData.settlement_summary || {}), null);
      return;
    }

    // 월 필터
    if (!hCache[month]) {
      try {
        hCache[month] = await fetchData('data/history/' + month + '.json');
      } catch (e) {
        console.error('[필터] history 로드 실패:', month, e.message);
        return;
      }
    }
    const h = hCache[month];

    updateKPIs(
      { gross_revenue: h.gross_revenue, net_profit: h.net_profit, order_count: h.order_count, unit_count: h.unit_count },
      { reply_rate: h.reply_rate, ad_rate: h.ad_rate, exp_rate: h.exp_rate }
    );
    clearKPISubs();
    renderDonutChart(h.inf_status || {});
    renderInfluencerGrid(historyToSummary(h.influencers || {}), month);
  }

  // ── 메인 초기화 ────────────────────────────────────────────────────────────
  async function renderDashboard() {
    try {
      gData = await fetchData('data/dashboard.json');
    } catch (e) {
      const b = el('error-banner');
      if (b) { b.textContent = '데이터 로드 실패: ' + e.message; b.classList.remove('hidden'); }
      return;
    }

    const f = gData.mail_funnel || {};
    const t = gData.trends      || {};

    if (gData.generated_at) set('generated-at', gData.generated_at.replace('T', ' '));

    const unreg = (gData.alerts || {}).unregistered_influencers || [];
    if (unreg.length && el('alert-banner')) {
      el('alert-banner').textContent = '미등재 인플루언서: ' + unreg.map(u => u.name + ' (' + u['건수'] + '건)').join(', ');
      el('alert-banner').classList.remove('hidden');
    }

    renderFilterButtons(t.months || []);
    renderFunnelBars(f);
    renderDonutChart(gData.inf_status || {});

    if (t.months && t.months.length > 0) {
      renderTrendChart(t);
      renderRevenueChart(t);
    }

    // 기본값: 전체 집계
    const { revenue, infMap } = await buildAllTimeData();
    updateKPIs(revenue, f);
    setKPISubs(revenue, f);
    renderInfluencerGrid(buildAllTimeSummary(infMap, gData.settlement_summary || {}), null);
  }

  // ── 퍼널 바 ───────────────────────────────────────────────────────────────
  function renderFunnelBars(f) {
    const c = el('funnel-bars');
    if (!c) return;
    const total = f.total_sent || 1;

    function bar(label, count, color) {
      const w      = Math.min((count / total) * 100, 100).toFixed(1);
      const pctStr = ((count / total) * 100).toFixed(1);
      return `
        <div class="f-bar">
          <div class="f-track">
            <div class="f-fill" style="width:${w}%;background:${color}"></div>
            <div class="f-label">
              <span class="f-name">${label}</span>
              <span class="f-cnt">${Number(count).toLocaleString()}건</span>
            </div>
          </div>
          <div class="f-pct" style="color:${color}">${pctStr}%</div>
        </div>`;
    }

    c.innerHTML = [
      bar('총 발송',   f.total_sent    || 0, '#D3D1C7'),
      bar('응답',      f.replied       || 0, '#85B7EB'),
      bar('미팅',      f.meeting_total || 0, '#EF9F27'),
      bar('체험 전환', f.exp_total     || 0, '#7F77DD'),
      bar('광고 수락', f.ad_total      || 0, '#97C459'),
    ].join('');
  }

  // ── 도넛 차트 ──────────────────────────────────────────────────────────────
  function renderDonutChart(infStatus) {
    const ctx = el('donut-chart');
    if (!ctx) return;
    if (_donut) { _donut.destroy(); _donut = null; }

    const cfg = [
      ['체험진행_1차', '1차 체험진행', '#AFA9EC'],
      ['체험진행_2차', '2차 체험진행', '#7F77DD'],
      ['체험진행_3차', '3차 체험진행', '#534AB7'],
      ['광고예정_1차', '1차 광고예정', '#C0DD97'],
      ['광고예정_2차', '2차 광고예정', '#97C459'],
      ['광고완료_1차', '1차 광고완료', '#639922'],
      ['기타',         '기타',         '#B4B2A9'],
    ];
    const total = cfg.reduce((s, [k]) => s + (infStatus[k] || 0), 0);
    const leg = el('donut-legend');

    if (!total) {
      _donut = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['없음'], datasets: [{ data: [1], backgroundColor: ['#E5E3D6'], borderWidth: 0 }] },
        options: { cutout: '62%', plugins: { legend: { display: false }, tooltip: { enabled: false } } },
      });
      if (leg) leg.innerHTML = '<div style="font-size:10px;color:var(--text3);padding:10px 0;text-align:center">현황 데이터 없음</div>';
      return;
    }

    _donut = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: cfg.map(([, l]) => l),
        datasets: [{
          data: cfg.map(([k]) => infStatus[k] || 0),
          backgroundColor: cfg.map(([,, c]) => c),
          borderWidth: 0,
        }],
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.label}: ${ctx.raw}명 (${Math.round(ctx.raw / total * 100)}%)`,
            },
          },
        },
      },
    });

    if (leg) {
      leg.innerHTML = cfg.map(([k, label, color]) => {
        const count = infStatus[k] || 0;
        const p = Math.round(count / total * 100);
        return `
          <div class="legend-row">
            <div class="legend-left">
              <div class="legend-dot" style="background:${color}"></div>
              <span class="legend-lbl">${label}</span>
            </div>
            <div class="legend-right"><span>${count}명</span><span>(${p}%)</span></div>
          </div>`;
      }).join('');
    }
  }

  // ── 인플루언서 카드 ────────────────────────────────────────────────────────
  function renderInfluencerGrid(summary, month) {
    const grid = el('inf-grid');
    if (!grid) return;

    const amountLabel = month ? monthLabel(month) + ' 정산액' : '누적 정산액';

    const items = Object.entries(summary).map(([name, d]) => ({ name, ...d }));
    items.sort((a, b) => {
      if (a['정산대상'] && !b['정산대상']) return -1;
      if (!a['정산대상'] && b['정산대상']) return 1;
      return (b['금액'] || 0) - (a['금액'] || 0);
    });

    grid.innerHTML = items.map(item => {
      const isTarget = item['정산대상'];
      const tag  = isTarget ? 'a' : 'div';
      const href = isTarget ? `href="influencer.html?name=${encodeURIComponent(item.name)}"` : '';
      const badge = isTarget
        ? `<span class="pill pill-target">정산대상</span>`
        : `<span class="pill pill-general">기타/일반</span>`;

      let statsHtml;
      if (isTarget) {
        const cum     = item['누적수량'] ?? 0;
        const qty     = item['수량'] ?? 0;
        const prevCum = Math.max(cum - qty, 0);
        const tiers   = tierBreakdownRange(prevCum, cum);
        const isMulti = tiers.length > 1;
        const total   = tiers.reduce((s, t) => s + t.qty * t.price, 0);

        const rows = tiers.map(t => `
          <div class="tier-row">
            <span>${t.qty}개 × ${money(t.price)}${t.price > 20000 ? '<span class="tier-up">▲</span>' : ''}</span>
            <span class="stat-val">${money(t.qty * t.price)}</span>
          </div>`).join('');

        const totalRow = isMulti ? `
          <div class="tier-total">
            <span style="color:var(--text3)">합계</span>
            <span class="stat-val">${money(total)}</span>
          </div>` : '';

        statsHtml = `
          <div style="margin-top:8px">
            <span class="stat-lbl">${amountLabel}</span>
            <div class="tier-section">${rows}${totalRow}</div>
          </div>
          <div class="inf-card-stats" style="grid-template-columns:1fr 1fr;margin-top:6px">
            <div><span class="stat-lbl">건수</span><span class="stat-val">${item['건수'] || 0}건</span></div>
            <div><span class="stat-lbl">누적수량</span><span class="stat-val">${cum}개</span></div>
          </div>`;
      } else {
        statsHtml = `
          <div class="inf-card-stats" style="margin-top:8px">
            <div><span class="stat-lbl">건수</span><span class="stat-val">${item['건수'] || 0}건</span></div>
          </div>`;
      }

      return `
        <${tag} class="inf-card" ${href}>
          <div class="inf-card-header">
            <span class="inf-card-name">${item.name}</span>
            ${badge}
          </div>
          <div style="margin-bottom:4px">${statusPill(item['현재상태'] || '')}</div>
          ${statsHtml}
        </${tag}>`;
    }).join('');
  }

  // ── 추세 차트 ──────────────────────────────────────────────────────────────
  function renderTrendChart(t) {
    const ctx = el('trend-chart');
    if (!ctx) return;
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: t.months.map(monthLabel),
        datasets: [
          { label: '응답률',    data: t.reply_rate.map(v => +(v * 100).toFixed(1)), borderColor: '#85B7EB', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '체험전환율', data: t.exp_rate.map(v => +(v * 100).toFixed(1)),   borderColor: '#7F77DD', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '광고수락률', data: t.ad_rate.map(v => +(v * 100).toFixed(1)),    borderColor: '#97C459', tension: 0.4, fill: false, pointRadius: 3 },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } } },
        scales: {
          x: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } },
               title: { display: true, text: '%', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  function renderRevenueChart(t) {
    const ctx = el('revenue-chart');
    if (!ctx) return;
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: t.months.map(monthLabel),
        datasets: [
          { type: 'bar',  label: '매출', data: t.gross_revenue, backgroundColor: 'rgba(127,119,221,0.5)' },
          { type: 'line', label: '수익', data: t.net_profit,    borderColor: '#97C459', tension: 0.4, fill: false, yAxisID: 'y1', pointRadius: 3 },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } } },
        scales: {
          x:  { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y:  { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } },
                title: { display: true, text: '매출 (₩)', font: { size: 10 }, color: '#A8A69C' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { font: { size: 10 } },
                title: { display: true, text: '수익 (₩)', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── 인플루언서 드릴다운 ────────────────────────────────────────────────────
  async function renderInfluencer() {
    const name = new URLSearchParams(window.location.search).get('name');
    if (!name) {
      document.body.innerHTML = '<p style="padding:24px;font-size:12px;color:#A8A69C">인플루언서 이름이 없습니다.</p>';
      return;
    }
    set('inf-name', name);

    let data;
    try {
      data = await fetchData('data/influencer/' + encodeURIComponent(name) + '.json');
    } catch (e) {
      const b = el('error-banner');
      if (b) { b.textContent = '데이터 없음: ' + name; b.classList.remove('hidden'); }
      return;
    }

    const cum = data.cumulative_qty || 0;
    set('inf-status',     data.current_status || '-');
    set('inf-cum-qty',    cum + '개');
    set('inf-unit-price', money(tierPrice(cum)));  // 누적 기반 차등 단가

    const monthly = data.monthly_orders || [];
    const ctx = el('monthly-chart');
    if (ctx && monthly.length) {
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: monthly.map(m => monthLabel(m.month)),
          datasets: [{
            label: '수량',
            data: monthly.map(m => m.qty),
            backgroundColor: 'rgba(127,119,221,0.6)',
          }],
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
            y: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          },
        },
      });
    }

    const sched = el('upcoming-schedule');
    if (sched && data.upcoming_schedule && data.upcoming_schedule.length) {
      sched.innerHTML = data.upcoming_schedule
        .map(s => `<li>${s.date} D-${s.days_until} &nbsp; ${s.label}</li>`)
        .join('');
    }
  }

  // ── 초기화 ────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.page === 'dashboard')  renderDashboard();
    if (document.body.dataset.page === 'influencer') renderInfluencer();
  });
})();
