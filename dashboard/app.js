"use strict";

/* =========================================================================
   AI Trading Brain — Dashboard client
   Plain JS, no dependencies. Connects to ws(s)://<host>/ws, paints state
   from a snapshot + incremental messages, and drives the settings panel
   via PUT /api/settings and the flatten-all button via POST /api/flatten-all.
   ========================================================================= */

(function () {
  "use strict";

  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------

  var state = {
    positions: {},          // symbol -> {symbol, quantity, avg_entry_price, unrealized_pnl, realized_pnl}
    account: null,          // {net_liquidation, cash, buying_power, realized_pnl_today, unrealized_pnl}
    orders: [],             // array of order-log entries, newest first
    settings: null,         // BotSettings shape
    connectionState: "disconnected", // connected | connecting | disconnected | error
    chartSymbol: null,      // currently selected instrument for the price chart
  };

  var chart = null;
  var chartSeries = null;

  var INSTRUMENT_LABELS = {
    "GC=F": "Gold GC=F",
    "ES=F": "S&P 500 ES=F",
    "CL=F": "Crude Oil CL=F",
    "EURUSD=X": "EUR/USD EURUSD=X",
  };
  var INSTRUMENT_ORDER = ["GC=F", "ES=F", "CL=F", "EURUSD=X"];

  var MAX_ORDER_LOG = 500; // keep the DOM/table bounded for a long-running session

  // -----------------------------------------------------------------------
  // DOM refs
  // -----------------------------------------------------------------------

  var el = {
    disconnectBanner: document.getElementById("disconnectBanner"),
    modeBadge: document.getElementById("modeBadge"),
    connBadge: document.getElementById("connBadge"),
    connBadgeText: document.getElementById("connBadgeText"),
    killIndicator: document.getElementById("killIndicator"),
    flattenBtn: document.getElementById("flattenBtn"),

    accountUpdated: document.getElementById("accountUpdated"),
    statNetLiq: document.getElementById("statNetLiq"),
    statCash: document.getElementById("statCash"),
    statBuyingPower: document.getElementById("statBuyingPower"),
    statRealizedToday: document.getElementById("statRealizedToday"),
    statUnrealized: document.getElementById("statUnrealized"),

    positionsBody: document.getElementById("positionsBody"),
    positionsEmpty: document.getElementById("positionsEmpty"),
    positionsCount: document.getElementById("positionsCount"),

    ordersBody: document.getElementById("ordersBody"),
    ordersEmpty: document.getElementById("ordersEmpty"),
    ordersCount: document.getElementById("ordersCount"),

    accountModeInput: document.getElementById("accountModeInput"),
    riskPercentInput: document.getElementById("riskPercentInput"),
    maxContractsInput: document.getElementById("maxContractsInput"),
    minTierInput: document.getElementById("minTierInput"),
    drawdownInput: document.getElementById("drawdownInput"),
    instrumentsList: document.getElementById("instrumentsList"),
    killSwitchInput: document.getElementById("killSwitchInput"),
    saveState: document.getElementById("saveState"),

    chartTabs: document.getElementById("chartTabs"),
    priceChart: document.getElementById("priceChart"),
    tabBar: document.getElementById("tabBar"),
  };

  // -----------------------------------------------------------------------
  // Formatting helpers
  // -----------------------------------------------------------------------

  function fmtMoney(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    var sign = n < 0 ? "-" : "";
    var abs = Math.abs(n);
    return sign + "$" + abs.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtSignedMoney(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    var s = fmtMoney(Math.abs(n));
    if (n > 0) return "+" + s;
    if (n < 0) return "-" + s;
    return s;
  }

  function fmtPrice(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }

  function fmtQty(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return String(n);
  }

  function pnlClass(n) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "";
    return n > 0 ? "good" : "critical";
  }

  function fmtTime(ts) {
    if (!ts) return "—";
    var d = new Date(ts);
    if (isNaN(d.getTime())) return String(ts);
    return d.toLocaleTimeString(undefined, { hour12: false }) + " " + d.toLocaleDateString();
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -----------------------------------------------------------------------
  // Rendering
  // -----------------------------------------------------------------------

  function renderConnection() {
    var s = state.connectionState;
    el.connBadge.className = "conn-badge " + s;
    var labels = {
      connected: "connected",
      connecting: "reconnecting…",
      disconnected: "disconnected",
      error: "connection error",
    };
    el.connBadgeText.textContent = labels[s] || s;

    var showBanner = s !== "connected";
    el.disconnectBanner.classList.toggle("show", showBanner);
  }

  function renderModeBadge() {
    var mode = state.settings && state.settings.account_mode ? state.settings.account_mode : "paper";
    var isLive = mode === "live";
    el.modeBadge.textContent = isLive ? "LIVE" : "PAPER";
    el.modeBadge.className = "mode-badge " + (isLive ? "live" : "paper");
  }

  function renderKillIndicator() {
    var active = !!(state.settings && state.settings.kill_switch_active);
    el.killIndicator.classList.toggle("active", active);
  }

  function renderAccount() {
    var a = state.account;
    if (!a) {
      el.statNetLiq.textContent = "—";
      el.statCash.textContent = "—";
      el.statBuyingPower.textContent = "—";
      el.statRealizedToday.textContent = "—";
      el.statUnrealized.textContent = "—";
      el.statRealizedToday.className = "stat-value";
      el.statUnrealized.className = "stat-value";
      el.accountUpdated.textContent = "no data";
      return;
    }
    el.statNetLiq.textContent = fmtMoney(a.net_liquidation);
    el.statCash.textContent = fmtMoney(a.cash);
    el.statBuyingPower.textContent = fmtMoney(a.buying_power);

    el.statRealizedToday.textContent = fmtSignedMoney(a.realized_pnl_today);
    el.statRealizedToday.className = "stat-value " + pnlClass(a.realized_pnl_today);

    el.statUnrealized.textContent = fmtSignedMoney(a.unrealized_pnl);
    el.statUnrealized.className = "stat-value " + pnlClass(a.unrealized_pnl);

    el.accountUpdated.textContent = "updated " + new Date().toLocaleTimeString(undefined, { hour12: false });
  }

  function renderPositions() {
    var symbols = Object.keys(state.positions || {});
    el.positionsCount.textContent = symbols.length + " open";

    if (symbols.length === 0) {
      el.positionsBody.innerHTML = "";
      el.positionsEmpty.style.display = "block";
      return;
    }
    el.positionsEmpty.style.display = "none";

    symbols.sort();
    var rows = symbols.map(function (sym) {
      var p = state.positions[sym] || {};
      var qty = Number(p.quantity);
      var side = "flat";
      if (qty > 0) side = "long";
      else if (qty < 0) side = "short";

      return (
        "<tr>" +
        "<td>" + escapeHtml(p.symbol || sym) + "</td>" +
        "<td><span class=\"side-tag " + side + "\">" + side + "</span></td>" +
        "<td class=\"num\">" + fmtQty(p.quantity) + "</td>" +
        "<td class=\"num\">" + fmtPrice(p.avg_entry_price) + "</td>" +
        "<td class=\"num " + pnlClass(p.unrealized_pnl) + "\">" + fmtSignedMoney(p.unrealized_pnl) + "</td>" +
        "<td class=\"num " + pnlClass(p.realized_pnl) + "\">" + fmtSignedMoney(p.realized_pnl) + "</td>" +
        "</tr>"
      );
    });
    el.positionsBody.innerHTML = rows.join("");
  }

  function orderRowHtml(o) {
    var status = (o.status || "").toLowerCase();
    var side = (o.side || "").toLowerCase();
    return (
      "<tr>" +
      "<td class=\"num\">" + escapeHtml(fmtTime(o.timestamp)) + "</td>" +
      "<td>" + escapeHtml(o.symbol) + "</td>" +
      "<td class=\"" + (side === "buy" ? "good" : side === "sell" ? "critical" : "") + "\">" + escapeHtml((o.side || "").toUpperCase()) + "</td>" +
      "<td><span class=\"pill " + status + "\">" + escapeHtml(status.replace("_", " ")) + "</span></td>" +
      "<td class=\"num\">" + fmtQty(o.quantity) + "</td>" +
      "<td class=\"num\">" + fmtPrice(o.avg_fill_price) + "</td>" +
      "<td>" + escapeHtml(o.reason || "") + "</td>" +
      "</tr>"
    );
  }

  function renderOrders() {
    el.ordersCount.textContent = state.orders.length + " orders";
    if (state.orders.length === 0) {
      el.ordersBody.innerHTML = "";
      el.ordersEmpty.style.display = "block";
      return;
    }
    el.ordersEmpty.style.display = "none";
    el.ordersBody.innerHTML = state.orders.map(orderRowHtml).join("");
  }

  function prependOrder(order) {
    state.orders.unshift(order);
    if (state.orders.length > MAX_ORDER_LOG) state.orders.length = MAX_ORDER_LOG;
    renderOrders();
  }

  // -----------------------------------------------------------------------
  // Settings panel
  // -----------------------------------------------------------------------

  var settingsEditing = false; // true while the user has an unsaved/pending edit in flight
  var pendingSave = null;      // debounce timer

  function renderInstrumentsList() {
    var enabled = (state.settings && state.settings.enabled_instruments) || {};
    el.instrumentsList.innerHTML = INSTRUMENT_ORDER.map(function (sym) {
      var label = INSTRUMENT_LABELS[sym] || sym;
      var checked = !!enabled[sym];
      var id = "instr_" + sym.replace(/[^a-zA-Z0-9]/g, "_");
      return (
        "<div class=\"toggle-row\">" +
        "<span class=\"label\">" + escapeHtml(label) + "</span>" +
        "<label class=\"switch\">" +
        "<input type=\"checkbox\" data-instrument=\"" + escapeHtml(sym) + "\" id=\"" + id + "\"" + (checked ? " checked" : "") + " />" +
        "<span class=\"slider\"></span>" +
        "</label>" +
        "</div>"
      );
    }).join("");

    // wire change handlers (immediate save, no debounce, per spec)
    var checkboxes = el.instrumentsList.querySelectorAll("input[type=checkbox]");
    checkboxes.forEach(function (cb) {
      cb.addEventListener("change", function () {
        var sym = cb.getAttribute("data-instrument");
        var next = cloneSettings();
        next.enabled_instruments[sym] = cb.checked;
        saveSettings(next, { immediate: true });
      });
    });
  }

  function renderSettingsForm() {
    var s = state.settings;
    if (!s) return;
    // Avoid clobbering an input the user is actively typing into.
    if (document.activeElement !== el.riskPercentInput) {
      el.riskPercentInput.value = s.risk_percent;
    }
    if (document.activeElement !== el.maxContractsInput) {
      el.maxContractsInput.value = s.max_contracts;
    }
    if (document.activeElement !== el.drawdownInput) {
      el.drawdownInput.value = s.daily_drawdown_limit_percent;
    }
    el.accountModeInput.value = s.account_mode;
    el.minTierInput.value = s.min_tier;
    el.killSwitchInput.checked = !!s.kill_switch_active;

    renderInstrumentsList();
  }

  function cloneSettings() {
    return JSON.parse(JSON.stringify(state.settings || defaultSettings()));
  }

  function defaultSettings() {
    return {
      account_mode: "paper",
      risk_percent: 0.5,
      max_contracts: 1,
      min_tier: "S",
      enabled_instruments: { "GC=F": false, "ES=F": false, "CL=F": false, "EURUSD=X": false },
      kill_switch_active: false,
      daily_drawdown_limit_percent: 2.0,
    };
  }

  function setSaveState(kind, message) {
    el.saveState.className = "save-state " + kind;
    var text = message || { saving: "Saving…", saved: "Saved", error: "Save failed — retry" }[kind] || "";
    el.saveState.innerHTML = kind ? "<span class=\"dot\"></span>" + escapeHtml(text) : "";
  }

  function saveSettings(newSettings, opts) {
    opts = opts || {};
    if (pendingSave) {
      clearTimeout(pendingSave);
      pendingSave = null;
    }

    var doSave = function () {
      setSaveState("saving");
      fetch(apiUrl("/api/settings"), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newSettings),
      })
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          return resp.json().catch(function () { return newSettings; });
        })
        .then(function (confirmed) {
          state.settings = confirmed && typeof confirmed === "object" ? confirmed : newSettings;
          setSaveState("saved");
          renderModeBadge();
          renderKillIndicator();
          renderSettingsForm();
          window.setTimeout(function () {
            // don't clear an error/saving state that arrived in the meantime
            if (el.saveState.classList.contains("saved")) setSaveState("");
          }, 2500);
        })
        .catch(function (err) {
          setSaveState("error", "Save failed: " + err.message);
        });
    };

    if (opts.immediate) {
      doSave();
    } else {
      pendingSave = window.setTimeout(doSave, 400);
    }
  }

  function wireSettingsInputs() {
    el.accountModeInput.addEventListener("change", function () {
      var next = cloneSettings();
      next.account_mode = el.accountModeInput.value;
      saveSettings(next, { immediate: true });
    });

    el.minTierInput.addEventListener("change", function () {
      var next = cloneSettings();
      next.min_tier = el.minTierInput.value;
      saveSettings(next, { immediate: true });
    });

    el.riskPercentInput.addEventListener("input", function () {
      var v = parseFloat(el.riskPercentInput.value);
      if (isNaN(v)) return;
      var next = cloneSettings();
      next.risk_percent = v;
      saveSettings(next, { immediate: false });
    });

    el.maxContractsInput.addEventListener("input", function () {
      var v = parseInt(el.maxContractsInput.value, 10);
      if (isNaN(v)) return;
      var next = cloneSettings();
      next.max_contracts = v;
      saveSettings(next, { immediate: false });
    });

    el.drawdownInput.addEventListener("input", function () {
      var v = parseFloat(el.drawdownInput.value);
      if (isNaN(v)) return;
      var next = cloneSettings();
      next.daily_drawdown_limit_percent = v;
      saveSettings(next, { immediate: false });
    });

    el.killSwitchInput.addEventListener("change", function () {
      var next = cloneSettings();
      next.kill_switch_active = el.killSwitchInput.checked;
      saveSettings(next, { immediate: true });
    });
  }

  // -----------------------------------------------------------------------
  // Flatten-all
  // -----------------------------------------------------------------------

  function wireFlattenButton() {
    el.flattenBtn.addEventListener("click", function () {
      var ok = window.confirm("Close ALL open positions immediately?");
      if (!ok) return;

      el.flattenBtn.disabled = true;
      var originalText = el.flattenBtn.textContent;
      el.flattenBtn.textContent = "Flattening…";

      fetch(apiUrl("/api/flatten-all"), { method: "POST" })
        .then(function (resp) {
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          return resp.json().catch(function () { return {}; });
        })
        .then(function () {
          el.flattenBtn.textContent = "Flatten submitted";
          window.setTimeout(function () {
            el.flattenBtn.textContent = originalText;
            el.flattenBtn.disabled = false;
          }, 2000);
        })
        .catch(function (err) {
          window.alert("Flatten-all failed: " + err.message);
          el.flattenBtn.textContent = originalText;
          el.flattenBtn.disabled = false;
        });
    });
  }

  // -----------------------------------------------------------------------
  // API base URL — derived from current location so this works whether the
  // dashboard is served by the trading service itself or reverse-proxied.
  // -----------------------------------------------------------------------

  function apiUrl(path) {
    return path; // relative to current origin; same-host by design
  }

  function wsUrl() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + location.host + "/ws";
  }

  // -----------------------------------------------------------------------
  // WebSocket connection with exponential backoff reconnect
  // -----------------------------------------------------------------------

  var ws = null;
  var backoffMs = 1000;
  var BACKOFF_MAX_MS = 15000;
  var reconnectTimer = null;
  var deliberatelyClosed = false;

  function setConnectionState(s) {
    state.connectionState = s;
    renderConnection();
  }

  function connect() {
    if (deliberatelyClosed) return;

    setConnectionState(ws ? "connecting" : "connecting");

    var url;
    try {
      url = wsUrl();
    } catch (e) {
      setConnectionState("error");
      scheduleReconnect();
      return;
    }

    try {
      ws = new WebSocket(url);
    } catch (e) {
      setConnectionState("error");
      scheduleReconnect();
      return;
    }

    ws.addEventListener("open", function () {
      backoffMs = 1000; // reset backoff on a successful connect
      setConnectionState("connected");
    });

    ws.addEventListener("message", function (evt) {
      handleMessage(evt.data);
    });

    ws.addEventListener("close", function () {
      if (deliberatelyClosed) return;
      setConnectionState("disconnected");
      scheduleReconnect();
    });

    ws.addEventListener("error", function () {
      setConnectionState("error");
      // 'close' will also fire after 'error' on most browsers; reconnect is
      // scheduled there. If it doesn't, this timer still recovers us.
      scheduleReconnect();
    });
  }

  function scheduleReconnect() {
    if (deliberatelyClosed || reconnectTimer) return;
    var delay = backoffMs;
    backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  function handleMessage(raw) {
    var msg;
    try {
      msg = JSON.parse(raw);
    } catch (e) {
      return; // ignore malformed frames rather than throwing
    }
    if (!msg || typeof msg !== "object") return;

    var type = msg.type;
    var data = msg.data;

    switch (type) {
      case "snapshot":
        applySnapshot(data || {});
        break;
      case "positions":
        state.positions = data || {};
        renderPositions();
        break;
      case "account":
        state.account = data || null;
        renderAccount();
        break;
      case "order":
        if (data) prependOrder(data);
        break;
      case "connection":
        if (data && data.state) setConnectionState(data.state);
        break;
      case "settings":
        state.settings = data || defaultSettings();
        renderModeBadge();
        renderKillIndicator();
        renderSettingsForm();
        break;
      default:
        // unknown message kind — ignore, forward-compatible
        break;
    }
  }

  function applySnapshot(data) {
    state.positions = data.positions || {};
    state.account = data.account || null;
    state.orders = Array.isArray(data.orders) ? data.orders.slice(0, MAX_ORDER_LOG) : [];
    state.settings = data.settings || defaultSettings();
    if (data.connection_state) state.connectionState = data.connection_state;

    renderPositions();
    renderAccount();
    renderOrders();
    renderModeBadge();
    renderKillIndicator();
    renderSettingsForm();
    renderConnection();
  }

  // -----------------------------------------------------------------------
  // Chart — historical candles from GET /api/candles/{symbol}. Not a live
  // feed (see the hint text in index.html): paper mode has no market-data
  // source wired into the running service yet, so this shows real
  // historical price action rather than a blank panel, but won't grow new
  // candles during a live session until that's built.
  // -----------------------------------------------------------------------

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function initChart() {
    if (!el.priceChart || typeof LightweightCharts === "undefined") return;

    chart = LightweightCharts.createChart(el.priceChart, {
      width: el.priceChart.clientWidth,
      height: 320,
      layout: {
        background: { type: LightweightCharts.ColorType.Solid, color: cssVar("--panel") },
        textColor: cssVar("--ink-dim"),
      },
      grid: {
        vertLines: { color: cssVar("--border") },
        horzLines: { color: cssVar("--border") },
      },
      rightPriceScale: { borderColor: cssVar("--border") },
      timeScale: { borderColor: cssVar("--border") },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });

    var good = cssVar("--good");
    var critical = cssVar("--critical");
    chartSeries = chart.addCandlestickSeries({
      upColor: good, downColor: critical,
      borderUpColor: good, borderDownColor: critical,
      wickUpColor: good, wickDownColor: critical,
    });

    window.addEventListener("resize", function () {
      if (chart && el.priceChart) chart.applyOptions({ width: el.priceChart.clientWidth });
    });
  }

  function renderChartTabs() {
    if (!el.chartTabs) return;
    el.chartTabs.innerHTML = INSTRUMENT_ORDER.map(function (sym) {
      var active = sym === state.chartSymbol ? " active" : "";
      return '<button type="button" class="chart-tab' + active + '" data-symbol="' + sym + '">'
        + (INSTRUMENT_LABELS[sym] || sym) + "</button>";
    }).join("");

    Array.prototype.forEach.call(el.chartTabs.querySelectorAll(".chart-tab"), function (btn) {
      btn.addEventListener("click", function () {
        state.chartSymbol = btn.getAttribute("data-symbol");
        renderChartTabs();
        loadChartData();
      });
    });
  }

  function loadChartData() {
    if (!chartSeries || !state.chartSymbol) return;
    fetch(apiUrl("/api/candles/" + encodeURIComponent(state.chartSymbol) + "?limit=300"))
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (candles) {
        chartSeries.setData(candles || []);
        if (chart) chart.timeScale().fitContent();
      })
      .catch(function () { /* chart just stays empty on failure — no crash */ });
  }

  // -----------------------------------------------------------------------
  // Mobile tab bar — desktop (min-width:900px, see styles.css) shows every
  // panel at once and hides this bar entirely; below that breakpoint only
  // the active tab's panels are visible. Harmless to wire up unconditionally
  // since CSS is what actually decides whether it has any visible effect.
  // -----------------------------------------------------------------------

  function setActiveTab(tab) {
    document.body.setAttribute("data-tab", tab);
    if (el.tabBar) {
      Array.prototype.forEach.call(el.tabBar.querySelectorAll(".tab-btn"), function (btn) {
        btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
      });
    }
    // The chart's canvas has zero size while its panel is display:none;
    // resize it once its container is visible again, or it stays blank.
    if (tab === "chart" && chart && el.priceChart) {
      chart.applyOptions({ width: el.priceChart.clientWidth });
      chart.timeScale().fitContent();
    }
  }

  function wireTabBar() {
    if (!el.tabBar) return;
    Array.prototype.forEach.call(el.tabBar.querySelectorAll(".tab-btn"), function (btn) {
      btn.addEventListener("click", function () {
        setActiveTab(btn.getAttribute("data-tab"));
      });
    });
  }

  function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("sw.js").catch(function () { /* installable without it too */ });
    });
  }

  // -----------------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------------

  function init() {
    state.settings = defaultSettings();
    state.chartSymbol = INSTRUMENT_ORDER[0];
    renderModeBadge();
    renderKillIndicator();
    renderSettingsForm();
    renderAccount();
    renderPositions();
    renderOrders();
    renderConnection();

    initChart();
    renderChartTabs();
    loadChartData();

    setActiveTab("chart");
    wireTabBar();
    registerServiceWorker();

    wireSettingsInputs();
    wireFlattenButton();

    connect();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
