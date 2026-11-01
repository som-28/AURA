const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { runs: [], tools: [], profile: null, file: null, page: 'home' };

const icons = {
  spark: '<path d="m12 2 1.7 6.3L20 10l-6.3 1.7L12 18l-1.7-6.3L4 10l6.3-1.7L12 2Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/>',
  'spark-small': '<path d="m12 2 1.5 6.5L20 10l-6.5 1.5L12 18l-1.5-6.5L4 10l6.5-1.5L12 2Z"/>',
  person: '<circle cx="12" cy="8" r="3.4"/><path d="M5 20c.4-3.5 2.8-5.4 7-5.4s6.6 1.9 7 5.4"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.3 2"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  chart: '<path d="M4 19V5M4 19h17"/><path d="m7 15 4-4 3 2 5-6"/><path d="M16 7h3v3"/>',
  shield: '<path d="M12 3 19 6v5.2c0 4.5-2.7 7.5-7 9.8-4.3-2.3-7-5.3-7-9.8V6l7-3Z"/><path d="m9 12 2 2 4-4"/>',
  route: '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h4a3 3 0 0 1 3 3v3a3 3 0 0 0 3 3"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m4 7 8 6 8-6"/>',
  chevron: '<path d="m7 10 5 5 5-5"/>',
  arrow: '<path d="M4 12h15M13 6l6 6-6 6"/>',
  'arrow-right': '<path d="M4 12h15M13 6l6 6-6 6"/>',
  'arrow-up-right': '<path d="M7 17 17 7M8 7h9v9"/>',
  briefcase: '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v2h4v-2"/>',
  orbit: '<circle cx="12" cy="12" r="2.2"/><ellipse cx="12" cy="12" rx="9" ry="4.5" transform="rotate(-35 12 12)"/><circle cx="5" cy="7" r="1"/>',
  doc: '<path d="M6 3.5h8l4 4V20a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1Z"/><path d="M14 3.5v5h4M8 13h8M8 16h8"/>',
  upload: '<path d="M12 15V4m0 0L8 8m4-4 4 4"/><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/>',
  search: '<circle cx="10.8" cy="10.8" r="6.5"/><path d="m16 16 4.2 4.2"/>',
  refresh: '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.7 9A7 7 0 0 1 18 6.5L20 12M4 12l2 5.5A7 7 0 0 0 18.3 15"/>',
  check: '<path d="m5 12 4.3 4.3L19 6.8"/>',
};

function paintIcons(root = document) {
  $$('[data-icon]', root).forEach((el) => {
    const name = el.dataset.icon;
    const paths = icons[name];
    if (!paths) return;
    el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
  });
}
paintIcons();

const themeToggle = $('#theme-toggle');
function setTheme(dark, persist = false) {
  document.documentElement.classList.toggle('dark-mode', dark);
  const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
  themeToggle.setAttribute('aria-label', label);
  themeToggle.title = label;
  const modeLabel = $('.theme-mode-label');
  if (modeLabel) modeLabel.textContent = dark ? 'LIGHT MODE' : 'DARK MODE';
  if (persist) {
    try { localStorage.setItem('aura-theme', dark ? 'dark' : 'light'); } catch {}
  }
}
setTheme(document.documentElement.classList.contains('dark-mode'));
themeToggle.addEventListener('click', () => setTheme(!document.documentElement.classList.contains('dark-mode'), true));

const skyCanvas = $('#sky-canvas');
const skyContext = skyCanvas.getContext('2d', { alpha: true });
const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
let skyWidth = 0;
let skyHeight = 0;
let skyScale = 1;
let skyDust = [];
let skyTrails = [];
let skyFrameId = 0;
let skyLastFrame = 0;
let nextMeteorAt = 0;
const randomBetween = (min, max) => min + Math.random() * (max - min);

function resizeSky() {
  skyWidth = window.innerWidth;
  skyHeight = window.innerHeight;
  skyScale = Math.min(window.devicePixelRatio || 1, 1.5);
  skyCanvas.width = Math.round(skyWidth * skyScale);
  skyCanvas.height = Math.round(skyHeight * skyScale);
  skyContext.setTransform(skyScale, 0, 0, skyScale, 0, 0);
  const count = Math.min(96, Math.max(30, Math.round(skyWidth * skyHeight / 17000)));
  skyDust = Array.from({ length: count }, () => ({
    x: Math.random() * skyWidth,
    y: Math.random() * skyHeight,
    radius: randomBetween(.5, 1.35),
    alpha: randomBetween(.17, .44),
    phase: Math.random() * Math.PI * 2,
    drift: randomBetween(.003, .012),
  }));
  skyTrails = [];
  skyContext.clearRect(0, 0, skyWidth, skyHeight);
  if (motionPreference.matches) drawSky(0);
  else startSky();
}

function drawSky(time) {
  skyContext.clearRect(0, 0, skyWidth, skyHeight);
  const dark = document.documentElement.classList.contains('dark-mode');
  const rgb = dark ? '191,211,255' : '94,124,174';
  skyDust.forEach((star) => {
    const twinkle = motionPreference.matches ? 1 : .64 + Math.sin(time * .00065 + star.phase) * .24;
    skyContext.beginPath();
    skyContext.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
    skyContext.fillStyle = `rgba(${rgb},${star.alpha * twinkle})`;
    skyContext.fill();
  });
  skyTrails.forEach((trail) => {
    const progress = Math.min(1, (time - trail.born) / trail.duration);
    const fade = Math.sin(Math.PI * progress);
    const headX = trail.x;
    const headY = trail.y;
    const tailX = headX - trail.vx * trail.length;
    const tailY = headY - trail.vy * trail.length;
    const gradient = skyContext.createLinearGradient(headX, headY, tailX, tailY);
    gradient.addColorStop(0, `rgba(${rgb},${.85 * fade})`);
    gradient.addColorStop(.16, `rgba(${rgb},${.45 * fade})`);
    gradient.addColorStop(1, `rgba(${rgb},0)`);
    skyContext.beginPath();
    skyContext.moveTo(headX, headY);
    skyContext.lineTo(tailX, tailY);
    skyContext.strokeStyle = gradient;
    skyContext.lineWidth = 1.5;
    skyContext.lineCap = 'round';
    skyContext.stroke();
    skyContext.beginPath();
    skyContext.arc(headX, headY, 1.5, 0, Math.PI * 2);
    skyContext.fillStyle = `rgba(${rgb},${.75 * fade})`;
    skyContext.fill();
  });
}

function startSky() {
  if (skyFrameId || motionPreference.matches || document.hidden) return;
  skyLastFrame = 0;
  nextMeteorAt = performance.now() + randomBetween(350, 900);
  skyFrameId = requestAnimationFrame(animateSky);
}

function animateSky(time) {
  skyFrameId = 0;
  if (document.hidden || motionPreference.matches) return;
  const delta = Math.min(34, skyLastFrame ? time - skyLastFrame : 16);
  skyLastFrame = time;
  skyDust.forEach((star) => {
    star.y -= star.drift * delta;
    if (star.y < -2) { star.y = skyHeight + 2; star.x = Math.random() * skyWidth; }
  });
  skyTrails.forEach((trail) => { trail.x += trail.vx * delta; trail.y += trail.vy * delta; });
  skyTrails = skyTrails.filter((trail) => time - trail.born < trail.duration);
  if (time >= nextMeteorAt) {
    const speed = randomBetween(.34, .62);
    skyTrails.push({
      x: randomBetween(skyWidth * .12, skyWidth * .9), y: randomBetween(0, skyHeight * .48),
      vx: speed, vy: speed * randomBetween(.42, .76), length: randomBetween(105, 175),
      born: time, duration: randomBetween(650, 1050),
    });
    nextMeteorAt = time + randomBetween(1800, 3800);
  }
  drawSky(time);
  skyFrameId = requestAnimationFrame(animateSky);
}

function updateSkyMotion() {
  if (skyFrameId) cancelAnimationFrame(skyFrameId);
  skyFrameId = 0;
  if (motionPreference.matches) drawSky(0);
  else startSky();
}
window.addEventListener('resize', resizeSky, { passive: true });
document.addEventListener('visibilitychange', () => document.hidden ? (skyFrameId && cancelAnimationFrame(skyFrameId), skyFrameId = 0) : startSky());
motionPreference.addEventListener?.('change', updateSkyMotion);
resizeSky();

const dashboardSections = $$('.page');
if ('IntersectionObserver' in window && !motionPreference.matches) {
  const sectionObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.04 });
  document.documentElement.classList.add('motion-ready');
  dashboardSections.forEach((section, index) => {
    if (index === 0) section.classList.add('is-visible');
    else sectionObserver.observe(section);
  });
} else {
  dashboardSections.forEach((section) => section.classList.add('is-visible'));
}

const plannerPicker = $('#planner-picker');
const plannerTrigger = $('#planner-trigger');
const plannerMenu = $('#planner-menu');
const plannerSelect = $('#planner-select');
function setPlannerMenu(open, focusSelected = false) {
  plannerMenu.hidden = !open;
  plannerTrigger.setAttribute('aria-expanded', String(open));
  plannerPicker.classList.toggle('is-open', open);
  if (open && focusSelected) plannerMenu.querySelector('[aria-selected="true"]')?.focus();
}
function choosePlanner(option) {
  const value = option.dataset.value;
  plannerSelect.value = value;
  $('#planner-current').textContent = option.querySelector('.planner-option-title').textContent;
  $$('.planner-option', plannerMenu).forEach((item) => {
    const selected = item === option;
    item.classList.toggle('selected', selected);
    item.setAttribute('aria-selected', String(selected));
  });
  setPlannerMenu(false);
  plannerTrigger.focus();
}
plannerTrigger.addEventListener('click', () => { const open = plannerMenu.hidden; setPlannerMenu(open, open); });
$$('.planner-option', plannerMenu).forEach((option) => option.addEventListener('click', () => choosePlanner(option)));
plannerTrigger.addEventListener('keydown', (event) => {
  if (['ArrowDown', 'Enter', ' '].includes(event.key)) { event.preventDefault(); setPlannerMenu(true, true); }
});
plannerMenu.addEventListener('keydown', (event) => {
  const options = $$('.planner-option', plannerMenu);
  const index = options.indexOf(document.activeElement);
  if (event.key === 'Escape') { event.preventDefault(); setPlannerMenu(false); plannerTrigger.focus(); }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const offset = event.key === 'ArrowDown' ? 1 : -1;
    options[(index + offset + options.length) % options.length].focus();
  }
  if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); document.activeElement.click(); }
});
document.addEventListener('pointerdown', (event) => {
  if (!plannerPicker.contains(event.target)) setPlannerMenu(false);
});

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`);
  return data;
}

async function streamRun(body, onProgress) {
  const response = await fetch('/run/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed (${response.status})`);
  }
  if (!response.body) throw new Error('Live progress is unavailable in this browser.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      const type = block.match(/^event:\s*(.+)$/m)?.[1]?.trim();
      const data = block.match(/^data:\s*(.+)$/m)?.[1];
      if (!type || !data) continue;
      const payload = JSON.parse(data);
      if (type === 'progress') onProgress(payload);
      if (type === 'result') return payload;
      if (type === 'error') throw new Error(payload.message || 'The journey could not be completed.');
    }
    if (done) break;
  }
  throw new Error('The progress stream ended before AURA returned its results.');
}

function progressLabel(event) {
  const tool = String(event.tool || '').replaceAll('_', ' ');
  if (event.event_type === 'planning') return event.message;
  if (event.event_type === 'plan_started') return 'Journey started';
  if (event.event_type === 'task_started') return `${tool} started…`;
  if (event.event_type === 'task_verified') return `${tool} checked`;
  if (event.event_type === 'task_completed') {
    const elapsed = event.metadata?.duration_ms;
    return `${tool} complete${elapsed ? ` · ${(elapsed / 1000).toFixed(1)}s` : ''}`;
  }
  if (event.event_type === 'task_failed') return `${tool} needs attention`;
  if (event.event_type === 'task_skipped') return `${tool} skipped`;
  return event.message || 'AURA is working…';
}

function formatDuration(milliseconds) {
  const seconds = Math.max(0, Number(milliseconds) || 0) / 1000;
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function toast(message, kind = '') {
  const node = document.createElement('div');
  node.className = `toast ${kind}`;
  node.textContent = message;
  $('#toast-region').append(node);
  window.setTimeout(() => node.remove(), 3600);
}

function setBusy(button, busy, label = 'Working…') {
  if (busy) {
    button.dataset.original = button.innerHTML;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.innerHTML = `<span class="spinner"></span><span>${label}</span>`;
  } else {
    button.disabled = false;
    button.removeAttribute('aria-busy');
    if (button.dataset.original) button.innerHTML = button.dataset.original;
  }
}

function navigate(page) {
  if (!$('#page-' + page)) page = 'home';
  state.page = page;
  $$('.page').forEach((el) => el.classList.toggle('active', el.dataset.page === page));
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.page === page));
  if (page === 'journeys') loadRuns(true);
  if (page === 'capabilities') loadCapabilities();
  if (page === 'insights') loadInsights();
  history.replaceState(null, '', `#${page}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

$$('.nav-item').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.page)));
$$('[data-navigate]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.navigate)));
document.addEventListener('keydown', (event) => {
  if (!(event.metaKey || event.ctrlKey) || !/^[1-5]$/.test(event.key)) return;
  event.preventDefault();
  navigate(['home', 'talent', 'journeys', 'capabilities', 'insights'][Number(event.key) - 1]);
});
window.addEventListener('hashchange', () => navigate(location.hash.slice(1) || 'home'));
if (location.hash) navigate(location.hash.slice(1));

$$('.suggestion').forEach((button) => button.addEventListener('click', () => {
  $('#goal-input').value = button.dataset.prompt;
  $('#goal-input').focus();
}));

function formatDate(value) {
  if (!value) return 'Date unknown';
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value).replace('T', ' ').slice(0, 16);
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
}

function renderRecent(runs) {
  const container = $('#recent-list');
  const recent = runs.slice(0, 4);
  if (!recent.length) {
    container.innerHTML = '<div class="empty-inline">Your first journey will show up here.</div>';
    return;
  }
  container.innerHTML = recent.map((run) => `
    <button class="recent-item" data-run-id="${escapeHtml(run.run_id)}">
      <span class="recent-glyph"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h12M4 17h8"/></svg></span>
      <span class="recent-text"><span class="recent-title">${escapeHtml(run.goal || 'Untitled journey')}</span>
      <span class="recent-meta"><i class="status-mark ${run.status === 'failed' ? 'failed' : run.status === 'partial' ? 'partial' : ''}"></i>${escapeHtml(run.status === 'partial' ? 'partially complete' : run.status || 'unknown')} · ${escapeHtml(formatDate(run.created_at))}</span></span>
    </button>`).join('');
  $$('.recent-item', container).forEach((button) => button.addEventListener('click', () => {
    navigate('journeys');
    window.setTimeout(() => $(`[data-journey-id="${CSS.escape(button.dataset.runId)}"] .journey-toggle`)?.click(), 100);
  }));
}

async function loadRuns(renderHistory = false) {
  if (renderHistory) $('#journey-list').innerHTML = '<div class="history-loading" role="status">Loading journey history…</div>';
  try {
    const data = await api('/runs');
    state.runs = Array.isArray(data.runs) ? data.runs : [];
    $('#home-runs').textContent = state.runs.length;
    const success = state.runs.length ? Math.round(state.runs.filter((run) => run.status === 'completed').length * 100 / state.runs.length) : 0;
    $('#home-success').textContent = `${success}%`;
    const partial = state.runs.filter((run) => run.status === 'partial').length;
    $('#overview-foot-text').textContent = state.runs.length ? `${partial ? `${partial} partial · ` : ''}Your journey history is up to date` : 'Ready for your first journey';
    renderRecent(state.runs);
    if (renderHistory || state.page === 'journeys') renderJourneyList();
  } catch (error) {
    $('#recent-list').innerHTML = '<div class="empty-inline">Could not reach the AURA API.</div>';
    if (renderHistory) $('#journey-list').innerHTML = `<div class="empty-state"><h3>History is unavailable</h3><p>${escapeHtml(error.message)}</p><button class="reset-link" type="button" id="retry-journey-history">Try again</button></div>`;
    $('#retry-journey-history')?.addEventListener('click', () => loadRuns(true));
  }
}

function renderJourneyList() {
  const query = ($('#journey-search').value || '').trim().toLowerCase();
  const statusFilter = $('#journey-status-filter')?.value || 'all';
  const dateFilter = $('#journey-date-filter')?.value || 'all';
  const sortOrder = $('#journey-sort')?.value || 'newest';
  const now = new Date();
  let runs = state.runs.filter((run) => {
    const searchable = `${run.goal || ''} ${run.run_id || ''} ${run.status || ''}`.toLowerCase();
    if (!searchable.includes(query)) return false;
    if (statusFilter !== 'all' && run.status !== statusFilter) return false;
    if (dateFilter !== 'all') {
      const created = new Date(run.created_at || 0);
      if (Number.isNaN(created.getTime())) return false;
      if (dateFilter === 'today' && created.toDateString() !== now.toDateString()) return false;
      if (dateFilter !== 'today' && now - created > Number(dateFilter) * 86400000) return false;
    }
    return true;
  });
  runs = [...runs].sort((a, b) => {
    const delta = new Date(b.created_at || 0) - new Date(a.created_at || 0);
    return sortOrder === 'oldest' ? -delta : delta;
  });
  const filtered = Boolean(query || statusFilter !== 'all' || dateFilter !== 'all');
  $('#journeys-total').textContent = filtered ? `${runs.length} of ${state.runs.length} journeys` : `${runs.length} ${runs.length === 1 ? 'journey' : 'journeys'}`;
  const list = $('#journey-list');
  if (!runs.length) {
    list.innerHTML = `<div class="empty-state"><span class="empty-state-icon" data-icon="clock"></span><h3>${filtered ? 'No journeys match these filters' : 'No journeys yet'}</h3><p>${filtered ? 'Change a filter or clear them to see more history.' : 'Start a journey from Home and its complete activity will appear here.'}</p>${filtered ? '<button class="reset-link" id="clear-journey-filters" type="button">Clear filters</button>' : ''}</div>`;
    paintIcons(list);
    $('#clear-journey-filters')?.addEventListener('click', () => {
      $('#journey-search').value = '';
      $('#journey-status-filter').value = 'all';
      $('#journey-date-filter').value = 'all';
      $('#journey-sort').value = 'newest';
      renderJourneyList();
    });
    return;
  }
  list.innerHTML = runs.map((run, index) => {
    const failed = run.status === 'failed';
    const runState = String(run.status || 'unknown').toLowerCase();
    const stateClass = runState === 'completed' ? 'complete' : runState === 'partial' ? 'partial' : failed ? 'failed' : 'in-progress';
    const id = escapeHtml(run.run_id || `journey-${index}`);
    const events = Array.isArray(run.events) ? run.events : [];
    const eventRows = events.map((event) => {
      const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';
      const type = String(event.event_type || 'event').replaceAll('_', ' ');
      const eventClass = /fail|error/i.test(type) ? 'failed' : /verified|completed/i.test(type) ? 'complete' : '';
      const elapsed = event.metadata?.duration_ms ? ` · ${formatDuration(event.metadata.duration_ms)}` : '';
      return `<div class="event-row ${eventClass}"><span class="event-rail" aria-hidden="true"><i class="event-node"></i></span><span class="event-time">${escapeHtml(timestamp)}</span><span class="event-copy"><span class="event-type">${escapeHtml(type)}${escapeHtml(elapsed)}</span><span class="event-message">${escapeHtml(event.message || '')}</span></span></div>`;
    }).join('');
    const detailId = `journey-detail-${id}`;
    return `<article class="journey-card" data-journey-id="${id}">
      <button class="journey-toggle" aria-expanded="false" aria-controls="${detailId}"><i class="journey-status ${stateClass}"></i><span class="journey-main"><span class="journey-title">${escapeHtml(run.goal || 'Untitled journey')}</span><span class="journey-meta"><span>${escapeHtml(formatDate(run.created_at))}</span><span>·</span><span>${escapeHtml(run.planner || 'rule')} planner</span><span>·</span><span>${escapeHtml(String(run.tasks_completed ?? events.filter((e) => e.event_type === 'task_completed').length))} steps</span>${run.duration_ms ? `<span>·</span><span>${escapeHtml(formatDuration(run.duration_ms))}</span>` : ''}</span></span><span class="journey-result ${stateClass}">${escapeHtml(runState === 'partial' ? 'partially complete' : runState.replaceAll('_', ' '))}</span><span class="journey-chevron" data-icon="chevron"></span></button>
      <div class="journey-detail" id="${detailId}"><p class="journey-goal">${escapeHtml(run.goal || '')}</p>${renderRunOutput(run)}<div class="journey-actions">${run.plan ? '<button data-detail="plan" aria-expanded="false">View plan</button>' : ''}${run.logs?.length ? '<button data-detail="logs" aria-expanded="false">View execution log</button>' : ''}<button data-detail="events" aria-expanded="false">${events.length} recorded events</button></div><div class="event-list">${eventRows || '<p class="journey-goal">No structured events were recorded.</p>'}</div></div>
    </article>`;
  }).join('');
  paintIcons(list);
  $$('.journey-toggle', list).forEach((button) => button.addEventListener('click', () => {
    const card = button.closest('.journey-card');
    const opened = card.classList.toggle('open');
    button.setAttribute('aria-expanded', String(opened));
  }));
  $$('.journey-actions button', list).forEach((button) => button.addEventListener('click', async (event) => {
    event.stopPropagation();
    const card = button.closest('.journey-card');
    try {
      const run = await api(`/runs/${encodeURIComponent(card.dataset.journeyId)}`);
      const label = button.dataset.detail;
      const payload = label === 'plan' ? run.plan : label === 'logs' ? run.logs : run.events;
      showJsonDetail(button, label, payload);
    } catch (error) { toast(error.message, 'error'); }
  }));
}

function showJsonDetail(button, label, payload) {
  let block = button.parentElement.nextElementSibling;
  const buttons = $$('button[data-detail]', button.parentElement);
  if (block?.classList.contains('detail-panel') && block.dataset.kind === label) {
    block.remove();
    buttons.forEach((item) => item.setAttribute('aria-expanded', 'false'));
    return;
  }
  if (block?.classList.contains('detail-panel')) block.remove();
  buttons.forEach((item) => item.setAttribute('aria-expanded', 'false'));
  block = document.createElement('section');
  block.className = 'detail-panel';
  block.dataset.kind = label;
  block.id = `detail-${button.closest('.journey-card')?.dataset.journeyId || 'run'}-${label}`;
  block.setAttribute('aria-label', label === 'plan' ? 'Plan steps' : label === 'logs' ? 'Execution log' : 'Journey events');
  block.innerHTML = detailPanelMarkup(label, payload);
  button.parentElement.after(block);
  button.setAttribute('aria-expanded', 'true');
  button.setAttribute('aria-controls', block.id);
}

function detailPanelMarkup(label, payload) {
  const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.steps) ? payload.steps : [];
  const heading = label === 'plan' ? 'Planned steps' : label === 'logs' ? 'Execution log' : 'Journey events';
  const rowMarkup = rows.length ? rows.map((item, index) => {
    if (typeof item === 'string') return `<li><span class="detail-index">${index + 1}</span><span>${escapeHtml(item)}</span></li>`;
    const title = item.tool || item.event_type || item.message || item.name || `Step ${index + 1}`;
    const description = item.description || item.message || item.summary || '';
    const dependencies = Array.isArray(item.dependencies) && item.dependencies.length ? `Depends on ${item.dependencies.join(', ')}` : '';
    const args = item.args && typeof item.args === 'object' ? Object.entries(item.args).filter(([key]) => !/email|recipient|password|token|key/i.test(key)).map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join(' · ') : '';
    const timestamp = item.timestamp ? formatDateTime(item.timestamp) : '';
    return `<li><span class="detail-index">${index + 1}</span><span class="detail-copy"><strong>${escapeHtml(String(title).replaceAll('_', ' '))}</strong>${description ? `<span>${escapeHtml(description)}</span>` : ''}${args ? `<span>${escapeHtml(args)}</span>` : ''}${dependencies ? `<span>${escapeHtml(dependencies)}</span>` : ''}${timestamp ? `<time>${escapeHtml(timestamp)}</time>` : ''}</span></li>`;
  }).join('') : '<li><span>This journey has no additional detail here.</span></li>';
  return `<h3>${heading}</h3><ol>${rowMarkup}</ol>`;
}

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

function resultSourceLabel(item) {
  try { return item.source || new URL(item.url).hostname.replace(/^www\./, ''); }
  catch { return item.source || 'Web result'; }
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-check-links]');
  if (!button || button.disabled) return;
  const section = button.closest('[data-link-check-section]');
  if (!section) return;
  const links = $$('.link-check', section).map((status) => status.dataset.link).filter(Boolean);
  if (!links.length) return;
  const original = button.textContent;
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  button.textContent = 'Checking links…';
  try {
    const response = await api('/links/check', { method: 'POST', body: JSON.stringify({ urls: links }) });
    const resultMap = new Map((response.results || []).map((item) => [item.url, item]));
    $$('.link-check', section).forEach((status) => {
      const result = resultMap.get(status.dataset.link);
      if (!result) return;
      status.dataset.state = result.status;
      const label = result.status === 'reachable' ? 'Reachable' : result.status === 'broken' ? 'Link may be unavailable' : result.status === 'redirect' ? 'Redirect · confirm destination' : result.status === 'unsafe' ? 'Blocked for safety' : 'Could not verify';
      const time = formatDateTime(response.checked_at);
      status.textContent = `${label}${time ? ` · checked ${time}` : ''}`;
    });
    button.textContent = 'Check again';
  } catch (error) {
    toast(`Could not check links: ${error.message}`, 'error');
    button.textContent = original;
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
});

function renderOpportunity(item, isJob = true) {
  const facts = [item.company, item.location, item.work_mode, item.employment_type, item.salary].filter(Boolean);
  return `<article class="run-result-card">
    <div class="run-result-heading"><h4>${escapeHtml(item.title || 'Opportunity')}</h4>${item.relevance ? `<span>${escapeHtml(item.relevance)}</span>` : ''}</div>
    <div class="result-meta"><span>${escapeHtml(resultSourceLabel(item))}${item.provider ? ` · ${escapeHtml(item.provider)}` : ''}</span>${item.published_at ? `<span>Posted ${escapeHtml(item.published_at)}</span>` : ''}${item.found_at ? `<time datetime="${escapeHtml(item.found_at)}">Found ${escapeHtml(formatDateTime(item.found_at))}</time>` : ''}</div>
    ${facts.length ? `<div class="job-facts">${facts.map((fact) => `<span>${escapeHtml(fact)}</span>`).join('')}</div>` : ''}
    ${item.snippet ? `<p>${escapeHtml(item.snippet)}</p>` : ''}
    <span class="link-check" role="status" aria-live="polite" data-link="${escapeHtml(item.url || '')}">Not checked yet</span>
    <a href="${escapeHtml(item.url || '#')}" target="_blank" rel="noopener noreferrer">Open ${isJob ? 'job' : 'source'} <span aria-hidden="true">↗</span></a>
  </article>`;
}

function renderRunOutput(run) {
  const results = Array.isArray(run.results) ? run.results : [];
  const isJobSearch = /job|role|internship|position|career/i.test(run.goal || '');
  const cards = results.map((item) => renderOpportunity(item, isJobSearch)).join('');
  const resultsMarkup = results.length
    ? `<section class="run-output" data-link-check-section><div class="run-output-heading"><h3>${isJobSearch ? 'Job links' : 'Sources'}</h3><span>${results.length} found</span></div><div class="run-result-grid">${cards}</div><button class="check-links" type="button" data-check-links>Check links</button></section>`
    : run.search_available === false
      ? `<section class="run-output-state"><h3>Live search needs setup</h3><p>${escapeHtml(run.search_message || 'Connect a search provider to get real job links.')}</p></section>`
      : run.search_available === true
        ? `<section class="run-output-state no-results-state"><h3>No matching results</h3><p>Try a broader role title, include a location, or remove a restrictive keyword.</p></section>`
      : '';
  const summaryMarkup = run.summary
    ? `<section class="run-summary"><h3>Summary</h3><p>${escapeHtml(run.summary)}</p></section>`
    : '';
  const emailMarkup = run.email_status
    ? `<p class="run-email-status">${escapeHtml(run.email_status)}</p>`
    : '';
  return `${resultsMarkup}${summaryMarkup}${emailMarkup}`;
}

function friendlyRunReason(run) {
  const reason = String(run.failure_reason || run.search_message || run.error || '').replace(/^Verification failed:\s*/i, '').trim();
  if (!reason) return 'AURA saved the completed steps and marked the remaining work.';
  if (/search returned no results/i.test(reason)) return 'No matching live results came back. Try a broader role title or location.';
  if (/not configured|credentials/i.test(reason)) return 'Live search needs a provider key in the local setup before AURA can find current links.';
  if (/quota|rate.?limit|429/i.test(reason)) return 'The search provider is temporarily limiting requests. Try again later.';
  return reason;
}

$('#journey-search').addEventListener('input', renderJourneyList);
['#journey-status-filter', '#journey-date-filter', '#journey-sort'].forEach((selector) => $(selector)?.addEventListener('change', renderJourneyList));

$('#run-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const goal = $('#goal-input').value.trim();
  if (!goal) { toast('Add a goal before starting a journey.'); return; }
  const button = $('#run-button');
  setBusy(button, true, 'AURA is working…');
  $('#run-live-status').textContent = 'AURA is working through your journey. This can take a moment.';
  $('#run-result').setAttribute('aria-busy', 'true');
  $('#run-result').classList.add('hidden');
  try {
    const result = await streamRun({ goal, email: $('#email-input').value.trim() || null, planner: $('#planner-select').value }, (progress) => {
      const label = progressLabel(progress);
      $('#run-live-status').textContent = label;
      const buttonLabel = button.querySelector('span:last-child');
      if (buttonLabel) buttonLabel.textContent = label;
    });
    const success = result.status === 'completed';
    const reason = result.email_status || friendlyRunReason(result);
    const bannerTitle = result.status === 'partial' ? 'Partially complete' : success ? 'Journey complete' : result.search_available === false ? 'Live search needs setup' : /SMTP|email/i.test(reason) ? 'Results found, email needs setup' : 'Journey stopped';
    const bannerCopy = success ? 'AURA completed the goal and recorded its results.' : friendlyRunReason(result);
    const panel = $('#run-result');
    const planDetails = result.plan ? `<details><summary>Plan steps</summary><div class="detail-panel">${detailPanelMarkup('plan', result.plan)}</div></details>` : '';
    const logDetails = result.logs?.length ? `<details><summary>Execution log</summary><div class="detail-panel">${detailPanelMarkup('logs', result.logs)}</div></details>` : '';
    const eventDetails = result.events?.length ? `<details><summary>Journey events (${result.events.length})</summary><div class="detail-panel">${detailPanelMarkup('events', result.events)}</div></details>` : '';
    const stepStats = `<div class="result-stats"><span>${Number(result.tasks_completed || 0)} steps completed</span><span>${Number(result.verification_events || 0)} checks verified</span>${result.duration_ms ? `<span>Completed in ${escapeHtml(formatDuration(result.duration_ms))}</span>` : ''}<span>${escapeHtml(String(result.planner || 'rule'))} planner</span></div>`;
    panel.innerHTML = `<div class="result-banner ${success ? 'success' : 'failed'}"><h3>${escapeHtml(bannerTitle)}</h3><p>${escapeHtml(bannerCopy)}</p>${stepStats}</div>${renderRunOutput(result)}<div class="result-details">${planDetails}${logDetails}${eventDetails}</div>`;
    panel.classList.remove('hidden');
    panel.removeAttribute('aria-busy');
    $('#run-live-status').textContent = `${bannerTitle}. ${bannerCopy}`;
    if (success) $('#goal-input').value = '';
    await loadRuns();
    if (success) toast('Your journey is complete.'); else toast('The journey ended with an issue.', 'error');
  } catch (error) {
    $('#run-result').innerHTML = `<div class="result-banner failed"><h3>Could not start this journey</h3><p>${escapeHtml(error.message)}</p></div>`;
    $('#run-result').classList.remove('hidden');
    $('#run-live-status').textContent = `Could not start journey. ${error.message}`;
    $('#run-result').removeAttribute('aria-busy');
  } finally { setBusy(button, false); }
});

function renderProfile(data) {
  const analysis = data.analysis || {};
  state.profile = analysis;
  const skills = Array.isArray(analysis.skills) ? analysis.skills : [];
  const exp = analysis.years_experience ?? analysis.experience_years;
  const experienceFact = exp === undefined || exp === null || exp === ''
    ? '<span class="fact-chip">Experience not specified</span>'
    : `<span class="fact-chip">${escapeHtml(String(exp))} years experience</span>`;
  $('#profile-content').className = 'profile-data';
  $('#profile-content').innerHTML = `<h3>${escapeHtml(analysis.name || 'Candidate')}</h3><span class="profile-sub">${escapeHtml(analysis.field_of_study || analysis.summary || 'Profile analyzed')}</span><div class="profile-facts">${experienceFact}${analysis.email ? `<span class="fact-chip">${escapeHtml(analysis.email)}</span>` : ''}</div><div class="skills-label">Core skills</div><div class="skills">${skills.length ? skills.map((skill) => `<span class="skill-chip">${escapeHtml(skill)}</span>`).join('') : '<span class="profile-sub">No skills were extracted.</span>'}</div>`;
  $('#matches-section').classList.remove('hidden');
}

const fileInput = $('#resume-file');
fileInput.addEventListener('change', () => {
  state.file = fileInput.files?.[0] || null;
  $('#upload-title').textContent = state.file ? state.file.name : 'Choose a file or drop it here';
  $('#upload-caption').textContent = state.file ? `${(state.file.size / 1024 / 1024).toFixed(2)} MB · ready to analyze` : 'Your document is processed by AURA.';
  $('#analyze-button').disabled = !state.file;
});
const dropzone = $('#dropzone');
['dragenter', 'dragover'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach((name) => dropzone.addEventListener(name, (event) => { event.preventDefault(); dropzone.classList.remove('dragover'); }));
dropzone.addEventListener('drop', (event) => { if (event.dataTransfer.files.length) { fileInput.files = event.dataTransfer.files; fileInput.dispatchEvent(new Event('change')); } });

$('#analyze-button').addEventListener('click', async () => {
  if (!state.file) return;
  if (state.file.size > 10 * 1024 * 1024) { toast('Choose a resume smaller than 10 MB.', 'error'); return; }
  const button = $('#analyze-button'); setBusy(button, true, 'Analyzing…');
  try {
    const contentBase64 = await new Promise((resolve, reject) => {
      const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('Could not read this file.')); reader.readAsDataURL(state.file);
    });
    const result = await api('/resume/analyze', { method: 'POST', body: JSON.stringify({ file_name: state.file.name, content_base64: contentBase64 }) });
    renderProfile(result); toast('Resume analysis is ready.');
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(button, false); button.disabled = !state.file; }
});

$('#match-button').addEventListener('click', async () => {
  if (!state.profile) return;
  const button = $('#match-button'); setBusy(button, true, 'Searching…');
  try {
    const data = await api('/resume/match', { method: 'POST', body: JSON.stringify({ analysis: state.profile, location: $('#location-input').value || 'remote', limit: 10 }) });
    const jobs = data.job_matches || [];
    $('#matches-list').innerHTML = jobs.length ? `<section class="run-output" data-link-check-section><div class="run-output-heading"><h3>Matching roles</h3><span>${jobs.length} found</span></div><div class="run-result-grid">${jobs.map((job) => renderOpportunity(job, true)).join('')}</div><button class="check-links" type="button" data-check-links>Check links</button></section>` : `<div class="empty-state"><h3>${data.message ? 'Live search needs setup' : 'No matches found'}</h3><p>${escapeHtml(data.message || 'Try a different location preference.')}</p><button class="reset-link" id="retry-match-search" type="button">Search again</button></div>`;
    $('#retry-match-search')?.addEventListener('click', () => $('#match-button').click());
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(button, false); }
});

async function loadCapabilities() {
  if (state.tools.length) return;
  $('#capability-list').innerHTML = '<div class="history-loading" role="status">Loading capabilities…</div>';
  try {
    const data = await api('/tools'); state.tools = data.tools || [];
    $('#capability-count').textContent = state.tools.length;
    $('#capability-list').innerHTML = state.tools.map((tool) => {
      const risk = String(tool.risk_level || 'low').toLowerCase();
      const glyph = String(tool.name || 'tool').slice(0, 2);
      return `<article class="capability-card"><div class="capability-top"><div class="capability-title-group"><span class="tool-glyph">${escapeHtml(glyph)}</span><h3>${escapeHtml(tool.name || 'Tool')}</h3></div><span class="risk ${escapeHtml(risk)}">${escapeHtml(risk)} risk</span></div><p>${escapeHtml(tool.description || '')}</p><div class="capability-meta">Timeout ${escapeHtml(tool.timeout_seconds ?? '—')}s <span>·</span> Max retries ${escapeHtml(tool.max_retries ?? '—')}</div></article>`;
    }).join('');
  } catch (error) {
    $('#capability-list').innerHTML = `<div class="empty-state"><h3>Capabilities are unavailable</h3><p>${escapeHtml(error.message)}</p><button class="reset-link" id="retry-capabilities" type="button">Try again</button></div>`;
    $('#retry-capabilities')?.addEventListener('click', loadCapabilities);
  }
}

async function loadInsights() {
  $('#insight-metrics').innerHTML = '<div class="history-loading" role="status">Loading workspace insights…</div>';
  try {
    const [evaluation, memory] = await Promise.all([api('/evaluation'), api('/memory')]);
    const metrics = [
      ['Total journeys', evaluation.total_runs ?? 0, 'Lifetime executions'],
      ['Success rate', `${Math.round((evaluation.success_rate || 0) * 100)}%`, `${evaluation.completed_runs ?? 0} complete · ${evaluation.partial_runs ?? 0} partial`],
      ['Self-healing', `${Math.round((evaluation.recovery_rate || 0) * 100)}%`, 'Autonomous recoveries'],
      ['Verification', `${Math.round((evaluation.verification_coverage || 0) * 100)}%`, 'Outputs verified'],
    ];
    $('#insight-metrics').innerHTML = metrics.map(([label, value, note]) => `<div class="insight-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></div>`).join('');
    const planners = Object.entries(evaluation.planner_comparison || {});
    $('#planner-breakdown').innerHTML = planners.length ? planners.map(([name, stats]) => `<div class="breakdown-row"><span>${escapeHtml(name)} planner</span><strong>${escapeHtml(stats.runs)} runs · ${Math.round((stats.success_rate || 0) * 100)}% success${stats.partial_runs ? ` · ${escapeHtml(stats.partial_runs)} partial` : ''}</strong></div>`).join('') : '<div class="breakdown-empty">Planner comparisons appear as journeys are recorded.</div>';
    const faults = Object.entries(evaluation.failure_categories || {});
    $('#fault-breakdown').innerHTML = faults.length ? faults.map(([name, count]) => `<div class="breakdown-row"><span>${escapeHtml(name.replaceAll('_', ' '))}</span><strong>${escapeHtml(count)}</strong></div>`).join('') : '<div class="breakdown-empty">No faults recorded. Your journeys are looking good.</div>';
    $('#memory-content').textContent = JSON.stringify(memory, null, 2);
  } catch (error) {
    $('#insight-metrics').innerHTML = `<div class="empty-state"><h3>Insights are unavailable</h3><p>${escapeHtml(error.message)}</p><button class="reset-link" id="retry-insights" type="button">Try again</button></div>`;
    $('#retry-insights')?.addEventListener('click', loadInsights);
  }
}

$('#preference-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await api('/memory/preference', { method: 'POST', body: JSON.stringify({ key: $('#preference-key').value.trim(), value: $('#preference-value').value.trim() }) });
    $('#preference-key').value = ''; $('#preference-value').value = ''; await loadInsights(); toast('Preference saved.');
  } catch (error) { toast(error.message, 'error'); }
});
$('#memory-refresh').addEventListener('click', loadInsights);
$('#memory-reset').addEventListener('click', async () => {
  if (!window.confirm('Reset the AURA memory archive? This clears saved preferences and remembered context.')) return;
  try { await api('/memory', { method: 'DELETE' }); await loadInsights(); toast('Memory archive reset.'); }
  catch (error) { toast(error.message, 'error'); }
});

async function checkConnection() {
  try { await api('/health'); $('#connection-label').textContent = 'System online'; $('.connection-dot').style.background = '#36A871'; }
  catch { $('#connection-label').textContent = 'API unavailable'; $('.connection-dot').style.background = '#D5676E'; }
}
Promise.all([checkConnection(), loadRuns(), loadCapabilities(), loadInsights()]);
