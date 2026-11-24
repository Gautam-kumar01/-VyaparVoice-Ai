/**
 * VyaparVoice AI - Frontend Controller & Multi-Page Manager
 * Minimal Light Orange, White & Warm Brown Theme (Zero Blue)
 */

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }

  // --- Multi-Shop State ---
  let currentShopId = localStorage.getItem("vyapar_shop_id") || "SHOP-001";
  let currentShopName = "Gupta Wholesale Mart";
  let latestShopState = null;
  let activeOrderFilter = "all";

  // --- UI Elements ---
  const currentShopNameEl = document.getElementById("current-shop-name");
  const openShopSwitchBtn = document.getElementById("open-shop-switch-btn");
  const authBtn = document.getElementById("auth-btn");
  const authModal = document.getElementById("auth-modal");
  const closeAuthModalBtn = document.getElementById("close-auth-modal-btn");
  const demoShopPickBtns = document.querySelectorAll(".demo-shop-pick-btn");
  const regShopNameInput = document.getElementById("reg-shop-name");
  const regOwnerNameInput = document.getElementById("reg-owner-name");
  const regPhoneInput = document.getElementById("reg-phone");
  const regSubmitBtn = document.getElementById("reg-submit-btn");

  // Metrics Elements
  const statGrahak = document.getElementById("stat-grahak");
  const statDues = document.getElementById("stat-dues");
  const statPaidOrders = document.getElementById("stat-paid-orders");
  const statDuesOrders = document.getElementById("stat-dues-orders");

  // Multi-Page Navigation Tabs & Views
  const navTabs = document.querySelectorAll(".nav-tab");
  const appViews = document.querySelectorAll(".app-view");

  // Customer Management Elements
  const customerSearchInput = document.getElementById("customer-search-input");
  const openAddCustModalBtn = document.getElementById("open-add-cust-modal-btn");
  const addCustModal = document.getElementById("add-customer-modal");
  const closeAddCustModalBtn = document.getElementById("close-add-cust-modal-btn");
  const newCustNameInput = document.getElementById("new-cust-name");
  const newCustPhoneInput = document.getElementById("new-cust-phone");
  const newCustInitialDuesInput = document.getElementById("new-cust-initial-dues");
  const newCustLimitInput = document.getElementById("new-cust-limit");
  const saveNewCustBtn = document.getElementById("save-new-cust-btn");

  // Orders and Customer Lists
  const ordersList = document.getElementById("orders-list");
  const customersList = document.getElementById("customers-list");
  const productsList = document.getElementById("products-list");
  const whatsappPreviewBox = document.getElementById("whatsapp-preview-box");
  const copyWhatsappBtn = document.getElementById("copy-whatsapp-btn");
  const orderFilterBtns = document.querySelectorAll(".order-filter-btn");

  // Voice and HUD Elements
  const micBtn = document.getElementById("mic-btn");
  const micPulse = document.getElementById("mic-pulse");
  const micCaption = document.getElementById("mic-caption");
  const micOverlay = document.getElementById("mic-status-overlay");
  const canvas = document.getElementById("waveform-canvas");
  const latencyDisplay = document.getElementById("latency-display");
  const spokenBubble = document.getElementById("spoken-response-bubble");
  const agentVoiceStatus = document.getElementById("agent-voice-status");
  const traceContainer = document.getElementById("execution-trace-container");
  const stepCountBadge = document.getElementById("step-count-badge");
  const hitlBanner = document.getElementById("hitl-banner");
  const hitlDescription = document.getElementById("hitl-description");
  const hitlApproveBtn = document.getElementById("hitl-approve-btn");
  const hitlRejectBtn = document.getElementById("hitl-reject-btn");
  const resetBtn = document.getElementById("reset-btn");
  const ttsToggle = document.getElementById("tts-toggle");
  const ttsStateText = document.getElementById("tts-state-text");
  const ttsIcon = document.getElementById("tts-icon");
  const voiceSelect = document.getElementById("voice-select");
  const testVoiceBtn = document.getElementById("test-voice-btn");
  const manualTextInput = document.getElementById("manual-text-input");
  const sendTextBtn = document.getElementById("send-text-btn");
  const scenarioBtns = document.querySelectorAll(".demo-scenario-btn");
  const quickChips = document.querySelectorAll(".quick-chip");

  // Passbook Modal Elements
  const passbookModal = document.getElementById("passbook-modal");
  const closeModalBtn = document.getElementById("close-modal-btn");
  const modalCustName = document.getElementById("modal-cust-name");
  const modalCustPhone = document.getElementById("modal-cust-phone");
  const modalCustBalance = document.getElementById("modal-cust-balance");
  const modalCustLimit = document.getElementById("modal-cust-limit");
  const modal20kAlert = document.getElementById("modal-20k-alert");
  const modalLedgerList = document.getElementById("modal-ledger-list");
  const quickPaymentAmount = document.getElementById("quick-payment-amount");
  const quickPaymentBtn = document.getElementById("quick-payment-btn");
  const modalDeleteCustBtn = document.getElementById("modal-delete-cust-btn");

  // State Variables
  let isListening = false;
  let isSpeaking = false;
  let speechEnabled = true;
  let recognition = null;
  let currentHitlPayload = null;
  let activeModalCustId = null;
  let availableVoices = [];
  let selectedVoice = null;

  // --- Page Switcher ---
  function switchPage(pageId) {
    navTabs.forEach(t => {
      if (t.getAttribute("data-page") === pageId) {
        t.classList.add("active-tab");
        t.classList.remove("inactive-tab");
      } else {
        t.classList.remove("active-tab");
        t.classList.add("inactive-tab");
      }
    });

    appViews.forEach(v => {
      if (v.id === pageId) {
        v.classList.remove("hidden");
      } else {
        v.classList.add("hidden");
      }
    });

    // Resize canvas if voice page is selected
    if (pageId === "page-voice" && canvas) {
      setTimeout(resizeCanvas, 50);
    }

    if (window.lucide) window.lucide.createIcons();
  }

  navTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const pageId = tab.getAttribute("data-page");
      switchPage(pageId);
    });
  });

  // --- Audio Synth Feedback ---
  const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  function playChime(freq1, freq2, duration = 0.12) {
    try {
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq1, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(freq2, audioCtx.currentTime + duration);
      gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
      gain.gain.linearRampToValueAtTime(0.001, audioCtx.currentTime + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + duration);
    } catch (e) {}
  }

  // --- Audio Canvas Waveform Visualizer ---
  const ctx = canvas.getContext("2d");
  let wavePhase = 0;

  function resizeCanvas() {
    if (!canvas || !canvas.parentElement) return;
    canvas.width = canvas.parentElement.clientWidth;
    canvas.height = canvas.parentElement.clientHeight;
  }
  window.addEventListener("resize", resizeCanvas);
  resizeCanvas();

  function renderWaveform() {
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const width = canvas.width;
    const height = canvas.height;
    const midY = height / 2;

    ctx.lineWidth = 2.5;

    if (isListening || isSpeaking) {
      wavePhase += 0.08;
      const waveGrad = ctx.createLinearGradient(0, 0, width, 0);
      waveGrad.addColorStop(0, '#ea580c');
      waveGrad.addColorStop(0.5, '#f59e0b');
      waveGrad.addColorStop(1, '#ea580c');
      ctx.strokeStyle = waveGrad;

      ctx.beginPath();
      for (let x = 0; x < width; x += 4) {
        const amplitude = (isListening ? 26 : 18) * Math.sin((x / 30) + wavePhase) * Math.sin(x / 60);
        const y = midY + amplitude;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    } else {
      ctx.strokeStyle = "rgba(234, 88, 12, 0.25)";
      ctx.beginPath();
      ctx.moveTo(0, midY);
      ctx.lineTo(width, midY);
      ctx.stroke();
    }

    requestAnimationFrame(renderWaveform);
  }
  renderWaveform();

  // --- Voice Synthesis (TTS) Engine ---
  function loadVoices() {
    if (!('speechSynthesis' in window)) return;
    availableVoices = window.speechSynthesis.getVoices();
    voiceSelect.innerHTML = "";

    const hindiVoices = availableVoices.filter(v => 
      v.lang.startsWith("hi") || 
      v.name.includes("Hindi") || 
      v.name.includes("Kalpana") || 
      v.name.includes("Hemant") || 
      v.name.includes("India")
    );

    const preferred = hindiVoices.length > 0 ? hindiVoices : availableVoices;

    preferred.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.name;
      opt.textContent = `${v.name} (${v.lang})`;
      voiceSelect.appendChild(opt);
    });

    const googleHindi = preferred.find(v => v.name.includes("Google हिन्दी") || v.lang === "hi-IN" || v.name.includes("Kalpana"));
    if (googleHindi) {
      selectedVoice = googleHindi;
      voiceSelect.value = googleHindi.name;
    } else if (preferred.length > 0) {
      selectedVoice = preferred[0];
      voiceSelect.value = preferred[0].name;
    }
  }

  if ('speechSynthesis' in window) {
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }

  voiceSelect.addEventListener("change", () => {
    const chosenName = voiceSelect.value;
    selectedVoice = availableVoices.find(v => v.name === chosenName) || null;
  });

  function speakResponse(text) {
    if (!speechEnabled || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();

    const cleanText = text
      .replace(/[#*`_~]/g, '')
      .replace(/₹/g, 'रुपये ')
      .replace(/ORD-[A-Za-z0-9-]+/g, 'आर्डर')
      .replace(/SKU-[A-Za-z0-9-]+/g, '')
      .trim();

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    if (selectedVoice) {
      utterance.voice = selectedVoice;
      utterance.lang = selectedVoice.lang || "hi-IN";
    } else {
      utterance.lang = "hi-IN";
    }

    utterance.onstart = () => {
      isSpeaking = true;
      agentVoiceStatus.innerHTML = `<span class="w-2 h-2 rounded-full bg-orange-500 animate-ping"></span> Bol raha hai...`;
    };

    utterance.onend = () => {
      isSpeaking = false;
      agentVoiceStatus.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Audio Ready`;
    };

    utterance.onerror = () => {
      isSpeaking = false;
      agentVoiceStatus.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Audio Ready`;
    };

    window.speechSynthesis.speak(utterance);
  }

  testVoiceBtn.addEventListener("click", () => {
    speakResponse("नमस्ते! मैं व्यापार-वाणी हूँ। आपकी दुकान का आर्डर और बही-खाता अब आवाज़ से चलेगा।");
  });

  ttsToggle.addEventListener("click", () => {
    speechEnabled = !speechEnabled;
    ttsStateText.textContent = speechEnabled ? "ON" : "OFF";
    ttsStateText.className = speechEnabled ? "text-orange-600" : "text-[#8a7667]";
    ttsIcon.className = speechEnabled ? "w-4 h-4 text-orange-600" : "w-4 h-4 text-[#8a7667]";
    if (!speechEnabled) window.speechSynthesis.cancel();
  });

  // --- 2. Web Speech Recognition (ASR) ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "hi-IN";

    recognition.onstart = () => {
      isListening = true;
      micPulse.classList.remove("hidden");
      micBtn.classList.add("mic-active-pulse");
      micCaption.textContent = "Listening (Sun raha hai)...";
      micCaption.className = "text-xs font-bold text-orange-600";
      micOverlay.classList.add("hidden");
      playChime(440, 880);
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      manualTextInput.value = transcript;
      executeVoiceInstruction(transcript);
    };

    recognition.onerror = () => {
      stopListening();
    };

    recognition.onend = () => {
      stopListening();
    };
  }

  function startListening() {
    if (!recognition) {
      alert("Aapka browser Speech Recognition support nahi karta. Chrome use karein ya command type karein.");
      return;
    }
    try {
      recognition.start();
    } catch (e) {
      stopListening();
    }
  }

  function stopListening() {
    isListening = false;
    micPulse.classList.add("hidden");
    micBtn.classList.remove("mic-active-pulse");
    micCaption.textContent = "Tap to Speak (माइक दबाएं)";
    micCaption.className = "text-xs font-bold text-[#23160e]";
    micOverlay.classList.remove("hidden");
  }

  micBtn.addEventListener("click", () => {
    if (isListening) {
      if (recognition) recognition.stop();
      stopListening();
    } else {
      startListening();
    }
  });

  // --- 3. Core Agentic Execution Loop ---
  async function executeVoiceInstruction(text) {
    if (!text.trim()) return;

    // Switch to voice tab automatically if user was on home
    switchPage("page-voice");

    playChime(660, 990);
    traceContainer.innerHTML = `
      <div class="flex items-center space-x-2 text-xs text-orange-600 p-2 bg-orange-50 rounded-xl animate-pulse">
        <i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>
        <span>Gemini AI agent processing spoken intent across tools...</span>
      </div>
    `;
    stepCountBadge.textContent = "Processing...";
    spokenBubble.innerHTML = `<span class="italic text-[#8a7667]">"${text}"</span>`;

    const startMs = performance.now();

    try {
      const res = await fetch("/api/execute-voice", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript: text, shop_id: currentShopId })
      });

      const data = await res.json();
      const elapsedMs = Math.round(performance.now() - startMs);

      if (data.status === "success") {
        const result = data.result;
        latencyDisplay.textContent = `⚡ ${result.latency_ms || elapsedMs}ms`;

        spokenBubble.textContent = result.spoken_response;
        speakResponse(result.spoken_response);

        renderTraceSteps(result.steps || []);

        if (result.whatsapp_challan) {
          whatsappPreviewBox.textContent = result.whatsapp_challan.whatsapp_text;
          whatsappPreviewBox.classList.add("border-emerald-400");
        }

        if (result.requires_hitl && result.pending_payload) {
          currentHitlPayload = result.pending_payload;
          hitlDescription.textContent = result.hitl_reason;
          hitlBanner.classList.remove("hidden");
          playChime(300, 200, 0.25);
        } else {
          hitlBanner.classList.add("hidden");
        }

        if (data.state) {
          latestShopState = data.state;
          renderDashboardState(data.state);
        }
      } else {
        spokenBubble.textContent = `Error: ${data.message}`;
        traceContainer.innerHTML = `<div class="p-3 rounded-xl bg-red-50 text-red-700 text-xs">Error: ${data.message}</div>`;
      }
    } catch (err) {
      spokenBubble.textContent = "Server se connect nahi ho saka.";
      traceContainer.innerHTML = `<div class="p-3 rounded-xl bg-red-50 text-red-700 text-xs">${err.message}</div>`;
    }
  }

  // --- 4. Render Agentic Trace Steps ---
  function renderTraceSteps(steps) {
    stepCountBadge.textContent = `${steps.length} Steps`;
    if (steps.length === 0) {
      traceContainer.innerHTML = `<p class="text-xs text-[#8a7667]">No tool executions.</p>`;
      return;
    }

    traceContainer.innerHTML = steps.map((s, idx) => {
      let icon = "activity";
      let iconColor = "text-orange-600";
      let borderClass = "border-[#e8ddd4] bg-[#faf7f3]";

      if (s.type === "intent") {
        icon = "brain";
        iconColor = "text-amber-600";
      } else if (s.type === "tool") {
        icon = "cpu";
        iconColor = "text-orange-600";
      } else if (s.type === "policy") {
        icon = "shield-check";
        iconColor = "text-emerald-700";
      } else if (s.type === "interruption") {
        icon = "zap";
        iconColor = "text-amber-600";
        borderClass = "border-amber-300 bg-amber-50/40";
      }

      if (s.status === "warning") {
        icon = "alert-triangle";
        iconColor = "text-red-600";
        borderClass = "border-red-300 bg-red-50/50";
      }

      return `
        <div class="animate-step p-3 rounded-xl border ${borderClass} text-xs transition">
          <div class="flex items-center justify-between mb-1">
            <span class="font-bold text-[#23160e] flex items-center gap-1.5">
              <i data-lucide="${icon}" class="w-3.5 h-3.5 ${iconColor}"></i>
              ${s.title}
            </span>
            <span class="text-[10px] font-mono text-[#8a7667]">${s.timestamp || ''}</span>
          </div>
          <p class="text-[11px] text-[#49382c] pl-5 leading-relaxed font-mono">${s.detail}</p>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  // --- 5. Render Full Dashboard State Across Pages ---
  function renderDashboardState(state) {
    if (!state) return;
    latestShopState = state;

    // Shop Profile Header
    if (state.shop) {
      currentShopName = state.shop.shop_name;
      currentShopNameEl.textContent = currentShopName;
    }

    // Top Metrics
    if (state.stats) {
      statGrahak.textContent = `${state.stats.total_grahak || (state.customers ? state.customers.length : 0)} Accounts`;
      statDues.textContent = `₹${(state.stats.total_receivables || 0).toLocaleString('en-IN')}`;
      statPaidOrders.textContent = `${state.stats.paid_orders || 0} Bills`;
      statDuesOrders.textContent = `${state.stats.dues_orders || 0} Bills`;
    }

    // Render Orders Feed (Page 5 & Live Card)
    renderOrders(state.recent_orders || []);

    // Render Customer Khata (Page 3)
    renderCustomers(state.customers || []);

    // Render Warehouse Inventory (Page 4)
    renderProducts(state.products || []);

    if (window.lucide) window.lucide.createIcons();
  }

  // Render Customers List (with Khatabook cards & Delete button)
  function renderCustomers(customers) {
    if (!customersList) return;
    const searchVal = customerSearchInput ? customerSearchInput.value.trim().toLowerCase() : "";

    const filtered = customers.filter(c => 
      !searchVal || 
      c.name.toLowerCase().includes(searchVal) || 
      (c.phone && c.phone.includes(searchVal)) ||
      (c.contact_person && c.contact_person.toLowerCase().includes(searchVal))
    );

    if (filtered.length === 0) {
      customersList.innerHTML = `
        <div class="text-center py-8 text-[#8a7667]">
          <i data-lucide="user-x" class="w-8 h-8 mx-auto mb-2 text-stone-400"></i>
          <p class="text-xs">Koi grahak nahi mila.</p>
          <button class="mt-2 text-xs font-bold text-orange-600 underline" onclick="document.getElementById('open-add-cust-modal-btn').click()">+ Naya Grahak Jodein</button>
        </div>
      `;
      if (window.lucide) window.lucide.createIcons();
      return;
    }

    customersList.innerHTML = filtered.map(c => {
      const isOver20k = c.current_balance > 20000;
      const isZero = c.current_balance <= 0;
      const cardBorder = isOver20k ? "border-red-300 bg-red-50/40" : "border-[#e8ddd4] bg-[#faf7f3]";

      return `
        <div id="cust-row-${c.id}" class="p-3.5 rounded-2xl border ${cardBorder} flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-orange-300 transition">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-orange-100 text-orange-700 font-extrabold flex items-center justify-center text-sm shadow-xs flex-shrink-0">
              ${c.name.substring(0, 1)}
            </div>
            <div>
              <div class="flex items-center gap-2">
                <h4 class="text-xs sm:text-sm font-bold text-[#23160e]">${c.name}</h4>
                ${isOver20k ? '<span class="text-[9px] px-2 py-0.5 rounded-full bg-red-600 text-white font-mono font-bold">🛑 >₹20k Block</span>' : ''}
              </div>
              <p class="text-[11px] text-[#8a7667] font-mono mt-0.5">${c.phone || '+91 98000 00000'} • ${c.location || 'Local'}</p>
            </div>
          </div>

          <div class="flex items-center justify-between md:justify-end gap-3 pt-2 md:pt-0 border-t md:border-t-0 border-[#f0e6dc]">
            <div class="text-left md:text-right mr-1">
              <span class="text-[10px] text-[#8a7667] block uppercase font-semibold">Bakaya (Dues)</span>
              <span class="text-sm font-bold font-mono ${isZero ? 'text-emerald-700' : 'text-red-600'}">
                ₹${c.current_balance.toLocaleString('en-IN')}
                <span class="text-[9px] px-1.5 py-0.2 rounded font-bold ${isZero ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'}">
                  ${isZero ? 'चुकता ✓' : 'बाकी ⏳'}
                </span>
              </span>
            </div>

            <!-- Action Buttons -->
            <div class="flex items-center gap-1.5">
              <button class="open-passbook-action-btn px-3 py-1.5 rounded-xl bg-orange-50 hover:bg-orange-100 border border-orange-200 text-orange-700 font-bold text-xs flex items-center gap-1 transition" data-id="${c.id}">
                <i data-lucide="book-marked" class="w-3.5 h-3.5"></i>
                पासबुक / रिपोर्ट
              </button>
              <button class="delete-cust-action-btn p-2 rounded-xl bg-red-50 hover:bg-red-100 border border-red-200 text-red-600 transition" data-id="${c.id}" data-name="${c.name}" title="खाता मिटाएं (Delete Khata)">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Attach event listeners for buttons
    document.querySelectorAll(".open-passbook-action-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        openPassbookModal(btn.getAttribute("data-id"));
      });
    });

    document.querySelectorAll(".delete-cust-action-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const cid = btn.getAttribute("data-id");
        const cname = btn.getAttribute("data-name");
        deleteCustomer(cid, cname);
      });
    });

    if (window.lucide) window.lucide.createIcons();
  }

  // Customer search listener
  if (customerSearchInput) {
    customerSearchInput.addEventListener("input", () => {
      if (latestShopState && latestShopState.customers) {
        renderCustomers(latestShopState.customers);
      }
    });
  }

  // Render Orders List
  function renderOrders(orders) {
    if (!ordersList) return;

    let filtered = orders;
    if (activeOrderFilter === "PAID") {
      filtered = orders.filter(o => o.payment_status === "PAID");
    } else if (activeOrderFilter === "DUES") {
      filtered = orders.filter(o => o.payment_status === "DUES");
    }

    if (filtered.length === 0) {
      ordersList.innerHTML = `<p class="text-stone-400 text-xs italic p-4 text-center">Koi order record nahi hai.</p>`;
      return;
    }

    ordersList.innerHTML = filtered.map(o => {
      const isPaid = o.payment_status === "PAID";
      const statusBadge = isPaid 
        ? `<span class="badge-paid px-2.5 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1">✓ PAID (चुका दिया)</span>`
        : `<span class="badge-dues px-2.5 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1">⏳ DUES (बाकी)</span>`;

      const itemsText = (o.items || []).map(i => `${i.quantity} ${i.unit} ${i.name}`).join(', ');

      return `
        <div class="p-3.5 rounded-2xl border border-[#e8ddd4] bg-[#faf7f3] flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 hover:border-orange-300 transition">
          <div>
            <div class="flex items-center space-x-2">
              <span class="text-xs font-extrabold text-[#23160e]">${o.customer_name}</span>
              ${statusBadge}
              <span class="text-[10px] font-mono text-[#8a7667]">#${o.id}</span>
            </div>
            <p class="text-xs text-[#5d4a3c] mt-1">${itemsText || 'Goods Dispatched'}</p>
            <span class="text-[10px] text-[#8a7667] font-mono">${o.created_at ? o.created_at.split('T')[0] : ''}</span>
          </div>
          <div class="text-left sm:text-right pt-2 sm:pt-0 border-t sm:border-t-0 border-[#f0e6dc]">
            <span class="text-sm font-mono font-extrabold ${isPaid ? 'text-emerald-700' : 'text-amber-800'}">₹${o.total_amount.toLocaleString('en-IN')}</span>
            <span class="text-[10px] text-[#8a7667] block">${o.payment_mode === 'cash' ? 'नकद बिल' : 'उधार बिल'}</span>
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  // Order filter button listeners
  orderFilterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      orderFilterBtns.forEach(b => {
        b.className = "order-filter-btn px-3 py-1 rounded-lg font-bold text-[#8a7667] hover:text-[#23160e]";
      });
      btn.className = "order-filter-btn px-3 py-1 rounded-lg font-bold bg-white text-orange-700 shadow-xs";
      activeOrderFilter = btn.getAttribute("data-filter");
      if (latestShopState && latestShopState.recent_orders) {
        renderOrders(latestShopState.recent_orders);
      }
    });
  });

  // Render Warehouse Inventory
  function renderProducts(products) {
    if (!productsList) return;

    productsList.innerHTML = products.map(p => {
      const isLow = p.stock <= p.min_stock;
      const barColor = isLow ? "bg-red-500" : "bg-orange-500";
      const stockPercent = Math.min(100, Math.round((p.stock / 100) * 100));

      return `
        <div class="p-3.5 rounded-2xl border border-[#e8ddd4] bg-[#faf7f3] hover:border-orange-300 transition">
          <div class="flex items-center justify-between mb-1">
            <span class="text-xs font-bold text-[#23160e] truncate max-w-[200px]">${p.name}</span>
            <span class="text-xs font-mono font-extrabold ${isLow ? 'text-red-600' : 'text-orange-700'}">
              ${p.stock} <span class="text-[10px] text-[#8a7667] font-normal">${p.unit}</span>
            </span>
          </div>
          <div class="w-full bg-stone-200 rounded-full h-1.5 overflow-hidden my-2">
            <div class="${barColor} h-1.5 rounded-full" style="width: ${stockPercent}%"></div>
          </div>
          <div class="flex justify-between items-center text-[11px] text-[#8a7667]">
            <span class="font-mono font-bold text-[#23160e]">₹${p.price_per_unit} / ${p.unit}</span>
            ${isLow ? '<span class="text-red-600 font-bold text-[10px]">⚠️ Low Stock</span>' : '<span class="text-emerald-700 text-[10px]">In Stock</span>'}
          </div>
        </div>
      `;
    }).join('');

    if (window.lucide) window.lucide.createIcons();
  }

  // --- 6. Passbook Statement Modal Logic ---
  async function openPassbookModal(customerId) {
    activeModalCustId = customerId;
    try {
      const res = await fetch(`/api/customer-history/${customerId}?shop_id=${currentShopId}`);
      const data = await res.json();
      if (data.status === "success") {
        const hist = data.data;
        const c = hist.customer;

        modalCustName.textContent = c.name;
        modalCustPhone.textContent = `${c.phone || '+91 98000 00000'} • ${c.location || 'Local'}`;
        modalCustBalance.textContent = `₹${c.current_balance.toLocaleString('en-IN')}`;
        modalCustLimit.textContent = `₹${c.credit_limit.toLocaleString('en-IN')}`;

        if (c.current_balance > 20000) {
          modal20kAlert.classList.remove("hidden");
        } else {
          modal20kAlert.classList.add("hidden");
        }

        if (hist.ledger && hist.ledger.length > 0) {
          modalLedgerList.innerHTML = hist.ledger.map(entry => {
            const isPayment = entry.entry_type.includes("PAYMENT");
            const badgeBg = isPayment ? "badge-paid" : "bg-stone-100 text-[#49382c] border-stone-200";
            const dateStr = entry.timestamp ? entry.timestamp.split("T")[0] : "";

            return `
              <div class="p-2.5 rounded-xl border border-[#e8ddd4] bg-[#faf7f3] flex items-center justify-between">
                <div>
                  <div class="font-medium text-[#23160e] flex items-center gap-1.5">
                    <span class="text-[9px] px-1.5 py-0.2 rounded border ${badgeBg}">${entry.entry_type}</span>
                    <span>${entry.description}</span>
                  </div>
                  <span class="text-[10px] text-[#8a7667]">${dateStr}</span>
                </div>
                <div class="text-right font-mono">
                  <span class="font-bold ${isPayment ? 'text-emerald-700' : 'text-red-600'}">
                    ${isPayment ? '-' : '+'}₹${entry.amount.toLocaleString('en-IN')}
                  </span>
                  <span class="text-[10px] text-[#8a7667] block">Naya: ₹${entry.new_balance.toLocaleString('en-IN')}</span>
                </div>
              </div>
            `;
          }).join('');
        } else {
          modalLedgerList.innerHTML = `<p class="text-stone-400 text-xs italic p-2">Koi purani entry nahi hai.</p>`;
        }

        passbookModal.classList.remove("hidden");
        if (window.lucide) window.lucide.createIcons();
      }
    } catch (err) {
      alert("Passbook load karne mein error: " + err.message);
    }
  }

  closeModalBtn.addEventListener("click", () => {
    passbookModal.classList.add("hidden");
    activeModalCustId = null;
  });

  // Collect Cash Payment from Passbook
  quickPaymentBtn.addEventListener("click", async () => {
    const amt = parseFloat(quickPaymentAmount.value);
    if (!amt || amt <= 0 || !activeModalCustId) {
      alert("Kripya valid payment amount likhein!");
      return;
    }

    try {
      const res = await fetch("/api/record-payment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: activeModalCustId,
          shop_id: currentShopId,
          amount: amt,
          note: "Passbook Quick Cash Entry"
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        playChime(523, 1046);
        quickPaymentAmount.value = "";
        speakResponse(data.result.message);
        await openPassbookModal(activeModalCustId);
        if (data.state) renderDashboardState(data.state);
      } else {
        alert(data.message);
      }
    } catch (e) {
      console.error(e);
    }
  });

  // Erase / Delete Customer Khata & Reports
  async function deleteCustomer(custId, custName) {
    if (!custId) return;
    const confirmed = confirm(`⚠️ Kya aap sach me "${custName}" ka poora bahi-khata aur reports hamesha ke liye delete/erase karna chahte hain?\n\nYeh wapas nahi aayega!`);
    if (!confirmed) return;

    try {
      const res = await fetch("/api/customer/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: custId,
          shop_id: currentShopId
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        playChime(300, 150);
        alert(data.result.message || `${custName} ka khata erase ho gaya.`);
        passbookModal.classList.add("hidden");
        activeModalCustId = null;
        if (data.state) renderDashboardState(data.state);
      } else {
        alert(data.message || "Delete karne mein error aaya.");
      }
    } catch (e) {
      alert("Error: " + e.message);
    }
  }

  // Delete button inside passbook modal
  if (modalDeleteCustBtn) {
    modalDeleteCustBtn.addEventListener("click", () => {
      if (activeModalCustId) {
        deleteCustomer(activeModalCustId, modalCustName.textContent);
      }
    });
  }

  // Add Customer Modal logic
  if (openAddCustModalBtn) {
    openAddCustModalBtn.addEventListener("click", () => {
      addCustModal.classList.remove("hidden");
    });
  }

  if (closeAddCustModalBtn) {
    closeAddCustModalBtn.addEventListener("click", () => {
      addCustModal.classList.add("hidden");
    });
  }

  if (saveNewCustBtn) {
    saveNewCustBtn.addEventListener("click", async () => {
      const name = newCustNameInput.value.trim();
      const phone = newCustPhoneInput.value.trim();
      const initDues = parseFloat(newCustInitialDuesInput.value) || 0.0;
      const limit = parseFloat(newCustLimitInput.value) || 20000.0;

      if (!name) {
        alert("Grahak ka naam zaroori hai!");
        return;
      }

      try {
        const res = await fetch("/api/customer/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            shop_id: currentShopId,
            name: name,
            phone: phone,
            initial_dues: initDues,
            credit_limit: limit
          })
        });
        const data = await res.json();
        if (data.status === "success") {
          playChime(523, 784);
          alert(`Naya grahak "${name}" safaltapoorvak jud gaya!`);
          newCustNameInput.value = "";
          newCustPhoneInput.value = "";
          newCustInitialDuesInput.value = "";
          addCustModal.classList.add("hidden");
          if (data.state) renderDashboardState(data.state);
        } else {
          alert(data.message || "Grahak jodne mein error aaya.");
        }
      } catch (e) {
        alert("Error: " + e.message);
      }
    });
  }

  // --- 7. Multi-Tenant Shop Switching & Registration ---
  async function fetchState(shopId) {
    try {
      const res = await fetch(`/api/state?shop_id=${shopId}`);
      const data = await res.json();
      if (data.status === "success") {
        renderDashboardState(data.data);
      }
    } catch (e) {
      console.error("State load error:", e);
    }
  }

  openShopSwitchBtn.addEventListener("click", () => {
    authModal.classList.remove("hidden");
  });

  authBtn.addEventListener("click", () => {
    authModal.classList.remove("hidden");
  });

  closeAuthModalBtn.addEventListener("click", () => {
    authModal.classList.add("hidden");
  });

  demoShopPickBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      currentShopId = btn.getAttribute("data-id");
      localStorage.setItem("vyapar_shop_id", currentShopId);
      authModal.classList.add("hidden");
      fetchState(currentShopId);
      speakResponse(`Dukan switch ho gayi hai: ${btn.getAttribute("data-name")}`);
    });
  });

  // Register New Shop (Guaranteed Unique ID & Isolated Dashboard)
  regSubmitBtn.addEventListener("click", async () => {
    const sName = regShopNameInput.value.trim();
    const oName = regOwnerNameInput.value.trim();
    const sPhone = regPhoneInput.value.trim();

    if (!sName || !oName) {
      alert("दुकान का नाम और अपना नाम ज़रूर लिखें!");
      return;
    }

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shop_name: sName,
          owner_name: oName,
          phone: sPhone || "+91 98000 00000",
          password: "password123"
        })
      });
      const data = await res.json();
      if (data.status === "success") {
        currentShopId = data.shop.id;
        localStorage.setItem("vyapar_shop_id", currentShopId);
        authModal.classList.add("hidden");
        fetchState(currentShopId);
        alert(`🎉 मुबारक़ हो! आपकी नई दुकान "${sName}" तैयार हो गई है। आपका नया डैशबोर्ड खुल रहा है!`);
        speakResponse(`मुबारक़ हो! नई दुकान ${sName} बन गई है।`);
        // Switch to Khata or Voice
        switchPage("page-khata");
      } else {
        alert(data.message);
      }
    } catch (e) {
      alert("Registration error: " + e.message);
    }
  });

  // Manual Text Submit
  sendTextBtn.addEventListener("click", () => {
    const val = manualTextInput.value.trim();
    if (val) executeVoiceInstruction(val);
  });

  manualTextInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const val = manualTextInput.value.trim();
      if (val) executeVoiceInstruction(val);
    }
  });

  scenarioBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const utterance = btn.getAttribute("data-utterance");
      manualTextInput.value = utterance;
      executeVoiceInstruction(utterance);
    });
  });

  quickChips.forEach(chip => {
    chip.addEventListener("click", () => {
      const txt = chip.getAttribute("data-text");
      manualTextInput.value = txt;
      executeVoiceInstruction(txt);
    });
  });

  // Copy WhatsApp Receipt
  copyWhatsappBtn.addEventListener("click", () => {
    const text = whatsappPreviewBox.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const orig = copyWhatsappBtn.textContent;
      copyWhatsappBtn.textContent = "Copied!";
      setTimeout(() => copyWhatsappBtn.textContent = orig, 1500);
    });
  });

  // Reset Demo State
  resetBtn.addEventListener("click", async () => {
    if (confirm("Kya aap initial demo benchmarks reset karna chahte hain?")) {
      await fetchState(currentShopId);
      traceContainer.innerHTML = `<p class="text-xs text-[#8a7667]">State reset. Bolkar test karein.</p>`;
      spokenBubble.textContent = "Demo benchmark reset ho gaya hai.";
    }
  });

  // Initial State Load
  fetchState(currentShopId);
});
