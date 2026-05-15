// app.js — 인플루언서 대시보드 메인 스크립트
(function () {
  'use strict';

  // ── 유틸 ──────────────────────────────────────────────────────────────
  const money = (v) =>
    v == null ? '-' : '₩' + Number(v).toLocaleString('ko-KR');

  const pct = (v) =>
    v == null ? '-' : (v * 100).toFixed(1) + '%';

  function el(id) { return document.getElementById(id); }

  function setKpi(id, val) {
    const e = el(id);
    if (e) e.textContent = val;
  }

  // ── 데이터 fetch ──────────────────────────────────────────────────────
  async function fetchData(path) {
    const url = path + '?v=' + Date.now();
    const res = await fetch(url);
    if (!res.ok) throw new Error('fetch 실패: ' + path);
    return res.json();
  }

  // ── 메인 대시보드 렌더 ─────────────────────────────────────────────────
  async function renderDashboard() {
    let data;
    try {
      data = await fetchData('data/dashboard.json');
    } catch (e) {
      el('error-banner').textContent = '데이터 로드 실패: ' + e.message;
      el('error-banner').classList.remove('hidden');
      return;
    }

    const r = data.revenue || {};
    const f = data.mail_funnel || {};
    const s = data.settlement_summary || {};
    const t = data.trends || {};

    // KPI 카드
    setKpi('kpi-revenue', money(r.gross_revenue));
    setKpi('kpi-orders', (r.order_count || 0) + '건');
    setKpi('kpi-profit', money(r.net_profit));
    setKpi('kpi-ad-rate', pct(f.ad_rate));
    setKpi('kpi-reply-rate', pct(f.reply_rate));
    setKpi('kpi-exp-rate', pct(f.exp_rate));

    // 생성일시
    if (data.generated_at && el('generated-at')) {
      el('generated-at').textContent = data.generated_at.replace('T', ' ');
    }

    // 알림 배너 (미등재)
    const unregistered = (data.alerts || {}).unregistered_influencers || [];
    if (unregistered.length > 0 && el('alert-banner')) {
      const names = unregistered.map(u => u.name + ' (' + u['건수'] + '건)').join(', ');
      el('alert-banner').textContent = '⚠ 관리탭 미등재 인플루언서: ' + names;
      el('alert-banner').classList.remove('hidden');
    }

    // 인플루언서 카드 그리드
    renderInfluencerGrid(s, data.inf_status || {});

    // 추세선 차트
    if (t.months && t.months.length > 0) {
      renderTrendChart(t);
      renderRevenueChart(t);
    }

    // 퍼널 KPI 상세
    renderFunnelTable(f);
  }

  function renderInfluencerGrid(summary, infStatus) {
    const grid = el('inf-grid');
    if (!grid) return;

    const items = Object.entries(summary).map(([name, d]) => ({ name, ...d }));
    // 정산 대상 먼저, 그 다음 기타/일반
    items.sort((a, b) => {
      if (a['정산대상'] && !b['정산대상']) return -1;
      if (!a['정산대상'] && b['정산대상']) return 1;
      return (b['금액'] || 0) - (a['금액'] || 0);
    });

    grid.innerHTML = items.map(item => {
      const badge = item['정산대상']
        ? `<span class="badge-blue">정산대상</span>`
        : `<span class="badge-gray">기타/일반</span>`;
      const link = item['정산대상']
        ? `<a href="influencer.html?name=${encodeURIComponent(item.name)}" class="card-link">`
        : '<div class="card">';
      const closeTag = item['정산대상'] ? '</a>' : '</div>';

      return `
        ${link}
          <div class="card-inner">
            <div class="card-header">
              <span class="card-name">${item.name}</span>
              ${badge}
            </div>
            <div class="card-stats">
              <div><span class="stat-label">이번달</span><span class="stat-val">${money(item['금액'])}</span></div>
              <div><span class="stat-label">누적수량</span><span class="stat-val">${item['누적수량'] != null ? item['누적수량'] + '개' : '-'}</span></div>
              <div><span class="stat-label">단가</span><span class="stat-val">${money(item['현재단가'])}</span></div>
            </div>
          </div>
        ${closeTag}`;
    }).join('');
  }

  function renderTrendChart(t) {
    const ctx = el('trend-chart');
    if (!ctx) return;
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: t.months,
        datasets: [
          {
            label: '응답률', data: t.reply_rate.map(v => +(v * 100).toFixed(1)),
            borderColor: '#6366f1', tension: 0.4, fill: false
          },
          {
            label: '체험전환율', data: t.exp_rate.map(v => +(v * 100).toFixed(1)),
            borderColor: '#22c55e', tension: 0.4, fill: false
          },
          {
            label: '광고수락률', data: t.ad_rate.map(v => +(v * 100).toFixed(1)),
            borderColor: '#f59e0b', tension: 0.4, fill: false
          },
        ]
      },
      options: {
        responsive: true, plugins: { legend: { position: 'top' } },
        scales: { y: { title: { display: true, text: '%' } } }
      }
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
          {
            type: 'bar', label: '매출',
            data: t.gross_revenue,
            backgroundColor: 'rgba(99,102,241,0.6)'
          },
          {
            type: 'line', label: '수익',
            data: t.net_profit,
            borderColor: '#f43f5e', tension: 0.4, fill: false, yAxisID: 'y1'
          },
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'top' } },
        scales: {
          y:  { title: { display: true, text: '매출 (₩)' } },
          y1: { position: 'right', title: { display: true, text: '수익 (₩)' }, grid: { drawOnChartArea: false } }
        }
      }
    });
  }

  function renderFunnelTable(f) {
    const tbody = el('funnel-tbody');
    if (!tbody) return;
    const rows = [
      ['총 발송', f.total_sent + '건', ''],
      ['기타 제외', f.etc_excluded + '건', ''],
      ['응답', f.replied + '건', pct(f.reply_rate)],
      ['미팅', f.meeting_total + '건', pct(f.meeting_rate)],
      ['체험 전환', f.exp_total + '건', pct(f.exp_rate)],
      ['광고 수락', f.ad_total + '건', pct(f.ad_rate)],
    ];
    tbody.innerHTML = rows.map(([label, val, rate]) =>
      `<tr><td>${label}</td><td class="text-right font-mono">${val}</td><td class="text-right font-mono text-indigo-400">${rate}</td></tr>`
    ).join('');
  }

  // ── 드릴다운 페이지 렌더 ───────────────────────────────────────────────
  async function renderInfluencer() {
    const params = new URLSearchParams(window.location.search);
    const name = params.get('name');
    if (!name) { document.body.innerHTML = '<p>인플루언서 이름이 없습니다.</p>'; return; }

    if (el('inf-name')) el('inf-name').textContent = name;

    let data;
    try {
      data = await fetchData('data/influencer/' + encodeURIComponent(name) + '.json');
    } catch (e) {
      el('error-banner').textContent = '데이터 없음: ' + name;
      el('error-banner').classList.remove('hidden');
      return;
    }

    setKpi('inf-status', data.current_status || '-');
    setKpi('inf-cum-qty', (data.cumulative_qty || 0) + '개');
    setKpi('inf-unit-price', money(data.current_tier_price));

    // 월별 차트
    const monthly = data.monthly_orders || [];
    const ctx = el('monthly-chart');
    if (ctx && monthly.length) {
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: monthly.map(m => m.month),
          datasets: [{
            label: '수량', data: monthly.map(m => m.qty),
            backgroundColor: 'rgba(99,102,241,0.7)'
          }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });
    }

    // 향후 일정
    const sched = el('upcoming-schedule');
    if (sched && data.upcoming_schedule) {
      sched.innerHTML = data.upcoming_schedule.map(s =>
        `<li>${s.date} D-${s.days_until} &nbsp; ${s.label}</li>`
      ).join('');
    }
  }

  // ── 초기화 ────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.page === 'dashboard') renderDashboard();
    if (document.body.dataset.page === 'influencer') renderInfluencer();
  });
})();
