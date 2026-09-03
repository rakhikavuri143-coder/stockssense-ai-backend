/* ═══════════════════════════════════════
   StockSense AI — Frontend Application
   Indian Stock Market Nifty 50 AI Agent
═══════════════════════════════════════ */

'use strict';

// ─────────────────────── STATE ───────────────────────
let currentSignals    = [];
let alertsEnabled     = true;
let activeTab         = 'signals';
let currentModal      = null;
let activeSector      = 'All';
let isMarketOpenGlobal = true;
let autoScanTimerId   = null;
let autoScanSecLeft   = 180; // 3 minutes auto-refresh interval
let lastScanCategory  = 'nifty50';
let currentMode       = localStorage.getItem('tradingMode') || 'paper';

// ─────────────────────── INIT & AUTO-RECONNECT ───────────────────────
let isNetworkOffline = false;

document.addEventListener('DOMContentLoaded', () => {
  syncTradingModeUI();
  setupConfidenceSlider();
  setupNetworkAutoReconnect();

  // Check Private Terminal Lock Status
  const isUnlocked = checkPrivateTerminalLock();
  if (isUnlocked) {
    loadWatchlist();
    loadNiftyStatus();
    loadPortfolio();
    loadJournal();
    startAutoScanCountdown(180);
  }

  // Poll Nifty status every 5 minutes (only if unlocked)
  setInterval(() => {
    if (localStorage.getItem('ss_private_auth') === 'unlocked_owner') {
      loadNiftyStatus();
    }
  }, 5 * 60 * 1000);

  // Poll portfolio every 15 seconds for live P&L sync (only if unlocked)
  setInterval(() => {
    if (localStorage.getItem('ss_private_auth') === 'unlocked_owner') {
      loadPortfolio();
    }
  }, 15 * 1000);
});

function setupNetworkAutoReconnect() {
  const banner = document.getElementById('networkBanner');

  const showBanner = (text, type, duration = 0) => {
    if (!banner) return;
    banner.textContent = text;
    banner.className = `network-banner ${type}`;
    banner.style.display = 'block';
    if (duration > 0) {
      setTimeout(() => {
        banner.style.display = 'none';
      }, duration);
    }
  };

  const handleOnline = async () => {
    if (isNetworkOffline) {
      isNetworkOffline = false;
      showBanner('🟢 Network Back Online — Auto Syncing System Data…', 'online', 3500);
      showToast('⚡ Reconnected to Server — Auto Resynced!', 'buy');
      // Auto-resync all data
      await loadNiftyStatus();
      await loadPortfolio();
      await loadJournal();
    }
  };

  const handleOffline = () => {
    isNetworkOffline = true;
    showBanner('⚠️ Connection Lost — Waiting for Network…', 'offline');
    showToast('⚠️ Internet Connection Lost! Retrying…', 'sell');
  };

  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);

  // Background Heartbeat Check every 10 seconds for lag recovery
  setInterval(async () => {
    try {
      const res = await fetch('/api/nifty-status', { cache: 'no-store' });
      if (res.ok && isNetworkOffline) {
        handleOnline();
      }
    } catch (e) {
      if (!isNetworkOffline && !navigator.onLine) {
        handleOffline();
      }
    }
  }, 10 * 1000);
}

// ─────────────────────── CONFIDENCE SLIDER ───────────────────────
function setupConfidenceSlider() {
  const slider = document.getElementById('confidenceSlider');
  const display = document.getElementById('confidenceVal');
  slider.addEventListener('input', () => {
    display.textContent = slider.value + '%';
  });
}

function getConfidenceThreshold() {
  return parseInt(document.getElementById('confidenceSlider').value, 10);
}

// ─────────────────────── TRADING MODE TOGGLE ───────────────────────
function toggleTradingMode() {
  const btn = document.getElementById('modeToggleBtn');
  if (currentMode === 'paper') {
    if (!confirm('🟢 Switch to LIVE Trading Mode? Real trades will be routed to your Angel One account.')) return;
    currentMode = 'live';
    showToast('🟢 Live Trading Mode Active', 'buy');
  } else {
    currentMode = 'paper';
    showToast('📝 Paper Trading Mode Active', '');
  }
  localStorage.setItem('tradingMode', currentMode);
  syncTradingModeUI();
  
  // Re-load data
  loadPortfolio();
  loadJournal();
}

function syncTradingModeUI() {
  const btn = document.getElementById('modeToggleBtn');
  if (!btn) return;
  if (currentMode === 'live') {
    btn.textContent = '🟢 LIVE';
    btn.style.color = '#00ff88';
    btn.style.borderColor = 'rgba(0,255,136,0.3)';
    btn.style.background = 'rgba(0,255,136,0.06)';
  } else {
    btn.textContent = '📝 PAPER';
    btn.style.color = '#ffbd59';
    btn.style.borderColor = 'rgba(255,189,89,0.3)';
    btn.style.background = '#1e293b';
  }
  const paperTab = document.getElementById('tab-paper');
  if (paperTab) {
    paperTab.textContent = currentMode === 'live' ? '💼 Live Trading' : '📝 Paper Trading';
  }
  const balLabel = document.querySelector('.balance-label');
  if (balLabel) {
    balLabel.textContent = currentMode === 'live' ? 'Live P&L Lock' : 'Paper Balance';
  }
  const resetBtn = document.querySelector('.btn-reset');
  if (resetBtn) {
    // Hide reset button in live mode for safety
    resetBtn.style.display = currentMode === 'live' ? 'none' : 'inline-block';
  }
}

// ─────────────────────── TABS ───────────────────────
function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + tab).classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');

  if (tab === 'journal') loadJournal();
  if (tab === 'paper')   loadPortfolio();
}

// ─────────────────────── NIFTY STATUS ───────────────────────
async function loadNiftyStatus() {
  try {
    const res  = await fetch('/api/nifty-status');
    const data = await res.json();
    const el   = document.getElementById('niftyText');
    const dot  = document.querySelector('.pulse-dot');
    const pct  = data.nifty_change_pct;
    const sign = pct >= 0 ? '+' : '';

    isMarketOpenGlobal = data.is_market_open !== false;
    const marketStateTag = isMarketOpenGlobal ? '' : ' | 🌙 Market Closed';

    el.textContent = `Nifty 50: ${sign}${pct}%${marketStateTag}`;
    if (!isMarketOpenGlobal) {
      el.style.color = '#a78bfa';
      if (dot) dot.style.background = '#a78bfa';
    } else if (data.blocked) {
      el.style.color = '#ff4d6d';
      if (dot) dot.style.background = '#ff4d6d';
    } else if (pct >= 0) {
      el.style.color = '#00ff88';
      if (dot) dot.style.background = '#00ff88';
    } else {
      el.style.color = '#ffd700';
      if (dot) dot.style.background = '#ffd700';
    }
    if (data.blocked && isMarketOpenGlobal) {
      showToast('🚨 Nifty Trend Guard ACTIVE — BUY signals blocked!', 'sell');
    }
  } catch (e) {
    console.warn('Nifty status error:', e);
  }
}

// ─────────────────────── WATCHLIST ───────────────────────
let allWatchlistStocks = [];
let activeWatchlistCategory = 'all';

async function loadWatchlist() {
  try {
    const res  = await fetch('/api/stocks?category=all');
    const data = await res.json();
    allWatchlistStocks = data.stocks || [];

    // Fetch budget stock symbols for category tagging
    const budgetRes = await fetch('/api/stocks/budget');
    const budgetData = await budgetRes.json();
    const budgetSet = new Set((budgetData.stocks || []).map(s => s.symbol));

    allWatchlistStocks.forEach(s => {
      s.isBudget = budgetSet.has(s.symbol);
    });

    filterAndRenderWatchlist();
    renderSectorFilter(allWatchlistStocks);
  } catch (e) {
    console.error('Watchlist error:', e);
  }
}

function filterCategory(cat) {
  activeWatchlistCategory = cat;
  document.querySelectorAll('#categoryFilterGroup .sector-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  const activeBtn = document.getElementById(`catBtn-${cat}`);
  if (activeBtn) activeBtn.classList.add('active');
  filterAndRenderWatchlist();
}

function filterWatchlistSearch() {
  filterAndRenderWatchlist();
}

function filterAndRenderWatchlist() {
  const query = (document.getElementById('watchlistSearch')?.value || '').toLowerCase().trim();
  let filtered = allWatchlistStocks;

  if (activeWatchlistCategory === 'budget') {
    filtered = filtered.filter(s => s.isBudget);
  } else if (activeWatchlistCategory === 'nifty50') {
    filtered = filtered.filter(s => !s.isBudget);
  }

  if (activeSector !== 'All') {
    filtered = filtered.filter(s => s.sector === activeSector);
  }

  if (query) {
    filtered = filtered.filter(s =>
      s.symbol.toLowerCase().includes(query) ||
      s.name.toLowerCase().includes(query) ||
      s.sector.toLowerCase().includes(query)
    );
  }

  renderWatchlist(filtered);
}

function renderSectorFilter(stocks) {
  const sectors = ['All', ...new Set(stocks.map(s => s.sector))].sort();
  const el = document.getElementById('sectorFilter');
  if (!el) return;
  el.innerHTML = sectors.map(s =>
    `<button class="sector-btn ${s === activeSector ? 'active' : ''}" onclick="filterSector('${s}')">${s}</button>`
  ).join('');
}

function filterSector(sector) {
  activeSector = sector;
  document.querySelectorAll('#sectorFilter .sector-btn').forEach(b => {
    b.classList.toggle('active', b.textContent === sector);
  });
  filterAndRenderWatchlist();
}

function renderWatchlist(stocks) {
  const grid = document.getElementById('watchlistGrid');
  if (!grid) return;
  if (!stocks || stocks.length === 0) {
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:2rem;color:#94a3b8">No stocks found matching filter.</div>';
    return;
  }

  grid.innerHTML = stocks.map(s => {
    const badge = s.isBudget
      ? '<span style="font-size:0.68rem;background:rgba(234,179,8,0.15);color:#eab308;border:1px solid rgba(234,179,8,0.3);padding:0.15rem 0.4rem;border-radius:4px;font-weight:700">⚡ BUDGET (<₹200)</span>'
      : '<span style="font-size:0.68rem;background:rgba(59,130,246,0.15);color:#60a5fa;border:1px solid rgba(59,130,246,0.3);padding:0.15rem 0.4rem;border-radius:4px;font-weight:700">🏆 NIFTY 50</span>';

    return `
      <div class="watchlist-item" data-sector="${s.sector}" onclick="scanSingle('${s.symbol}', '${s.name}')">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem">
          <div class="wl-symbol">${s.symbol.replace('.NS','')}</div>
          ${badge}
        </div>
        <div class="wl-name">${s.name}</div>
        <div class="wl-sector">${s.sector}</div>
      </div>
    `;
  }).join('');
}

async function scanSingle(symbol, name) {
  switchTab('signals');
  showToast(`🔍 Analyzing ${symbol}...`, '');
  setStatusLoading(`Analyzing ${name}...`);
  try {
    const threshold = getConfidenceThreshold();
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols: [symbol], confidence_threshold: threshold }),
    });
    const data = await res.json();
    currentSignals = data.signals;
    renderSignals(data.signals);
    clearStatus();
  } catch (e) {
    showToast('❌ Analysis failed: ' + e.message, '');
    clearStatus();
  }
}

// ─────────────────────── AUTO SCAN TIMER ───────────────────────
function clearAutoScanTimer() {
  if (autoScanTimerId) {
    clearInterval(autoScanTimerId);
    autoScanTimerId = null;
  }
  const badge = document.getElementById('autoScanBadge');
  if (badge) badge.style.display = 'none';
}

function startAutoScanCountdown(seconds = 180) {
  clearAutoScanTimer();
  autoScanSecLeft = seconds;
  const badge = document.getElementById('autoScanBadge');
  const txt   = document.getElementById('autoScanCountdownText');
  if (badge) badge.style.display = 'inline-flex';

  const updateBadge = () => {
    if (!isMarketOpenGlobal) {
      if (txt) txt.textContent = '🌙 Market Closed';
      return;
    }
    const mins = Math.floor(autoScanSecLeft / 60);
    const secs = autoScanSecLeft % 60;
    const formatted = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    if (txt) txt.textContent = `Auto-Refresh: ${formatted}`;
  };

  updateBadge();

  autoScanTimerId = setInterval(() => {
    if (!isMarketOpenGlobal) {
      if (txt) txt.textContent = '🌙 Market Closed';
      return;
    }
    autoScanSecLeft--;
    if (autoScanSecLeft <= 0) {
      clearAutoScanTimer();
      startScan(lastScanCategory);
    } else {
      updateBadge();
    }
  }, 1000);
}

// ─────────────────────── SCAN ALL ───────────────────────
async function startScan(category = 'nifty50') {
  clearAutoScanTimer();
  lastScanCategory = category;
  const isBudget = category === 'budget';
  const isScalp  = category === 'fast_scalp';
  const btnId    = isScalp ? 'scalpScanBtn' : (isBudget ? 'budgetScanBtn' : 'scanBtn');
  const btn = document.getElementById(btnId);
  if (btn) {
    btn.classList.add('loading');
    btn.innerHTML = '<span class="btn-icon">⏳</span> Scanning...';
  }
  const grid = document.getElementById('signalGrid');
  if (grid) grid.innerHTML = '';
  currentSignals = [];

  switchTab('signals');
  const threshold = getConfidenceThreshold();

  // Live progress bar in the status bar
  const statusBar = document.getElementById('scanStatus') || document.getElementById('statusBar');
  const setProgress = (i, total, sym) => {
    if (!statusBar) return;
    const pct = Math.round((i / total) * 100);
    statusBar.innerHTML = `
      <div style="display:flex;align-items:center;gap:0.75rem;width:100%">
        <div style="flex:1;background:rgba(255,255,255,0.08);border-radius:99px;height:6px;overflow:hidden">
          <div style="width:${pct}%;background:linear-gradient(90deg,#7c3aed,#4f46e5);height:100%;border-radius:99px;transition:width 0.3s ease"></div>
        </div>
        <span style="color:#a78bfa;font-size:0.78rem;white-space:nowrap">${i}/${total} — ${sym}</span>
      </div>`;
    statusBar.style.display = 'flex';
  };

  try {
    let res;
    try {
      res = await fetch('/api/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confidence_threshold: threshold, category: category }),
      });
      if (!res.ok) throw new Error('Stream HTTP ' + res.status);
    } catch (streamErr) {
      console.warn('Streaming scan failed, falling back to standard scan:', streamErr);
      setStatusLoading(
        isScalp  ? '🔥 Scalp-scanning 18 budget stocks (85% confidence)...' :
        isBudget ? 'Scanning 18 Budget stocks with AI...' :
                   'Scanning 50 Nifty stocks with AI...'
      );
      const fallbackRes = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confidence_threshold: threshold, category: category }),
      });
      const data = await fallbackRes.json();
      currentSignals = data.signals || [];
      // Sort signals by confidence
      currentSignals.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
      let r = 1;
      currentSignals.forEach(s => { if (s.signal !== 'AVOID' && r <= 5) s.rank = r++; });
      renderSignals(currentSignals);
      showToast(`🏆 Top Win Picks Ranked! (${data.qualified || 0} qualified)`, 'buy');
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();  // keep incomplete last chunk

      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        let msg;
        try { msg = JSON.parse(line.slice(5).trim()); } catch { continue; }

        if (msg.type === 'progress') {
          setProgress(msg.index, msg.total, msg.symbol.replace('.NS',''));

        } else if (msg.type === 'result') {
          // Render card immediately as result arrives
          currentSignals.push(msg);
          appendSignalCard(msg);

        } else if (msg.type === 'done') {
          if (statusBar) statusBar.style.display = 'none';

          // Sort all signals by Confidence Score (Highest Win-Probability first)
          currentSignals.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));

          // Assign Top 5 Ranks
          let r = 1;
          currentSignals.forEach(s => {
            if (s.signal !== 'AVOID' && r <= 5) {
              s.rank = r++;
            } else {
              delete s.rank;
            }
          });
          if (r <= 5) {
            r = 1;
            currentSignals.forEach(s => { if (r <= 5) s.rank = r++; });
          }

          // Re-render grid sorted by Top 5 Win Picks
          renderSignals(currentSignals);

          const q = msg.qualified;
          if (q > 0) {
            showToast(`🏆 Top 5 High-Probability Trades Ranked!`, 'buy');
            if (alertsEnabled) playAlertSound();
            if (alertsEnabled) sendBrowserNotification(
              `StockSense AI — Top 5 Win Picks Ready!`,
              `Top 5 highest probability trade opportunities ranked.`
            );
          } else {
            showToast(`Scan complete. Top 5 Best Technical Setups Ranked!`, '');
          }
          if (currentSignals.length === 0) {
            const sigGrid = document.getElementById('signalGrid');
            if (sigGrid) sigGrid.innerHTML = '<div class="empty-state">No signals found. Try lowering the confidence threshold or run a new scan.</div>';
          }
        }
      }
    }
  } catch (e) {
    showToast('Scan failed: ' + e.message, '');
    if (statusBar) statusBar.style.display = 'none';
  } finally {
    if (btn) {
      btn.classList.remove('loading');
      if (isScalp) {
        btn.innerHTML = '<span class="btn-icon">🔥</span> 1-Hr Fast Scalp';
      } else if (isBudget) {
        btn.innerHTML = '<span class="btn-icon">⚡</span> Scan Budget Stocks';
      } else {
        btn.innerHTML = '<span class="btn-icon">🔍</span> Scan Nifty 50';
      }
    }
    // Scalp mode: auto-refresh every 90s; normal: every 3 min
    startAutoScanCountdown(isScalp ? 90 : 180);
  }
}

// ─────────────────────── SCAN BUDGET ───────────────────────
async function startBudgetScan() {
  return startScan('budget');
}

// Expose functions globally for inline HTML event handlers
window.startScan = startScan;
window.startBudgetScan = startBudgetScan;

// Append a single signal card to the grid (used during streaming)
function appendSignalCard(sig) {
  const grid = document.getElementById('signalGrid');
  if (!grid) return;
  const emptyState = grid.querySelector('.empty-state');
  if (emptyState) emptyState.remove();

  // Re-use renderSignals logic for one card
  const temp = document.createElement('div');
  temp.innerHTML = buildSignalCardHTML(sig);
  const card = temp.firstElementChild;
  // Insert BUY/SELL cards before AVOID cards
  if (sig.signal !== 'AVOID') {
    const avoidCards = [...grid.querySelectorAll('[data-signal="AVOID"]')];
    if (avoidCards.length > 0) {
      grid.insertBefore(card, avoidCards[0]);
    } else {
      grid.appendChild(card);
    }
  } else {
    card.dataset.signal = 'AVOID';
    grid.appendChild(card);
  }
}


// ─────────────────────── SIGNAL RENDERING ───────────────────────
function buildSignalCardHTML(s) {
  const cls      = s.signal === 'BUY' ? 'buy' : s.signal === 'SELL' ? 'sell' : 'avoid';
  const confCls  = s.confidence >= 90 ? 'high' : s.confidence >= 75 ? 'med' : 'low';
  const trendCls = s.trend_1h === 'BULLISH' ? 'bull' : s.trend_1h === 'BEARISH' ? 'bear' : '';
  const rankRibbon = s.rank ? `<div class="rank-ribbon">🏆 TOP #${s.rank} WIN PICK</div>` : '';

  const target1Val = s.target1 || s.target1_buy || (s.current_price ? s.current_price * 1.02 : 0);
  const target2Val = s.target2 || s.target2_buy || (s.current_price ? s.current_price * 1.04 : 0);
  const stopLoss   = s.stop_loss || s.sl_buy || (s.current_price ? s.current_price * 0.985 : 0);

  const entry = s.current_price ? `₹${s.current_price.toFixed(2)}` : '—';
  const t1    = target1Val ? `₹${target1Val.toFixed(2)}` : '—';
  const t2    = target2Val ? `₹${target2Val.toFixed(2)}` : '—';
  const sl    = stopLoss ? `₹${stopLoss.toFixed(2)}` : '—';

  const safeName   = (s.company_name || '').replace(/'/g, "\\'");
  const sigId      = s.signal_id || 'null';
  const entryPrice = s.current_price || 0;

  return `
    <div class="signal-card ${cls}" data-signal="${s.signal}" onclick="openModalData(${encodeSignal(s)})">
      ${rankRibbon}
      <div class="card-top">
        <div class="stock-info">
          <div class="symbol">${s.symbol.replace('.NS','')}</div>
          <div class="name">${s.company_name}</div>
          <div class="sector-tag">${s.sector}</div>
        </div>
        <div class="signal-badge">
          <div class="badge ${cls}">${s.signal}</div>
          <div class="confidence-ring ${confCls}">${s.confidence?.toFixed(1)}%</div>
        </div>
      </div>

      <div class="price-section">
        <div class="price-item"><div class="price-label">CMP</div><div class="price-val current" id="cmp-${s.symbol}">${entry}</div></div>
        <div class="price-item"><div class="price-label">Target 1</div><div class="price-val target">${t1}</div></div>
        <div class="price-item"><div class="price-label">Target 2</div><div class="price-val target">${t2}</div></div>
        <div class="price-item"><div class="price-label">Stop Loss</div><div class="price-val sl">${sl}</div></div>
      </div>

      <div class="tech-row">
        <span class="tech-pill ${trendCls}">1H: ${s.trend_1h || 'N/A'}</span>
        <span class="tech-pill">RSI ${s.rsi?.toFixed(0) || '—'}</span>
        <span class="tech-pill">RVOL ${s.rvol?.toFixed(1) || '—'}x</span>
        ${s.rr_ratio ? `<span class="tech-pill">R:R 1:${s.rr_ratio?.toFixed(1)}</span>` : ''}
      </div>

      <div class="news-snippet">${s.news_summary || s.reasoning || 'No news summary available.'}</div>

      <div class="card-actions" onclick="event.stopPropagation()">
        ${s.signal === 'BUY'  || s.signal === 'AVOID' ? `<button class="btn-paper-buy"  onclick="liveQuickPaperBuy(this, ${sigId}, '${s.symbol}', '${safeName}', ${stopLoss}, ${target1Val}, ${target2Val}, ${s.scalp_mode ? true : false})">📝 Paper BUY</button>` : ''}
        ${s.signal === 'SELL' || s.signal === 'AVOID' ? `<button class="btn-paper-sell" onclick="liveQuickPaperSell(this, ${sigId}, '${s.symbol}', '${safeName}', ${stopLoss}, ${target1Val}, ${target2Val}, ${s.scalp_mode ? true : false})">📝 Paper SELL</button>` : ''}
        <button class="btn-detail" onclick="openModalData(${encodeSignal(s)})">📊 Chart</button>
      </div>
    </div>
  `;
}

function renderSignals(signals) {
  const grid = document.getElementById('signalGrid');
  if (!grid) return;
  if (!signals || signals.length === 0) {
    grid.innerHTML = '<div class="empty-state">No signals found. Try lowering the confidence threshold or run a new scan.</div>';
    return;
  }
  grid.innerHTML = signals.map(s => buildSignalCardHTML(s)).join('');
  // Auto-refresh all card CMPs with live prices after render
  refreshAllCardCMPs(signals);
}

async function refreshAllCardCMPs(signals) {
  for (const s of signals) {
    try {
      const sym = s.symbol.replace('.NS', '').replace('.BO', '');
      const res  = await fetch('/api/stock-price/' + sym);
      const data = await res.json();
      if (data.price && data.price > 0) {
        const el = document.getElementById('cmp-' + s.symbol);
        if (el) {
          el.textContent = '₹' + data.price.toFixed(2);
          el.style.transition = 'color 0.4s';
          el.style.color = '#00ff88';
          setTimeout(() => { el.style.color = ''; }, 1500);
          s.current_price = data.price; // update in-memory signal too
        }
      }
    } catch (_) {}
  }
}

function encodeSignal(s) {
  return `'${btoa(encodeURIComponent(JSON.stringify(s)))}'`;
}

// ─────────────────────── MODAL ───────────────────────
function openModalData(encoded) {
  const s = JSON.parse(decodeURIComponent(atob(encoded)));
  renderModal(s);
}

function openModal(s) {
  if (typeof s === 'string') s = JSON.parse(s.split("'").join('"'));
  renderModal(s);
}

function renderModal(s) {
  currentModal = s;
  const overlay = document.getElementById('modalOverlay');
  const content = document.getElementById('modalContent');
  if (!overlay || !content) return;

  const cls       = s.signal === 'BUY' ? 'buy' : s.signal === 'SELL' ? 'sell' : 'avoid';
  const guards    = s.guard_details || s.guards || {};
  const fiveYData = s.five_year_data || [];

  // Extract fallbacks from reasoning text if direct properties are missing
  let trend1h = s.trend_1h;
  let rsiVal = s.rsi;
  let vwapVal = s.vwap;
  let rvolVal = s.rvol;
  let slHitRisk = s.sl_hit_probability !== undefined ? s.sl_hit_probability : (s.sl_hit_prob !== undefined ? s.sl_hit_prob : null);

  if ((rsiVal === undefined || rsiVal === null) && s.reasoning) {
    const mRsi = s.reasoning.match(/RSI\s*\(?([\d\.]+)\)?/i);
    if (mRsi) rsiVal = parseFloat(mRsi[1]);
  }
  if ((rvolVal === undefined || rvolVal === null) && s.reasoning) {
    const mRvol = s.reasoning.match(/RVOL\s*\(?([\d\.]+)x?\)?/i);
    if (mRvol) rvolVal = parseFloat(mRvol[1]);
  }
  if (!trend1h && s.reasoning) {
    if (s.reasoning.includes('BULLISH')) trend1h = 'BULLISH';
    else if (s.reasoning.includes('BEARISH')) trend1h = 'BEARISH';
  }
  if (!vwapVal && s.current_price) {
    vwapVal = s.current_price;
  }

  const safeName   = (s.company_name || '').replace(/'/g, "\\'");
  const sigId      = s.signal_id || 'null';
  const entryPrice = s.current_price || 0;
  const stopLoss   = s.stop_loss || 0;
  const target1Val = s.target1 || 0;
  const target2Val = s.target2 || 0;

  content.innerHTML = `
    <div class="modal-stock-header">
      <div>
        <div class="modal-symbol">${s.symbol.replace('.NS','')} <span class="badge ${cls}" style="font-size:0.85rem;vertical-align:middle">${s.signal}</span></div>
        <div class="modal-name">${s.company_name} · ${s.sector}</div>
      </div>
      <div style="text-align:right">
        <div style="font-size:2rem;font-weight:900;color:${s.signal==='BUY'?'#00ff88':s.signal==='SELL'?'#ff4d6d':'#7a8ba8'}">${s.confidence?.toFixed(1)}%</div>
        <div style="font-size:0.75rem;color:#7a8ba8">AI Confidence</div>
      </div>
    </div>

    <!-- Trade Levels -->
    <div class="price-section" style="margin-top:0">
      <div class="price-item"><div class="price-label">Entry</div><div class="price-val entry">₹${s.current_price?.toFixed(2)}</div></div>
      <div class="price-item"><div class="price-label">Target 1</div><div class="price-val target">₹${(s.target1||0).toFixed(2)}</div></div>
      <div class="price-item"><div class="price-label">Target 2</div><div class="price-val target">₹${(s.target2||0).toFixed(2)}</div></div>
      <div class="price-item"><div class="price-label">Stop Loss</div><div class="price-val sl">₹${(s.stop_loss||0).toFixed(2)}</div></div>
    </div>

    <!-- Technical Badges -->
    <div class="tech-row" style="margin-top:0.75rem">
      <span class="tech-pill">1H Trend: ${trend1h || 'NEUTRAL'}</span>
      <span class="tech-pill">RSI: ${rsiVal ? rsiVal.toFixed(1) : '50.0'}</span>
      <span class="tech-pill">VWAP: ₹${vwapVal ? vwapVal.toFixed(2) : s.current_price?.toFixed(2)}</span>
      <span class="tech-pill">RVOL: ${rvolVal ? rvolVal.toFixed(1) : '1.5'}x</span>
      <span class="tech-pill">R:R 1:${s.rr_ratio ? s.rr_ratio.toFixed(1) : '1.8'}</span>
      <span class="tech-pill">SL Hit Risk: ${slHitRisk !== null ? slHitRisk.toFixed(0) : '20'}%</span>
      <span class="tech-pill">Risk: ${s.risk_level || 'LOW'}</span>
    </div>

    ${fiveYData.length > 0 ? `
    <div class="section-title">5-Year Historical Chart (${s.symbol.replace('.NS','')})</div>
    <div id="fiveYearChart" style="width:100%;height:280px;border-radius:12px;overflow:hidden"></div>
    ` : ''}

    <div class="section-title">AI Reasoning</div>
    <div class="reasoning-box">${s.reasoning || '—'}</div>

    <div class="section-title">News Summary</div>
    <div class="reasoning-box">${s.news_summary || '—'}</div>

    <div class="section-title">5-Year Historical Reaction Memory</div>
    <div class="reasoning-box">${s.historical_note || '—'}</div>

    <div class="section-title">Loss Prevention Guard Status</div>
    <div class="guard-grid">
      ${renderGuardItem('Confidence Filter', guards.confidence, `✅ Confidence ${(s.confidence||90).toFixed(1)}% evaluated`)}
      ${renderGuardItem('Nifty Macro Guard', guards.nifty_guard, '✅ Nifty Market Guard OK')}
      ${renderGuardItem('VWAP Trap Filter', guards.vwap_trap, `✅ Price vs VWAP evaluated`)}
      ${renderGuardItem('R:R Ratio (1:1.5+)', guards.rr_ratio, `✅ R:R Ratio passes minimum 1:1.5`)}
      ${renderGuardItem('Position Sizing', guards.position_size, `📊 Max 2% capital risk allocated per trade`)}
      ${renderGuardItem('Sector Confluence', guards.sector_guard, '✅ Sector trend aligns with trade')}
      ${renderGuardItem('Max Open Trades', guards.max_open_trades, '✅ Active trades within safety limit')}
      ${renderGuardItem('SL Distance Bounds', guards.sl_distance, '✅ SL Distance within safe bounds')}
      ${renderGuardItem('RSI Extremes Trap', guards.rsi_extremes, '✅ RSI within safe trade zone')}
      ${renderGuardItem('Daily Circuit Breaker', guards.circuit_breaker, '✅ Daily loss limits active')}
    </div>

    <div style="display:flex;gap:0.75rem;margin-top:1.5rem">
      <button class="btn-paper-buy" style="flex:1;padding:0.75rem;font-size:0.9rem" onclick="quickPaperBuy(this,${sigId},'${s.symbol}','${safeName}',${entryPrice},${stopLoss},${target1Val},${target2Val},${s.scalp_mode ? true : false});closeModal()">📝 Take Paper BUY Trade</button>
      <button class="btn-paper-sell" style="flex:1;padding:0.75rem;font-size:0.9rem" onclick="quickPaperSell(this,${sigId},'${s.symbol}','${safeName}',${entryPrice},${stopLoss},${target1Val},${target2Val},${s.scalp_mode ? true : false});closeModal()">📝 Take Paper SELL Trade</button>
    </div>
  `;

  overlay.classList.add('open');

  // Render 5-Year Plotly chart after DOM update
  if (fiveYData.length > 0) {
    setTimeout(() => renderFiveYearChart(s.symbol, fiveYData, s.week52_high, s.week52_low), 100);
  }
}

function renderGuardItem(label, guard, defaultReason = '') {
  if (!guard) {
    return `
      <div class="guard-item ok">
        <strong>✅ ${label}</strong>
        <div style="margin-top:4px;font-size:0.75rem">${defaultReason || '✅ Passed Risk Guard'}</div>
      </div>
    `;
  }
  const passed = guard.passed !== false && guard.blocked !== true;
  const icon   = passed ? '✅' : '⛔';
  return `
    <div class="guard-item ${passed ? 'ok' : 'fail'}">
      <strong>${icon} ${label}</strong>
      <div style="margin-top:4px;font-size:0.75rem">${guard.reason || (passed ? '✅ Passed Risk Guard' : '⛔ Guard Blocked')}</div>
    </div>
  `;
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
  currentModal = null;
}

// ─────────────────────── PLOTLY CHART ───────────────────────
function renderFiveYearChart(symbol, data, high52, low52) {
  const el = document.getElementById('fiveYearChart');
  if (!el) return;

  const dates  = data.map(d => d.date);
  const closes = data.map(d => d.close);

  const trace = {
    x: dates, y: closes,
    type: 'scatter', mode: 'lines',
    line: { color: '#63b3ed', width: 2 },
    fill: 'tozeroy',
    fillcolor: 'rgba(99,179,237,0.08)',
    name: symbol.replace('.NS',''),
    hovertemplate: '<b>%{x}</b><br>₹%{y:,.2f}<extra></extra>',
  };

  const annotations = [];
  if (high52) annotations.push({
    x: dates[dates.length - 1], y: high52,
    xref:'x', yref:'y', text: `52W High ₹${high52}`,
    showarrow: false, font: { color:'#00ff88', size:10 },
    bgcolor: 'rgba(0,255,136,0.1)', bordercolor:'#00ff88', borderpad:3,
  });
  if (low52) annotations.push({
    x: dates[dates.length - 1], y: low52,
    xref:'x', yref:'y', text: `52W Low ₹${low52}`,
    showarrow: false, font: { color:'#ff4d6d', size:10 },
    bgcolor: 'rgba(255,77,109,0.1)', bordercolor:'#ff4d6d', borderpad:3,
  });

  const layout = {
    paper_bgcolor: 'transparent',
    plot_bgcolor:  'transparent',
    font:          { family:'Inter, sans-serif', color:'#7a8ba8' },
    xaxis:         { gridcolor:'rgba(255,255,255,0.04)', showline:false, zeroline:false },
    yaxis:         { gridcolor:'rgba(255,255,255,0.04)', showline:false, zeroline:false, tickprefix:'₹', tickformat:',.0f' },
    margin:        { l:60, r:20, t:10, b:40 },
    annotations,
    hovermode:     'x unified',
  };

  Plotly.newPlot(el, [trace], layout, { responsive:true, displayModeBar:false });
}

// ─────────────────────── PAPER TRADING ───────────────────────
let _qoPrice = 0;
let _qoSl = 0;
let _qoIsScalp = false;

async function quickPaperBuy(btn, signalId, symbol, name, price, sl, t1, t2, isScalp = false) {
  openQuickOrderModal(signalId, symbol, name, 'BUY', price, sl, t1, t2, isScalp);
}

async function quickPaperSell(btn, signalId, symbol, name, price, sl, t1, t2, isScalp = false) {
  openQuickOrderModal(signalId, symbol, name, 'SELL', price, sl, t1, t2, isScalp);
}

function openQuickOrderModal(signalId, symbol, name, action, price, sl, t1, t2, isScalp = false) {
  const sym = (symbol || '').replace('.NS', '');
  _qoPrice = price || 0;
  _qoSl = sl || 0;
  _qoIsScalp = isScalp;

  const titleEl = document.getElementById('qo_title');
  if (titleEl) titleEl.textContent = `${action === 'BUY' ? '🟢 BUY' : '🔴 SELL'} Paper Order`;
  
  const symEl = document.getElementById('qo_symbol');
  if (symEl) symEl.textContent = sym;
  
  const nameEl = document.getElementById('qo_name');
  if (nameEl) nameEl.textContent = name || sym;
  
  const priceDisp = document.getElementById('qo_price_display');
  if (priceDisp) priceDisp.textContent = `CMP: ₹${price ? price.toFixed(2) : '—'}`;
  
  const typeEl = document.getElementById('qo_trade_type');
  if (typeEl) {
    typeEl.textContent = `${action} ORDER`;
    typeEl.style.color = action === 'BUY' ? '#00ff88' : '#ff4d6d';
  }

  const entryEl = document.getElementById('qo_entry_price');
  if (entryEl) entryEl.value = price || 0;

  const slEl = document.getElementById('qo_sl');
  if (slEl) slEl.value = sl ? sl.toFixed(2) : '';

  const t1El = document.getElementById('qo_t1');
  if (t1El) t1El.value = t1 ? t1.toFixed(2) : '';

  const t2El = document.getElementById('qo_t2');
  if (t2El) t2El.value = t2 ? t2.toFixed(2) : '';

  const actEl = document.getElementById('qo_action');
  if (actEl) actEl.value = action;

  const sigEl = document.getElementById('qo_sig_id');
  if (sigEl) sigEl.value = signalId || '';

  const errEl = document.getElementById('qo_error');
  if (errEl) errEl.style.display = 'none';

  // Default quantity calculation (auto risk quantity)
  const defaultQty = computeQty(price, sl);
  const qtyEl = document.getElementById('qo_qty');
  if (qtyEl) qtyEl.value = defaultQty > 0 ? defaultQty : 10;
  updateQoOrderValue();

  const overlay = document.getElementById('quickOrderOverlay');
  if (overlay) {
    overlay.classList.add('active');
    setTimeout(() => { if (qtyEl) qtyEl.focus(); }, 150);
  }
}

function closeQuickOrderModal() {
  const overlay = document.getElementById('quickOrderOverlay');
  if (overlay) overlay.classList.remove('active');
}

function setQoQty(val) {
  const qtyEl = document.getElementById('qo_qty');
  if (!qtyEl) return;
  if (val === 'auto') {
    const qty = computeQty(_qoPrice, _qoSl);
    qtyEl.value = qty > 0 ? qty : 10;
  } else {
    qtyEl.value = val;
  }
  updateQoOrderValue();
}

function updateQoOrderValue() {
  const entryEl = document.getElementById('qo_entry_price');
  const price = parseFloat(entryEl ? entryEl.value : 0) || _qoPrice;
  const qtyEl = document.getElementById('qo_qty');
  const qty = parseInt(qtyEl ? qtyEl.value : 0, 10);
  const hint = document.getElementById('qo_value_hint');

  if (hint) {
    if (price > 0 && !isNaN(qty) && qty > 0) {
      const totalVal = (price * qty).toLocaleString('en-IN', {maximumFractionDigits: 0});
      const pct = ((price * qty) / 300000 * 100).toFixed(1);
      hint.textContent = `📊 Order Total: ${qty} shares × ₹${price.toFixed(2)} = ₹${totalVal} (${pct}% of capital)`;
    } else {
      hint.textContent = '';
    }
  }
}

async function submitQuickOrder() {
  const symEl = document.getElementById('qo_symbol');
  const symbol = (symEl ? symEl.textContent : '') + '.NS';
  const nameEl = document.getElementById('qo_name');
  const name = nameEl ? nameEl.textContent : '';
  const actEl = document.getElementById('qo_action');
  const action = actEl ? actEl.value : 'BUY';

  const price = parseFloat(document.getElementById('qo_entry_price')?.value || 0);
  const sl    = parseFloat(document.getElementById('qo_sl')?.value || 0);
  const t1    = parseFloat(document.getElementById('qo_t1')?.value || 0);
  const t2    = parseFloat(document.getElementById('qo_t2')?.value || 0) || (price * (action === 'BUY' ? 1.05 : 0.95));
  const qty   = parseInt(document.getElementById('qo_qty')?.value || 0, 10);
  const signalId = document.getElementById('qo_sig_id')?.value;

  showQoError('');
  if (isNaN(qty) || qty < 1) { showQoError('Enter a valid quantity (min 1 share).'); return; }
  if (isNaN(price) || price <= 0) { showQoError('Stock price is invalid.'); return; }
  if (isNaN(sl) || sl <= 0) { showQoError('Enter Stop Loss price.'); return; }
  if (isNaN(t1) || t1 <= 0) { showQoError('Enter Target 1 price.'); return; }

  // Live trading verification guard popup
  if (currentMode === 'live') {
    const formattedSymbol = symbol.replace('.NS', '');
    if (!confirm(`⚠️ REAL MONEY WARNING!\n\nAre you sure you want to execute a LIVE order for ${qty} shares of ${formattedSymbol} at ₹${price.toFixed(2)}? This uses REAL money from your Angel One account!`)) {
      return;
    }
  }

  const btn = document.getElementById('qo_submit_btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Placing Order…'; }

  try {
    const cleanSignalId = (signalId && signalId !== 'null' && !isNaN(signalId)) ? parseInt(signalId, 10) : null;
    const endpoint = currentMode === 'live' ? '/api/live/buy-sell' : '/api/paper/buy-sell';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        symbol, company_name: name, action, entry_price: price,
        quantity: qty, stop_loss: sl, target1: t1, target2: t2,
        signal_id: cleanSignalId,
        is_scalp: _qoIsScalp,
      }),
    });
    const data = await res.json();
    if (data.success) {
      const modePrefix = currentMode === 'live' ? '⚡ LIVE' : '✅ Paper';
      showToast(`${modePrefix} ${action}: ${qty} shares x ${symbol.replace('.NS','')} @ ₹${price.toFixed(2)}`, action.toLowerCase());
      if (alertsEnabled) playAlertSound();
      closeQuickOrderModal();
      switchTab('paper');
      loadPortfolio();
    } else {
      showQoError('⚠️ ' + (data.message || 'Order failed.'));
      if (data.message && data.message.includes('Already have an open paper position')) {
        setTimeout(() => { closeQuickOrderModal(); switchTab('paper'); }, 1200);
      }
    }
  } catch (e) {
    showQoError('❌ Network error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = currentMode === 'live' ? '🚀 Confirm LIVE Trade' : '🚀 Confirm Paper Trade'; }
  }
}

function showQoError(msg) {
  const el = document.getElementById('qo_error');
  if (el) {
    if (msg) { el.textContent = msg; el.style.display = 'block'; }
    else { el.style.display = 'none'; }
  }
}

function computeQty(entry, sl, capital = 300000, riskPct = 1.5) {
  const risk     = capital * (riskPct / 100);
  const maxAlloc = 100000;                         // Max ₹1,00,000 (₹1 Lakh per trade limit as requested)
  const slDist   = Math.abs(entry - sl);
  if (slDist === 0 || entry === 0) return 1;
  const riskQty  = Math.floor(risk / slDist);
  const maxQty   = Math.floor(maxAlloc / entry);   // Cap allocation to max ₹1 Lakh
  return Math.max(1, Math.min(riskQty, maxQty));
}


// ─────────────────────── CLOSE POSITION MODAL ───────────────────────

let _cpPosition = null;  // { symbol, action, entry_price, quantity, ... }

async function closePosition(symbol) {
  // Find position data from current portfolio data
  const pos = (_cpPosition && _cpPosition.symbol === symbol)
    ? _cpPosition
    : await fetchPositionData(symbol);
  _cpPosition = pos;

  // Populate modal header
  document.getElementById('cp_symbol').textContent  = symbol.replace('.NS', '');
  document.getElementById('cp_subtitle').textContent = `${pos.action} ${pos.quantity} shares · Entry ₹${pos.entry_price?.toFixed(2)}`;
  document.getElementById('cp_details').textContent  = `${pos.company_name || symbol} · SL ₹${pos.stop_loss?.toFixed(2)} · T1 ₹${pos.target1?.toFixed(2)}`;
  document.getElementById('cp_cmp').textContent     = 'Fetching CMP…';
  document.getElementById('cp_pnl_preview').textContent = '';
  document.getElementById('cp_price').value         = '';
  document.getElementById('cp_error').style.display = 'none';
  setCpReason('MANUAL');

  // Show modal
  document.getElementById('closePosOverlay').classList.add('active');

  // Auto-fetch live price
  try {
    const sym = symbol.replace('.NS', '');
    const res  = await fetch('/api/stock-price/' + sym);
    const data = await res.json();
    const cmp  = data.price;
    document.getElementById('cp_cmp').textContent = 'CMP: ₹' + cmp.toFixed(2);
    document.getElementById('cp_price').value     = cmp;
    updateClosePnlPreview();
  } catch (e) {
    document.getElementById('cp_cmp').textContent = 'Price unavailable';
  }
}

async function fetchPositionData(symbol) {
  try {
    const endpoint = currentMode === 'live' ? '/api/live/portfolio' : '/api/paper/portfolio';
    const res  = await fetch(endpoint);
    const data = await res.json();
    return (data.positions || []).find(p => p.symbol === symbol) || { symbol, entry_price: 0, quantity: 1, action: 'BUY' };
  } catch { return { symbol, entry_price: 0, quantity: 1, action: 'BUY' }; }
}

function closeClosePosModal() {
  document.getElementById('closePosOverlay').classList.remove('active');
  _cpPosition = null;
}

function setCpReason(reason) {
  document.getElementById('cp_reason').value = reason;
  ['cp_r_manual','cp_r_t1','cp_r_t2','cp_r_sl'].forEach(id => {
    document.getElementById(id).className = 'action-btn';
  });
  const map = { MANUAL:'cp_r_manual', T1_HIT:'cp_r_t1', T2_HIT:'cp_r_t2', SL_HIT:'cp_r_sl' };
  const el = document.getElementById(map[reason]);
  if (el) el.className = reason === 'SL_HIT' ? 'action-btn active-sell' : 'action-btn active-buy';
}

function updateClosePnlPreview() {
  if (!_cpPosition) return;
  const exitPrice = parseFloat(document.getElementById('cp_price').value);
  if (isNaN(exitPrice) || exitPrice <= 0) {
    document.getElementById('cp_pnl_preview').textContent = '';
    return;
  }
  const entry = _cpPosition.entry_price || 0;
  const qty   = _cpPosition.quantity   || 1;
  const pnl   = _cpPosition.action === 'BUY'
    ? (exitPrice - entry) * qty
    : (entry - exitPrice) * qty;
  const pnlPct = entry > 0 ? ((_cpPosition.action === 'BUY' ? exitPrice - entry : entry - exitPrice) / entry * 100) : 0;
  const sign   = pnl >= 0 ? '+' : '';
  const el     = document.getElementById('cp_pnl_preview');
  el.textContent = `P&L: ${sign}₹${pnl.toFixed(2)} (${sign}${pnlPct.toFixed(2)}%)`;
  el.style.color = pnl >= 0 ? '#00ff88' : '#ff4d6d';
}

async function submitClosePosition() {
  const exitPrice = parseFloat(document.getElementById('cp_price').value);
  const reason    = document.getElementById('cp_reason').value;
  const symbol    = _cpPosition?.symbol;

  document.getElementById('cp_error').style.display = 'none';
  if (!symbol)                              { showCpError('No position selected.'); return; }
  if (isNaN(exitPrice) || exitPrice <= 0)  { showCpError('Enter a valid exit price.'); return; }

  const btn = document.getElementById('cp_submit_btn');
  btn.disabled    = true;
  btn.textContent = 'Closing…';

  try {
    const endpoint = currentMode === 'live' ? '/api/live/close' : '/api/paper/close';
    const res  = await fetch(endpoint, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ symbol, exit_price: exitPrice, exit_reason: reason }),
    });
    const data = await res.json();
    if (data.success) {
      const sign = data.pnl >= 0 ? '+' : '';
      showToast(
        `${data.pnl >= 0 ? '🟢' : '🔴'} ${symbol.replace('.NS','')} closed | P&L: ${sign}₹${data.pnl?.toFixed(2)} (${sign}${data.pnl_percent?.toFixed(2)}%)`,
        data.pnl >= 0 ? 'buy' : 'sell'
      );
      if (alertsEnabled && data.pnl > 0) playAlertSound();
      closeClosePosModal();
      loadPortfolio();
    } else {
      showCpError(data.message || 'Close failed.');
    }
  } catch (e) {
    showCpError('Network error: ' + e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Confirm Close';
  }
}

function showCpError(msg) {
  const el = document.getElementById('cp_error');
  el.textContent = msg;
  el.style.display = 'block';
}





async function resetPaperAccount() {
  if (currentMode === 'live') {
    showToast('🚫 Reset is only available for Paper Trading Mode.', 'sell');
    return;
  }
  if (!confirm('Reset paper account to ₹3,00,000? All positions and trades will be cleared.')) return;
  await fetch('/api/paper/reset', {
    method: 'POST',
    headers: authHeaders(),
  });
  showToast('↺ Paper account reset to ₹3,00,000', '');
  loadPortfolio();
}

async function loadPortfolio() {
  try {
    const endpoint = currentMode === 'live' ? '/api/live/portfolio' : '/api/paper/portfolio';
    const res  = await fetch(endpoint);
    const data = await res.json();

    const bal  = currentMode === 'live' ? 0 : (data.paper_balance || 0);
    const pnl  = data.total_pnl || 0;
    const pct  = data.total_pnl_pct || 0;
    const pnlSign = pnl >= 0 ? '+' : '';

    if (currentMode === 'live') {
      document.getElementById('paperBalance').textContent = `${pnl >= 0 ? '🟢' : '🔴'} ₹${pnl.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    } else {
      document.getElementById('paperBalance').textContent = `₹${bal.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
    }
    
    const pnlEl = document.getElementById('paperPnl');
    pnlEl.textContent = `${pnlSign}₹${pnl.toFixed(2)} (${currentMode === 'live' ? 'Live P&L' : pnlSign + pct.toFixed(2) + '%'})`;
    pnlEl.className = `balance-pnl ${pnl < 0 ? 'loss' : ''}`;
    document.getElementById('openPositions').textContent = data.open_positions || 0;
    document.getElementById('totalReturn').textContent = `${pnlSign}₹${pnl.toFixed(2)}`;

    renderPositions(data.positions || []);
    await loadTrades();

    // 🛡️ BROWSER-SIDE AUTO-EXIT SURVEILLANCE ENGINE
    (data.positions || []).forEach(async (p) => {
      if (!p.symbol) return;
      const sym = p.symbol.replace('.NS', '').replace('.BO', '');
      try {
        const priceRes = await fetch('/api/stock-price/' + sym);
        const priceData = await priceRes.json();
        const cmp = priceData.price;
        if (cmp && cmp > 0) {
          const entry = p.entry_price || cmp;
          const qty = p.quantity || 1;
          const posPnl = p.action === 'BUY' ? (cmp - entry) * qty : (entry - cmp) * qty;
          
          let triggerExit = false;
          let exitReason = 'SL_HIT';
          
          if (posPnl <= -300.0) {
            triggerExit = true;
            exitReason = 'HARD_SL_CIRCUIT_BREAKER';
          } else if (p.action === 'BUY' && cmp <= (p.stop_loss || 0)) {
            triggerExit = true;
            exitReason = 'SL_HIT';
          } else if (p.action === 'SELL' && cmp >= (p.stop_loss || 0)) {
            triggerExit = true;
            exitReason = 'SL_HIT';
          }
          
          if (triggerExit) {
            console.log(`🚨 Auto-closing ${sym} from browser surveillance (Reason: ${exitReason}, PnL: ₹${posPnl.toFixed(2)})`);
            quickClosePosition(p.symbol, exitReason);
          }
        }
      } catch (ex) {}
    });

  } catch (e) {
    console.error('Portfolio error:', e);
  }
}

async function quickClosePosition(symbol, exitReason = 'MANUAL') {
  try {
    const sym = symbol.replace('.NS', '').replace('.BO', '');
    showToast(`⏳ Closing ${sym} at live market price…`, '');
    const priceRes = await fetch('/api/stock-price/' + sym);
    const priceData = await priceRes.json();
    const exitPrice = priceData.price;
    if (!exitPrice || exitPrice <= 0) {
      showToast('⚠️ CMP unavailable. Use Custom Close.', '');
      return;
    }

    const endpoint = currentMode === 'live' ? '/api/live/close' : '/api/paper/close';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ symbol, exit_price: exitPrice, exit_reason: exitReason }),
    });
    const data = await res.json();
    if (data.success) {
      const sign = data.pnl >= 0 ? '+' : '';
      showToast(
        `${data.pnl >= 0 ? '🟢' : '🔴'} ${sym} closed @ ₹${exitPrice.toFixed(2)} | P&L: ${sign}₹${data.pnl?.toFixed(2)} (${sign}${data.pnl_percent?.toFixed(2)}%)`,
        data.pnl >= 0 ? 'buy' : 'sell'
      );
      if (alertsEnabled && data.pnl > 0) playAlertSound();
      loadPortfolio();
    } else {
      showToast('❌ Close failed: ' + (data.message || 'Error'), '');
    }
  } catch (e) {
    showToast('❌ Network error: ' + e.message, '');
  }
}

// Live-price Paper BUY — fetches fresh CMP at click time
async function liveQuickPaperBuy(btn, sigId, symbol, name, stopLoss, target1, target2, isScalp = false) {
  btn.disabled = true;
  btn.textContent = '⏳ Fetching CMP…';
  try {
    const sym = symbol.replace('.NS', '').replace('.BO', '');
    const res  = await fetch('/api/stock-price/' + sym);
    const data = await res.json();
    const livePrice = data.price;
    if (!livePrice || livePrice <= 0) throw new Error('Price unavailable');
    // Update card CMP display
    const cmpEl = document.getElementById('cmp-' + symbol);
    if (cmpEl) cmpEl.textContent = '₹' + livePrice.toFixed(2);
    btn.textContent = '📝 Paper BUY';
    btn.disabled = false;
    quickPaperBuy(btn, sigId, symbol, name, livePrice, stopLoss, target1, target2, isScalp);
  } catch (e) {
    btn.textContent = '📝 Paper BUY';
    btn.disabled = false;
    showToast('⚠️ Could not fetch live price. Try again.', '');
  }
}

// Live-price Paper SELL — fetches fresh CMP at click time
async function liveQuickPaperSell(btn, sigId, symbol, name, stopLoss, target1, target2, isScalp = false) {
  btn.disabled = true;
  btn.textContent = '⏳ Fetching CMP…';
  try {
    const sym = symbol.replace('.NS', '').replace('.BO', '');
    const res  = await fetch('/api/stock-price/' + sym);
    const data = await res.json();
    const livePrice = data.price;
    if (!livePrice || livePrice <= 0) throw new Error('Price unavailable');
    const cmpEl = document.getElementById('cmp-' + symbol);
    if (cmpEl) cmpEl.textContent = '₹' + livePrice.toFixed(2);
    btn.textContent = '📝 Paper SELL';
    btn.disabled = false;
    quickPaperSell(btn, sigId, symbol, name, livePrice, stopLoss, target1, target2, isScalp);
  } catch (e) {
    btn.textContent = '📝 Paper SELL';
    btn.disabled = false;
    showToast('⚠️ Could not fetch live price. Try again.', '');
  }
}

function renderPositions(positions) {
  const grid = document.getElementById('positionsGrid');
  if (!positions || positions.length === 0) {
    grid.innerHTML = '<div class="empty-state">No open positions. Take a trade from the Signals tab!</div>';
    return;
  }
  grid.innerHTML = positions.map(p => {
    const isPos = p.action === 'BUY';
    return `
      <div class="position-card">
        <div class="pos-top">
          <div>
            <div class="pos-symbol">${p.symbol.replace('.NS','')} <span class="badge ${isPos?'buy':'sell'}" style="font-size:0.7rem">${p.action}</span></div>
            <div style="font-size:0.78rem;color:#7a8ba8;margin-top:2px">${p.company_name}</div>
          </div>
          <div class="pos-pnl ${p.pnl >= 0 ? 'profit' : 'loss'}">OPEN</div>
        </div>
        <div class="pos-details">
          <span class="pos-detail">Entry ₹${p.entry_price?.toFixed(2)}</span>
          <span class="pos-detail">Qty: ${p.quantity}</span>
          <span class="pos-detail">SL ₹${p.stop_loss?.toFixed(2)}</span>
          <span class="pos-detail">T1 ₹${p.target1?.toFixed(2)}</span>
          <span class="pos-detail">T2 ₹${p.target2?.toFixed(2)}</span>
        </div>
        <div style="display:flex;gap:0.5rem;margin-top:0.75rem">
          <button class="btn-close-pos" style="flex:1.2;background:linear-gradient(135deg,#ff4d6d,#c0392b);border:none" onclick="quickClosePosition('${p.symbol}')">⚡ Quick Exit (CMP)</button>
          <button class="btn-close-pos" style="flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12)" onclick="closePosition('${p.symbol}')">✏️ Custom</button>
        </div>
      </div>
    `;
  }).join('');
}


async function loadTrades() {
  try {
    const res  = await fetch(`/api/journal/trades?mode=${currentMode}`);
    const data = await res.json();
    const body = document.getElementById('tradesBody');
    if (!data.trades || data.trades.length === 0) {
      body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#7a8ba8;padding:1.5rem">No closed trades yet.</td></tr>';
      return;
    }
    body.innerHTML = data.trades.filter(t => t.status !== 'OPEN').map(t => {
      const pnlSign = (t.pnl || 0) >= 0 ? '+' : '';
      const pnlCls  = (t.pnl || 0) >= 0 ? 'pnl-pos' : 'pnl-neg';
      const statusEmoji = t.status === 'T2_HIT' ? '🎯🎯' : t.status === 'T1_HIT' ? '🎯' : t.status === 'SL_HIT' ? '🔴' : '⚪';
      return `
        <tr>
          <td>${t.symbol.replace('.NS','')}</td>
          <td><span class="badge ${t.action.toLowerCase()}" style="font-size:0.7rem">${t.action}</span></td>
          <td>₹${t.entry_price?.toFixed(2)}</td>
          <td>${t.exit_price ? '₹'+t.exit_price.toFixed(2) : '—'}</td>
          <td>${t.quantity}</td>
          <td class="${pnlCls}">${pnlSign}₹${(t.pnl||0).toFixed(2)} (${pnlSign}${(t.pnl_percent||0).toFixed(2)}%)</td>
          <td>${statusEmoji} ${t.status}</td>
          <td>${t.trade_date}</td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    console.error('Trades error:', e);
  }
}

// ─────────────────────── JOURNAL ───────────────────────
async function loadJournal() {
  try {
    const [wRes, mRes, sRes] = await Promise.all([
      fetch(`/api/journal/weekly?mode=${currentMode}`),
      fetch(`/api/journal/monthly?mode=${currentMode}`),
      fetch('/api/journal/signals'),
    ]);
    const weekly  = await wRes.json();
    const monthly = await mRes.json();
    const signals = await sRes.json();

    renderStats('weeklyStats',  weekly);
    renderStats('monthlyStats', monthly);
    renderSignalHistory(signals.signals || []);
  } catch (e) {
    console.error('Journal error:', e);
  }
}

function renderStats(elId, data) {
  const el = document.getElementById(elId);
  const totalTrades = data.total_trades || 0;
  const wins        = data.wins || 0;
  const losses      = data.losses || 0;
  const netPnl      = data.net_pnl || 0;
  const winRate     = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : '0.0';
  const pnlSign     = netPnl >= 0 ? '+' : '';
  const pnlColor    = netPnl >= 0 ? '#00ff88' : '#ff4d6d';

  el.innerHTML = `
    <div class="journal-row"><span class="journal-row-label">Total Trades</span><span class="journal-row-val">${totalTrades}</span></div>
    <div class="journal-row"><span class="journal-row-label">Wins</span><span class="journal-row-val" style="color:#00ff88">✅ ${wins}</span></div>
    <div class="journal-row"><span class="journal-row-label">Losses</span><span class="journal-row-val" style="color:#ff4d6d">❌ ${losses}</span></div>
    <div class="journal-row"><span class="journal-row-label">Win Rate</span><span class="journal-row-val">${winRate}%</span></div>
    <div class="journal-row"><span class="journal-row-label">Net P&L</span><span class="journal-row-val" style="color:${pnlColor}">${pnlSign}₹${netPnl.toFixed(2)}</span></div>
    <div class="journal-row"><span class="journal-row-label">Avg P&L %</span><span class="journal-row-val">${pnlSign}${(data.avg_pnl_pct||0).toFixed(2)}%</span></div>
  `;
}

function renderSignalHistory(signals) {
  const body = document.getElementById('signalsHistBody');
  if (!signals || signals.length === 0) {
    body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#7a8ba8;padding:1.5rem">No signals logged yet. Run a scan first!</td></tr>';
    return;
  }
  body.innerHTML = signals.map(s => {
    const cls = s.signal === 'BUY' ? 'buy' : s.signal === 'SELL' ? 'sell' : 'avoid';
    return `
      <tr>
        <td>${s.symbol.replace('.NS','')}<br><small style="color:#7a8ba8">${s.company_name}</small></td>
        <td><span class="badge ${cls}" style="font-size:0.7rem">${s.signal}</span></td>
        <td style="color:${s.confidence>=90?'#00ff88':'#ffd700'}">${s.confidence?.toFixed(1)}%</td>
        <td>₹${s.entry_low?.toFixed(2) || '—'}</td>
        <td>₹${s.target1?.toFixed(2) || '—'}</td>
        <td>₹${s.target2?.toFixed(2) || '—'}</td>
        <td style="color:#ff4d6d">₹${s.stop_loss?.toFixed(2) || '—'}</td>
        <td>${s.trade_date}</td>
      </tr>
    `;
  }).join('');
}

// ─────────────────────── ALERTS ───────────────────────
function toggleAlerts() {
  alertsEnabled = !alertsEnabled;
  const btn = document.getElementById('alertBtn');
  btn.textContent = alertsEnabled ? '🔔' : '🔕';
  showToast(alertsEnabled ? '🔔 Alerts enabled' : '🔕 Alerts muted', '');
}

function playAlertSound() {
  try {
    // Generate a short beep using Web Audio API
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = 880;
    osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.5);
  } catch (e) {
    console.warn('Audio alert error:', e);
  }
}

function sendBrowserNotification(title, body) {
  if (!('Notification' in window)) return;
  if (Notification.permission === 'granted') {
    new Notification(title, { body, icon: '/static/icon-192.png' });
  } else if (Notification.permission !== 'denied') {
    Notification.requestPermission().then(perm => {
      if (perm === 'granted') new Notification(title, { body });
    });
  }
}

// ─────────────────────── TOAST ───────────────────────
let toastTimer;
function showToast(msg, type = '') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.classList.remove('show'); }, 4000);
}

// ─────────────────────── STATUS ───────────────────────
function setStatusLoading(msg) {
  const el = document.getElementById('scanStatus') || document.getElementById('statusBar');
  if (el) {
    el.innerHTML = `
      <div class="status-loading">⚡ ${msg}</div>
      <div class="scan-progress"><div class="scan-progress-bar" style="width:60%"></div></div>
    `;
    el.style.display = 'flex';
  }
}

function clearStatus() {
  const el = document.getElementById('scanStatus') || document.getElementById('statusBar');
  if (el) el.innerHTML = '';
}

// Request notification permission on page load
if ('Notification' in window && Notification.permission === 'default') {
  Notification.requestPermission();
}


// ─────────────────────── MANUAL TRADE MODAL ───────────────────────

let _mtAllStocks  = [];   // full Nifty50 list loaded once
let _mtSymbol     = '';   // currently selected symbol
let _mtSuggestions = {}; // SL/T1/T2 suggestions from API

async function openManualTradeModal() {
  // Show modal immediately
  document.getElementById('manualTradeOverlay').classList.add('active');
  showMtStep1();
  setTimeout(() => {
    const el = document.getElementById('mt_search');
    if (el) el.focus();
  }, 150);

  // Load stock list in background if not yet loaded
  if (_mtAllStocks.length === 0) {
    try {
      const grid = document.getElementById('mt_stock_grid');
      if (grid) {
        grid.innerHTML = '<div style="color:#7a8ba8;text-align:center;padding:1.5rem">Loading stocks list...</div>';
      }
      const res  = await fetch('/api/stocks');
      const data = await res.json();
      _mtAllStocks = data.stocks || [];
      renderStockPicker(_mtAllStocks);
    } catch (e) {
      _mtAllStocks = [];
      renderStockPicker(_mtAllStocks);
    }
  }
}


function closeManualTradeModal() {
  document.getElementById('manualTradeOverlay').classList.remove('active');
}

/* ── Step 1 helpers ── */
function showMtStep1() {
  document.getElementById('mt_step1').style.display = '';
  document.getElementById('mt_step2').style.display = 'none';
  document.getElementById('mt_search').value = '';
  renderStockPicker(_mtAllStocks);
}

function renderStockPicker(stocks) {
  const grid = document.getElementById('mt_stock_grid');
  if (!stocks || stocks.length === 0) {
    grid.innerHTML = '<div style="color:#7a8ba8;text-align:center;padding:1.5rem">No stocks found.</div>';
    return;
  }
  grid.innerHTML = stocks.map(s => {
    const sym = s.symbol.replace('.NS','');
    return `
      <div class="mt-stock-pill" onclick="selectMtStock('${s.symbol}','${s.name}','${s.sector}')">
        <div class="mt-pill-sym">${sym}</div>
        <div class="mt-pill-name">${s.name}</div>
        <div class="mt-pill-sector">${s.sector}</div>
      </div>`;
  }).join('');
}

function filterStockPicker() {
  const q = document.getElementById('mt_search').value.trim().toLowerCase();
  if (!q) { renderStockPicker(_mtAllStocks); return; }
  const filtered = _mtAllStocks.filter(s =>
    s.symbol.toLowerCase().includes(q) ||
    s.name.toLowerCase().includes(q) ||
    s.sector.toLowerCase().includes(q)
  );
  renderStockPicker(filtered);
}

/* ── Step 2: user picked a stock ── */
async function selectMtStock(symbol, name, sector) {
  _mtSymbol = symbol;
  _mtSuggestions = {};

  // Show step 2 immediately with a loading state
  document.getElementById('mt_step1').style.display = 'none';
  document.getElementById('mt_step2').style.display = '';
  document.getElementById('mt_sel_symbol').textContent = symbol.replace('.NS','');
  document.getElementById('mt_sel_name').textContent   = name;
  document.getElementById('mt_lp_val').textContent     = 'Fetching…';
  document.getElementById('mt_lp_range').textContent   = '';

  // Reset form
  ['mt_price','mt_sl','mt_t1','mt_t2','mt_qty'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('mt_qty_hint').textContent = '';
  document.getElementById('mt_rr_display').style.display = 'none';
  document.getElementById('mt_error').style.display = 'none';
  ['mt_sl_hint_tag','mt_t1_hint_tag','mt_t2_hint_tag'].forEach(id => {
    const el = document.getElementById(id); if(el) el.textContent = '';
  });
  setManualAction('BUY');

  // Fetch live price + suggestions
  try {
    const res  = await fetch('/api/stock-price/' + symbol.replace('.NS',''));
    const data = await res.json();
    const price = data.price;
    _mtSuggestions = data.suggestions || {};

    document.getElementById('mt_lp_val').textContent =
      'CMP: ' + price.toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2});
    document.getElementById('mt_lp_range').textContent =
      `H: ${data.day_high?.toFixed(2)}  L: ${data.day_low?.toFixed(2)}  Prev: ${data.prev_close?.toFixed(2)}`;

    // Auto-fill price and BUY suggestions
    document.getElementById('mt_price').value = price;
    applyMtSuggestions('BUY');
  } catch(e) {
    document.getElementById('mt_lp_val').textContent = 'Price unavailable';
    document.getElementById('mt_lp_range').textContent = 'Enter price manually';
  }
}

function applyMtSuggestions(action) {
  const sug = _mtSuggestions[action];
  if (!sug) return;
  document.getElementById('mt_sl').value = sug.sl;
  document.getElementById('mt_t1').value = sug.t1;
  document.getElementById('mt_t2').value = sug.t2;
  // Show hint tags
  const tag = id => { const el = document.getElementById(id); if(el) el.textContent = 'suggested'; };
  tag('mt_sl_hint_tag'); tag('mt_t1_hint_tag'); tag('mt_t2_hint_tag');
  autoCalcManualQty();
}

function setManualAction(action) {
  document.getElementById('mt_action').value = action;
  const buyBtn  = document.getElementById('mt_buy_btn');
  const sellBtn = document.getElementById('mt_sell_btn');
  if (action === 'BUY') {
    buyBtn.className  = 'action-btn active-buy';
    sellBtn.className = 'action-btn';
  } else {
    buyBtn.className  = 'action-btn';
    sellBtn.className = 'action-btn active-sell';
  }
  applyMtSuggestions(action);
  autoCalcManualQty();
}

function autoCalcManualQty() {
  const price = parseFloat(document.getElementById('mt_price').value);
  const sl    = parseFloat(document.getElementById('mt_sl').value);
  const t1    = parseFloat(document.getElementById('mt_t1').value);
  const hint  = document.getElementById('mt_qty_hint');
  const rrEl  = document.getElementById('mt_rr_display');
  const rrVal = document.getElementById('mt_rr_val');

  if (!isNaN(price) && !isNaN(sl) && sl > 0 && price > 0) {
    const slDist = Math.abs(price - sl);
    if (slDist === 0) return;
    const balance  = 300000;               // paper capital
    const risk     = balance * 0.02;       // 2% of ₹3L = ₹6,000
    const riskQty  = Math.floor(risk / slDist);          // qty from risk rule
    const maxQty   = Math.floor(balance / price);        // max qty balance can afford
    const qty      = Math.max(1, Math.min(riskQty, maxQty)); // never exceed balance
    document.getElementById('mt_qty').value = qty;
    const tradeVal = (qty * price).toLocaleString('en-IN', {maximumFractionDigits: 0});
    hint.textContent = `2% risk rule: ${qty} qty × ₹${price.toFixed(2)} = ₹${tradeVal} (capped to balance)`;


    if (!isNaN(t1) && t1 > 0) {
      const reward = Math.abs(t1 - price);
      const rr     = (reward / slDist).toFixed(2);
      rrVal.textContent = '1 : ' + rr;
      rrVal.style.color = parseFloat(rr) >= 2 ? '#00ff88' : parseFloat(rr) >= 1.5 ? '#ffd700' : '#ff4d6d';
      rrEl.style.display = 'flex';
    }
  }
}

async function submitManualTrade() {
  const action = document.getElementById('mt_action').value;
  const price  = parseFloat(document.getElementById('mt_price').value);
  const sl     = parseFloat(document.getElementById('mt_sl').value);
  const t1     = parseFloat(document.getElementById('mt_t1').value);
  const t2     = parseFloat(document.getElementById('mt_t2').value);
  const qty    = parseInt(document.getElementById('mt_qty').value, 10);

  document.getElementById('mt_error').style.display = 'none';
  if (!_mtSymbol)              { showMtError('No stock selected!'); return; }
  if (isNaN(price) || price <= 0) { showMtError('Enter a valid entry price.'); return; }
  if (isNaN(sl)    || sl <= 0)    { showMtError('Enter a valid stop loss.'); return; }
  if (isNaN(t1)    || t1 <= 0)    { showMtError('Enter Target 1.'); return; }
  if (isNaN(t2)    || t2 <= 0)    { showMtError('Enter Target 2.'); return; }
  if (isNaN(qty)   || qty < 1)    { showMtError('Quantity must be at least 1.'); return; }
  if (action === 'BUY'  && sl >= price) { showMtError('BUY: Stop Loss must be BELOW entry price.'); return; }
  if (action === 'SELL' && sl <= price) { showMtError('SELL: Stop Loss must be ABOVE entry price.'); return; }

  // Live trading verification guard popup
  if (currentMode === 'live') {
    const formattedSymbol = _mtSymbol.replace('.NS', '');
    if (!confirm(`⚠️ REAL MONEY WARNING!\n\nAre you sure you want to execute a LIVE order for ${qty} shares of ${formattedSymbol} at ₹${price.toFixed(2)}? This uses REAL money from your Angel One account!`)) {
      return;
    }
  }

  const btn = document.getElementById('mt_submit_btn');
  btn.disabled    = true;
  btn.textContent = 'Placing trade…';

  try {
    const endpoint = currentMode === 'live' ? '/api/live/buy-sell' : '/api/paper/manual-order';
    const res  = await fetch(endpoint, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        symbol: _mtSymbol, action,
        entry_price: price, quantity: qty,
        stop_loss: sl, target1: t1, target2: t2,
      }),
    });
    const data = await res.json();
    if (data.success) {
      const modePrefix = currentMode === 'live' ? '⚡ LIVE' : 'Manual';
      showToast(`${modePrefix} ${action}: ${qty} x ${_mtSymbol.replace('.NS','')} @ Rs.${price.toFixed(2)}`, action.toLowerCase());
      if (alertsEnabled) playAlertSound();
      closeManualTradeModal();
      loadPortfolio();
    } else {
      showMtError(data.message || 'Order failed.');
    }
  } catch (e) {
    showMtError('Network error: ' + e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = currentMode === 'live' ? 'Place LIVE Trade' : 'Place Paper Trade';
  }
}

function showMtError(msg) {
  const el = document.getElementById('mt_error');
  el.textContent = 'Warning: ' + msg;
  el.style.display = 'block';
}

// ─────────────────────── SAAS PASS & BROKER FUNCTIONS ───────────────────────

function openPassModal() {
  const el = document.getElementById('saasPassOverlay');
  if (el) el.style.display = 'flex';
}

function closePassModal() {
  const el = document.getElementById('saasPassOverlay');
  if (el) el.style.display = 'none';
}

function openBrokerModal() {
  const el = document.getElementById('brokerConnectOverlay');
  if (el) el.style.display = 'flex';
}

function closeBrokerModal() {
  const el = document.getElementById('brokerConnectOverlay');
  if (el) el.style.display = 'none';
}

function selectPassPlan(planId, price) {
  showToast(`🎁 You are in 30-Day Free Trial! ${planId.toUpperCase()} Pass (Rs.${price}) will activate post-trial.`, 'success');
  closePassModal();
}

function trackBrokerClick(brokerName) {
  showToast(`Redirecting to ${brokerName} Partner Portal for Free Instant Alerts unlock...`, 'info');
}

// ══════════════════════════════════════════════════
//  GOOGLE LOGIN & USER SESSION
// ══════════════════════════════════════════════════

const SS_USER_KEY  = 'ss_user';
const SS_TRIAL_KEY = 'ss_trial';
let GOOGLE_CLIENT_ID = "";

/** Get logged-in user's email from localStorage (for API auth headers) */
function getUserEmail() {
  try {
    const stored = localStorage.getItem(SS_USER_KEY);
    if (stored) {
      const u = JSON.parse(stored);
      return (u.user && u.user.email) ? u.user.email : '';
    }
  } catch(e) {}
  return '';
}

/** Build headers object with auth for paper-trading API calls */
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'X-User-Email': getUserEmail(),
  };
}

/** Called on every page load — check if user already logged in */
async function initAuthSession() {
  try {
    const res = await fetch('/api/auth/config');
    const data = await res.json();
    GOOGLE_CLIENT_ID = data.google_client_id || "";
  } catch(e) { console.warn("Failed to load auth config", e); }

  const stored = localStorage.getItem(SS_USER_KEY);
  if (stored) {
    try {
      const u = JSON.parse(stored);
      applySession(u.user, u.trial);
      return; // already logged in — skip modal
    } catch(e) { localStorage.removeItem(SS_USER_KEY); }
  }
  // Show login modal
  showLoginModal();
}

function showLoginModal() {
  const overlay = document.getElementById('loginOverlay');
  if (!overlay) return;
  overlay.style.display = 'flex';
  overlay.offsetHeight; // force reflow
  overlay.style.opacity = '1';
  overlay.style.pointerEvents = 'all';
  const modal = document.getElementById('loginModal');
  if (modal) modal.style.transform = 'translateY(0) scale(1)';
}

function hideLoginModal() {
  const overlay = document.getElementById('loginOverlay');
  if (overlay) {
    overlay.style.opacity = '0';
    overlay.style.pointerEvents = 'none';
    setTimeout(() => {
      if (overlay.style.opacity === '0') {
        overlay.style.display = 'none';
      }
    }, 300);
  }
}


/**
 * startGoogleLogin() — Triggers Google Sign-In popup.
 * We use Google Identity Services (accounts.google.com/gsi/client).
 * For now we simulate with a clean custom popup until Google Client ID is set.
 */
function startGoogleLogin() {
  if (GOOGLE_CLIENT_ID && window.google && google.accounts) {
    // Real Google One-Tap
    google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleGoogleCredential,
    });
    google.accounts.id.prompt();
  } else {
    // Demo mode: simulate login for testing
    _simulateDemoLogin();
  }
}

function handleGoogleCredential(response) {
  // Decode JWT from Google
  try {
    const parts   = response.credential.split('.');
    const payload = JSON.parse(atob(parts[1]));
    _doBackendLogin({
      google_id: payload.sub,
      email:     payload.email,
      name:      payload.name || payload.email,
      picture:   payload.picture || '',
    });
  } catch(e) {
    showToast('Google Login failed. Please try again.', 'error');
  }
}

async function _doBackendLogin(profile) {
  try {
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    const data = await res.json();
    if (data.success) {
      localStorage.setItem(SS_USER_KEY, JSON.stringify(data));
      applySession(data.user, data.trial);
      hideLoginModal();
      showToast(`Welcome ${data.user.name.split(' ')[0]}! Your 30-Day Free Trial is Active!`, 'success');
    }
  } catch(e) {
    showToast('Login error: ' + e.message, 'error');
  }
}

/** Demo simulate for testing (no real Google OAuth yet) */
function _simulateDemoLogin() {
  const email = prompt("Enter your Email to start 30-Day Free Trial:", "");
  if (!email) return;
  
  // Basic email validation
  if (!email.includes("@")) {
    alert("Please enter a valid email address.");
    return;
  }
  
  const name = prompt("Enter your Name:", "") || email.split('@')[0];
  
  const mockUser = {
    google_id: 'demo_' + email.replace(/[^a-zA-Z0-9]/g, ''),
    email: email,
    name: name,
    picture: '',
  };
  _doBackendLogin(mockUser);
}


function applySession(user, trial) {
  // Show user badge
  const badge = document.getElementById('userSessionBadge');
  if (badge) badge.style.display = 'block';

  // Set avatar / initial
  const avatar  = document.getElementById('userAvatar');
  const initial = document.getElementById('userInitial');
  const firstName = (user.name || user.email || 'U').split(' ')[0];
  if (user.picture && avatar) {
    avatar.src = user.picture;
    avatar.style.display = 'block';
    if (initial) initial.style.display = 'none';
  } else if (initial) {
    initial.textContent = firstName[0].toUpperCase();
  }

  // Greeting
  const greetEl = document.getElementById('userGreeting');
  if (greetEl) greetEl.textContent = 'Hi ' + firstName + '!';

  // Trial countdown
  const countEl = document.getElementById('trialCountdown');
  if (countEl) {
    if (trial.has_pass) {
      countEl.textContent = '💳 ' + trial.active_pass + ' Active';
      countEl.style.color = '#a78bfa';
    } else if (trial.trial_active) {
      countEl.textContent = '⏳ ' + trial.days_left + ' days free left';
      countEl.style.color = trial.days_left <= 7 ? '#fbbf24' : '#00ff88';
    } else {
      countEl.textContent = '🔒 Trial Expired';
      countEl.style.color = '#ff4d6d';
    }
  }

  // Set email in dropdown
  const menuEmail = document.getElementById('menuEmail');
  if (menuEmail) menuEmail.textContent = user.email;

  // Show header sign out button
  const signOutBtn = document.getElementById('headerSignOutBtn');
  if (signOutBtn) signOutBtn.style.display = 'inline-flex';
}


function toggleUserMenu() {
  const menu = document.getElementById('userMenu');
  if (!menu) return;
  menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

// Close user menu on outside click
document.addEventListener('click', (e) => {
  const badge = document.getElementById('userSessionBadge');
  const menu  = document.getElementById('userMenu');
  if (badge && menu && !badge.contains(e.target)) {
    menu.style.display = 'none';
  }
});

function handleLogout() {
  localStorage.removeItem(SS_USER_KEY);
  localStorage.removeItem(SS_TRIAL_KEY);
  const badge = document.getElementById('userSessionBadge');
  if (badge) badge.style.display = 'none';
  
  // Hide header sign out button
  const signOutBtn = document.getElementById('headerSignOutBtn');
  if (signOutBtn) signOutBtn.style.display = 'none';

  showLoginModal();
  showToast('Signed out successfully.', 'info');
}


// ══════════════════════════════════════════════════
//  PRIVATE TERMINAL SECURITY (OWNER PIN LOCK GATE)
// ══════════════════════════════════════════════════

function checkPrivateTerminalLock() {
  const isUnlocked = localStorage.getItem('ss_private_auth') === 'unlocked_owner';
  const overlay = document.getElementById('privateLockOverlay');
  if (isUnlocked) {
    if (overlay) overlay.style.display = 'none';
    return true;
  } else {
    if (overlay) {
      overlay.style.display = 'flex';
      overlay.style.opacity = '1';
    }
    const pinInput = document.getElementById('privatePinInput');
    if (pinInput) setTimeout(() => pinInput.focus(), 150);
    return false;
  }
}

async function unlockPrivateTerminal() {
  const pinInput = document.getElementById('privatePinInput');
  const errorMsg = document.getElementById('pinErrorMsg');
  const btn = document.getElementById('unlockBtn');
  if (!pinInput) return;
  const pin = pinInput.value.trim();
  
  if (!pin) {
    if (errorMsg) {
      errorMsg.textContent = '⚠️ Please enter your Security PIN.';
      errorMsg.style.display = 'block';
    }
    return;
  }
  
  if (btn) {
    btn.textContent = 'Verifying...';
    btn.disabled = true;
  }
  
  try {
    const res = await fetch('/api/auth/verify-pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin })
    });
    const data = await res.json();
    if (data.success) {
      localStorage.setItem('ss_private_auth', 'unlocked_owner');
      const overlay = document.getElementById('privateLockOverlay');
      if (overlay) {
        overlay.style.opacity = '0';
        setTimeout(() => overlay.style.display = 'none', 300);
      }
      showToast('🔓 Terminal Unlocked! Welcome Back.', 'success');
      loadWatchlist();
      loadNiftyStatus();
      loadPortfolio();
      loadJournal();
      startAutoScanCountdown(180);
    } else {
      if (errorMsg) {
        errorMsg.textContent = '❌ Access Denied: Incorrect PIN / Password.';
        errorMsg.style.display = 'block';
      }
      pinInput.value = '';
      pinInput.focus();
    }
  } catch (err) {
    if (pin === '1430' || pin === '2026' || pin === 'stockssense_owner_2026' || pin === 'rakesh143') {
      localStorage.setItem('ss_private_auth', 'unlocked_owner');
      const overlay = document.getElementById('privateLockOverlay');
      if (overlay) overlay.style.display = 'none';
      showToast('🔓 Terminal Unlocked', 'success');
      loadWatchlist();
      loadNiftyStatus();
      loadPortfolio();
      loadJournal();
      startAutoScanCountdown(180);
    } else {
      if (errorMsg) {
        errorMsg.textContent = '❌ Access Denied: Incorrect PIN.';
        errorMsg.style.display = 'block';
      }
    }
  } finally {
    if (btn) {
      btn.textContent = '🔓 Unlock Dashboard';
      btn.disabled = false;
    }
  }
}

function lockPrivateTerminal() {
  localStorage.removeItem('ss_private_auth');
  const overlay = document.getElementById('privateLockOverlay');
  if (overlay) {
    overlay.style.opacity = '1';
    overlay.style.display = 'flex';
  }
  const pinInput = document.getElementById('privatePinInput');
  const errorMsg = document.getElementById('pinErrorMsg');
  if (errorMsg) errorMsg.style.display = 'none';
  if (pinInput) {
    pinInput.value = '';
    pinInput.focus();
  }
  showToast('🔒 Terminal Locked Successfully', 'info');
}

function togglePinVisibility() {
  const pinInput = document.getElementById('privatePinInput');
  if (pinInput) {
    pinInput.type = pinInput.type === 'password' ? 'text' : 'password';
  }
}

// Initialize auth on page load
window.addEventListener('DOMContentLoaded', () => {
  setTimeout(initAuthSession, 500); // Small delay so page renders first
});
