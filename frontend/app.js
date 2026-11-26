/**
 * VyaparVoice AI - XSS-Safe Frontend Controller & Gemini Live Audio Client
 * - Uses safe DOM APIs (createElement + textContent) exclusively; zero untrusted innerHTML
 * - Connects to Gemini Multimodal Live API via server-minted ephemeral tokens
 * - Supports barge-in/interruption, measured latency, CSRF & Idempotency-Key headers
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- Session & Auth State ---
  let csrfToken = "";
  let activeShop = null;
  let latestState = null;
  let activeDraft = null;
  let activeHitlDraft = null;
  let lastCommittedOrderId = null;
  let speechEnabled = true;

  // --- Gemini Live Audio State ---
  let liveWs = null;
  let liveAudioCtx = null;
  let liveMicStream = null;
  let liveProcessor = null;
  let isLiveStreaming = false;
  let playbackCtx = null;
  let nextPlayTime = 0;
  let activeAudioSources = [];

  // --- DOM Helpers (XSS-Safe) ---
  const $ = (id) => document.getElementById(id);
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function newIdempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "idem-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
  }

  async function apiFetch(url, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    if (options.method && options.method !== "GET") {
      headers["Content-Type"] = "application/json";
      if (csrfToken) headers["X-CSRF-Token"] = csrfToken;
      if (!headers["Idempotency-Key"]) headers["Idempotency-Key"] = newIdempotencyKey();
    }
    const resp = await fetch(url, Object.assign({}, options, { headers, credentials: "same-origin" }));
    const text = await resp.text();
    let json = {};
    try {
      json = JSON.parse(text);
    } catch {
      throw new Error(`Unexpected server response (${resp.status})`);
    }
    if (!resp.ok && resp.status === 401) {
      showAuthBanner(true);
    }
    return { ok: resp.ok, status: resp.status, data: json };
  }

  // --- Navigation ---
  const navTabs = document.querySelectorAll(".nav-tab");
  const appViews = document.querySelectorAll(".app-view");

  function switchPage(pageId) {
    navTabs.forEach((t) => {
      const active = t.getAttribute("data-page") === pageId;
      t.classList.toggle("active-tab", active);
      t.classList.toggle("inactive-tab", !active);
    });
    appViews.forEach((v) => v.classList.toggle("hidden", v.id !== pageId));
  }

  navTabs.forEach((tab) => tab.addEventListener("click", () => switchPage(tab.getAttribute("data-page"))));
  document.querySelectorAll(".footer-nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchPage(btn.getAttribute("data-page"));
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  $("brand-home-btn")?.addEventListener("click", () => switchPage("page-home"));
  $("hero-start-voice-btn")?.addEventListener("click", () => switchPage("page-voice"));

  // --- Auth & Session Management ---
  function showAuthBanner(show) {
    $("auth-required-banner")?.classList.toggle("hidden", !show);
  }

  function openAuthModal() {
    $("auth-modal-msg")?.classList.add("hidden");
    $("auth-modal")?.classList.remove("hidden");
  }
  function closeAuthModal() {
    $("auth-modal")?.classList.add("hidden");
  }

  $("open-shop-switch-btn")?.addEventListener("click", openAuthModal);
  $("auth-btn")?.addEventListener("click", openAuthModal);
  $("banner-login-btn")?.addEventListener("click", openAuthModal);
  $("close-auth-modal-btn")?.addEventListener("click", closeAuthModal);

  async function loginDemoShop(shopId) {
    const { ok, data } = await apiFetch("/api/auth/demo-login", {
      method: "POST",
      body: JSON.stringify({ shop_id: shopId }),
    });
    if (ok && data.status === "success") {
      csrfToken = data.csrf_token || "";
      activeShop = data.shop;
      showAuthBanner(false);
      closeAuthModal();
      applyShopState(data.state);
      checkGeminiHealth();
    } else {
      showAuthError(data.message || "Demo login failed");
    }
  }

  function showAuthError(msg) {
    const box = $("auth-modal-msg");
    if (box) {
      box.textContent = msg;
      box.classList.remove("hidden");
    }
  }

  document.querySelectorAll(".demo-shop-pick-btn").forEach((btn) => {
    btn.addEventListener("click", () => loginDemoShop(btn.getAttribute("data-shop-id")));
  });
  $("banner-demo1-btn")?.addEventListener("click", () => loginDemoShop("SHOP-001"));
  $("hero-demo-btn")?.addEventListener("click", async () => {
    await loginDemoShop("SHOP-001");
    switchPage("page-voice");
  });

  $("login-submit-btn")?.addEventListener("click", async () => {
    const email_or_phone = $("login-email-input").value.trim();
    const password = $("login-password-input").value;
    const { ok, data } = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email_or_phone, password }),
    });
    if (ok && data.status === "success") {
      csrfToken = data.csrf_token || "";
      activeShop = data.shop;
      showAuthBanner(false);
      closeAuthModal();
      applyShopState(data.state);
      checkGeminiHealth();
    } else {
      showAuthError(data.message || "Login failed");
    }
  });

  $("reg-submit-btn")?.addEventListener("click", async () => {
    const shop_name = $("reg-shop-name").value.trim();
    const owner_name = $("reg-owner-name").value.trim();
    const phone = $("reg-phone").value.trim();
    const password = $("reg-password").value;
    if (!shop_name || !owner_name || password.length < 8) {
      showAuthError("Shop name, owner name aur kam se kam 8-character password dalein.");
      return;
    }
    const { ok, data } = await apiFetch("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ shop_name, owner_name, phone, password }),
    });
    if (ok && data.status === "success") {
      csrfToken = data.csrf_token || "";
      activeShop = data.shop;
      showAuthBanner(false);
      closeAuthModal();
      applyShopState(data.state);
      checkGeminiHealth();
    } else {
      showAuthError(data.message || "Registration failed");
    }
  });

  // --- Health & Capability Disclosure ---
  async function checkGeminiHealth() {
    try {
      const { data } = await apiFetch("/api/health");
      const engineBadge = $("badge-engine-mode");
      const livePill = $("live-connection-pill");
      const capNote = $("live-capability-note");
      if (data.gemini_live_configured) {
        if (engineBadge) engineBadge.textContent = "Gemini Live Audio Ready";
        if (livePill) livePill.textContent = "🟢 Gemini Live Audio: Available (Click Mic)";
        if (capNote) capNote.textContent = "Browser streams live PCM to Gemini Live using ephemeral token (not recorded).";
      } else {
        if (engineBadge) engineBadge.textContent = "Fallback Mode (No API Key)";
        if (livePill) livePill.textContent = "🟡 Gemini Live Unavailable — Server/Text Fallback";
        if (capNote) capNote.textContent = "GEMINI_API_KEY server par set nahi hai; text/scripted workflow aur browser TTS active hai.";
      }
    } catch {
      // Ignore network check failure
    }
  }

  // --- State Rendering (100% XSS-Safe DOM Builders) ---
  function applyShopState(state) {
    if (!state) return;
    latestState = state;
    if (state.shop) {
      activeShop = state.shop;
      $("current-shop-name").textContent = state.shop.shop_name;
      $("auth-btn-text").textContent = state.shop.owner_name;
      const badgeData = $("badge-data-mode");
      if (badgeData) {
        badgeData.textContent = state.shop.is_demo ? "Synthetic Demo Data" : "Private Registered Shop";
      }
    }

    const stats = state.stats || {};
    $("stat-grahak").textContent = String(stats.total_customers || 0);
    $("stat-dues").textContent = `₹${Number(stats.total_receivables || 0).toLocaleString("en-IN")}`;
    $("stat-paid-orders").textContent = String(stats.paid_orders_count || 0);
    $("stat-pending-approvals").textContent = String(stats.pending_approvals_count || 0);
    if ($("stat-cash-sales")) $("stat-cash-sales").textContent = `₹${Number(stats.total_cash_sales || 0).toLocaleString("en-IN")}`;
    if ($("stat-credit-sales")) $("stat-credit-sales").textContent = `₹${Number(stats.total_credit_sales || 0).toLocaleString("en-IN")}`;
    if ($("stat-low-stock")) $("stat-low-stock").textContent = String(stats.low_stock_count || 0);

    // Sync pending confirmation / HITL drafts from server state
    const drafts = state.pending_drafts || [];
    const confirmDraft = drafts.find((d) => d.status === "PENDING_CONFIRMATION") || null;
    const hitlDraft = drafts.find((d) => d.status === "PENDING_APPROVAL") || null;
    renderPendingDraftCard(confirmDraft);
    renderHitlCard(hitlDraft);

    renderCustomers(state.customers || []);
    renderProducts(state.products || []);
    renderOrders(state.recent_orders || []);
    renderWhatsappOutbox(state.whatsapp_outbox || []);
    renderAuditLogs(state.audit_logs || []);
  }

  function renderPendingDraftCard(draft) {
    activeDraft = draft;
    const card = $("draft-preview-card");
    if (!draft) {
      card.classList.add("hidden");
      return;
    }
    card.classList.remove("hidden");
    $("draft-preview-id").textContent = draft.id;
    const box = $("draft-preview-details");
    box.replaceChildren();
    box.appendChild(el("div", "font-bold", `Grahak: ${draft.customer_name}`));
    (draft.items || []).forEach((it) => {
      box.appendChild(el("div", "", `• ${it.name}: ${it.quantity} ${it.unit} × ₹${it.price_per_unit} = ₹${Number(it.item_total).toLocaleString("en-IN")}`));
    });
    box.appendChild(el("div", "font-bold pt-1", `Total: ₹${Number(draft.total_amount).toLocaleString("en-IN")} | Mode: ${String(draft.payment_mode).toUpperCase()}`));
  }

  function renderHitlCard(draft) {
    activeHitlDraft = draft;
    const banner = $("hitl-banner");
    if (!draft) {
      banner.classList.add("hidden");
      return;
    }
    banner.classList.remove("hidden");
    $("hitl-description").textContent = `${draft.customer_name} — ₹${Number(draft.total_amount).toLocaleString("en-IN")} (${draft.reason || "Credit limit exceeded"}). Stock aur khata abhi update nahi hua hai.`;
  }

  function renderCustomers(customers) {
    const container = $("customers-list");
    const q = ($("customer-search-input")?.value || "").toLowerCase().trim();
    const filtered = customers.filter((c) => !q || c.name.toLowerCase().includes(q));
    container.replaceChildren();

    if (filtered.length === 0) {
      container.appendChild(el("p", "text-xs text-[#8a7667] m-0", "Koi grahak nahi mila."));
      return;
    }

    filtered.forEach((c) => {
      const card = el("div", "p-4 rounded-xl border border-[#e8ddd4] bg-[#faf7f3] flex items-center justify-between gap-3");
      const left = el("div", "space-y-1");
      left.appendChild(el("div", "text-sm font-bold text-[#23160e]", c.name));
      left.appendChild(el("div", "text-xs text-[#8a7667]", `${c.phone || "No phone"} • Limit: ₹${Number(c.credit_limit).toLocaleString("en-IN")}`));

      const right = el("div", "text-right space-y-1");
      const balClass = Number(c.current_balance) > Number(c.credit_limit) ? "text-sm font-extrabold text-red-700" : "text-sm font-extrabold text-amber-700";
      right.appendChild(el("div", balClass, `₹${Number(c.current_balance).toLocaleString("en-IN")}`));
      const openBtn = el("button", "px-2.5 py-1 rounded-lg bg-white border border-[#e8ddd4] text-xs font-bold cursor-pointer", "Passbook");
      openBtn.type = "button";
      openBtn.addEventListener("click", () => openPassbookModal(c.id));
      right.appendChild(openBtn);

      card.appendChild(left);
      card.appendChild(right);
      container.appendChild(card);
    });
  }

  $("customer-search-input")?.addEventListener("input", () => {
    if (latestState) renderCustomers(latestState.customers || []);
  });

  function renderProducts(products) {
    const container = $("products-list");
    container.replaceChildren();
    products.forEach((p) => {
      const low = Number(p.stock) <= Number(p.min_stock);
      const card = el("div", `p-4 rounded-xl border ${low ? "border-red-300 bg-red-50" : "border-[#e8ddd4] bg-[#faf7f3]"} space-y-1.5`);
      card.appendChild(el("div", "text-xs font-mono text-[#8a7667]", p.sku));
      card.appendChild(el("div", "text-sm font-bold text-[#23160e]", p.name));
      card.appendChild(el("div", "text-xs text-[#49382c]", `Rate: ₹${Number(p.price_per_unit).toLocaleString("en-IN")} / ${p.unit}`));
      const row = el("div", "flex items-center justify-between gap-2 pt-1");
      row.appendChild(el("span", `text-xs font-bold ${low ? "text-red-700" : "text-emerald-700"}`, `Stock: ${p.stock} ${p.unit} ${low ? "(Low)" : ""}`));
      const restockBtn = el("button", "px-2.5 py-1 rounded-lg bg-white hover:bg-orange-50 border border-[#e8ddd4] text-[11px] font-bold cursor-pointer", "+20 Restock");
      restockBtn.type = "button";
      restockBtn.addEventListener("click", async () => {
        const { ok, data } = await apiFetch("/api/product/restock", {
          method: "POST",
          body: JSON.stringify({ sku: p.sku, add_qty: 20 }),
        });
        if (ok) applyShopState(data.state);
      });
      row.appendChild(restockBtn);
      card.appendChild(row);
      container.appendChild(card);
    });
  }

  function renderOrders(orders) {
    const container = $("orders-list");
    container.replaceChildren();
    if (orders.length === 0) {
      container.appendChild(el("p", "text-xs text-[#8a7667] m-0", "Abhi koi order nahi hai."));
      return;
    }
    orders.forEach((o) => {
      const card = el("div", "p-3.5 rounded-xl border border-[#e8ddd4] bg-[#faf7f3] space-y-1.5");
      const top = el("div", "flex items-center justify-between gap-2");
      top.appendChild(el("span", "text-xs font-mono font-bold text-[#23160e]", `${o.id} — ${o.customer_name}`));
      const badgeCls = o.status === "Cancelled" ? "badge-blocked" : o.payment_status === "PAID" ? "badge-paid" : "badge-dues";
      top.appendChild(el("span", `px-2 py-0.5 rounded-full text-[10px] font-bold ${badgeCls}`, o.status === "Cancelled" ? "CANCELLED" : o.payment_status));
      card.appendChild(top);

      const itemsSummary = (o.items || []).map((i) => `${i.quantity} ${i.unit} ${i.name}`).join(", ");
      card.appendChild(el("div", "text-xs text-[#49382c]", itemsSummary));
      const bot = el("div", "flex items-center justify-between gap-2 pt-1");
      bot.appendChild(el("span", "text-xs font-bold text-[#23160e]", `Total: ₹${Number(o.total_amount).toLocaleString("en-IN")} • ${o.approved_by || "Owner"}`));
      const qrBtn = el("button", "px-2.5 py-1 rounded-lg bg-white hover:bg-orange-50 border border-[#e8ddd4] text-[11px] font-bold cursor-pointer", "🧾 Challan / UPI QR");
      qrBtn.type = "button";
      qrBtn.addEventListener("click", () => openChallanModal(o));
      bot.appendChild(qrBtn);
      card.appendChild(bot);
      container.appendChild(card);
    });
  }

  // --- Add Product Modal ---
  $("open-add-prod-modal-btn")?.addEventListener("click", () => $("add-product-modal").classList.remove("hidden"));
  $("close-add-prod-modal-btn")?.addEventListener("click", () => $("add-product-modal").classList.add("hidden"));
  $("save-new-prod-btn")?.addEventListener("click", async () => {
    const { ok, data } = await apiFetch("/api/product/add", {
      method: "POST",
      body: JSON.stringify({
        name: $("new-prod-name").value.trim(),
        unit: $("new-prod-unit").value.trim() || "peti",
        price_per_unit: Number($("new-prod-price").value || 0),
        stock: Number($("new-prod-stock").value || 0),
      }),
    });
    if (ok) {
      $("add-product-modal").classList.add("hidden");
      $("new-prod-name").value = "";
      applyShopState(data.state);
    }
  });

  // --- Safe CSV Export (Formula Injection Protected) ---
  function safeCsvCell(val) {
    let s = String(val ?? "").replace(/"/g, '""');
    if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
    return `"${s}"`;
  }
  function downloadCsv(filename, headers, rows) {
    const lines = [headers.map(safeCsvCell).join(",")];
    rows.forEach((r) => lines.push(r.map(safeCsvCell).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }
  $("export-khata-csv-btn")?.addEventListener("click", () => {
    if (!latestState) return;
    downloadCsv(
      "vyaparvoice_khata.csv",
      ["Customer ID", "Name", "Phone (Masked)", "Credit Limit", "Current Dues"],
      (latestState.customers || []).map((c) => [c.id, c.name, c.phone || "", c.credit_limit, c.current_balance])
    );
  });
  $("export-orders-csv-btn")?.addEventListener("click", () => {
    if (!latestState) return;
    downloadCsv(
      "vyaparvoice_orders.csv",
      ["Order ID", "Customer", "Total Amount", "Mode", "Status", "Approved By", "Created At"],
      (latestState.recent_orders || []).map((o) => [o.id, o.customer_name, o.total_amount, o.payment_mode, o.status, o.approved_by, o.created_at])
    );
  });

  // --- Digital Challan & Simulated UPI QR Modal ---
  function openChallanModal(order) {
    const box = $("challan-summary-box");
    box.replaceChildren();
    box.appendChild(el("div", "font-bold text-[#23160e]", `Order #${order.id} — ${order.customer_name}`));
    (order.items || []).forEach((it) => {
      box.appendChild(el("div", "", `• ${it.name}: ${it.quantity} ${it.unit} = ₹${Number(it.item_total).toLocaleString("en-IN")}`));
    });
    box.appendChild(el("div", "font-bold pt-1", `Total: ₹${Number(order.total_amount).toLocaleString("en-IN")} (${order.payment_status})`));

    const upiUri = `upi://pay?pa=vyaparvoice.demo@upi&pn=VyaparVoiceDemo&am=${Number(order.total_amount).toFixed(2)}&cu=INR&tn=${encodeURIComponent(order.id)}`;
    $("upi-uri-text").textContent = upiUri;

    // Render deterministic visual QR-style matrix on canvas for demo preview
    const canvas = $("upi-qr-canvas");
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#23160e";
      const cells = 14;
      const sz = Math.floor(canvas.width / cells);
      let hash = 0;
      for (let i = 0; i < upiUri.length; i++) hash = ((hash << 5) - hash + upiUri.charCodeAt(i)) | 0;
      for (let r = 0; r < cells; r++) {
        for (let c = 0; c < cells; c++) {
          const isFinder = (r < 3 && c < 3) || (r < 3 && c >= cells - 3) || (r >= cells - 3 && c < 3);
          const bit = ((hash >> ((r * cells + c) % 24)) & 1) ^ ((r + c) % 2);
          if (isFinder || bit) ctx.fillRect(c * sz, r * sz, sz - 1, sz - 1);
        }
      }
    }
    $("challan-modal").classList.remove("hidden");
  }
  $("close-challan-modal-btn")?.addEventListener("click", () => $("challan-modal").classList.add("hidden"));
  $("print-challan-btn")?.addEventListener("click", () => window.print());
  }

  function renderWhatsappOutbox(outbox) {
    const container = $("whatsapp-outbox-list");
    container.replaceChildren();
    if (outbox.length === 0) {
      container.appendChild(el("p", "text-xs text-[#8a7667] m-0", "No simulated WhatsApp receipts yet."));
      return;
    }
    outbox.forEach((w) => {
      const box = el("div", "p-3 rounded-xl border border-orange-200 bg-orange-50 space-y-1");
      box.appendChild(el("div", "font-bold text-[#23160e]", `${w.id} → ${w.recipient_masked} (${w.mode})`));
      box.appendChild(el("pre", "text-[11px] whitespace-pre-wrap m-0 text-[#49382c]", w.message_text));
      container.appendChild(box);
    });
  }

  function renderAuditLogs(logs) {
    const container = $("audit-logs-list");
    container.replaceChildren();
    logs.forEach((l) => {
      container.appendChild(el("div", "p-2 rounded-lg bg-[#faf7f3] border border-[#e8ddd4] text-[#49382c]", `[${l.action}] ${l.entity_type} ${l.entity_id || ""} by ${l.actor}`));
    });
  }

  // --- Workflow Timeline & Spoken Response ---
  function renderWorkflowSteps(steps) {
    const container = $("execution-trace-container");
    container.replaceChildren();
    $("step-count-badge").textContent = `${(steps || []).length} steps`;
    if (!steps || steps.length === 0) {
      container.appendChild(el("p", "text-xs text-[#8a7667] m-0", "No tool calls recorded."));
      return;
    }
    steps.forEach((s) => {
      const cls =
        s.status === "completed" ? "workflow-state-completed" :
        s.status === "pending" ? "workflow-state-pending" :
        s.status === "failed" ? "workflow-state-failed" : "workflow-state-clarify";
      const row = el("div", `p-3 rounded-xl ${cls} space-y-0.5`);
      row.appendChild(el("div", "font-bold font-mono", `${s.tool} [${String(s.status).toUpperCase()}]`));
      row.appendChild(el("div", "", s.detail));
      container.appendChild(row);
    });
  }

  function speakFallbackTTS(text) {
    if (!speechEnabled || !("speechSynthesis" in window) || isLiveStreaming) return;
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = $("language-select")?.value || "hi-IN";
    window.speechSynthesis.speak(utter);
  }

  // --- Backend Command Execution (with Measured Latency) ---
  async function executeVoiceUtterance(utterance) {
    const clean = (utterance || "").trim();
    if (!clean) return;
    $("live-transcript-box").classList.remove("hidden");
    $("transcript-text").textContent = clean;
    $("transcript-timestamp").textContent = new Date().toLocaleTimeString();
    $("voice-state-badge").textContent = "⚙️ Processing...";

    const t0 = performance.now();
    try {
      const { ok, data } = await apiFetch("/api/execute-voice", {
        method: "POST",
        body: JSON.stringify({ transcript: clean }),
      });
      const measuredMs = Math.round(performance.now() - t0);
      $("latency-display").textContent = `⏱️ ${measuredMs}ms`;

      if (!ok) {
        $("spoken-response-bubble").textContent = data.message || "Request failed.";
        $("voice-state-badge").textContent = "⚠️ Error";
        return;
      }

      const res = data.result || {};
      $("agent-engine-badge").textContent = `${res.engine_mode || "SERVER"} • ${res.latency_ms || measuredMs}ms`;
      $("spoken-response-bubble").textContent = res.spoken_response || "";
      renderWorkflowSteps(res.steps || []);
      applyShopState(data.state);
      speakFallbackTTS(res.spoken_response || "");

      if (res.intent === "ORDER_COMMITTED") {
        lastCommittedOrderId = res.order_id;
        $("last-commit-bar").classList.remove("hidden");
        $("last-commit-text").textContent = `Committed Order #${res.order_id} (₹${res.total_amount}) • WhatsApp: MOCK_OUTBOX`;
        $("voice-state-badge").textContent = "✅ Committed";
      } else if (res.status === "pending") {
        $("voice-state-badge").textContent = "⏳ Awaiting Action";
      } else if (res.status === "clarify") {
        $("voice-state-badge").textContent = "❓ Clarification";
      } else {
        $("voice-state-badge").textContent = "⚪ Ready";
      }
      return res;
    } catch (err) {
      $("spoken-response-bubble").textContent = `Error: ${err.message}`;
      $("voice-state-badge").textContent = "⚠️ Error";
    }
  }

  // Confirmation & HITL & Compensate Buttons
  $("confirm-draft-btn")?.addEventListener("click", async () => {
    if (!activeDraft) return;
    const t0 = performance.now();
    const { ok, data } = await apiFetch("/api/confirm-draft", {
      method: "POST",
      body: JSON.stringify({ draft_id: activeDraft.id }),
    });
    $("latency-display").textContent = `⏱️ ${Math.round(performance.now() - t0)}ms`;
    if (ok && data.result) {
      $("spoken-response-bubble").textContent = data.result.spoken_response;
      renderWorkflowSteps(data.result.steps || []);
      applyShopState(data.state);
      speakFallbackTTS(data.result.spoken_response);
      if (data.result.order_id) {
        lastCommittedOrderId = data.result.order_id;
        $("last-commit-bar").classList.remove("hidden");
        $("last-commit-text").textContent = `Committed Order #${data.result.order_id} • WhatsApp: MOCK_OUTBOX`;
      }
    }
  });

  $("cancel-draft-btn")?.addEventListener("click", () => executeVoiceUtterance("cancel draft"));

  $("hitl-approve-btn")?.addEventListener("click", async () => {
    if (!activeHitlDraft) return;
    const { ok, data } = await apiFetch("/api/hitl-decision", {
      method: "POST",
      body: JSON.stringify({ approved: true, draft_id: activeHitlDraft.id, note: "Authenticated Owner UI Approval" }),
    });
    if (ok && data.result) {
      $("spoken-response-bubble").textContent = data.result.spoken_response;
      renderWorkflowSteps(data.result.steps || []);
      applyShopState(data.state);
      speakFallbackTTS(data.result.spoken_response);
    }
  });

  $("hitl-reject-btn")?.addEventListener("click", async () => {
    if (!activeHitlDraft) return;
    const { ok, data } = await apiFetch("/api/hitl-decision", {
      method: "POST",
      body: JSON.stringify({ approved: false, draft_id: activeHitlDraft.id, note: "Rejected by Owner" }),
    });
    if (ok && data.result) {
      $("spoken-response-bubble").textContent = data.result.spoken_response;
      renderWorkflowSteps(data.result.steps || []);
      applyShopState(data.state);
    }
  });

  $("compensate-rollback-btn")?.addEventListener("click", async () => {
    const { ok, data } = await apiFetch("/api/rollback", {
      method: "POST",
      body: JSON.stringify({ order_id: lastCommittedOrderId }),
    });
    if (ok && data.result) {
      $("spoken-response-bubble").textContent = data.result.spoken_response;
      renderWorkflowSteps(data.result.steps || []);
      applyShopState(data.state);
      $("last-commit-bar").classList.add("hidden");
    }
  });

  // Text Input & Scripted Demo Buttons
  $("send-text-btn")?.addEventListener("click", () => {
    const val = $("manual-text-input").value;
    $("manual-text-input").value = "";
    executeVoiceUtterance(val);
  });
  $("manual-text-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("send-text-btn").click();
  });
  document.querySelectorAll(".demo-scenario-btn").forEach((btn) => {
    btn.addEventListener("click", () => executeVoiceUtterance(btn.getAttribute("data-utterance")));
  });

  // TTS Toggle & Reset Demo
  $("tts-toggle")?.addEventListener("click", () => {
    speechEnabled = !speechEnabled;
    $("tts-state-text").textContent = speechEnabled ? "ON" : "OFF";
    if (!speechEnabled && "speechSynthesis" in window) window.speechSynthesis.cancel();
  });

  $("reset-btn")?.addEventListener("click", async () => {
    const { ok, data } = await apiFetch("/api/reset", { method: "POST", body: JSON.stringify({}) });
    if (ok) {
      $("spoken-response-bubble").textContent = data.message;
      $("last-commit-bar").classList.add("hidden");
      applyShopState(data.state);
    } else {
      $("spoken-response-bubble").textContent = data.message || "Reset denied.";
    }
  });

  // --- Customer Add & Passbook Modal ---
  $("open-add-cust-modal-btn")?.addEventListener("click", () => $("add-customer-modal").classList.remove("hidden"));
  $("close-add-cust-modal-btn")?.addEventListener("click", () => $("add-customer-modal").classList.add("hidden"));
  $("save-new-cust-btn")?.addEventListener("click", async () => {
    const { ok, data } = await apiFetch("/api/customer/add", {
      method: "POST",
      body: JSON.stringify({
        name: $("new-cust-name").value.trim(),
        phone: $("new-cust-phone").value.trim(),
        credit_limit: Number($("new-cust-limit").value || 20000),
        initial_dues: Number($("new-cust-initial-dues").value || 0),
      }),
    });
    if (ok) {
      $("add-customer-modal").classList.add("hidden");
      applyShopState(data.state);
    }
  });

  let activeModalCustId = null;
  async function openPassbookModal(custId) {
    activeModalCustId = custId;
    const { ok, data } = await apiFetch(`/api/customer-history/${encodeURIComponent(custId)}`);
    if (!ok || !data.data) return;
    const { customer, ledger } = data.data;
    $("modal-cust-name").textContent = customer.name;
    $("modal-cust-phone").textContent = customer.phone || "No phone";
    $("modal-cust-balance").textContent = `₹${Number(customer.current_balance).toLocaleString("en-IN")}`;
    $("modal-cust-limit").textContent = `₹${Number(customer.credit_limit).toLocaleString("en-IN")}`;

    const list = $("modal-ledger-list");
    list.replaceChildren();
    (ledger || []).forEach((entry) => {
      const row = el("div", "p-2.5 rounded-xl border border-[#e8ddd4] bg-[#faf7f3] flex justify-between gap-2");
      row.appendChild(el("span", "", `${entry.entry_type}: ${entry.description}`));
      row.appendChild(el("b", "", `₹${Number(entry.amount).toLocaleString("en-IN")}`));
      list.appendChild(row);
    });
    $("passbook-modal").classList.remove("hidden");
  }

  $("close-modal-btn")?.addEventListener("click", () => $("passbook-modal").classList.add("hidden"));
  $("quick-payment-btn")?.addEventListener("click", async () => {
    if (!activeModalCustId) return;
    const amount = Number($("quick-payment-amount").value || 0);
    if (amount <= 0) return;
    const { ok, data } = await apiFetch("/api/record-payment", {
      method: "POST",
      body: JSON.stringify({ customer_id: activeModalCustId, amount }),
    });
    if (ok) {
      $("quick-payment-amount").value = "";
      applyShopState(data.state);
      openPassbookModal(activeModalCustId);
    }
  });

  $("modal-delete-cust-btn")?.addEventListener("click", async () => {
    if (!activeModalCustId) return;
    const { ok, data } = await apiFetch("/api/customer/delete", {
      method: "POST",
      body: JSON.stringify({ customer_id: activeModalCustId }),
    });
    if (ok) {
      $("passbook-modal").classList.add("hidden");
      applyShopState(data.state);
    }
  });

  // --- Gemini Live Audio-to-Audio WebSocket Client ---
  function stopLiveAudioPlayback() {
    activeAudioSources.forEach((src) => {
      try { src.stop(); } catch {}
    });
    activeAudioSources = [];
    if (playbackCtx) nextPlayTime = playbackCtx.currentTime;
  }

  function playPcm24kBase64(b64) {
    if (!speechEnabled) return;
    if (!playbackCtx) playbackCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    const bin = atob(b64);
    const len = bin.length / 2;
    const float32 = new Float32Array(len);
    for (let i = 0; i < len; i++) {
      const lo = bin.charCodeAt(i * 2);
      const hi = bin.charCodeAt(i * 2 + 1);
      let val = (hi << 8) | lo;
      if (val >= 0x8000) val -= 0x10000;
      float32[i] = val / 32768.0;
    }
    const buf = playbackCtx.createBuffer(1, len, 24000);
    buf.getChannelData(0).set(float32);
    const src = playbackCtx.createBufferSource();
    src.buffer = buf;
    src.connect(playbackCtx.destination);
    const startAt = Math.max(playbackCtx.currentTime, nextPlayTime);
    src.start(startAt);
    nextPlayTime = startAt + buf.duration;
    activeAudioSources.push(src);
    src.onended = () => {
      activeAudioSources = activeAudioSources.filter((s) => s !== src);
    };
  }

  function drawWaveform(rms) {
    const canvas = $("waveform-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const bars = 28;
    const barW = canvas.width / bars;
    for (let i = 0; i < bars; i++) {
      const h = Math.max(4, Math.min(canvas.height - 6, (rms * 240) * (0.4 + Math.sin(Date.now() / 120 + i) * 0.4)));
      ctx.fillStyle = isLiveStreaming ? "#ea580c" : "#d8c2ad";
      ctx.fillRect(i * barW + 2, (canvas.height - h) / 2, barW - 4, h);
    }
  }

  function stopLiveSession() {
    isLiveStreaming = false;
    stopLiveAudioPlayback();
    if (liveProcessor) {
      liveProcessor.disconnect();
      liveProcessor = null;
    }
    if (liveMicStream) {
      liveMicStream.getTracks().forEach((t) => t.stop());
      liveMicStream = null;
    }
    if (liveAudioCtx) {
      liveAudioCtx.close().catch(() => {});
      liveAudioCtx = null;
    }
    if (liveWs) {
      liveWs.close();
      liveWs = null;
    }
    $("mic-btn").classList.remove("listening-glow");
    $("barge-in-btn").classList.add("hidden");
    $("voice-state-badge").textContent = "⚪ तैयार (Ready)";
    $("mic-permission-pill").textContent = "🎤 Mic: Idle (Not Recorded)";
    drawWaveform(0.02);
  }

  $("barge-in-btn")?.addEventListener("click", () => {
    stopLiveAudioPlayback();
    $("voice-state-badge").textContent = "✋ Interrupted — बोलिए";
  });

  $("mic-btn")?.addEventListener("click", async () => {
    if (isLiveStreaming) {
      stopLiveSession();
      return;
    }
    if (!activeShop) {
      openAuthModal();
      return;
    }

    const lang = $("language-select")?.value || "hi-IN";
    const { ok, data } = await apiFetch("/api/live/session", {
      method: "POST",
      body: JSON.stringify({ language: lang }),
    });

    if (!ok || data.mode !== "GEMINI_LIVE") {
      // Honest disclosure + fallback to browser SpeechRecognition if available
      $("live-connection-pill").textContent = "🟡 Fallback Mode (Gemini Live Unavailable)";
      $("live-capability-note").textContent = data.reason || "Gemini Live ephemeral token unavailable.";
      startBrowserSpeechFallback(lang);
      return;
    }

    try {
      liveMicStream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000 } });
      $("mic-permission-pill").textContent = "🎤 Mic: Streaming Live (Not Recorded)";
    } catch (err) {
      $("mic-permission-pill").textContent = "🎤 Mic: Permission Denied";
      $("live-capability-note").textContent = `Microphone access denied: ${err.message}. Use Text Input below.`;
      return;
    }

    const tStart = performance.now();
    liveWs = new WebSocket(data.ws_url);
    liveWs.onopen = () => {
      liveWs.send(JSON.stringify({ setup: data.setup }));
      isLiveStreaming = true;
      $("mic-btn").classList.add("listening-glow");
      $("barge-in-btn").classList.remove("hidden");
      $("live-connection-pill").textContent = "🟢 Connected: Gemini Live Audio";
      $("voice-state-badge").textContent = "🔴 Live Audio...";
      $("latency-display").textContent = `⏱️ ${Math.round(performance.now() - tStart)}ms`;

      liveAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = liveAudioCtx.createMediaStreamSource(liveMicStream);
      liveProcessor = liveAudioCtx.createScriptProcessor(4096, 1, 1);
      source.connect(liveProcessor);
      liveProcessor.connect(liveAudioCtx.destination);

      liveProcessor.onaudioprocess = (ev) => {
        if (!isLiveStreaming || !liveWs || liveWs.readyState !== WebSocket.OPEN) return;
        const input = ev.inputBuffer.getChannelData(0);
        let sumSq = 0;
        const pcm16 = new Int16Array(input.length);
        for (let i = 0; i < input.length; i++) {
          const s = Math.max(-1, Math.min(1, input[i]));
          sumSq += s * s;
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }
        const rms = Math.sqrt(sumSq / input.length);
        drawWaveform(rms);
        // Barge-in detection: if user speaks loudly while AI audio plays, interrupt playback
        if (rms > 0.08 && activeAudioSources.length > 0) {
          stopLiveAudioPlayback();
        }
        const bytes = new Uint8Array(pcm16.buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        liveWs.send(JSON.stringify({
          realtimeInput: { mediaChunks: [{ mimeType: "audio/pcm;rate=16000", data: btoa(binary) }] },
        }));
      };
    };

    liveWs.onmessage = async (event) => {
      const msg = JSON.parse(event.data);
      if (msg.serverContent?.modelTurn?.parts) {
        for (const part of msg.serverContent.modelTurn.parts) {
          if (part.inlineData?.data) playPcm24kBase64(part.inlineData.data);
          if (part.text) $("spoken-response-bubble").textContent = part.text;
        }
      }
      if (msg.toolCall?.functionCalls) {
        const responses = [];
        for (const fc of msg.toolCall.functionCalls) {
          let result = {};
          if (fc.name === "prepare_order_draft") {
            result = await executeVoiceUtterance(fc.args?.utterance || "");
          } else if (fc.name === "modify_pending_draft") {
            result = await executeVoiceUtterance(fc.args?.correction_text || "");
          } else if (fc.name === "confirm_pending_draft") {
            result = await executeVoiceUtterance("haan confirm karo");
          } else if (fc.name === "cancel_or_rollback") {
            result = await executeVoiceUtterance("cancel karo");
          }
          responses.push({ id: fc.id, name: fc.name, response: { output: result } });
        }
        liveWs.send(JSON.stringify({ toolResponse: { functionResponses: responses } }));
      }
    };

    liveWs.onerror = () => {
      $("live-capability-note").textContent = "Gemini Live WebSocket error; falling back to text input.";
      stopLiveSession();
    };
  });

  function startBrowserSpeechFallback(lang) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      $("live-capability-note").textContent += " (Browser SpeechRecognition bhi unavailable hai; neeche Text Input use karein.)";
      return;
    }
    const rec = new SR();
    rec.lang = lang;
    rec.interimResults = false;
    rec.onstart = () => {
      $("mic-permission-pill").textContent = "🎤 Mic: Browser Fallback Listening (Not Recorded)";
      $("voice-state-badge").textContent = "🔴 Listening (Fallback)...";
    };
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      executeVoiceUtterance(text);
    };
    rec.onerror = (e) => {
      $("mic-permission-pill").textContent = `🎤 Mic Error: ${e.error}`;
      $("voice-state-badge").textContent = "⚪ Ready";
    };
    rec.start();
  }

  // --- Initial Boot ---
  async function boot() {
    drawWaveform(0.02);
    await checkGeminiHealth();
    const { ok, data } = await apiFetch("/api/auth/me");
    if (ok && data.authenticated) {
      csrfToken = data.csrf_token || "";
      activeShop = data.shop;
      showAuthBanner(false);
      applyShopState(data.state);
    } else {
      showAuthBanner(true);
    }
  }

  boot();
});
