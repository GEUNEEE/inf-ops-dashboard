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
  let _sumChart = null;
  const hCache = {};

  // ── 구간 단가 ─────────────────────────────────────────────────────────────
  const GROSS_PRICE_INF  = 120000; // 정산대상 매출 단가
  const GROSS_PRICE_GEN  = 130000; // 기타/일반 매출 단가
  const COGS             = 36000;  // 원가 (개당)
  const MARGIN_GENERAL   = 84000;  // 기타/일반 정산가

  function tierPrice(cumQty) {
    if (cumQty >= 100) return 25000;
    if (cumQty >= 30)  return 22000;
    return 20000;
  }

  function calcTieredAmount(n) {
    if (n <= 0)  return 0;
    if (n < 30)  return n * 20000;
    if (n < 100) return 29 * 20000 + (n - 29) * 22000;
    return 29 * 20000 + 70 * 22000 + (n - 99) * 25000;
  }

  function tierBreakdownRange(prevCum, cum) {
    const tiers = [];
    const t1 = Math.min(cum, 29)               - Math.min(prevCum, 29);
    const t2 = Math.min(Math.max(cum, 29), 99) - Math.min(Math.max(prevCum, 29), 99);
    const t3 = Math.max(cum, 99)               - Math.max(prevCum, 99);
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
    if      (status.includes('체험'))       cls = 'pill-exp';
    else if (status.includes('광고완료'))   cls = 'pill-addone';
    else if (status.includes('광고예정'))   cls = 'pill-adplan';
    else if (status.includes('미팅진행'))   cls = 'pill-meeting-active';
    else if (status.includes('미팅예정'))   cls = 'pill-meeting-plan';
    else if (status.includes('미팅'))       cls = 'pill-meeting';
    else if (status.includes('거절'))       cls = 'pill-reject';
    return `<span class="pill ${cls}">${status}</span>`;
  }

  function monthLabel(ym) {
    return parseInt(ym.slice(5), 10) + '월';
  }

  // ── KPI ───────────────────────────────────────────────────────────────────
  function updateKPIs(r, f) {
    set('kpi-revenue',    money(r.gross_revenue));
    set('kpi-orders',     (r.unit_count != null ? r.unit_count : 0) + '개');
    set('kpi-profit',     money(r.net_profit));
    set('kpi-reply-rate', pct(f.reply_rate));
    set('kpi-exp-rate',   pct(f.exp_rate));
    set('kpi-ad-rate',    pct(f.ad_rate));
    const pe = el('kpi-profit');
    if (pe) {
      const p = r.net_profit;
      pe.style.color = p > 0 ? '#3B6D11' : p < 0 ? '#A32D2D' : '';
    }
  }

  function setKPISubs(r, f) {
    set('kpi-revenue-sub', r.unit_count != null ? r.unit_count + '개 판매' : '');
    set('kpi-orders-sub',  r.order_count != null ? '주문수 ' + r.order_count + '건' : '');
    set('kpi-profit-sub',  r.net_profit > 0 ? '흑자' : r.net_profit < 0 ? '적자' : '');
    const sentStr = f.total_sent ? Number(f.total_sent).toLocaleString() + '건 발송 기준' : '';
    set('kpi-reply-sub', sentStr);
    set('kpi-exp-sub',   sentStr);
    set('kpi-ad-sub',    sentStr);
  }

  function clearKPISubs() {
    ['kpi-revenue-sub','kpi-orders-sub','kpi-profit-sub',
     'kpi-reply-sub','kpi-exp-sub','kpi-ad-sub'].forEach(id => set(id, ''));
  }

  // ── 영업이익 KPI ───────────────────────────────────────────────────────────
  function renderProfitKPIs(pa, month) {
    if (!pa) return;
    let op, rate, cumulative;
    if (!month) {
      const entries = Object.values(pa.monthly || {});
      op = entries.reduce((s, e) => s + (e.operating_profit || 0), 0);
      const totalRev = entries.reduce((s, e) => s + (e.gross_revenue || 0), 0);
      rate = totalRev ? op / totalRev : 0;
      const lastKey = Object.keys(pa.monthly || {}).sort().pop();
      cumulative = lastKey ? (pa.monthly[lastKey].cumulative_profit || 0) : 0;
    } else {
      const m = (pa.monthly || {})[month] || {};
      op         = m.operating_profit      || 0;
      rate       = m.operating_profit_rate || 0;
      cumulative = m.cumulative_profit     || 0;
    }
    set('kpi-op-profit',  money(op));
    set('kpi-op-rate',    pct(rate));
    set('kpi-cumulative', money(cumulative));
    const oe = el('kpi-op-profit');
    if (oe) oe.style.color = op > 0 ? '#3B6D11' : op < 0 ? '#A32D2D' : '';
    const ce = el('kpi-cumulative');
    if (ce) ce.style.color = cumulative > 0 ? '#3B6D11' : cumulative < 0 ? '#A32D2D' : '';
    set('kpi-op-profit-sub',  month ? monthLabel(month) + ' 기준' : '전체 합계');
    set('kpi-op-rate-sub',    month ? '' : '전체 평균');
    set('kpi-cumulative-sub', month ? month + '까지 누계' : '전체 누계');
  }

  // ── 히스토리 → summary 변환 ────────────────────────────────────────────────
  function historyToSummary(influencers, settlementSummary) {
    const ss = settlementSummary || {};
    const s = {};
    for (const [name, d] of Object.entries(influencers)) {
      const cum   = d.cumulative_qty;
      const qty   = d.qty || 0;
      const isGen = d.is_general || false;
      const cs    = ss[name] || {};
      s[name] = {
        '건수':      d.order_count ?? 0,
        '수량':      qty,
        '누적수량':  isGen ? null : (cum ?? null),
        // 정산 단가·금액은 스냅샷 저장값 우선 (정산 미지급=0 등 실제 정산 반영). 없으면 tier 재계산 폴백.
        '현재단가':  isGen ? null : (d.unit_price != null ? d.unit_price : tierPrice(cum || 0)),
        '금액':      isGen
          ? (d.amount ?? null)
          : (d.amount != null ? d.amount : calcTieredAmount(cum || 0) - calcTieredAmount(Math.max((cum || 0) - qty, 0))),
        '정산대상':  !isGen,
        '현재상태':  cs['현재상태'] || '',
        '체험횟수':  cs['체험횟수'] ?? null,
        '협찬원가':  cs['협찬원가'] ?? null,
        '체험월목록': cs['체험월목록'] || [],
      };
    }
    return s;
  }

  // ── 전체 기간 집계 ─────────────────────────────────────────────────────────
  async function buildAllTimeData() {
    const months = (gData.trends || {}).months || [];
    await Promise.all(months.map(async m => {
      if (!hCache[m]) {
        try { hCache[m] = await fetchData('data/history/' + m + '.json'); }
        catch (e) { console.warn('[전체] 로드 실패:', m); }
      }
    }));
    const histories = months.map(m => hCache[m]).filter(Boolean);

    const revenue = { gross_revenue: 0, net_profit: 0, order_count: 0, unit_count: 0 };
    for (const h of histories) {
      revenue.gross_revenue += h.gross_revenue || 0;
      revenue.net_profit    += h.net_profit    || 0;
      revenue.order_count   += h.order_count   || 0;
      revenue.unit_count    += h.unit_count    || 0;
    }

    const infMap = {};
    for (const m of months) {
      const h = hCache[m];
      if (!h) continue;
      for (const [name, d] of Object.entries(h.influencers || {})) {
        if (!infMap[name]) infMap[name] = { order_count: 0, qty: 0, amount: 0, is_general: d.is_general, monthly: {} };
        infMap[name].order_count += d.order_count || 0;
        infMap[name].qty         += d.qty || 0;
        if (d.amount != null) infMap[name].amount += d.amount;
        if ((d.qty || 0) > 0) infMap[name].monthly[m] = { qty: d.qty || 0, amount: d.amount || 0 };
      }
    }
    for (const d of Object.values(infMap)) {
      if (!d.is_general) {
        d.cumulative_qty = d.qty;
        d.unit_price     = tierPrice(d.qty);
        d.amount         = calcTieredAmount(d.qty);
      } else {
        d.cumulative_qty = null;
      }
    }
    return { revenue, infMap };
  }

  function buildAllTimeSummary(infMap, currentSummary) {
    const result = {};
    for (const [name, d] of Object.entries(infMap)) {
      const cs = currentSummary[name] || {};
      result[name] = {
        '건수': d.order_count, '수량': d.qty,
        '누적수량': d.cumulative_qty, '현재단가': d.unit_price,
        '금액': d.amount ?? null, '정산대상': !d.is_general,
        '현재상태': cs['현재상태'] || '',
        '체험횟수': cs['체험횟수'] ?? null,
        '협찬원가': cs['협찬원가'] ?? null,
        '체험월목록': cs['체험월목록'] || [],
        'monthly': d.monthly || {},
      };
    }
    for (const [name, d] of Object.entries(currentSummary)) {
      if (!result[name] && d['정산대상']) {
        result[name] = {
          '건수': 0, '수량': 0, '누적수량': 0,
          '현재단가': 20000, '금액': 0,
          '정산대상': true, '현재상태': d['현재상태'] || '',
          '체험횟수': d['체험횟수'] ?? null,
          '협찬원가': d['협찬원가'] ?? null,
          '체험월목록': d['체험월목록'] || [],
        };
      }
    }
    return result;
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
    const pa = (gData || {}).profit_analysis || null;

    if (!month) {
      // 전체 모드: 즉시 현재월 표시 후 누적 업데이트
      const r = gData.revenue     || {};
      const f = gData.mail_funnel || {};
      updateKPIs(r, f);
      setKPISubs(r, f);
      renderProfitKPIs(pa, null);
      renderFunnelBars(f);
      renderDonutChart(gData.inf_status || {});
      renderInfluencerGrid(gData.settlement_summary || {}, null);
      renderContribTable(pa, null, null, gData.settlement_summary);
      renderStoreSplit(null);

      buildAllTimeData().then(({ revenue, infMap }) => {
        updateKPIs(revenue, f);
        setKPISubs(revenue, f);
        renderInfluencerGrid(buildAllTimeSummary(infMap, gData.settlement_summary || {}), null);
      }).catch(() => {});
      return;
    }

    // 월별 모드
    if (!hCache[month]) {
      try {
        hCache[month] = await fetchData('data/history/' + month + '.json');
      } catch (e) {
        console.error('[필터] history 로드 실패:', month, e.message);
        return;
      }
    }
    const h  = hCache[month];
    const mf = (gData.mail_funnel_by_month || {})[month] || {};

    updateKPIs(
      { gross_revenue: h.gross_revenue, net_profit: h.net_profit,
        order_count: h.order_count, unit_count: h.unit_count },
      { reply_rate: mf.reply_rate || h.reply_rate,
        exp_rate:   mf.exp_rate   || h.exp_rate,
        ad_rate:    mf.ad_rate    || h.ad_rate,
        total_sent: mf.sent       || h.total_sent }
    );
    clearKPISubs();
    renderProfitKPIs(pa, month);
    renderFunnelBars({
      total_sent:    mf.sent    || h.total_sent    || 0,
      replied:       mf.replied || h.replied        || 0,
      meeting_total: mf.meeting || h.meeting_total  || 0,
      exp_total:     mf.exp     || h.exp_total      || 0,
      ad_total:      (gData.ad_by_month || {})[month] || mf.ad || 0,
    });
    renderDonutChart(h.inf_status || {});
    renderInfluencerGrid(historyToSummary(h.influencers || {}, gData.settlement_summary), month);
    renderContribTable(pa, month, h, gData.settlement_summary);
    renderStoreSplit(month);
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

    const r  = gData.revenue     || {};
    const f  = gData.mail_funnel || {};
    const t  = gData.trends      || {};
    const pa = gData.profit_analysis || null;

    if (gData.generated_at) set('generated-at', gData.generated_at.replace('T', ' '));


    renderFilterButtons(t.months || []);

    // 즉시 렌더 (동기)
    updateKPIs(r, f);
    setKPISubs(r, f);
    renderProfitKPIs(pa, null);
    renderFunnelBars(f);
    renderDonutChart(gData.inf_status || {});

    // 인플루언서 카운트
    const st = gData.inf_status || {};
    const stTotal  = Object.values(st).reduce((s, v) => s + v, 0);
    // 광고 진행 예정 인원: 현재 상태가 '광고예정'인 인플루언서 합산 (광고완료 제외)
    const adInfCount = Object.entries(st).reduce((s, [k, v]) => s + (k.includes('광고예정') ? v : 0), 0);
    const lbl = el('inf-count-label');
    if (lbl) lbl.innerHTML =
      `<span style="background:var(--text1);color:var(--bg);font-size:10px;font-weight:700;` +
      `padding:2px 10px;border-radius:10px">` +
      `광고 ${adInfCount}<span style="font-weight:400;opacity:0.55"> / ${stTotal}명</span></span>`;

    renderInfluencerGrid(gData.settlement_summary || {}, null);
    renderFunnelMonthlyTable(gData.mail_funnel_by_month || {}, gData.current_month);

    if (t.months && t.months.length > 0) {
      renderTrendChart(t);
      renderRevenueChart(t);
    }

    renderProfitChart(pa);
    renderContribTable(pa, null, null, gData.settlement_summary);

    // 탭 · 요약 · 제품별 · 스토어 분리 렌더
    ensureProductPanels();
    renderSummaryFilter();
    renderSummary(null);
    renderStoreSplit(null);
    renderTabs();

    // 전체 집계로 업데이트 (비동기, 실패해도 화면 유지)
    buildAllTimeData().then(({ revenue, infMap }) => {
      updateKPIs(revenue, f);
      setKPISubs(revenue, f);
      renderInfluencerGrid(buildAllTimeSummary(infMap, gData.settlement_summary || {}), null);
    }).catch(() => {});
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

  // ── 도넛 차트 ─────────────────────────────────────────────────────────────
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
        datasets: [{ data: cfg.map(([k]) => infStatus[k] || 0), backgroundColor: cfg.map(([,, c]) => c), borderWidth: 0 }],
      },
      options: {
        cutout: '62%',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => ` ${c.label}: ${c.raw}명 (${Math.round(c.raw / total * 100)}%)` } },
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

  // ── 인플루언서 카드 그리드 ────────────────────────────────────────────────
  function renderInfluencerGrid(summary, month) {
    const grid = el('inf-grid');
    if (!grid) return;

    const infCum = ((gData || {}).profit_analysis || {}).influencer_cumulative || {};
    const amountLabel = month ? '당월 정산액' : '누적 정산액';

    let items = Object.entries(summary).map(([name, d]) => ({ name, ...d }));

    if (month) {
      // 월별 필터: 해당 월에 수량이 있는 인플루언서만, 수량 내림차순
      items = items.filter(d => (d['수량'] || 0) > 0);
    }
    items.sort((a, b) => (b['수량'] || 0) - (a['수량'] || 0));

    // 이번 달 정산 대상 판별 (건수 > 0인 정산대상)
    const curMonth     = (gData || {}).settlement_month;
    const curMonthLabel = curMonth ? curMonth + '월' : '';
    const curSummary   = (gData || {}).settlement_summary || {};
    const thisMonthTargets = new Set(
      Object.entries(curSummary)
        .filter(([, d]) => d['정산대상'] && (d['건수'] || 0) > 0)
        .map(([name]) => name)
    );

    grid.innerHTML = items.map(item => {
      const isTarget = item['정산대상'];
      const tag  = isTarget ? 'a' : 'div';
      const href = isTarget ? `href="influencer.html?name=${encodeURIComponent(item.name)}"` : '';

      // 전체 필터: 이번달 정산대상만 badge, 나머지는 표기 없음
      // 월별 필터: 정산대상 / 기타일반 구분 표기
      let badge = '';
      if (month) {
        badge = isTarget
          ? `<span class="pill pill-target">정산대상</span>`
          : `<span class="pill pill-general">기타/일반</span>`;
      } else if (thisMonthTargets.has(item.name)) {
        badge = `<span class="pill pill-target">${curMonthLabel} 정산대상</span>`;
      }

      // 기여수익 표시
      let contribHtml = '';
      if (!month) {
        const c = infCum[item.name];
        const mData = item['monthly'] || {};
        const mEntries = Object.entries(mData).sort(([a], [b]) => a.localeCompare(b)).filter(([, d]) => d.qty > 0);
        const monthlyRows = mEntries.map(([m, d]) =>
          `<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--text2);padding:1px 0">
            <span>${monthLabel(m)}</span>
            <span>${d.qty}개${d.amount ? ' · ' + money(d.amount) : ''}</span>
          </div>`
        ).join('');
        contribHtml = `
          ${monthlyRows ? `<div style="margin-top:6px;padding-top:5px;border-top:0.5px solid var(--border)">
            <span class="stat-lbl" style="display:block;margin-bottom:3px">월별 현황</span>
            ${monthlyRows}
          </div>` : ''}
          ${c && (c.settlement || c.contribution) ? `<div style="margin-top:6px;padding-top:5px;border-top:0.5px solid var(--border)">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span class="stat-lbl">누적 정산금액</span>
              <span class="stat-val" style="color:#3B6D11;font-weight:700">${money(c.settlement ?? 0)}</span>
            </div>
            ${item['협찬원가'] > 0 ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
              <span class="stat-lbl" style="font-size:10px;color:var(--text3)">누적 협찬원가</span>
              <span style="font-size:10px;color:#C0392B">−${money(item['협찬원가'])}</span>
            </div>` : ''}
            ${c.contribution != null ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
              <span class="stat-lbl" style="font-size:10px;color:var(--text3)">기여수익</span>
              <span style="font-size:10px;color:var(--text3)">${money(c.contribution)}</span>
            </div>` : ''}
          </div>` : ''}`;
      } else {
        const qty = item['수량'] ?? 0;
        if (qty > 0) {
          const mCum = item['누적수량'] ?? 0;
          const mPrevCum = Math.max(mCum - qty, 0);
          let settlementAmt = 0;
          if (isTarget) {
            for (let q = mPrevCum; q < mCum; q++) settlementAmt += tierPrice(q + 1);
          }
          // 기여수익 = 매출 − 원가(3.6만×qty) − 정산액 − 해당월 협찬원가
          const expMonths = item['체험월목록'] || [];
          const monthSponsorCost = expMonths.filter(m => m === month).length * 40000;
          const grossRev = qty * (isTarget ? GROSS_PRICE_INF : GROSS_PRICE_GEN);
          const mc = grossRev - qty * COGS - settlementAmt - monthSponsorCost;
          if (settlementAmt > 0 || mc > 0) {
            const sponsorLine = monthSponsorCost > 0
              ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                  <span class="stat-lbl" style="font-size:10px;color:var(--text3)">협찬원가</span>
                  <span style="font-size:10px;color:#C0392B">−${money(monthSponsorCost)}</span>
                </div>` : '';
            contribHtml = `
            <div style="margin-top:6px;padding-top:5px;border-top:0.5px solid var(--border)">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span class="stat-lbl">${monthLabel(month)} 정산금액</span>
                <span class="stat-val" style="color:#3B6D11;font-weight:700">${money(settlementAmt)}</span>
              </div>
              ${sponsorLine}
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px">
                <span class="stat-lbl" style="font-size:10px;color:var(--text3)">기여수익</span>
                <span style="font-size:10px;color:var(--text3)">${money(mc)}</span>
              </div>
            </div>`;
          }
        }
      }

      // 체험 횟수: JSON 필드 우선, 없으면 현재상태 문자열에서 파싱
      const expCount = item['체험횟수'] != null
        ? item['체험횟수']
        : (() => { const m = (item['현재상태'] || '').match(/^(\d+)차/); return m ? parseInt(m[1], 10) : 0; })();
      const sponsorCost = item['협찬원가'] != null ? item['협찬원가'] : expCount * 40000;

      // 정산 금액 / 티어 섹션
      let statsHtml;
      if (isTarget) {
        const cum     = item['누적수량'] ?? 0;
        const qty     = item['수량'] ?? 0;
        const prevCum = Math.max(cum - qty, 0);
        const tiers   = qty > 0 ? tierBreakdownRange(prevCum, cum) : [];
        const isMulti = tiers.length > 1;
        const tierTotal = tiers.reduce((s, t) => s + t.qty * t.price, 0);

        const rows = tiers.map(t =>
          `<div class="tier-row">
            <span>${t.qty}개 × ${money(t.price)}${t.price > 20000 ? '<span class="tier-up">▲</span>' : ''}</span>
            <span class="stat-val">${money(t.qty * t.price)}</span>
          </div>`).join('');
        const totalRow = isMulti
          ? `<div class="tier-total"><span style="color:var(--text3)">합계</span><span class="stat-val">${money(tierTotal)}</span></div>`
          : '';
        const sponsorRow = sponsorCost > 0
          ? `<div class="tier-row" style="margin-top:4px;color:var(--text3)">
               <span>협찬원가 ${expCount}회 × ₩40,000</span>
               <span style="color:#C0392B">−${money(sponsorCost)}</span>
             </div>`
          : '';

        statsHtml = `
          <div style="margin-top:8px">
            <span class="stat-lbl">${amountLabel}</span>
            <div class="tier-section">${rows || '<span style="color:var(--text3);font-size:11px">-</span>'}${totalRow}${sponsorRow}</div>
          </div>
          <div class="inf-card-stats" style="grid-template-columns:1fr 1fr;margin-top:6px">
            <div><span class="stat-lbl">수량(주문건수)</span><span class="stat-val">${item['수량'] || 0}개(${item['건수'] || 0}건)</span></div>
            <div><span class="stat-lbl">누적수량</span><span class="stat-val">${cum}개</span></div>
          </div>`;
      } else {
        const genQty = item['수량'] ?? 0;
        const genAmt = item['금액'];
        const amtRow = genQty > 0
          ? `<div class="tier-row" style="margin-top:4px"><span>${genQty}개 × ₩84,000</span><span class="stat-val">${money(genAmt)}</span></div>`
          : `<span style="color:var(--text3);font-size:11px">-</span>`;
        statsHtml = `
          <div style="margin-top:8px">
            <span class="stat-lbl">${amountLabel}</span>
            <div class="tier-section">${amtRow}</div>
          </div>
          <div class="inf-card-stats" style="grid-template-columns:1fr 1fr;margin-top:6px">
            <div><span class="stat-lbl">주문건수</span><span class="stat-val">${item['건수'] || 0}건</span></div>
            <div><span class="stat-lbl">수량</span><span class="stat-val">${genQty}개</span></div>
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
          ${contribHtml}
        </${tag}>`;
    }).join('');
  }

  // ── 퍼널 월별 테이블 ──────────────────────────────────────────────────────
  function renderFunnelMonthlyTable(byMonth, currentMonth) {
    const c = el('funnel-monthly-table');
    if (!c) return;
    const months = Object.keys(byMonth).sort();
    if (!months.length) {
      c.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:4px 0">데이터 없음</div>';
      return;
    }
    function cell(count, rate) {
      if (!count && !rate) return '<td>-</td>';
      return `<td><span class="fmonth-cnt">${Number(count).toLocaleString()}</span><span class="fmonth-pct">(${(rate * 100).toFixed(1)}%)</span></td>`;
    }
    const body = months.map(m => {
      const d = byMonth[m];
      const isCur = m === currentMonth;
      return `<tr${isCur ? ' class="fmonth-cur"' : ''}>
        <td>${monthLabel(m)}${isCur ? ' ★' : ''}</td>
        <td><span class="fmonth-cnt">${Number(d.sent).toLocaleString()}</span></td>
        ${cell(d.replied, d.reply_rate)}
        ${cell(d.meeting, d.meeting_rate)}
        ${cell(d.exp,     d.exp_rate)}
        ${cell(d.ad,      d.ad_rate)}
      </tr>`;
    }).join('');
    c.innerHTML = `<table class="fmonth-table">
      <thead><tr><th>월</th><th>발송</th><th>응답</th><th>미팅</th><th>체험</th><th>광고</th></tr></thead>
      <tbody>${body}</tbody>
    </table>`;
  }

  // ── 추세 차트 ─────────────────────────────────────────────────────────────
  function renderTrendChart(t) {
    const ctx = el('trend-chart');
    if (!ctx) return;
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: t.months.map(monthLabel),
        datasets: [
          { label: '응답률',    data: t.reply_rate.map(v => +(v * 100).toFixed(1)), borderColor: '#85B7EB', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '체험전환율', data: t.exp_rate.map(v => +(v * 100).toFixed(1)),  borderColor: '#7F77DD', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '광고수락률', data: t.ad_rate.map(v => +(v * 100).toFixed(1)),   borderColor: '#97C459', tension: 0.4, fill: false, pointRadius: 3 },
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

  // ── 영업이익 차트 ─────────────────────────────────────────────────────────
  function renderProfitChart(pa) {
    const ctx = el('profit-chart');
    if (!ctx || !pa || !pa.monthly) return;
    const months    = Object.keys(pa.monthly).sort();
    const labels    = months.map(monthLabel);
    const grossRevs = months.map(m => pa.monthly[m].gross_revenue     || 0);
    const opProfits = months.map(m => pa.monthly[m].operating_profit  || 0);
    const opRates   = months.map(m => +((pa.monthly[m].operating_profit_rate || 0) * 100).toFixed(1));
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { type: 'bar',  label: '매출',    data: grossRevs,  backgroundColor: 'rgba(127,119,221,0.25)', yAxisID: 'y' },
          { type: 'bar',  label: '영업이익', data: opProfits,  backgroundColor: 'rgba(97,176,89,0.7)',   yAxisID: 'y' },
          { type: 'line', label: '이익률',   data: opRates,    borderColor: '#EF9F27', tension: 0.4, fill: false, yAxisID: 'y1', pointRadius: 3 },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } },
          tooltip: { callbacks: { label: c => c.dataset.yAxisID === 'y1'
            ? ` ${c.dataset.label}: ${c.parsed.y}%`
            : ` ${c.dataset.label}: ₩${Number(c.parsed.y).toLocaleString('ko-KR')}` } },
        },
        scales: {
          x:  { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y:  { grid: { color: '#E5E3D6' },
                ticks: { font: { size: 10 }, callback: v => '₩' + (v / 10000).toFixed(0) + '만' },
                title: { display: true, text: '금액 (₩)', font: { size: 10 }, color: '#A8A69C' } },
          y1: { position: 'right', grid: { drawOnChartArea: false },
                ticks: { font: { size: 10 }, callback: v => v + '%' },
                title: { display: true, text: '이익률', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── 기여수익 테이블 ────────────────────────────────────────────────────────
  function renderContribTable(pa, month, h, settlementSummary) {
    const c = el('contrib-table');
    if (!c) return;

    let items = [], totalQty = 0;

    if (month && h) {
      totalQty = h.unit_count || 0;
      const ss = settlementSummary || {};
      let knownQty = 0;
      items = Object.entries(h.influencers || {}).map(([name, d]) => {
        const qty     = d.qty || 0;
        const isGen   = d.is_general || false;
        const cum     = d.cumulative_qty || 0;
        const prevCum = Math.max(cum - qty, 0);
        let settlementAmt = 0;
        if (!isGen) {
          for (let q = prevCum; q < cum; q++) settlementAmt += tierPrice(q + 1);
        }
        let sponsorCost = d.sponsor_cost_this_month || 0;
        if (!sponsorCost) {
          const expMonths = (ss[name] || {})['체험월목록'] || [];
          sponsorCost = expMonths.filter(m => m === month).length * 40000;
        }
        const grossRev = qty * (isGen ? GROSS_PRICE_GEN : GROSS_PRICE_INF);
        const contribution = grossRev - qty * COGS - settlementAmt - sponsorCost;
        knownQty += qty;
        return { name, qty, settlement: settlementAmt, sponsorCost, contribution, isGen };
      });
      const miscQty = totalQty - knownQty;
      if (miscQty > 0) items.push({ name: '(기타/미등재)', qty: miscQty, settlement: 0, sponsorCost: 0, contribution: miscQty * (GROSS_PRICE_GEN - COGS), isGen: true });
    } else {
      if (!pa) { c.innerHTML = ''; return; }
      // 누적 모드: build_kpi.py가 이미 원가·협찬원가 차감한 기여수익을 inf_cum에 담음
      const ss = settlementSummary || {};
      items = Object.entries(pa.influencer_cumulative || {}).map(([name, d]) => ({
        name,
        qty: d.qty || 0,
        settlement: d.settlement || 0,
        sponsorCost: (ss[name] || {})['협찬원가'] || 0,
        contribution: d.contribution || 0,
        isGen: !d.settlement,
      }));
      totalQty = Object.values(pa.monthly || {}).reduce((s, m) => s + (m.unit_count || 0), 0);
    }

    items.sort((a, b) => b.contribution - a.contribution);
    if (!items.length) { c.innerHTML = '<div style="font-size:11px;color:var(--text3)">데이터 없음</div>'; return; }

    const totalContrib   = items.reduce((s, i) => s + (i.contribution || 0), 0);
    const totalSponsor   = items.reduce((s, i) => s + (i.sponsorCost || 0), 0);
    const totalSettlement = items.reduce((s, i) => s + (i.settlement || 0), 0);
    const laborCost      = totalQty * 10000;
    const laborLabel     = month ? monthLabel(month) : '전체 누적';
    const showSponsor    = totalSponsor > 0;

    const rows = items.map(i => `<tr>
      <td>${i.name}</td>
      <td>${i.qty}개</td>
      <td>${i.settlement ? money(i.settlement) : '<span style="color:var(--text3)">-</span>'}</td>
      ${showSponsor ? `<td style="color:#C0392B">${i.sponsorCost ? '−' + money(i.sponsorCost) : '<span style="color:var(--text3)">-</span>'}</td>` : ''}
      <td style="color:#3B6D11;font-weight:500">${money(i.contribution)}</td>
    </tr>`).join('');

    c.innerHTML = `
      <table class="contrib-tbl">
        <thead><tr><th>인플루언서</th><th>수량</th><th>정산금액</th>${showSponsor ? '<th>협찬원가</th>' : ''}<th>기여수익</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><td>합계</td><td>${totalQty}개</td><td>${totalSettlement ? money(totalSettlement) : ''}</td>${showSponsor ? `<td style="color:#C0392B">${totalSponsor ? '−' + money(totalSponsor) : ''}</td>` : ''}<td>${money(totalContrib)}</td></tr></tfoot>
      </table>
      <div style="margin-top:6px;text-align:right;font-size:10px;color:var(--text3)">
        눈길 인건비 (${laborLabel}): ${money(laborCost)} (${totalQty}개 × ₩10,000)
      </div>`;
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
    set('inf-unit-price', money(tierPrice(cum)));

    const monthly = data.monthly_orders || [];
    const ctx = el('monthly-chart');
    if (ctx && monthly.length) {
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: monthly.map(m => monthLabel(m.month)),
          datasets: [{ label: '수량', data: monthly.map(m => m.qty), backgroundColor: 'rgba(127,119,221,0.6)' }],
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

  // ── 탭 시스템 (드래그 정렬 + localStorage 저장) ─────────────────────────────
  const TAB_ORDER_KEY = 'dashTabOrder_v1';
  let _activeTab = null;

  function getProducts() {
    return (gData && Array.isArray(gData.products) && gData.products.length)
      ? gData.products
      : [{ key: '흑염소', label: '흑염소', icon: '🐐', default: true }];
  }
  function defaultProductKey() {
    const p = getProducts().find(x => x.default);
    return p ? p.key : (getProducts()[0] || {}).key;
  }
  function tabDefList() {
    return [{ key: 'summary', label: 'Summary', icon: '📊' }]
      .concat(getProducts().map(p => ({ key: p.key, label: p.label, icon: p.icon || '📦' })));
  }
  function loadTabOrder(keys) {
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem(TAB_ORDER_KEY) || '[]'); } catch (e) {}
    const valid = saved.filter(k => keys.includes(k));
    return valid.concat(keys.filter(k => !valid.includes(k)));
  }
  function saveTabOrder(order) {
    try { localStorage.setItem(TAB_ORDER_KEY, JSON.stringify(order)); } catch (e) {}
  }

  function renderTabs() {
    const bar = el('tabbar');
    if (!bar) return;
    const defs = tabDefList();
    const keyMap = {}; defs.forEach(d => keyMap[d.key] = d);
    const order  = loadTabOrder(defs.map(d => d.key));

    bar.innerHTML = order.map(k => {
      const d = keyMap[k]; if (!d) return '';
      return `<div class="tab" draggable="true" data-tab="${k}"><span class="tab-icon">${d.icon}</span>${d.label}</div>`;
    }).join('');

    let dragEl = null;
    bar.querySelectorAll('.tab').forEach(t => {
      t.addEventListener('click', () => switchTab(t.dataset.tab));
      t.addEventListener('dragstart', e => { dragEl = t; t.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; });
      t.addEventListener('dragend',   () => { t.classList.remove('dragging'); bar.querySelectorAll('.tab').forEach(x => x.classList.remove('dragover')); });
      t.addEventListener('dragover',  e => { e.preventDefault(); if (t !== dragEl) t.classList.add('dragover'); });
      t.addEventListener('dragleave', () => t.classList.remove('dragover'));
      t.addEventListener('drop', e => {
        e.preventDefault(); t.classList.remove('dragover');
        if (!dragEl || dragEl === t) return;
        const tabs = Array.from(bar.querySelectorAll('.tab'));
        if (tabs.indexOf(dragEl) < tabs.indexOf(t)) t.after(dragEl); else t.before(dragEl);
        saveTabOrder(Array.from(bar.querySelectorAll('.tab')).map(x => x.dataset.tab));
      });
    });

    switchTab(_activeTab && order.includes(_activeTab) ? _activeTab : order[0]);
  }

  function switchTab(key) {
    _activeTab = key;
    document.querySelectorAll('#tabbar .tab').forEach(t => t.classList.toggle('active', t.dataset.tab === key));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.tab === key));
    // 숨겨진 패널에서 0 크기로 그려진 Chart.js 차트를 레이아웃 완료 후 처리
    // 탭 전환 시 보이는 패널의 Chart.js 차트를 리사이즈 (ResizeObserver 보조)
    try { window.dispatchEvent(new Event('resize')); } catch (e) {}
    // 차트는 패널이 보이는 시점에 새로 생성해야 첫 draw가 올바른 폭으로 됨
    if (key === 'summary' && gData) {
      setTimeout(() => { if (_activeTab === 'summary') renderSummaryChart(); }, 80);
    } else if (gData && productKeysExtra().includes(key)) {
      setTimeout(() => { if (_activeTab === key) renderProductChart(key); }, 80);
    }
  }

  // ── 제품별 시계열 (by_product_by_month) ────────────────────────────────────
  function productSeries(productKey) {
    const bpm = ((gData || {}).trends || {}).by_product_by_month || {};
    const months = Object.keys(bpm).sort();
    const rows = []; let totQty = 0, totRev = 0, totOrd = 0;
    months.forEach(m => {
      const d = (bpm[m] || {})[productKey];
      if (d) { rows.push({ month: m, ...d }); totQty += d.qty || 0; totRev += d.gross_revenue || 0; totOrd += d.order_count || 0; }
    });
    return { rows, totQty, totRev, totOrd };
  }

  // ── 기타 제품 패널 (흑염소와 동일 구성: 필터 + KPI + 추이 차트 + 표) ──────────
  const _prodCharts = {};
  const _prodMonth  = {};

  function productKeysExtra() {
    const defKey = defaultProductKey();
    return getProducts().filter(p => p.key !== defKey).map(p => p.key);
  }

  function ensureProductPanels() {
    const host = el('panels-extra');
    if (!host) return;
    const others = getProducts().filter(p => p.key !== defaultProductKey());
    host.innerHTML = others.map(p => `
      <section class="tab-panel" data-tab="${p.key}" id="panel-${p.key}">
        <div class="filter-row" data-pk="filter"></div>
        <div class="kpi-grid" style="grid-template-columns:repeat(4,minmax(0,1fr))">
          <div class="kpi-card"><div class="kpi-lbl">${p.label} 매출</div><div class="kpi-val" data-pk="rev">-</div><div class="kpi-sub" data-pk="rev-sub"></div></div>
          <div class="kpi-card"><div class="kpi-lbl">판매량</div><div class="kpi-val" data-pk="qty">-</div><div class="kpi-sub" data-pk="qty-sub"></div></div>
          <div class="kpi-card"><div class="kpi-lbl">주문수</div><div class="kpi-val" data-pk="ord">-</div><div class="kpi-sub" data-pk="ord-sub"></div></div>
          <div class="kpi-card"><div class="kpi-lbl">수익</div><div class="kpi-val" data-pk="profit">-</div><div class="kpi-sub" data-pk="profit-sub"></div></div>
        </div>
        <div class="card mb12" data-pk="chartcard"><div class="slbl">월별 매출 · 판매량</div><canvas data-pk="chart"></canvas></div>
        <div class="card mb12" data-pk="tablecard"><div class="slbl">월별 판매 내역</div><div data-pk="table"></div></div>
        <div data-pk="empty"></div>
      </section>`).join('');
    others.forEach(p => {
      const panel = document.getElementById('panel-' + p.key);
      const fc = panel && panel.querySelector('[data-pk="filter"]');
      if (fc) fc.addEventListener('click', e => {
        const btn = e.target.closest('.filter-chip');
        if (!btn) return;
        _prodMonth[p.key] = btn.dataset.month || null;
        renderProductView(p.key);
      });
      renderProductView(p.key);
    });
  }

  function productMonths(key) {
    const bpm = ((gData || {}).trends || {}).by_product_by_month || {};
    return Object.keys(bpm).filter(m => bpm[m] && bpm[m][key]).sort();
  }

  function renderProductView(key, month) {
    const p = getProducts().find(x => x.key === key);
    const panel = document.getElementById('panel-' + key);
    if (!p || !panel) return;
    if (month === undefined) month = _prodMonth[key] || null;
    _prodMonth[key] = month || null;
    const bpm = ((gData || {}).trends || {}).by_product_by_month || {};
    const months = productMonths(key);
    const q = s => panel.querySelector(`[data-pk="${s}"]`);

    const fc = q('filter');
    if (fc) fc.innerHTML = months.length
      ? [''].concat(months.slice().reverse()).map(m =>
          `<button class="filter-chip${(m || null) === (month || null) ? ' active' : ''}" data-month="${m}">${m ? monthLabel(m) : '전체'}</button>`).join('')
      : '';

    const cc = q('chartcard'), tc = q('tablecard');
    if (!months.length) {
      ['rev', 'qty', 'ord'].forEach(k => { const e = q(k); if (e) e.textContent = '-'; });
      ['rev-sub', 'qty-sub', 'ord-sub'].forEach(k => { const e = q(k); if (e) e.textContent = ''; });
      if (cc) cc.classList.add('hidden');
      if (tc) tc.classList.add('hidden');
      q('empty').innerHTML = `<div class="empty-state"><div class="es-title">${p.icon || ''} ${p.label} 데이터가 아직 없어요</div>판매가 시작되면 주문 반영 시 자동으로 집계됩니다.</div>`;
      return;
    }
    q('empty').innerHTML = '';
    if (cc) cc.classList.remove('hidden');
    if (tc) tc.classList.remove('hidden');

    const sel = month ? [month] : months;
    let totQty = 0, totRev = 0, totOrd = 0, totProfit = 0;
    sel.forEach(m => { const d = bpm[m][key] || {}; totQty += d.qty || 0; totRev += d.gross_revenue || 0; totOrd += d.order_count || 0; totProfit += d.net_profit || 0; });
    const scope = month ? monthLabel(month) : '전체 기간';
    q('rev').textContent = totRev ? money(totRev) : (totQty ? '집계예정' : '—');
    q('qty').textContent = totQty + '개';
    q('ord').textContent = totOrd + '건';
    q('rev-sub').textContent = scope;
    q('qty-sub').textContent = month ? scope : ('월평균 ' + Math.round(totQty / months.length) + '개');
    q('ord-sub').textContent = scope;
    const pf = q('profit');
    if (pf) {
      pf.textContent = totProfit ? money(totProfit) : (totRev ? '집계예정' : '—');
      pf.style.color = totProfit > 0 ? '#3B6D11' : '';
      const ps = q('profit-sub'); if (ps) ps.textContent = scope;
    }

    const body = months.map(m => {
      const d = bpm[m][key] || {};
      const cur = (m === month) ? ' class="fmonth-cur"' : '';
      return `<tr${cur}><td>${monthLabel(m)}${m === month ? ' ★' : ''}</td><td>${d.qty || 0}개</td><td>${d.order_count || 0}건</td><td>${d.gross_revenue ? money(d.gross_revenue) : '-'}</td><td style="color:#3B6D11">${d.net_profit ? money(d.net_profit) : '-'}</td></tr>`;
    }).join('');
    q('table').innerHTML = `<table class="fmonth-table"><thead><tr><th>월</th><th>판매량</th><th>주문수</th><th>매출</th><th>수익</th></tr></thead><tbody>${body}</tbody></table>`;

    renderProductChart(key);
  }

  function renderProductChart(key) {
    const panel = document.getElementById('panel-' + key);
    if (!panel) return;
    const ctx = panel.querySelector('[data-pk="chart"]');
    if (!ctx) return;
    const card = ctx.closest('.card');
    const cw = card ? card.clientWidth : 0;
    if (cw <= 0) return;  // 숨김 상태면 탭 표시 시점에 생성
    if (_prodCharts[key]) { _prodCharts[key].destroy(); _prodCharts[key] = null; }
    const bpm = ((gData || {}).trends || {}).by_product_by_month || {};
    const months = productMonths(key);
    if (!months.length) return;
    ctx.width = Math.max(cw - 28, 300);
    ctx.height = 220;
    const labels = months.map(monthLabel);
    const rev = months.map(m => (bpm[m][key] || {}).gross_revenue || 0);
    const qty = months.map(m => (bpm[m][key] || {}).qty || 0);
    _prodCharts[key] = new Chart(ctx, {
      data: { labels, datasets: [
        { type: 'bar',  label: '매출',   data: rev, backgroundColor: 'rgba(127,119,221,0.5)', yAxisID: 'y',  order: 2 },
        { type: 'line', label: '판매량', data: qty, borderColor: '#EF9F27', backgroundColor: '#EF9F27', tension: 0.4, fill: false, yAxisID: 'y1', pointRadius: 3, order: 1 },
      ] },
      options: {
        responsive: false, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } },
          tooltip: { callbacks: { label: c => c.dataset.yAxisID === 'y1' ? ` ${c.dataset.label}: ${c.parsed.y}개` : ` ${c.dataset.label}: ₩${Number(c.parsed.y).toLocaleString('ko-KR')}` } },
        },
        scales: {
          x:  { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y:  { beginAtZero: true, grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 }, callback: v => '₩' + (v / 10000).toFixed(0) + '만' }, title: { display: true, text: '매출 (₩)', font: { size: 10 }, color: '#A8A69C' } },
          y1: { position: 'right', beginAtZero: true, grid: { drawOnChartArea: false }, ticks: { font: { size: 10 }, callback: v => v + '개' }, title: { display: true, text: '판매량', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── Summary 탭 (전체/월별 필터) ─────────────────────────────────────────────
  let _sumMonth = null;  // null = 전체

  function renderSummaryFilter() {
    const c = el('summary-month-filter');
    if (!c) return;
    const bpm = ((gData || {}).trends || {}).by_product_by_month || {};
    const months = Object.keys(bpm).sort().reverse();
    c.innerHTML = [''].concat(months).map(m =>
      `<button class="filter-chip${(m || null) === _sumMonth ? ' active' : ''}" data-month="${m}">${m ? monthLabel(m) : '전체'}</button>`
    ).join('');
    c.onclick = e => {
      const btn = e.target.closest('.filter-chip');
      if (!btn) return;
      _sumMonth = btn.dataset.month || null;
      c.querySelectorAll('.filter-chip').forEach(b => b.classList.toggle('active', b === btn));
      renderSummary(_sumMonth);
    };
  }

  function renderSummary(month) {
    if (month === undefined) month = _sumMonth;
    _sumMonth = month || null;
    const bpm    = ((gData || {}).trends || {}).by_product_by_month || {};
    const trends = (gData || {}).trends || {};
    const prods  = getProducts();
    const order  = prods.map(p => p.key);

    const agg = {};
    prods.forEach(p => { agg[p.key] = { qty: 0, rev: 0, ord: 0, prof: 0, active: false }; });
    const scanMonths = month ? [month] : Object.keys(bpm);
    scanMonths.forEach(m => {
      const md = bpm[m] || {};
      Object.keys(md).forEach(k => {
        if (!agg[k]) { agg[k] = { qty: 0, rev: 0, ord: 0, prof: 0, active: false }; if (!order.includes(k)) order.push(k); }
        agg[k].qty += md[k].qty || 0; agg[k].rev += md[k].gross_revenue || 0; agg[k].ord += md[k].order_count || 0;
        agg[k].prof += md[k].net_profit || 0;
        if ((md[k].qty || 0) > 0) agg[k].active = true;
      });
    });

    const totalUnits  = order.reduce((s, k) => s + agg[k].qty, 0);
    const totalOrders = order.reduce((s, k) => s + agg[k].ord, 0);
    const totalRev    = order.reduce((s, k) => s + agg[k].rev, 0);
    // 흑염소 수익(정산모델, 스냅샷 top-level) + 그 외 제품 수익(by_product net_profit)
    let baseProfit;
    if (month) {
      const idx = (trends.months || []).indexOf(month);
      baseProfit = idx >= 0 ? ((trends.net_profit || [])[idx] || 0) : 0;
    } else {
      baseProfit = (trends.net_profit || []).reduce((s, v) => s + (v || 0), 0);
    }
    const totalProfit = baseProfit + order.reduce((s, k) => s + (agg[k].prof || 0), 0);
    const activeCnt  = order.filter(k => agg[k].active).length;
    const scopeLabel = month ? monthLabel(month) : '전체 기간';

    set('summary-scope-label', '· ' + scopeLabel);
    set('sum-revenue', money(totalRev));
    set('sum-units',   totalUnits + '개');
    set('sum-profit',  money(totalProfit));
    set('sum-revenue-sub', totalOrders + '건 주문 · ' + scopeLabel);
    set('sum-units-sub',   activeCnt + '개 제품' + (month ? ' 판매' : ' 판매중'));
    set('sum-profit-sub',  (totalProfit > 0 ? '흑자' : totalProfit < 0 ? '적자' : '') + ' · ' + scopeLabel);
    const pe = el('sum-profit'); if (pe) pe.style.color = totalProfit > 0 ? '#3B6D11' : totalProfit < 0 ? '#A32D2D' : '';
    // 추이 차트는 Summary 탭이 보이는 시점(switchTab)에 전체 기간 기준으로 생성한다

    // 제품별 카드 (매출 있으면 매출 비중, 없으면 수량 비중)
    const useRev = totalRev > 0;
    const denom  = (useRev ? totalRev : totalUnits) || 1;
    const labelMap = {}; prods.forEach(p => labelMap[p.key] = p);
    const grid = el('summary-prod-grid');
    if (grid) {
      grid.innerHTML = order.map(k => {
        const p = labelMap[k] || { label: k, icon: '📦' };
        const a = agg[k];
        const share = ((useRev ? a.rev : a.qty) / denom * 100);
        const revStr = a.rev ? money(a.rev) : (a.qty ? '집계예정' : '—');
        return `<div class="prod-card">
          <div class="prod-card-head"><span class="tab-icon">${p.icon || '📦'}</span><span class="prod-card-name">${p.label}</span></div>
          <div class="prod-card-rev">${revStr}</div>
          <div class="prod-card-sub">${a.qty}개 · ${a.ord}건${a.prof ? ' · 수익 <span style="color:#3B6D11">' + money(a.prof) + '</span>' : (a.active ? '' : ' · 대기')}</div>
          <div class="prod-bar-track"><div class="prod-bar-fill" style="width:${Math.min(share,100).toFixed(1)}%"></div></div>
          <div class="prod-card-sub">${useRev ? '매출' : '수량'} 비중 ${share.toFixed(1)}%</div>
        </div>`;
      }).join('');
    }

    // 제품 · 월별 추이 테이블 (항상 전체 월 표시, 선택 월은 하이라이트)
    const months = Object.keys(bpm).sort();
    const tbl = el('summary-monthly-table');
    if (tbl) {
      if (!months.length) { tbl.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:4px 0">데이터 없음</div>'; }
      else {
        // 컬럼: 전체 기간 기준 한 번이라도 판매된 제품 (월 필터와 무관하게 고정)
        const colActive = {};
        months.forEach(m => Object.keys(bpm[m] || {}).forEach(k => { if (((bpm[m][k] || {}).qty || 0) > 0) colActive[k] = true; }));
        const cols = order.filter(k => colActive[k]);
        const head = `<tr><th>월</th>${cols.map(k => `<th>${(labelMap[k] || {}).label || k}</th>`).join('')}<th>합계</th></tr>`;
        const rows = months.map(m => {
          const md = bpm[m] || {};
          let rowTot = 0;
          const cells = cols.map(k => { const v = (md[k] || {}).qty || 0; rowTot += v; return `<td>${v ? v + '개' : '-'}</td>`; }).join('');
          const cur = (m === month) ? ' class="fmonth-cur"' : '';
          return `<tr${cur}><td>${monthLabel(m)}${m === month ? ' ★' : ''}</td>${cells}<td class="fmonth-cnt">${rowTot}개</td></tr>`;
        }).join('');
        tbl.innerHTML = `<table class="fmonth-table"><thead>${head}</thead><tbody>${rows}</tbody></table>`;
      }
    }
  }

  // ── Summary 전체 월별 매출·수익·판매량 차트 ────────────────────────────────
  function renderSummaryChart() {
    const ctx = el('summary-trend-chart');
    if (!ctx) return;
    if (_sumChart) { _sumChart.destroy(); _sumChart = null; }
    const t   = (gData || {}).trends || {};
    const bpm = t.by_product_by_month || {};
    const months = (t.months || []).slice();
    if (!months.length) return;
    // 캔버스 픽셀을 컨테이너 폭에 맞춰 직접 지정 (responsive 타이밍 이슈 회피)
    const card = ctx.closest('.card');
    const cw = card ? card.clientWidth : 900;
    ctx.width  = Math.max(cw - 28, 300);
    ctx.height = 240;
    const labels = months.map(monthLabel);
    // Summary 차트는 전 제품 합산 기준. 매출·판매량은 by_product 합, 수익은
    // 흑염소 순이익(trends.net_profit) + 비흑염소 제품 net_profit(by_product) 합.
    const rev   = months.map(m => Object.values(bpm[m] || {}).reduce((s, d) => s + (d.gross_revenue || 0), 0));
    const prof  = months.map((m, i) => ((t.net_profit || [])[i] || 0)
                    + Object.values(bpm[m] || {}).reduce((s, d) => s + (d.net_profit || 0), 0));
    const units = months.map(m => Object.values(bpm[m] || {}).reduce((s, d) => s + (d.qty || 0), 0));

    // 제품(카테고리)별 매출 = 누적 막대(stack:'rev')로 함께 표시
    const PALETTE = { '흑염소': '#7F77DD', '수면영양제': '#85B7EB', '화장품': '#E48FB0', '올리브오일캡슐': '#97C459' };
    const FALLBACK = ['#7F77DD', '#85B7EB', '#E48FB0', '#97C459', '#EFB36B', '#9A8FE0'];
    let ci = 0;
    const productBars = getProducts()
      .map(p => ({ p, series: months.map(m => ((bpm[m] || {})[p.key] || {}).gross_revenue || 0) }))
      .filter(x => x.series.some(v => v > 0))
      .map(x => ({
        type: 'bar', label: x.p.label, stack: 'rev', data: x.series,
        backgroundColor: PALETTE[x.p.key] || FALLBACK[ci++ % FALLBACK.length],
        yAxisID: 'y', order: 5,
      }));
    // 매출 집계된 카테고리가 없으면 총매출 단일 막대로 폴백
    if (!productBars.length) {
      productBars.push({ type: 'bar', label: '매출', stack: 'rev', data: rev,
        backgroundColor: 'rgba(127,119,221,0.45)', yAxisID: 'y', order: 5 });
    }

    _sumChart = new Chart(ctx, {
      data: {
        labels,
        datasets: [
          ...productBars,
          { type: 'line', label: '수익',   stack: 'profit', data: prof, borderColor: '#3B6D11', backgroundColor: '#3B6D11', tension: 0.4, fill: false, yAxisID: 'y', pointRadius: 3, order: 1 },
          { type: 'line', label: '판매량', data: units, borderColor: '#EF9F27', backgroundColor: '#EF9F27', tension: 0.4, fill: false, yAxisID: 'y1', pointRadius: 3, order: 0 },
        ],
      },
      options: {
        responsive: false,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } },
          tooltip: { callbacks: { label: c => c.dataset.yAxisID === 'y1'
            ? ` ${c.dataset.label}: ${c.parsed.y}개`
            : ` ${c.dataset.label}: ₩${Number(c.parsed.y).toLocaleString('ko-KR')}` } },
        },
        scales: {
          x:  { stacked: true, grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y:  { stacked: true, grid: { color: '#E5E3D6' }, beginAtZero: true,
                ticks: { font: { size: 10 }, callback: v => '₩' + (v / 10000).toFixed(0) + '만' },
                title: { display: true, text: '금액 (₩)', font: { size: 10 }, color: '#A8A69C' } },
          y1: { position: 'right', grid: { drawOnChartArea: false }, beginAtZero: true,
                ticks: { font: { size: 10 }, callback: v => v + '개' },
                title: { display: true, text: '판매량', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── 흑염소 스토어 분리 (A/B, 7월부터) ───────────────────────────────────────
  function renderStoreSplit(month) {
    const card = el('store-split-card');
    const grid = el('store-split-grid');
    if (!card || !grid) return;
    const bsm    = ((gData || {}).trends || {}).by_store_by_month || {};
    const stores = (gData || {}).stores || { A: '초방리농장', B: '슬립케어랩' };

    let data = {};
    if (month) {
      data = JSON.parse(JSON.stringify(bsm[month] || {}));
    } else {
      Object.values(bsm).forEach(md => Object.keys(md).forEach(s => {
        data[s] = data[s] || { qty: 0, order_count: 0, gross_revenue: 0 };
        data[s].qty += md[s].qty || 0; data[s].order_count += md[s].order_count || 0; data[s].gross_revenue += md[s].gross_revenue || 0;
      }));
    }
    const present = ['A', 'B'].filter(s => data[s]);
    if (!present.length) { card.classList.add('hidden'); return; }
    card.classList.remove('hidden');
    const colors = { A: '#7F77DD', B: '#EF9F27' };
    grid.innerHTML = present.map(s => `
      <div class="store-card">
        <div class="store-card-name"><span class="store-dot" style="background:${colors[s] || '#999'}"></span>${stores[s] || s} (${s})</div>
        <div class="store-card-val">${money(data[s].gross_revenue)}</div>
        <div class="store-card-sub">${data[s].qty}개 · ${data[s].order_count}건</div>
      </div>`).join('');
  }

  // ── 초기화 ────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.page === 'dashboard')  renderDashboard();
    if (document.body.dataset.page === 'influencer') renderInfluencer();
  });

  // responsive:false 인 Summary 차트는 창 크기 변경 시 직접 재생성
  let _rzTimer = null;
  window.addEventListener('resize', () => {
    if (!gData) return;
    clearTimeout(_rzTimer);
    _rzTimer = setTimeout(() => {
      if (_activeTab === 'summary') renderSummaryChart();
      else if (productKeysExtra().includes(_activeTab)) renderProductChart(_activeTab);
    }, 200);
  });
})();
