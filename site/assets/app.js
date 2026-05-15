// app.js — 인플루언서 대시보드 메인 스크립트
(function () {
  'use strict';

  const money = v => v == null ? '-' : '₩' + Number(v).toLocaleString('ko-KR');
  const pct   = v => v == null ? '-' : (v * 100).toFixed(1) + '%';
  const el    = id => document.getElementById(id);
  const set   = (id, val) => { const e = el(id); if (e) e.textContent = val; };

  // Chart.js 전역 기본값 — 라이트 테마
  Chart.defaults.color       = '#A8A69C';
  Chart.defaults.borderColor = '#E5E3D6';
  Chart.defaults.font.family = "'Pretendard', -apple-system, sans-serif";
  Chart.defaults.font.size   = 11;

  // ── 전역 상태 ─────────────────────────────────────────────────────────────
  let gData  = null;   // dashboard.json 전체 데이터
  let _donut = null;   // 도넛 Chart 인스턴스 (재렌더 시 destroy 필요)
  const hCache = {};   // month key → history JSON 캐시

  // ── 유틸 ──────────────────────────────────────────────────────────────────
  async function fetchData(path) {
    const res = await fetch(path + '?v=' + Date.now());
    if (!res.ok) throw new Error('fetch 실패: ' + path);
    return res.json();
  }

  function statusPill(status) {
    if (!status) return `<span class="pill pill-etc">-</span>`;
    let cls = 'pill-etc';
    if (status.includes('체험'))         cls = 'pill-exp';
    else if (status.includes('광고예정')) cls = 'pill-adplan';
    else if (status.includes('광고완료')) cls = 'pill-addone';
    return `<span class="pill ${cls}">${status}</span>`;
  }

  function monthLabel(ym) {
    // "2026-04" → "4월"
    return parseInt(ym.slice(5), 10) + '월';
  }

  // ── KPI 업데이트 (필터 전환마다 호출) ────────────────────────────────────
  function updateKPIs(r, f) {
    set('kpi-revenue',    money(r.gross_revenue));
    set('kpi-orders',     (r.order_count || 0) + '건');
    set('kpi-profit',     money(r.net_profit));
    set('kpi-reply-rate', pct(f.reply_rate));
    set('kpi-ad-rate',    pct(f.ad_rate));
    set('kpi-exp-rate',   pct(f.exp_rate));
  }

  // ── 히스토리 → settlement_summary 형식 변환 ──────────────────────────────
  function historyToSummary(influencers) {
    const s = {};
    for (const [name, d] of Object.entries(influencers)) {
      s[name] = {
        '건수':     d.order_count ?? 0,
        '수량':     d.qty ?? 0,
        '누적수량': d.cumulative_qty ?? null,
        '현재단가': d.unit_price   ?? null,
        '금액':     d.amount       ?? null,
        '정산대상': !d.is_general,
        '현재상태': '',
      };
    }
    return s;
  }

  // ── 월별 필터 버튼 렌더 ───────────────────────────────────────────────────
  function renderFilterButtons(months) {
    const c = el('month-filter');
    if (!c) return;

    // 최신 월이 앞 (내림차순)
    const sorted = months.slice().sort().reverse();

    c.innerHTML = [''].concat(sorted).map((m, i) =>
      `<button class="filter-chip${i === 0 ? ' active' : ''}" data-month="${m}">${m ? monthLabel(m) : '전체'}</button>`
    ).join('');

    c.addEventListener('click', e => {
      const btn = e.target.closest('.filter-chip');
      if (btn) selectMonth(btn);
    });
  }

  // ── 월별 필터 선택 ────────────────────────────────────────────────────────
  async function selectMonth(btn) {
    document.querySelectorAll('#month-filter .filter-chip')
      .forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const month = btn.dataset.month;

    if (!month) {
      // 전체 — dashboard.json 원본으로 복원
      updateKPIs(gData.revenue || {}, gData.mail_funnel || {});
      renderDonutChart(gData.inf_status || {});
      renderInfluencerGrid(gData.settlement_summary || {});
      return;
    }

    // 해당 월 히스토리 로드 (캐시 우선)
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
      { gross_revenue: h.gross_revenue, net_profit: h.net_profit, order_count: h.order_count },
      { reply_rate: h.reply_rate, ad_rate: h.ad_rate, exp_rate: h.exp_rate }
    );
    renderDonutChart(h.inf_status || {});
    renderInfluencerGrid(historyToSummary(h.influencers || {}));
  }

  // ── 메인 대시보드 초기화 ──────────────────────────────────────────────────
  async function renderDashboard() {
    try {
      gData = await fetchData('data/dashboard.json');
    } catch (e) {
      const b = el('error-banner');
      if (b) { b.textContent = '데이터 로드 실패: ' + e.message; b.classList.remove('hidden'); }
      return;
    }

    const r = gData.revenue     || {};
    const f = gData.mail_funnel || {};
    const t = gData.trends      || {};

    if (gData.generated_at) set('generated-at', gData.generated_at.replace('T', ' '));

    const unreg = (gData.alerts || {}).unregistered_influencers || [];
    if (unreg.length && el('alert-banner')) {
      el('alert-banner').textContent =
        '미등재 인플루언서: ' + unreg.map(u => u.name + ' (' + u['건수'] + '건)').join(', ');
      el('alert-banner').classList.remove('hidden');
    }

    // 필터 버튼 (trends.months 기준)
    renderFilterButtons(t.months || []);

    // 전체 기본값으로 렌더
    updateKPIs(r, f);
    renderFunnelBars(f);          // 퍼널 바는 항상 누적 데이터 (필터 불변)
    renderDonutChart(gData.inf_status || {});
    renderInfluencerGrid(gData.settlement_summary || {});

    // 추세 차트는 한 번만 렌더 (필터와 무관)
    if (t.months && t.months.length > 0) {
      renderTrendChart(t);
      renderRevenueChart(t);
    }
  }

  // ── 퍼널 바 ──────────────────────────────────────────────────────────────
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
      bar('총 발송',   f.total_sent || 0, '#D3D1C7'),
      bar('응답',      f.replied    || 0, '#85B7EB'),
      bar('체험 전환', f.exp_total  || 0, '#7F77DD'),
      bar('광고 수락', f.ad_total   || 0, '#97C459'),
    ].join('');
  }

  // ── 도넛 차트 (재렌더 가능) ───────────────────────────────────────────────
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
              label: ctx =>
                ` ${ctx.label}: ${ctx.raw}명 (${total ? Math.round(ctx.raw / total * 100) : 0}%)`,
            },
          },
        },
      },
    });

    const leg = el('donut-legend');
    if (leg) {
      leg.innerHTML = cfg.map(([k, label, color]) => {
        const count = infStatus[k] || 0;
        const p = total ? Math.round(count / total * 100) : 0;
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

  // ── 인플루언서 카드 그리드 (재렌더 가능) ─────────────────────────────────
  function renderInfluencerGrid(summary) {
    const grid = el('inf-grid');
    if (!grid) return;

    const items = Object.entries(summary).map(([name, d]) => ({ name, ...d }));
    items.sort((a, b) => {
      if (a['정산대상'] && !b['정산대상']) return -1;
      if (!a['정산대상'] && b['정산대상']) return 1;
      return (b['금액'] || 0) - (a['금액'] || 0);
    });

    grid.innerHTML = items.map(item => {
      const isTarget = item['정산대상'];
      const tag  = isTarget ? 'a' : 'div';
      const href = isTarget
        ? `href="influencer.html?name=${encodeURIComponent(item.name)}"`
        : '';
      const badge = isTarget
        ? `<span class="pill pill-target">정산대상</span>`
        : `<span class="pill pill-general">기타/일반</span>`;

      return `
        <${tag} class="inf-card" ${href}>
          <div class="inf-card-header">
            <span class="inf-card-name">${item.name}</span>
            ${badge}
          </div>
          <div style="margin-bottom:6px">${statusPill(item['현재상태'] || '')}</div>
          <div class="inf-card-stats">
            <div>
              <span class="stat-lbl">이번달</span>
              <span class="stat-val">${money(item['금액'])}</span>
            </div>
            <div>
              <span class="stat-lbl">누적수량</span>
              <span class="stat-val">${item['누적수량'] != null ? item['누적수량'] + '개' : '-'}</span>
            </div>
            <div>
              <span class="stat-lbl">단가</span>
              <span class="stat-val">${money(item['현재단가'])}</span>
            </div>
          </div>
        </${tag}>`;
    }).join('');
  }

  // ── 추세 차트 (정적 — 필터와 무관하게 한 번만 렌더) ──────────────────────
  function renderTrendChart(t) {
    const ctx = el('trend-chart');
    if (!ctx) return;
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: t.months,
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
          y: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } }, title: { display: true, text: '%', font: { size: 10 }, color: '#A8A69C' } },
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
        labels: t.months,
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
          y:  { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } }, title: { display: true, text: '매출 (₩)', font: { size: 10 }, color: '#A8A69C' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { font: { size: 10 } }, title: { display: true, text: '수익 (₩)', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── 드릴다운 페이지 ───────────────────────────────────────────────────────
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

    set('inf-status',     data.current_status || '-');
    set('inf-cum-qty',    (data.cumulative_qty || 0) + '개');
    set('inf-unit-price', money(data.current_tier_price));

    const monthly = data.monthly_orders || [];
    const ctx = el('monthly-chart');
    if (ctx && monthly.length) {
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: monthly.map(m => m.month),
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
