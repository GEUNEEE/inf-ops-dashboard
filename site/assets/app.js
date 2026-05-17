// app.js — 인플루언서 대시보드 메인 스크립트
(function () {
  'use strict';

  if (typeof Chart === 'undefined') {
    document.addEventListener('DOMContentLoaded', function () {
      var b = document.getElementById('error-banner');
      if (b) { b.textContent = 'Chart.js 로드 실패. 새로고침을 시도하세요.'; b.classList.remove('hidden'); }
    });
    return;
  }

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
  const hCache = {};

  // ── 구간 단가 ─────────────────────────────────────────────────────────────
  const MARGIN_SETTLEMENT = 45000;
  const MARGIN_GENERAL    = 84000;

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

  // prevCum → cum 구간의 티어별 {qty, price} 배열
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

  // ── KPI 업데이트 ───────────────────────────────────────────────────────────
  function updateKPIs(r, f) {
    set('kpi-revenue',    money(r.gross_revenue));
    set('kpi-orders',     (r.order_count || 0) + '건');
    set('kpi-profit',     money(r.net_profit));
    set('kpi-reply-rate', pct(f.reply_rate));
    set('kpi-exp-rate',   pct(f.exp_rate));
    set('kpi-ad-rate',    pct(f.ad_rate));
    const pe = el('kpi-profit');
    if (pe) {
      const profit = r.net_profit;
      pe.style.color = profit > 0 ? '#3B6D11' : profit < 0 ? '#A32D2D' : '';
    }
  }

  function setKPISubs(r, f) {
    set('kpi-revenue-sub', r.unit_count != null ? r.unit_count + '개 판매' : '');
    set('kpi-orders-sub',  r.unit_count != null ? r.unit_count + '개 단위' : '');
    set('kpi-profit-sub',  r.net_profit > 0 ? '흑자' : r.net_profit < 0 ? '적자' : '');
    const sentStr = f.total_sent ? Number(f.total_sent).toLocaleString() + '건 발송 기준' : '';
    set('kpi-reply-sub', sentStr);
    set('kpi-exp-sub',   sentStr);
    set('kpi-ad-sub',    sentStr);
  }

  function clearKPISubs() {
    ['kpi-revenue-sub','kpi-orders-sub','kpi-profit-sub','kpi-reply-sub','kpi-exp-sub','kpi-ad-sub']
      .forEach(id => set(id, ''));
  }

  // ── 영업이익 KPI 행 ────────────────────────────────────────────────────────
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

  // ── 히스토리 → settlement_summary 형식 ────────────────────────────────────
  function historyToSummary(influencers) {
    const s = {};
    for (const [name, d] of Object.entries(influencers)) {
      const cum   = d.cumulative_qty;
      const qty   = d.qty || 0;
      const isGen = d.is_general || false;
      s[name] = {
        '건수':     d.order_count ?? 0,
        '수량':     qty,
        '누적수량': isGen ? null : (cum ?? null),
        '현재단가': isGen ? null : tierPrice(cum || 0),
        '금액':     isGen
          ? (d.amount ?? null)
          : calcTieredAmount(cum || 0) - calcTieredAmount(Math.max((cum || 0) - qty, 0)),
        '정산대상': !isGen,
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
      // 전체 모드
      const r  = gData.revenue     || {};
      const f  = gData.mail_funnel || {};
      updateKPIs(r, f);
      setKPISubs(r, f);
      renderProfitKPIs(gData.profit_analysis || null, null);
      renderFunnelBars(f);
      renderDonutChart(gData.inf_status || {});
      renderInfluencerGrid(gData.settlement_summary || {}, null);
      renderContribTable(gData.profit_analysis || null, null, null);
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
      { reply_rate: mf.reply_rate, exp_rate: mf.exp_rate,
        ad_rate: mf.ad_rate, total_sent: mf.sent }
    );
    clearKPISubs();
    renderProfitKPIs(gData.profit_analysis || null, month);
    renderFunnelBars({
      total_sent:    mf.sent    || 0,
      replied:       mf.replied || 0,
      meeting_total: mf.meeting || 0,
      exp_total:     mf.exp     || 0,
      ad_total:      (gData.ad_by_month || {})[month] || 0,
    });
    renderDonutChart(h.inf_status || {});
    renderInfluencerGrid(historyToSummary(h.influencers || {}), month);
    renderContribTable(gData.profit_analysis || null, month, h);
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

    try {
      const r  = gData.revenue     || {};
      const f  = gData.mail_funnel || {};
      const t  = gData.trends      || {};
      const pa = gData.profit_analysis || null;
      const byMonth = gData.mail_funnel_by_month || {};

      if (gData.generated_at) set('generated-at', gData.generated_at.replace('T', ' '));

      const unreg = (gData.alerts || {}).unregistered_influencers || [];
      if (unreg.length) {
        const b = el('alert-banner');
        if (b) {
          b.textContent = '미등재 인플루언서: ' + unreg.map(u => u.name + ' (' + u['건수'] + '건)').join(', ');
          b.classList.remove('hidden');
        }
      }

      renderFilterButtons(t.months || []);
      updateKPIs(r, f);
      setKPISubs(r, f);
      renderProfitKPIs(pa, null);
      renderFunnelBars(f);
      renderDonutChart(gData.inf_status || {});

      // 인플루언서 카운트 레이블
      const st     = gData.inf_status || {};
      const stTotal  = Object.values(st).reduce((s, v) => s + v, 0);
      const stActive = stTotal - (st['기타'] || 0);
      const lbl = el('inf-count-label');
      if (lbl) lbl.innerHTML =
        `<span style="background:var(--text1);color:var(--bg);font-size:10px;font-weight:700;padding:2px 10px;border-radius:10px">` +
        `진행 ${stActive}<span style="font-weight:400;opacity:0.55"> / ${stTotal}명</span></span>`;

      renderInfluencerGrid(gData.settlement_summary || {}, null);
      renderFunnelMonthlyTable(byMonth, gData.current_month);

      if (t.months && t.months.length > 0) {
        renderTrendChart(byMonth, gData.current_month);
        renderRevenueChart(t);
      }

      renderProfitChart(pa);
      renderContribTable(pa, null, null);
    } catch (e) {
      console.error('[대시보드 오류]', e);
      const b = el('error-banner');
      if (b) { b.textContent = '렌더링 오류: ' + e.message; b.classList.remove('hidden'); }
    }
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
              label: c => ` ${c.label}: ${c.raw}명 (${Math.round(c.raw / total * 100)}%)`,
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

  // ── 인플루언서 카드 그리드 ────────────────────────────────────────────────
  function renderInfluencerGrid(summary, month) {
    const grid = el('inf-grid');
    if (!grid) return;

    const infCum = ((gData || {}).profit_analysis || {}).influencer_cumulative || {};
    const amountLabel = month ? monthLabel(month) + ' 정산액' : '당월 정산액';

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

      // 기여수익 섹션
      let contribHtml = '';
      if (!month) {
        const cum = infCum[item.name];
        if (cum && cum.contribution) {
          contribHtml = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding-top:5px;border-top:0.5px solid var(--border)">
              <span class="stat-lbl">누적 기여수익</span>
              <span class="stat-val" style="color:#3B6D11;font-weight:700">${money(cum.contribution)}</span>
            </div>`;
        }
      } else {
        const qty = item['수량'] ?? 0;
        if (qty > 0) {
          let monthContrib = 0;
          if (isTarget) {
            const cum     = item['누적수량'] ?? 0;
            const prevCum = Math.max(cum - qty, 0);
            for (let q = prevCum; q < cum; q++) monthContrib += MARGIN_SETTLEMENT - tierPrice(q + 1);
          } else {
            monthContrib = qty * MARGIN_GENERAL;
          }
          if (monthContrib > 0) {
            contribHtml = `
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px;padding-top:5px;border-top:0.5px solid var(--border)">
                <span class="stat-lbl">${monthLabel(month)} 기여수익</span>
                <span class="stat-val" style="color:#3B6D11;font-weight:700">${money(monthContrib)}</span>
              </div>`;
          }
        }
      }

      // 정산 금액 / 티어 섹션
      let statsHtml;
      if (isTarget) {
        const cum     = item['누적수량'] ?? 0;
        const qty     = item['수량'] ?? 0;
        const prevCum = Math.max(cum - qty, 0);
        const tiers   = qty > 0 ? tierBreakdownRange(prevCum, cum) : [];
        const isMulti = tiers.length > 1;
        const tierTotal = tiers.reduce((s, t) => s + t.qty * t.price, 0);

        let tierSection = '';
        if (tiers.length > 0) {
          const rows = tiers.map(t =>
            `<div class="tier-row">
              <span>${t.qty}개 × ${money(t.price)}${t.price > 20000 ? '<span class="tier-up">▲</span>' : ''}</span>
              <span class="stat-val">${money(t.qty * t.price)}</span>
            </div>`).join('');
          const totalRow = isMulti
            ? `<div class="tier-total"><span style="color:var(--text3)">합계</span><span class="stat-val">${money(tierTotal)}</span></div>`
            : '';
          tierSection = `<div class="tier-section">${rows}${totalRow}</div>`;
        } else {
          tierSection = `<div style="font-size:11px;color:var(--text3);padding:2px 0">-</div>`;
        }

        statsHtml = `
          <div style="margin-top:8px">
            <span class="stat-lbl">${amountLabel}</span>
            ${tierSection}
          </div>
          <div class="inf-card-stats" style="grid-template-columns:1fr 1fr;margin-top:6px">
            <div><span class="stat-lbl">건수</span><span class="stat-val">${item['건수'] || 0}건</span></div>
            <div><span class="stat-lbl">누적수량</span><span class="stat-val">${cum}개</span></div>
          </div>`;
      } else {
        const genQty = item['수량'] ?? 0;
        const genAmt = item['금액'];
        const amtRow = genQty > 0
          ? `<div class="tier-row" style="margin-top:4px">
               <span>${genQty}개</span>
               <span class="stat-val">${money(genAmt)}</span>
             </div>`
          : `<div style="font-size:11px;color:var(--text3);padding:2px 0">-</div>`;
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
      c.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:8px 0">데이터 없음</div>';
      return;
    }

    function cell(count, rate) {
      if (!count && !rate) return '<td>-</td>';
      return `<td><span class="fmonth-cnt">${Number(count).toLocaleString()}</span><span class="fmonth-pct">(${(rate * 100).toFixed(1)}%)</span></td>`;
    }

    const header = '<tr><th>월</th><th>발송</th><th>응답</th><th>미팅</th><th>체험</th><th>광고</th></tr>';
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

    c.innerHTML = `<table class="fmonth-table"><thead>${header}</thead><tbody>${body}</tbody></table>`;
  }

  // ── 추세 차트 ─────────────────────────────────────────────────────────────
  function renderTrendChart(byMonth, currentMonth) {
    const ctx = el('trend-chart');
    if (!ctx) return;

    const months = Object.keys(byMonth).sort();
    if (!months.length) return;

    const labels     = months.map(m => monthLabel(m) + (m === currentMonth ? ' ★' : ''));
    const replyRates = months.map(m => +((byMonth[m].reply_rate   || 0) * 100).toFixed(1));
    const meetRates  = months.map(m => +((byMonth[m].meeting_rate || 0) * 100).toFixed(1));
    const expRates   = months.map(m => +((byMonth[m].exp_rate     || 0) * 100).toFixed(1));
    const adRates    = months.map(m => +((byMonth[m].ad_rate      || 0) * 100).toFixed(1));

    new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: '응답률',     data: replyRates, borderColor: '#85B7EB', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '미팅전환율', data: meetRates,  borderColor: '#EF9F27', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '체험전환율', data: expRates,   borderColor: '#7F77DD', tension: 0.4, fill: false, pointRadius: 3 },
          { label: '광고수락률', data: adRates,    borderColor: '#97C459', tension: 0.4, fill: false, pointRadius: 3 },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 8, font: { size: 10 } } },
          tooltip: {
            callbacks: {
              label: c => {
                const m = months[c.dataIndex];
                const d = byMonth[m] || {};
                const cntMap = { '응답률': d.replied, '미팅전환율': d.meeting, '체험전환율': d.exp, '광고수락률': d.ad };
                const cnt = cntMap[c.dataset.label];
                return ` ${c.dataset.label}: ${cnt != null ? cnt + '건 ' : ''}(${c.parsed.y}%)`;
              },
            },
          },
        },
        scales: {
          x: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } } },
          y: { grid: { color: '#E5E3D6' }, ticks: { font: { size: 10 } },
               title: { display: true, text: '%', font: { size: 10 }, color: '#A8A69C' } },
        },
      },
    });
  }

  // ── 매출/수익 차트 ─────────────────────────────────────────────────────────
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
    const grossRevs = months.map(m => pa.monthly[m].gross_revenue || 0);
    const opProfits = months.map(m => pa.monthly[m].operating_profit || 0);
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
          tooltip: {
            callbacks: {
              label: c => c.dataset.yAxisID === 'y1'
                ? ` ${c.dataset.label}: ${c.parsed.y}%`
                : ` ${c.dataset.label}: ₩${Number(c.parsed.y).toLocaleString('ko-KR')}`,
            },
          },
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
  function renderContribTable(pa, month, h) {
    const c = el('contrib-table');
    if (!c) return;

    let items = [];
    let totalQty = 0;

    if (month && h) {
      // 월별 모드: history 파일 기준 계산
      const influencers = h.influencers || {};
      totalQty = h.unit_count || 0;
      let knownQty = 0;
      items = Object.entries(influencers).map(([name, d]) => {
        const qty    = d.qty || 0;
        const isGen  = d.is_general || false;
        const cum    = d.cumulative_qty || 0;
        const prevCum = Math.max(cum - qty, 0);
        let contribution = 0;
        if (isGen) {
          contribution = qty * MARGIN_GENERAL;
        } else {
          for (let q = prevCum; q < cum; q++) contribution += MARGIN_SETTLEMENT - tierPrice(q + 1);
        }
        knownQty += qty;
        return { name, qty, settlement: isGen ? 0 : (d.amount || 0), contribution, isGen };
      });
      const miscQty = totalQty - knownQty;
      if (miscQty > 0) items.push({ name: '(기타/미등재)', qty: miscQty, settlement: 0, contribution: miscQty * MARGIN_GENERAL, isGen: true });
    } else {
      // 전체 모드: profit_analysis.influencer_cumulative
      if (!pa) { c.innerHTML = ''; return; }
      items = Object.entries(pa.influencer_cumulative || {}).map(([name, d]) => ({
        name, qty: d.qty || 0, settlement: d.settlement || 0,
        contribution: d.contribution || 0, isGen: (d.settlement || 0) === 0 && name.includes('기타'),
      }));
      totalQty = Object.values(pa.monthly || {}).reduce((s, m) => s + (m.unit_count || 0), 0);
    }

    items.sort((a, b) => b.contribution - a.contribution);
    if (!items.length) {
      c.innerHTML = '<div style="font-size:11px;color:var(--text3);padding:8px 0">데이터 없음</div>';
      return;
    }

    const totalContrib = items.reduce((s, i) => s + (i.contribution || 0), 0);
    const laborCost    = totalQty * 10000;
    const laborLabel   = month ? monthLabel(month) : '전체 누적';

    const rows = items.map(item => `<tr>
      <td>${item.name}</td>
      <td>${item.qty}개</td>
      <td>${item.settlement ? money(item.settlement) : '<span style="color:var(--text3)">-</span>'}</td>
      <td style="color:#3B6D11;font-weight:500">${money(item.contribution)}</td>
    </tr>`).join('');

    c.innerHTML = `
      <table class="contrib-tbl">
        <thead><tr><th>인플루언서</th><th style="text-align:right">수량</th><th style="text-align:right">정산액</th><th style="text-align:right">기여수익</th></tr></thead>
        <tbody>${rows}</tbody>
        <tfoot><tr><td>합계</td><td>${totalQty}개</td><td></td><td>${money(totalContrib)}</td></tr></tfoot>
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

  // ── 초기화 ────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.page === 'dashboard')  renderDashboard();
    if (document.body.dataset.page === 'influencer') renderInfluencer();
  });
})();
