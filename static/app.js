/* ==========================================================================
   GRIMOIRE // TECHNOWITCH — Client Runtime
   Scriptorium Markdown Editor + Multi-Stage SSE Oracle Chasm
   ========================================================================== */

(() => {
  'use strict';

  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  const state = {
    todayKey: getLocalIsoDate(new Date()),
    currentDate: getLocalIsoDate(new Date()),
    editorMode: 'write', // 'write' | 'preview'
    archiveCollapsed: localStorage.getItem('grimoire.archiveCollapsed') === '1',
    chasmCollapsed: localStorage.getItem('grimoire.chasmCollapsed') === '1',
    journalDirty: false,
    lastSavedContent: '',
    saveTimer: null,
    searchTimer: null,

    vesselState: 'dormant',
    spreadMode: 'daily', // 'daily' | 'trinity'
    selectedExtraCast: null, // 'card' | 'rune' | 'iching' | null

    sessions: [],
    activeSession: null,
    streaming: false,
  };

  // -------------------------------------------------------------------------
  // DOM References
  // -------------------------------------------------------------------------
  const el = {
    workspace: document.getElementById('sanctuary-workspace'),
    archiveSidebar: document.getElementById('archive-sidebar'),
    archiveSearch: document.getElementById('archive-search'),
    archiveList: document.getElementById('archive-list'),
    btnToggleArchive: document.getElementById('btn-toggle-archive'),
    btnJumpToday: document.getElementById('btn-jump-today'),
    btnReturnToday: document.getElementById('btn-return-today'),
    btnPrevDay: document.getElementById('btn-prev-day'),
    btnNextDay: document.getElementById('btn-next-day'),
    folioHumanDate: document.getElementById('folio-human-date'),
    folioFileTag: document.getElementById('folio-file-tag'),
    folioWordCount: document.getElementById('folio-word-count'),
    folioSaveStatus: document.getElementById('folio-save-status'),
    btnModeWrite: document.getElementById('btn-mode-write'),
    btnModePreview: document.getElementById('btn-mode-preview'),
    journalEditor: document.getElementById('journal-editor'),
    journalPreview: document.getElementById('journal-preview'),

    // Telemetry ribbon
    pillUndergrowth: document.getElementById('pill-undergrowth'),
    valUndergrowth: document.getElementById('val-undergrowth'),
    pillLights: document.getElementById('pill-lights'),
    valLights: document.getElementById('val-lights'),
    pillCelestial: document.getElementById('pill-celestial'),
    valCelestial: document.getElementById('val-celestial'),
    pillVessel: document.getElementById('pill-vessel'),
    valVessel: document.getElementById('val-vessel'),
    btnVesselToggle: document.getElementById('btn-vessel-toggle'),
    btnToggleChasm: document.getElementById('btn-toggle-chasm'),

    // Chasm
    sessionSelect: document.getElementById('oracle-session-select'),
    btnNewRitual: document.getElementById('btn-new-ritual'),
    btnDeleteSession: document.getElementById('btn-delete-session'),
    chasmScroll: document.getElementById('chasm-scroll'),
    chasmAltar: document.getElementById('chasm-altar'),
    chasmReading: document.getElementById('chasm-reading'),
    spreadOptDaily: document.getElementById('spread-opt-daily'),
    spreadOptTrinity: document.getElementById('spread-opt-trinity'),
    fissureQuestion: document.getElementById('fissure-question'),
    btnConsultChasm: document.getElementById('btn-consult-chasm'),

    ritualBanner: document.getElementById('ritual-stage-banner'),
    ritualStageCode: document.getElementById('ritual-stage-code'),
    ritualStageLabel: document.getElementById('ritual-stage-label'),

    talismansSection: document.getElementById('talismans-section'),
    talismanModeBadge: document.getElementById('talisman-mode-badge'),
    entropyStamp: document.getElementById('entropy-stamp'),
    btnToggleEntrails: document.getElementById('btn-toggle-entrails'),
    quietCountPill: document.getElementById('quiet-count-pill'),
    entrailsDrawer: document.getElementById('entrails-drawer'),
    entrailsModelMeta: document.getElementById('entrails-model-meta'),
    smokePacketPre: document.getElementById('smoke-packet-pre'),
    talismansGrid: document.getElementById('talismans-grid'),

    chasmErrorBox: document.getElementById('chasm-error-box'),
    omenVessel: document.getElementById('omen-vessel'),
    omenQuestionEpigraph: document.getElementById('omen-question-epigraph'),
    btnInscribeOmen: document.getElementById('btn-inscribe-omen'),
    omenBody: document.getElementById('omen-body'),
    chatThread: document.getElementById('pythia-chat-thread'),

    chasmComposer: document.getElementById('chasm-composer'),
    chatInput: document.getElementById('chat-input'),
    btnSendChat: document.getElementById('btn-send-chat'),
    toast: document.getElementById('brass-toast'),
  };

  // -------------------------------------------------------------------------
  // Date & Text Utilities
  // -------------------------------------------------------------------------
  function getLocalIsoDate(d) {
    const yr = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const da = String(d.getDate()).padStart(2, '0');
    return `${yr}-${mo}-${da}`;
  }

  function isIsoDate(str) {
    return /^\d{4}-\d{2}-\d{2}$/.test(str);
  }

  function formatHumanDate(dateKey) {
    if (!isIsoDate(dateKey)) return dateKey;
    const [y, m, d] = dateKey.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return dt.toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  }

  function formatShortArchiveDate(dateKey) {
    if (!isIsoDate(dateKey)) return dateKey;
    const [y, m, d] = dateKey.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    return dt.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  }

  function shiftIsoDate(dateKey, deltaDays) {
    const base = isIsoDate(dateKey) ? dateKey : state.todayKey;
    const [y, m, d] = base.split('-').map(Number);
    const dt = new Date(y, m - 1, d);
    dt.setDate(dt.getDate() + deltaDays);
    return getLocalIsoDate(dt);
  }

  function countWords(text) {
    const trimmed = (text || '').trim();
    if (!trimmed) return 0;
    return trimmed.split(/\s+/).length;
  }

  function formatTimeHHMM(isoStr) {
    const dt = isoStr ? new Date(isoStr) : new Date();
    if (Number.isNaN(dt.getTime())) return '';
    return dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(raw) {
    return String(raw ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  let toastTimeout = null;
  function showToast(message) {
    el.toast.textContent = message;
    el.toast.classList.remove('hidden');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
      el.toast.classList.add('hidden');
    }, 2600);
  }

  // -------------------------------------------------------------------------
  // Safe Symbolist Markdown Parser
  // -------------------------------------------------------------------------
  function formatInlineMarkdown(escapedLine) {
    let out = escapedLine;
    // Inline code
    out = out.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold + Italic
    out = out.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
    // Bold
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>');
    // Italic
    out = out.replace(/(^|[\s(>])\*([^\n*]+?)\*(?=[\s.,;:!?)<]|$)/g, '$1<em>$2</em>');
    out = out.replace(/(^|[\s(>])_([^\n_]+?)_(?=[\s.,;:!?)<]|$)/g, '$1<em>$2</em>');
    return out;
  }

  function renderMarkdown(md) {
    if (!md || !md.trim()) return '';
    const lines = md.replace(/\r\n/g, '\n').split('\n');
    const html = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        i += 1;
        continue;
      }

      // Horizontal rule
      if (/^(---+|\*\*\*+|___+)\s*$/.test(trimmed)) {
        html.push('<hr />');
        i += 1;
        continue;
      }

      // Headings
      const hMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (hMatch) {
        const level = hMatch[1].length;
        html.push(`<h${level}>${formatInlineMarkdown(escapeHtml(hMatch[2]))}</h${level}>`);
        i += 1;
        continue;
      }

      // Blockquote
      if (trimmed.startsWith('>')) {
        const quoteLines = [];
        while (i < lines.length && lines[i].trim().startsWith('>')) {
          quoteLines.push(lines[i].trim().replace(/^>\s?/, ''));
          i += 1;
        }
        html.push(`<blockquote>${renderMarkdown(quoteLines.join('\n'))}</blockquote>`);
        continue;
      }

      // Unordered list
      if (/^[-*+]\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^[-*+]\s+/.test(lines[i].trim())) {
          const itemText = lines[i].trim().replace(/^[-*+]\s+/, '');
          items.push(`<li>${formatInlineMarkdown(escapeHtml(itemText))}</li>`);
          i += 1;
        }
        html.push(`<ul>${items.join('')}</ul>`);
        continue;
      }

      // Ordered list
      if (/^\d+\.\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
          const itemText = lines[i].trim().replace(/^\d+\.\s+/, '');
          items.push(`<li>${formatInlineMarkdown(escapeHtml(itemText))}</li>`);
          i += 1;
        }
        html.push(`<ol>${items.join('')}</ol>`);
        continue;
      }

      // Paragraph
      const paraLines = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !lines[i].trim().startsWith('>') &&
        !/^(#{1,4})\s+/.test(lines[i].trim()) &&
        !/^(---+|\*\*\*+|___+)\s*$/.test(lines[i].trim()) &&
        !/^[-*+]\s+/.test(lines[i].trim()) &&
        !/^\d+\.\s+/.test(lines[i].trim())
      ) {
        paraLines.push(formatInlineMarkdown(escapeHtml(lines[i].trim())));
        i += 1;
      }
      html.push(`<p>${paraLines.join('<br />')}</p>`);
    }

    return html.join('\n');
  }

  // -------------------------------------------------------------------------
  // Top Brass Telemetry & Vessel Controls
  // -------------------------------------------------------------------------
  async function refreshTelemetry() {
    try {
      const res = await fetch('/api/telemetry');
      if (!res.ok) return;
      const data = await res.json();

      // 1. Undergrowth Tub
      const tub = data.tub || {};
      const rh = tub.humidity_pct != null ? `${Math.round(Number(tub.humidity_pct))}% RH` : '—% RH';
      const co2 = tub.co2_ppm != null ? `${Math.round(Number(tub.co2_ppm))} ppm` : '— ppm';
      const temp = tub.temperature_c != null ? `${Number(tub.temperature_c).toFixed(1)}°C` : '—°C';
      el.valUndergrowth.textContent = `${rh} · ${co2} · ${temp}`;
      const plant = data.plant || null;
      const plantLine = plant && plant.line ? `\n${plant.label || 'Botanical'}: ${plant.line}` : '';
      el.pillUndergrowth.title = `Undergrowth: ${tub.status || 'live'}${tub.power_w != null ? ` (${tub.power_w}W)` : ''}${plantLine}`;

      // 2. Hearth Light & Dynamic CSS Variable --ambient-light
      const lights = data.lights || {};
      if (lights.ambient_hex && /^#[0-9a-fA-F]{3,8}$/.test(lights.ambient_hex)) {
        document.documentElement.style.setProperty('--ambient-light', lights.ambient_hex);
      }
      el.valLights.textContent = lights.summary || 'Quiet hearth';
      if (lights.ambient_hex) {
        el.pillLights.title = `Hearth ambient (${lights.ambient_hex}): ${lights.summary || ''}`;
      }

      // 3. Celestial & Chaldean Planetary Hour
      const cel = data.celestial || {};
      const moon = cel.moon || {};
      const plan = cel.planetary || {};
      const moonPart = `${moon.glyph || '☽'} ${moon.illumination_pct != null ? `${Math.round(Number(moon.illumination_pct))}%` : ''} ${moon.zodiac_sign || ''}`.trim();
      const hourPart = `${plan.hour_glyph || '♄'} ${plan.hour_ruler ? `Hour of ${plan.hour_ruler}` : ''}`.trim();
      el.valCelestial.textContent = [moonPart, hourPart].filter(Boolean).join(' · ') || '☽ Celestial';
      el.pillCelestial.title = [
        moon.phase_name ? `${moon.phase_name} in ${moon.zodiac_sign || ''}` : '',
        plan.day_ruler ? `Day of ${plan.day_ruler} (${plan.day_glyph || ''})` : '',
        plan.correspondence ? `Correspondence: ${plan.correspondence}` : '',
      ].filter(Boolean).join(' · ');

      // 4. Pythia Vessel
      if (data.vessel) {
        applyVesselStatus(data.vessel);
      }
    } catch (err) {
      console.warn('Telemetry refresh warning:', err);
    }
  }

  function applyVesselStatus(vessel) {
    const st = vessel.state || 'dormant';
    state.vesselState = st;
    el.pillVessel.dataset.state = st;

    const labels = {
      awake: 'Awake',
      loading: 'Waking…',
      waking: 'Waking…',
      dormant: 'Dormant',
      server_off: 'Offline',
    };
    el.valVessel.textContent = labels[st] || st;
    el.pillVessel.title = `${vessel.model_id || 'Fallen Gemma'} — ${vessel.detail || st}`;

    if (st === 'loading' || st === 'waking') {
      el.btnVesselToggle.textContent = 'Waking…';
      el.btnVesselToggle.disabled = true;
    } else if (st === 'awake') {
      el.btnVesselToggle.textContent = 'Banish';
      el.btnVesselToggle.disabled = false;
    } else {
      el.btnVesselToggle.textContent = 'Wake';
      el.btnVesselToggle.disabled = false;
    }
  }

  async function handleVesselButtonClick() {
    if (state.vesselState === 'awake') {
      el.btnVesselToggle.disabled = true;
      el.btnVesselToggle.textContent = 'Banishing…';
      try {
        const res = await fetch('/api/vessel/banish', { method: 'POST' });
        const data = await res.json();
        applyVesselStatus(data.state ? data : await (await fetch('/api/vessel/status')).json());
        showToast('Pythia banished from VRAM');
      } catch (err) {
        showToast('Banish failed');
        el.btnVesselToggle.disabled = false;
      }
    } else {
      applyVesselStatus({ state: 'loading', detail: 'Summoning Fallen Gemma into VRAM…' });
      try {
        const res = await fetch('/api/vessel/wake', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ttl: 1800, context_length: 8192 }),
        });
        const data = await res.json();
        applyVesselStatus(data.state ? data : await (await fetch('/api/vessel/status')).json());
        showToast('Fallen Gemma is awake in the chasm');
      } catch (err) {
        applyVesselStatus({ state: 'server_off', detail: String(err) });
        showToast('Could not wake LM Studio vessel');
      }
    }
  }

  // -------------------------------------------------------------------------
  // Scriptorium: Archive & Distraction-Free Folio Editor
  // -------------------------------------------------------------------------
  async function loadArchiveList(query = '') {
    try {
      const url = query
        ? `/api/journal?q=${encodeURIComponent(query)}`
        : '/api/journal';
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      renderArchiveList(data.entries || []);
    } catch (err) {
      console.warn('Archive list error:', err);
    }
  }

  function renderArchiveList(entries) {
    if (!entries.length) {
      el.archiveList.innerHTML = `<div class="archive-empty">No matching folios found.</div>`;
      return;
    }
    el.archiveList.innerHTML = entries
      .map((entry) => {
        const active = entry.date === state.currentDate ? 'active' : '';
        return `
          <button type="button" class="archive-item ${active}" data-date="${escapeHtml(entry.date)}">
            <div class="archive-item-top">
              <span class="archive-item-date">${escapeHtml(formatShortArchiveDate(entry.date))}</span>
              <span class="archive-item-words">${entry.word_count || 0}w</span>
            </div>
            <p class="archive-item-preview">${escapeHtml(entry.preview || 'Blank folio')}</p>
          </button>
        `;
      })
      .join('');

    el.archiveList.querySelectorAll('.archive-item').forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetDate = btn.dataset.date;
        if (targetDate && targetDate !== state.currentDate) {
          switchDate(targetDate);
        }
      });
    });
  }

  async function flushPendingJournalSave() {
    if (state.saveTimer) {
      clearTimeout(state.saveTimer);
      state.saveTimer = null;
    }
    if (state.journalDirty) {
      await saveCurrentJournal();
    }
  }

  async function switchDate(dateKey, { syncOracle = true } = {}) {
    await flushPendingJournalSave();
    state.currentDate = dateKey;
    el.folioHumanDate.textContent = formatHumanDate(dateKey);
    el.folioFileTag.textContent = `${dateKey}.md`;
    el.btnReturnToday.classList.toggle('hidden', dateKey === state.todayKey);

    // Highlight active item in sidebar
    el.archiveList.querySelectorAll('.archive-item').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.date === dateKey);
    });

    await loadJournalEntry(dateKey);
    if (syncOracle && !state.streaming) {
      await loadOracleForDate(dateKey);
    }
  }

  async function loadJournalEntry(dateKey) {
    try {
      const res = await fetch(`/api/journal/${encodeURIComponent(dateKey)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const entry = await res.json();
      state.journalDirty = false;
      state.lastSavedContent = entry.content || '';
      el.journalEditor.value = state.lastSavedContent;
      updateWordCountAndPreview();

      if (entry.exists && entry.updated_at) {
        setSaveStatus(`Inscribed · ${formatTimeHHMM(entry.updated_at)}`);
      } else {
        setSaveStatus('Unwritten folio');
      }
    } catch (err) {
      setSaveStatus('Read error', 'error');
    }
  }

  function setSaveStatus(text, variant = '') {
    el.folioSaveStatus.textContent = text;
    el.folioSaveStatus.classList.remove('saving', 'error');
    if (variant) el.folioSaveStatus.classList.add(variant);
  }

  function updateWordCountAndPreview() {
    const text = el.journalEditor.value;
    const wc = countWords(text);
    el.folioWordCount.textContent = `${wc.toLocaleString()} ${wc === 1 ? 'word' : 'words'}`;
    if (state.editorMode === 'preview') {
      el.journalPreview.innerHTML = text.trim()
        ? renderMarkdown(text)
        : '<p><em>This folio awaits ink…</em></p>';
    }
  }

  async function saveCurrentJournal() {
    const dateKey = state.currentDate;
    const content = el.journalEditor.value;
    if (!state.journalDirty && content === state.lastSavedContent) return;

    setSaveStatus('Inscribing…', 'saving');
    try {
      const res = await fetch(`/api/journal/${encodeURIComponent(dateKey)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const saved = await res.json();
      state.lastSavedContent = content;
      state.journalDirty = false;
      if (saved.exists) {
        setSaveStatus(`Inscribed · ${formatTimeHHMM(saved.updated_at)}`);
      } else {
        setSaveStatus('Unwritten folio');
      }
      loadArchiveList(el.archiveSearch.value.trim());
    } catch (err) {
      setSaveStatus('Save failed', 'error');
    }
  }

  function setEditorMode(mode) {
    state.editorMode = mode;
    const isPreview = mode === 'preview';
    el.btnModeWrite.classList.toggle('active', !isPreview);
    el.btnModePreview.classList.toggle('active', isPreview);
    el.journalEditor.classList.toggle('hidden', isPreview);
    el.journalPreview.classList.toggle('hidden', !isPreview);
    if (isPreview) {
      updateWordCountAndPreview();
    } else {
      el.journalEditor.focus();
    }
  }

  async function inscribePassageToJournal(fullText, sourceLabel = 'The Pythia') {
    await flushPendingJournalSave();

    // If user highlighted specific text inside the Chasm, offer that exact selection!
    let chosenText = (fullText || '').trim();
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) {
      const selText = sel.toString().trim();
      if (selText && el.chasmScroll.contains(sel.anchorNode)) {
        chosenText = selText;
      }
    }
    if (!chosenText) return;

    const spreadSummary = buildCompactSpreadLabel(state.activeSession?.spread);
    try {
      const res = await fetch(`/api/journal/${encodeURIComponent(state.currentDate)}/inscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: chosenText,
          source: sourceLabel,
          spread_summary: spreadSummary || null,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const updated = await res.json();
      state.lastSavedContent = updated.content || '';
      state.journalDirty = false;
      el.journalEditor.value = state.lastSavedContent;
      updateWordCountAndPreview();
      setSaveStatus(`Inscribed · ${formatTimeHHMM(updated.updated_at)}`);
      loadArchiveList(el.archiveSearch.value.trim());
      showToast(`Inscribed to ${state.currentDate}.md`);
    } catch (err) {
      showToast('Failed to inscribe passage');
    }
  }

  // -------------------------------------------------------------------------
  // Oracle Sessions & Talismans Rendering
  // -------------------------------------------------------------------------
  async function refreshSessionDropdown() {
    try {
      const res = await fetch('/api/oracle/sessions?limit=50');
      if (!res.ok) return;
      const data = await res.json();
      state.sessions = data.sessions || [];
      renderSessionDropdown();
    } catch (err) {
      console.warn('Oracle sessions list error:', err);
    }
  }

  function renderSessionDropdown() {
    const activeId = getSessionId(state.activeSession);
    const options = [`<option value="">New Rite (${escapeHtml(state.currentDate)})</option>`];
    for (const s of state.sessions) {
      const sid = getSessionId(s);
      const dateTag = s.date_key || s.date || '';
      const title = s.title || 'Oracle Consultation';
      const selected = sid && sid === activeId ? 'selected' : '';
      options.push(
        `<option value="${escapeHtml(sid)}" ${selected}>${escapeHtml(dateTag)} — ${escapeHtml(title)}</option>`
      );
    }
    el.sessionSelect.innerHTML = options.join('');
  }

  function getSessionId(session) {
    if (!session) return '';
    return session.id || session.session_id || '';
  }

  async function loadOracleForDate(dateKey) {
    try {
      const res = await fetch(`/api/oracle/by-date/${encodeURIComponent(dateKey)}`);
      if (!res.ok) {
        showAltarEmptyState();
        return;
      }
      const data = await res.json();
      await refreshSessionDropdown();
      if (data.session && (data.session.spread || data.session.omen_markdown)) {
        renderSessionState(data.session, { animateFlip: false });
      } else {
        state.activeSession = null;
        renderSessionDropdown();
        showAltarEmptyState();
      }
    } catch (err) {
      showAltarEmptyState();
    }
  }

  async function loadOracleSessionById(sessionId) {
    if (!sessionId) {
      state.activeSession = null;
      showAltarEmptyState();
      return;
    }
    try {
      const res = await fetch(`/api/oracle/sessions/${encodeURIComponent(sessionId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const session = await res.json();
      if (session.spread || session.omen_markdown || (session.messages && session.messages.length)) {
        renderSessionState(session, { animateFlip: false });
      } else {
        state.activeSession = session;
        showAltarEmptyState();
      }
    } catch (err) {
      showToast('Could not load Oracle thread');
    }
  }

  function showAltarEmptyState() {
    el.chasmAltar.classList.remove('hidden');
    el.chasmReading.classList.add('hidden');
    el.chasmComposer.classList.add('hidden');
    el.btnDeleteSession.classList.add('hidden');
    el.chasmErrorBox.classList.add('hidden');
  }

  function renderSessionState(session, { animateFlip = false } = {}) {
    state.activeSession = session;
    renderSessionDropdown();

    el.chasmAltar.classList.add('hidden');
    el.chasmReading.classList.remove('hidden');
    el.btnDeleteSession.classList.toggle('hidden', !getSessionId(session));
    el.chasmErrorBox.classList.add('hidden');
    el.ritualBanner.classList.add('hidden');

    // Render Talismans
    if (session.spread) {
      renderTalismans(session.spread, {
        smokePacket: session.smoke_packet || '',
        entrailsSummary: session.entrails_summary || {},
        animateFlip,
      });
    } else {
      el.talismansSection.classList.add('hidden');
    }

    // Render Daily Omen
    if (session.omen_markdown) {
      el.omenVessel.classList.remove('hidden');
      const q = session.entrails_summary?.question || session.question || '';
      if (q) {
        el.omenQuestionEpigraph.textContent = `“${q}”`;
        el.omenQuestionEpigraph.classList.remove('hidden');
      } else {
        el.omenQuestionEpigraph.classList.add('hidden');
      }
      el.omenBody.innerHTML = renderMarkdown(session.omen_markdown);
    } else {
      el.omenVessel.classList.add('hidden');
    }

    // Render Chat Messages
    renderChatMessages(session.messages || []);
    el.chasmComposer.classList.remove('hidden');
  }

  function buildCompactSpreadLabel(spread) {
    if (!spread) return '';
    const parts = [];
    if (Array.isArray(spread.cards) && spread.cards.length) {
      parts.push(spread.cards.map((c) => c.name).join(' / '));
    }
    if (spread.iching?.primary?.number) {
      parts.push(`Hex ${spread.iching.primary.number}`);
    }
    if (Array.isArray(spread.runes) && spread.runes[0]?.name) {
      parts.push(spread.runes[0].name);
    }
    return parts.join(' · ');
  }

  // -------------------------------------------------------------------------
  // SVG I Ching Hexagram, Thoth Cards & Elder Futhark Rune Builders
  // -------------------------------------------------------------------------
  function buildHexagramSvg(lines, { mini = false } = {}) {
    if (!Array.isArray(lines) || lines.length !== 6) return '';
    // Traditional lines array: index 0 is bottom Line 1, index 5 is top Line 6.
    const w = 100;
    const h = 84;
    const barH = 6.5;
    const gapCenter = 18;
    const rowStep = 13;
    const rects = [];

    const glowId = mini ? 'oxblood-glow-mini' : 'oxblood-glow-main';

    for (let idx = 5; idx >= 0; idx -= 1) {
      const val = Number(lines[idx]);
      const visualRow = 5 - idx;
      const y = 6 + visualRow * rowStep;
      const isMoving = val === 6 || val === 9;
      const isYang = val === 7 || val === 9 || val === 1;
      const color = isMoving ? '#C84B5F' : '#CCA962';
      const glowAttr = isMoving ? `filter="url(#${glowId})"` : '';

      if (isYang) {
        rects.push(`<rect x="6" y="${y}" width="78" height="${barH}" rx="1" fill="${color}" ${glowAttr} />`);
      } else {
        const segW = (78 - gapCenter) / 2;
        rects.push(`<rect x="6" y="${y}" width="${segW}" height="${barH}" rx="1" fill="${color}" ${glowAttr} />`);
        rects.push(`<rect x="${6 + segW + gapCenter}" y="${y}" width="${segW}" height="${barH}" rx="1" fill="${color}" ${glowAttr} />`);
      }

      if (!mini && isMoving) {
        const mark = val === 9 ? '○' : '×';
        rects.push(
          `<text x="92" y="${y + 5.8}" text-anchor="middle" fill="#C84B5F" font-family="JetBrains Mono, monospace" font-size="9">${mark}</text>`
        );
      }
    }

    return `
      <svg class="hexagram-svg ${mini ? 'mini' : ''}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
        <defs>
          <filter id="${glowId}" x="-25%" y="-40%" width="150%" height="180%">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        ${rects.join('')}
      </svg>
    `;
  }

  function deriveTransformedLines(lines) {
    if (!Array.isArray(lines) || lines.length !== 6) return null;
    return lines.map((v) => {
      if (v === 9) return 8;
      if (v === 6) return 7;
      return v;
    });
  }

  function renderTalismans(spread, { smokePacket = '', entrailsSummary = {}, animateFlip = false } = {}) {
    el.talismansSection.classList.remove('hidden');
    const mode = spread.mode || 'daily';
    el.talismanModeBadge.textContent = mode === 'trinity' ? 'THOTH TRINITY' : 'DAILY RITE';
    const entropyHex = spread.entropy_hex || spread.iching?.entropy_hex || '';
    el.entropyStamp.textContent = entropyHex
      ? `0x${String(entropyHex).replace(/^0x/, '').slice(0, 12)}`
      : '0x—';

    const quietCount = entrailsSummary?.quiet_count ?? 0;
    el.quietCountPill.textContent = `${quietCount} [quiet]`;
    el.smokePacketPre.textContent = smokePacket || 'Distilling ritual smoke…';

    const hMeta = entrailsSummary?.haruspex || {};
    const metaBits = [];
    if (hMeta.model) metaBits.push(hMeta.model);
    if (hMeta.duration_ms != null) metaBits.push(`${hMeta.duration_ms}ms`);
    el.entrailsModelMeta.textContent = metaBits.join(' · ');

    const alcoves = [];
    const trinityPositions = ['I · Root', 'II · Crux', 'III · Vector'];

    // 1. Thoth Cards
    (spread.cards || []).forEach((card, idx) => {
      const posLabel = mode === 'trinity' ? trinityPositions[idx] || `Card ${idx + 1}` : (card.arcana === 'major' ? `ATU ${card.number ?? ''}` : card.suit || 'THOTH');
      const kw = Array.isArray(card.keywords) ? card.keywords.join(' · ') : (card.keywords || '');
      alcoves.push(`
        <div class="talisman-alcove ${animateFlip ? 'flipping' : ''}" data-delay="${idx * 130}">
          <div class="talisman-flipper">
            <div class="talisman-back"></div>
            <div class="talisman-face">
              <div class="talisman-top-row">
                <span>${escapeHtml(posLabel)}</span>
                <span>${escapeHtml(card.attribution || card.element || '')}</span>
              </div>
              <div class="talisman-center">
                <h3 class="talisman-name">${escapeHtml(card.name || 'Thoth')}</h3>
                ${card.title ? `<p class="talisman-subtitle">${escapeHtml(card.title)}</p>` : ''}
                ${kw ? `<div class="talisman-keywords">${escapeHtml(kw)}</div>` : ''}
              </div>
              ${card.shadow ? `<div class="talisman-shadow">Shadow: ${escapeHtml(card.shadow)}</div>` : '<div></div>'}
            </div>
          </div>
        </div>
      `);
    });

    // 2. I Ching Hexagram
    if (spread.iching && spread.iching.primary) {
      const ich = spread.iching;
      const prim = ich.primary;
      const trans = ich.transformed;
      const transLines = trans ? (trans.lines || deriveTransformedLines(ich.lines)) : null;
      const movingStr = Array.isArray(ich.moving_lines) && ich.moving_lines.length
        ? `Lines ${ich.moving_lines.join(', ')}`
        : 'Unchanging';

      alcoves.push(`
        <div class="talisman-alcove ${animateFlip ? 'flipping' : ''}" data-delay="140">
          <div class="talisman-flipper">
            <div class="talisman-back"></div>
            <div class="talisman-face">
              <div class="talisman-top-row">
                <span>HEXAGRAM ${escapeHtml(prim.number)}</span>
                <span>${escapeHtml(movingStr)}</span>
              </div>
              <div class="talisman-center">
                <div class="hexagram-stage">
                  ${buildHexagramSvg(ich.lines)}
                  ${trans ? `<span class="hex-mutate-arrow">⟶</span>${buildHexagramSvg(transLines, { mini: true })}` : ''}
                </div>
                <h3 class="talisman-name">${escapeHtml(prim.name)} ${prim.chinese ? `<span>${escapeHtml(prim.chinese)}</span>` : ''}</h3>
                <p class="talisman-subtitle">${trans ? `Mutates ⟶ #${escapeHtml(trans.number)} ${escapeHtml(trans.name)}` : `${escapeHtml(prim.upper_trigram || '')} over ${escapeHtml(prim.lower_trigram || '')}`}</p>
              </div>
              <div class="talisman-keywords">${escapeHtml(prim.judgment || prim.image || '')}</div>
            </div>
          </div>
        </div>
      `);
    }

    // 3. Elder Futhark Rune
    (spread.runes || []).forEach((rune) => {
      const orient = String(rune.orientation || 'brightstave').toLowerCase();
      const isMerk = orient.includes('merk') || orient.includes('rev') || orient.includes('inv');
      const kw = Array.isArray(rune.keywords) ? rune.keywords.join(' · ') : (rune.keywords || '');
      alcoves.push(`
        <div class="talisman-alcove ${animateFlip ? 'flipping' : ''}" data-delay="280">
          <div class="talisman-flipper">
            <div class="talisman-back"></div>
            <div class="talisman-face">
              <div class="talisman-top-row">
                <span>${escapeHtml(rune.aett ? `${rune.aett} Aett` : 'ELDER FUTHARK')}</span>
                <span class="orientation-tag ${isMerk ? 'merkstave' : ''}">${isMerk ? 'Merkstave' : 'Brightstave'}</span>
              </div>
              <div class="talisman-center">
                <div class="rune-glyph-wrap">
                  <span class="rune-glyph ${isMerk ? 'merkstave' : ''}">${escapeHtml(rune.glyph || 'ᛉ')}</span>
                </div>
                <h3 class="talisman-name">${escapeHtml(rune.name)}</h3>
                ${rune.phoneme ? `<p class="talisman-subtitle">Phoneme: ${escapeHtml(rune.phoneme)}</p>` : ''}
                ${kw ? `<div class="talisman-keywords">${escapeHtml(kw)}</div>` : ''}
              </div>
              ${rune.essence ? `<div class="talisman-shadow">${escapeHtml(rune.essence)}</div>` : '<div></div>'}
            </div>
          </div>
        </div>
      `);
    });

    el.talismansGrid.innerHTML = alcoves.join('');

    if (animateFlip) {
      el.talismansGrid.querySelectorAll('.talisman-alcove.flipping').forEach((node) => {
        const delay = Number(node.dataset.delay || 0);
        setTimeout(() => {
          node.classList.remove('flipping');
        }, 60 + delay);
      });
    }
  }

  function renderExtraCastBadge(castData) {
    if (!castData) return '';
    if (Array.isArray(castData.cards) && castData.cards[0]) {
      const c = castData.cards[0];
      return `<div class="inline-extra-cast"><span>🂠 Thoth Draw:</span> <strong>${escapeHtml(c.name)}</strong> ${c.title ? `<em>(${escapeHtml(c.title)})</em>` : ''}</div>`;
    }
    if (Array.isArray(castData.runes) && castData.runes[0]) {
      const r = castData.runes[0];
      const orient = String(r.orientation || '').toLowerCase();
      const isMerk = orient.includes('merk') || orient.includes('rev');
      return `<div class="inline-extra-cast"><span style="display:inline-block;${isMerk ? 'transform:rotate(180deg);color:#C84B5F' : ''}">${escapeHtml(r.glyph || 'ᛉ')}</span> <strong>${escapeHtml(r.name)}</strong> <em>(${isMerk ? 'Merkstave' : 'Brightstave'})</em></div>`;
    }
    if (castData.iching && castData.iching.primary) {
      const p = castData.iching.primary;
      return `<div class="inline-extra-cast"><span>☰ Yarrow Draw:</span> <strong>Hexagram ${escapeHtml(p.number)} · ${escapeHtml(p.name)}</strong></div>`;
    }
    return '';
  }

  function renderChatMessages(messages) {
    el.chatThread.innerHTML = (messages || [])
      .map((msg, idx) => {
        const isUser = msg.role === 'user';
        if (isUser) {
          return `
            <div class="chat-msg user">
              <div class="chat-msg-head">
                <span class="chat-role-label">INQUIRY</span>
              </div>
              ${renderExtraCastBadge(msg.cast_data)}
              <div class="prose-symbolist">${renderMarkdown(msg.content || '')}</div>
            </div>
          `;
        }
        return `
          <div class="chat-msg assistant" data-msg-idx="${idx}">
            <div class="chat-msg-head">
              <span class="chat-role-label">THE PYTHIA</span>
              <button type="button" class="inscribe-btn btn-inscribe-msg" data-idx="${idx}">✒ Inscribe to Page</button>
            </div>
            <div class="prose-symbolist">${renderMarkdown(msg.content || '')}</div>
          </div>
        `;
      })
      .join('');

    el.chatThread.querySelectorAll('.btn-inscribe-msg').forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = Number(btn.dataset.idx);
        const msg = (state.activeSession?.messages || [])[idx];
        if (msg && msg.content) {
          inscribePassageToJournal(msg.content, 'Pythia Dialogue');
        }
      });
    });
  }

  // -------------------------------------------------------------------------
  // SSE Stream Reader Helper
  // -------------------------------------------------------------------------
  async function consumeSseStream(response, onEvent) {
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sepIdx;
      while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
        const rawBlock = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        for (const line of rawBlock.split('\n')) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data:')) {
            const jsonStr = trimmed.slice(5).trim();
            if (jsonStr) {
              try {
                const evt = JSON.parse(jsonStr);
                onEvent(evt);
              } catch (parseErr) {
                console.warn('SSE JSON parse warning:', parseErr);
              }
            }
          }
        }
      }
    }
  }

  // -------------------------------------------------------------------------
  // Consult the Chasm (Omen SSE)
  // -------------------------------------------------------------------------
  async function consultTheChasm({ forceNew = false } = {}) {
    if (state.streaming) return;
    state.streaming = true;
    el.btnConsultChasm.disabled = true;
    el.btnSendChat.disabled = true;
    el.chasmErrorBox.classList.add('hidden');

    const question = el.fissureQuestion.value.trim();
    el.chasmAltar.classList.add('hidden');
    el.chasmReading.classList.remove('hidden');
    el.ritualBanner.classList.remove('hidden');
    el.talismansSection.classList.add('hidden');
    el.omenVessel.classList.add('hidden');
    el.chatThread.innerHTML = '';
    el.chasmComposer.classList.add('hidden');

    if (question) {
      el.omenQuestionEpigraph.textContent = `“${question}”`;
      el.omenQuestionEpigraph.classList.remove('hidden');
    } else {
      el.omenQuestionEpigraph.classList.add('hidden');
    }

    let streamedOmen = '';
    let currentSpread = null;
    let quietCount = 0;
    let smokePacket = '';

    try {
      const res = await fetch('/api/oracle/omen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date_key: state.currentDate,
          spread_mode: state.spreadMode,
          question: question || null,
          force_new: forceNew,
        }),
      });

      await consumeSseStream(res, (evt) => {
        if (evt.event === 'stage') {
          el.ritualBanner.classList.remove('hidden');
          el.ritualStageCode.textContent = String(evt.stage || 'RITUAL').trim().toUpperCase();
          el.ritualStageLabel.textContent = evt.label || '';
          if (evt.stage && evt.stage.trim() === 'awakening') {
            applyVesselStatus({ state: 'loading', detail: evt.label });
          }
        } else if (evt.event === 'spread') {
          currentSpread = evt.spread;
          state.activeSession = {
            id: evt.session_id,
            date_key: state.currentDate,
            spread: currentSpread,
          };
          renderTalismans(currentSpread, { animateFlip: true });
        } else if (evt.event === 'smoke') {
          smokePacket = evt.smoke_packet || '';
          quietCount = evt.quiet_count ?? 0;
          el.quietCountPill.textContent = `${quietCount} [quiet]`;
          el.smokePacketPre.textContent = smokePacket;
          if (evt.haruspex) {
            const bits = [evt.haruspex.model, evt.haruspex.duration_ms != null ? `${evt.haruspex.duration_ms}ms` : ''].filter(Boolean);
            el.entrailsModelMeta.textContent = bits.join(' · ');
          }
        } else if (evt.event === 'delta') {
          el.omenVessel.classList.remove('hidden');
          streamedOmen += evt.text || '';
          el.omenBody.innerHTML = renderMarkdown(streamedOmen);
        } else if (evt.event === 'done') {
          el.ritualBanner.classList.add('hidden');
          if (evt.session) {
            renderSessionState(evt.session, { animateFlip: false });
          }
          el.fissureQuestion.value = '';
          refreshSessionDropdown();
          refreshTelemetry();
        } else if (evt.event === 'error') {
          el.ritualBanner.classList.add('hidden');
          el.chasmErrorBox.textContent = `Ritual interrupted: ${evt.message || 'Unknown error'}`;
          el.chasmErrorBox.classList.remove('hidden');
        }
      });
    } catch (err) {
      el.ritualBanner.classList.add('hidden');
      el.chasmErrorBox.textContent = `Could not reach the Chasm: ${err.message || err}`;
      el.chasmErrorBox.classList.remove('hidden');
    } finally {
      state.streaming = false;
      el.btnConsultChasm.disabled = false;
      el.btnSendChat.disabled = false;
    }
  }

  // -------------------------------------------------------------------------
  // Converse with the Pythia (Chat SSE)
  // -------------------------------------------------------------------------
  async function sendChatMessage() {
    if (state.streaming) return;
    const sessionId = getSessionId(state.activeSession);
    if (!sessionId) return;

    const message = el.chatInput.value.trim();
    const castExtra = state.selectedExtraCast;
    if (!message && !castExtra) return;

    state.streaming = true;
    el.btnSendChat.disabled = true;
    el.chasmErrorBox.classList.add('hidden');

    const displayMsg = message || `Interpret this ${castExtra} drawn into our thread.`;
    el.chatInput.value = '';
    autoResizeChatInput();
    clearExtraCastChips();

    // Optimistic user turn + live assistant vessel
    const userNode = document.createElement('div');
    userNode.className = 'chat-msg user';
    userNode.innerHTML = `
      <div class="chat-msg-head"><span class="chat-role-label">INQUIRY</span></div>
      <div class="user-extra-slot"></div>
      <div class="prose-symbolist">${renderMarkdown(displayMsg)}</div>
    `;
    el.chatThread.appendChild(userNode);

    const assistantNode = document.createElement('div');
    assistantNode.className = 'chat-msg assistant';
    assistantNode.innerHTML = `
      <div class="chat-msg-head"><span class="chat-role-label">THE PYTHIA</span></div>
      <div class="prose-symbolist live-reply"><em>Listening through the vapors…</em></div>
    `;
    el.chatThread.appendChild(assistantNode);
    const liveReplyBody = assistantNode.querySelector('.live-reply');
    el.chasmScroll.scrollTop = el.chasmScroll.scrollHeight;

    let streamedReply = '';

    try {
      const res = await fetch(`/api/oracle/sessions/${encodeURIComponent(sessionId)}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: displayMsg,
          cast_extra: castExtra,
        }),
      });

      await consumeSseStream(res, (evt) => {
        if (evt.event === 'stage') {
          el.ritualBanner.classList.remove('hidden');
          el.ritualStageCode.textContent = String(evt.stage || 'PYTHIA').toUpperCase();
          el.ritualStageLabel.textContent = evt.label || '';
        } else if (evt.event === 'extra_cast') {
          const slot = userNode.querySelector('.user-extra-slot');
          if (slot) slot.innerHTML = renderExtraCastBadge(evt.cast);
        } else if (evt.event === 'delta') {
          streamedReply += evt.text || '';
          liveReplyBody.innerHTML = renderMarkdown(streamedReply);
          el.chasmScroll.scrollTop = el.chasmScroll.scrollHeight;
        } else if (evt.event === 'done') {
          el.ritualBanner.classList.add('hidden');
          if (evt.session) {
            state.activeSession = evt.session;
            renderChatMessages(evt.session.messages || []);
          }
          refreshTelemetry();
        } else if (evt.event === 'error') {
          el.ritualBanner.classList.add('hidden');
          el.chasmErrorBox.textContent = `Pythia stream error: ${evt.message || 'Unknown error'}`;
          el.chasmErrorBox.classList.remove('hidden');
        }
      });
    } catch (err) {
      el.ritualBanner.classList.add('hidden');
      el.chasmErrorBox.textContent = `Connection lost: ${err.message || err}`;
      el.chasmErrorBox.classList.remove('hidden');
    } finally {
      state.streaming = false;
      el.btnSendChat.disabled = false;
      el.chatInput.focus();
    }
  }

  function clearExtraCastChips() {
    state.selectedExtraCast = null;
    document.querySelectorAll('.cast-chip').forEach((c) => c.classList.remove('active'));
  }

  function autoResizeChatInput() {
    el.chatInput.style.height = 'auto';
    el.chatInput.style.height = `${Math.min(el.chatInput.scrollHeight, 130)}px`;
  }

  // -------------------------------------------------------------------------
  // Layout Toggles & Event Listeners
  // -------------------------------------------------------------------------
  function applyLayoutState() {
    el.archiveSidebar.classList.toggle('collapsed', state.archiveCollapsed);
    el.workspace.classList.toggle('chasm-collapsed', state.chasmCollapsed);
  }

  function toggleArchive() {
    state.archiveCollapsed = !state.archiveCollapsed;
    localStorage.setItem('grimoire.archiveCollapsed', state.archiveCollapsed ? '1' : '0');
    applyLayoutState();
  }

  function toggleChasm() {
    state.chasmCollapsed = !state.chasmCollapsed;
    localStorage.setItem('grimoire.chasmCollapsed', state.chasmCollapsed ? '1' : '0');
    applyLayoutState();
  }

  function bindEvents() {
    el.btnToggleArchive.addEventListener('click', toggleArchive);
    el.btnToggleChasm.addEventListener('click', toggleChasm);
    el.btnVesselToggle.addEventListener('click', handleVesselButtonClick);

    // Date navigation
    el.btnPrevDay.addEventListener('click', () => switchDate(shiftIsoDate(state.currentDate, -1)));
    el.btnNextDay.addEventListener('click', () => switchDate(shiftIsoDate(state.currentDate, 1)));
    el.btnJumpToday.addEventListener('click', () => switchDate(state.todayKey));
    el.btnReturnToday.addEventListener('click', () => switchDate(state.todayKey));

    // Archive search
    el.archiveSearch.addEventListener('input', () => {
      clearTimeout(state.searchTimer);
      state.searchTimer = setTimeout(() => {
        loadArchiveList(el.archiveSearch.value.trim());
      }, 220);
    });

    // Editor typing & auto-save (900ms debounce)
    el.journalEditor.addEventListener('input', () => {
      state.journalDirty = true;
      updateWordCountAndPreview();
      setSaveStatus('Unsaved ink…', 'saving');
      clearTimeout(state.saveTimer);
      state.saveTimer = setTimeout(() => {
        saveCurrentJournal();
      }, 900);
    });

    el.btnModeWrite.addEventListener('click', () => setEditorMode('write'));
    el.btnModePreview.addEventListener('click', () => setEditorMode('preview'));

    // Spread mode selector
    [el.spreadOptDaily, el.spreadOptTrinity].forEach((btn) => {
      btn.addEventListener('click', () => {
        state.spreadMode = btn.dataset.mode;
        el.spreadOptDaily.classList.toggle('active', state.spreadMode === 'daily');
        el.spreadOptTrinity.classList.toggle('active', state.spreadMode === 'trinity');
      });
    });

    // Consult Chasm
    el.btnConsultChasm.addEventListener('click', () => {
      const forceNew = Boolean(state.activeSession && (state.activeSession.omen_markdown || state.activeSession._forceNew));
      consultTheChasm({ forceNew });
    });
    el.fissureQuestion.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const forceNew = Boolean(state.activeSession && (state.activeSession.omen_markdown || state.activeSession._forceNew));
        consultTheChasm({ forceNew });
      }
    });

    // Session picker & + New Ritual Thread
    el.sessionSelect.addEventListener('change', () => {
      const sid = el.sessionSelect.value;
      if (!sid) {
        state.activeSession = null;
        showAltarEmptyState();
      } else {
        loadOracleSessionById(sid);
      }
    });

    el.btnNewRitual.addEventListener('click', () => {
      if (state.streaming) return;
      // Keep reference that we want a fresh thread on cast
      state.activeSession = { _forceNew: true };
      el.sessionSelect.value = '';
      showAltarEmptyState();
      el.fissureQuestion.focus();
    });

    el.btnDeleteSession.addEventListener('click', async () => {
      const sid = getSessionId(state.activeSession);
      if (!sid || state.streaming) return;
      if (!window.confirm('Dissolve this Oracle thread from the archive?')) return;
      try {
        await fetch(`/api/oracle/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
        state.activeSession = null;
        await refreshSessionDropdown();
        showAltarEmptyState();
        showToast('Ritual thread dissolved');
      } catch (err) {
        showToast('Delete failed');
      }
    });

    // Entrails smoke drawer toggle
    el.btnToggleEntrails.addEventListener('click', () => {
      const hidden = el.entrailsDrawer.classList.toggle('hidden');
      el.btnToggleEntrails.setAttribute('aria-expanded', String(!hidden));
    });

    // Inscribe Daily Omen
    el.btnInscribeOmen.addEventListener('click', () => {
      const omenMd = state.activeSession?.omen_markdown;
      if (omenMd) {
        inscribePassageToJournal(omenMd, 'Daily Omen');
      }
    });

    // Quick-cast talisman chips
    document.querySelectorAll('.cast-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const type = chip.dataset.cast;
        if (state.selectedExtraCast === type) {
          clearExtraCastChips();
        } else {
          clearExtraCastChips();
          state.selectedExtraCast = type;
          chip.classList.add('active');
        }
      });
    });

    // Chat composer
    el.chatInput.addEventListener('input', autoResizeChatInput);
    el.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
    el.btnSendChat.addEventListener('click', sendChatMessage);

    // Global keyboard shortcuts
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        flushPendingJournalSave().then(() => {
          if (el.journalEditor.value.trim()) showToast('Folio inscribed');
        });
      } else if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
        e.preventDefault();
        toggleChasm();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'e') {
        e.preventDefault();
        setEditorMode(state.editorMode === 'write' ? 'preview' : 'write');
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b' && document.activeElement !== el.journalEditor) {
        e.preventDefault();
        toggleArchive();
      } else if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault();
        switchDate(shiftIsoDate(state.currentDate, -1));
      } else if (e.altKey && e.key === 'ArrowRight') {
        e.preventDefault();
        switchDate(shiftIsoDate(state.currentDate, 1));
      }
    });

    // Save before unload if dirty
    window.addEventListener('beforeunload', () => {
      if (state.journalDirty) {
        navigator.sendBeacon?.(
          `/api/journal/${encodeURIComponent(state.currentDate)}`,
          new Blob([JSON.stringify({ content: el.journalEditor.value })], { type: 'application/json' })
        );
      }
    });
  }

  // -------------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------------
  async function init() {
    applyLayoutState();
    bindEvents();
    el.folioHumanDate.textContent = formatHumanDate(state.currentDate);
    el.folioFileTag.textContent = `${state.currentDate}.md`;

    await Promise.all([
      refreshTelemetry(),
      loadArchiveList(),
      loadJournalEntry(state.currentDate),
      loadOracleForDate(state.currentDate),
    ]);

    // Refresh top brass telemetry every 30s
    setInterval(refreshTelemetry, 30000);
  }

  init();
})();
