(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const storageKey = 'aura-resume-studio-v1';
  const blankResume = () => ({ name: '', title: '', email: '', phone: '', location: '', links: [], summary: '', skills: '', experience: [], education: [], projects: [] });
  let resume = blankResume();
  let saveTimer;
  let saveRevision = 0;
  const form = $('#resume-form');
  if (!form) return;

  function normalizeResume(parsed) {
    const legacyLocation = typeof parsed.links === 'string' ? parsed.links : '';
    return { ...blankResume(), ...parsed, location: parsed.location || legacyLocation, links: Array.isArray(parsed.links) ? parsed.links : [], experience: Array.isArray(parsed.experience) ? parsed.experience : [], education: Array.isArray(parsed.education) ? parsed.education : [], projects: Array.isArray(parsed.projects) ? parsed.projects : [] };
  }

  function loadSaved() {
    try {
      const parsed = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (parsed && typeof parsed === 'object') {
        resume = normalizeResume(parsed);
        return true;
      }
    } catch { resume = blankResume(); }
    return false;
  }

  function collectForm() {
    for (const [key, value] of new FormData(form).entries()) resume[key] = String(value).trim();
    ['experience', 'education', 'projects', 'links'].forEach((kind) => {
      resume[kind] = [...document.querySelectorAll(`[data-resume-group="${kind}"]`)].map((row) => {
        const item = {};
        row.querySelectorAll('[data-resume-field]').forEach((field) => { item[field.dataset.resumeField] = field.value.trim(); });
        return item;
      });
    });
    renderPaper();
    updateCompletion();
    scheduleSave();
  }

  function setField(name, value) {
    const field = form.elements.namedItem(name);
    if (field) field.value = value || '';
  }

  function renderRows(kind, labels) {
    const root = $(`#resume-${kind}-fields`);
    root.innerHTML = (resume[kind] || []).map((item, index) => `<fieldset class="resume-row" data-resume-group="${kind}"><div class="resume-row-top"><span>${labels[0]} ${String(index + 1).padStart(2, '0')}</span><button type="button" data-resume-remove aria-label="Remove ${labels[0].toLowerCase()}">×</button></div>${labels.slice(1).map(([field, label, type, placeholder]) => `<label>${label}${type === 'textarea' ? `<textarea rows="3" data-resume-field="${field}" placeholder="${placeholder || ''}">${escapeHTML(item[field] || '')}</textarea>` : `<input type="${type || 'text'}" data-resume-field="${field}" value="${escapeHTML(item[field] || '')}" placeholder="${placeholder || ''}" />`}</label>`).join('')}</fieldset>`).join('');
  }

  function fillEditor() {
    ['name', 'title', 'email', 'phone', 'location', 'summary', 'skills'].forEach((field) => setField(field, resume[field]));
    renderRows('experience', ['Experience', ['role', 'Role', 'text', 'e.g. Software engineering intern'], ['company', 'Company', 'text', 'Company or organisation'], ['dates', 'Dates', 'text', 'Jan 2024 – present'], ['details', 'What you did', 'textarea', 'One achievement per line. Keep it factual.']]);
    renderRows('education', ['Education', ['degree', 'Degree or course', 'text', 'B.Tech in Computer Science'], ['school', 'School', 'text', 'University or institute'], ['dates', 'Dates', 'text', '2022 – 2026'], ['detail', 'Details (optional)', 'text', 'Relevant coursework, distinction…']]);
    renderRows('projects', ['Project', ['name', 'Project name', 'text', 'What did you make?'], ['detail', 'What it does', 'textarea', 'Tools used and your contribution'], ['link', 'Link (optional)', 'url', 'https://…']]);
    renderRows('links', ['Link', ['label', 'Display name', 'text', 'e.g. Portfolio'], ['url', 'Destination URL', 'url', 'https://…']]);
    renderPaper();
    updateCompletion();
    $('#resume-doc-name').textContent = resume.name ? `${resume.name} — resume` : 'Untitled resume';
  }

  function section(title, body) { return body ? `<section class="resume-paper-section"><h2>${title}</h2>${body}</section>` : ''; }

  function renderPaper() {
    const paper = $('#resume-paper');
    const skills = (resume.skills || '').split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
    const experience = (resume.experience || []).filter((item) => Object.values(item).some(Boolean));
    const education = (resume.education || []).filter((item) => Object.values(item).some(Boolean));
    const projects = (resume.projects || []).filter((item) => Object.values(item).some(Boolean));
    const contact = [resume.email, resume.phone, resume.location].filter(Boolean).map((value) => `<span>${escapeHTML(value)}</span>`);
    const linkedContacts = (resume.links || []).filter((item) => item.label && item.url).map((item) => {
      const url = safeWebURL(item.url);
      return url ? `<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.label)}</a>` : `<span>${escapeHTML(item.label)}</span>`;
    });
    const intro = [...contact, ...linkedContacts].join('<span class="resume-contact-separator">·</span>');
    const experienceHTML = experience.map((item) => `<article class="resume-paper-entry"><div class="resume-paper-entry-head"><div><h3>${escapeHTML(item.role || 'Role')}</h3><p>${escapeHTML(item.company || '')}</p></div><time>${escapeHTML(item.dates || '')}</time></div>${item.details ? `<ul>${item.details.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => `<li>${escapeHTML(line.replace(/^[-•*]\s*/, ''))}</li>`).join('')}</ul>` : ''}</article>`).join('');
    const educationHTML = education.map((item) => `<article class="resume-paper-entry"><div class="resume-paper-entry-head"><div><h3>${escapeHTML(item.degree || 'Course or degree')}</h3><p>${escapeHTML(item.school || '')}</p></div><time>${escapeHTML(item.dates || '')}</time></div>${item.detail ? `<p class="resume-entry-detail">${escapeHTML(item.detail)}</p>` : ''}</article>`).join('');
    const projectsHTML = projects.map((item) => { const url = safeWebURL(item.link);const lines = String(item.detail || '').split(/\n+/).map((line) => line.trim()).filter(Boolean);const bullets = lines.filter((line) => /^[-•*▪●]\s*/.test(line));const context = lines.filter((line) => !/^[-•*▪●]\s*/.test(line)).map((line) => line.replace(/^@meta\s*/, ''));const content = `${context.length ? `<p class="resume-project-meta">${escapeHTML(context.join(' · '))}</p>` : ''}${bullets.length ? `<ul class="resume-project-bullets">${bullets.slice(0,4).map((line) => `<li>${escapeHTML(line.replace(/^[-•*▪●]\s*/, ''))}</li>`).join('')}</ul>` : (!context.length && lines.length ? `<ul class="resume-project-bullets">${lines.slice(0,4).map((line) => `<li>${escapeHTML(line)}</li>`).join('')}</ul>` : '')}`;return `<article class="resume-paper-entry resume-project-entry"><div class="resume-paper-entry-head"><div><h3>${escapeHTML(item.name || 'Project')}</h3></div>${url ? `<a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer">Link ↗</a>` : ''}</div>${content}</article>`; }).join('');
    paper.innerHTML = `<header class="resume-paper-header"><h1>${escapeHTML(resume.name || 'Your name')}</h1><p class="resume-paper-title">${escapeHTML(resume.title || 'Professional title')}</p><div class="resume-paper-contact">${intro || '<span class="resume-contact-placeholder">Add email, location or links</span>'}</div></header>${section('Profile', `<p class="resume-paper-summary">${escapeHTML(resume.summary || 'Add a short, specific introduction about your work and strengths.')}</p>`)}${section('Experience', experienceHTML)}${section('Education', educationHTML)}${section('Skills', skills.length ? `<div class="resume-paper-skills">${skills.map((skill) => `<span>${escapeHTML(skill)}</span>`).join('')}</div>` : '')}${section('Selected projects', projectsHTML)}<footer class="resume-paper-footer"><span>AURA · RESUME</span><span>${escapeHTML(resume.name || '')}</span></footer>`;
    updateATS();
  }

  function safeWebURL(value) {
    try { const input = String(value || '').trim();const url = new URL(/^[a-z][a-z\d+.-]*:/i.test(input) ? input : `https://${input}`);return ['http:', 'https:'].includes(url.protocol) && url.hostname.includes('.') ? url.href : ''; }
    catch { return ''; }
  }

  function updateCompletion() {
    const basics = ['name', 'title', 'email', 'summary'].filter((field) => resume[field]).length;
    const sections = basics + (resume.experience.some((item) => item.role || item.details) ? 1 : 0) + (resume.education.some((item) => item.degree) ? 1 : 0) + (resume.skills ? 1 : 0);
    const percent = Math.round(sections / 7 * 100);
    $('#resume-completion').textContent = `${percent}% complete`;
    $('#resume-completion').style.setProperty('--resume-completion', `${percent}%`);
  }

  function scheduleSave() {
    const revision = ++saveRevision;
    $('#resume-save-state').textContent = 'Saving…';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const snapshot = JSON.stringify(resume);
      try { localStorage.setItem(storageKey, snapshot); }
      catch { if (revision === saveRevision) $('#resume-save-state').textContent = 'Could not save';return; }
      $('#resume-doc-name').textContent = resume.name ? `${resume.name} — resume` : 'Untitled resume';
      try {
        const response = await fetch('/resume/studio', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resume: JSON.parse(snapshot) }) });
        if (!response.ok) throw new Error(`Save failed (${response.status})`);
        if (revision === saveRevision) $('#resume-save-state').textContent = 'Saved to AURA profile';
      } catch {
        if (revision === saveRevision) $('#resume-save-state').textContent = 'Saved on this device · cloud sync unavailable';
      }
    }, 250);
  }

  async function loadCloudDraft(hasLocalDraft) {
    $('#resume-save-state').textContent = 'Checking saved profile…';
    try {
      const response = await fetch('/resume/studio');
      if (!response.ok) throw new Error(`Load failed (${response.status})`);
      const payload = await response.json();
      if (payload.resume && typeof payload.resume === 'object') {
        resume = normalizeResume(payload.resume);
        fillEditor();
        try { localStorage.setItem(storageKey, JSON.stringify(resume)); } catch {}
        $('#resume-save-state').textContent = 'Saved to AURA profile';
      } else if (hasLocalDraft) {
        scheduleSave();
      } else {
        $('#resume-save-state').textContent = 'Ready · changes save to your profile';
      }
    } catch {
      $('#resume-save-state').textContent = hasLocalDraft ? 'Saved on this device · cloud sync unavailable' : 'Profile sync unavailable';
    }
  }

  function addRow(kind) {
    collectForm();
    const defaults = { experience: { role: '', company: '', dates: '', details: '' }, education: { degree: '', school: '', dates: '', detail: '' }, projects: { name: '', detail: '', link: '' }, links: { label: '', url: '' } };
    resume[kind].push(defaults[kind]);
    fillEditor();
    const last = $(`#resume-${kind}-fields .resume-row:last-child`);
    last?.querySelector('input,textarea')?.focus();
    scheduleSave();
  }

  function parseResumeText(rawText, embeddedLinks = []) {
    const result = blankResume();
    const buckets = { intro: [], summary: [], experience: [], education: [], skills: [], projects: [] };
    const headings = [
      ['summary', /^(?:professional\s+)?(?:summary|profile|about(?:\s+me)?)$/i],
      ['experience', /^(?:(?:professional|work|employment)\s+)?(?:experience|history)(?:\s+&\s+internships?)?$/i],
      ['education', /^(?:education|academic(?:\s+background)?|qualifications?)(?:\s*(?:&|and)\s*(?:certifications?|coursework))?$/i],
      ['skills', /^(?:(?:technical|core|key)\s+)?skills(?:\s+&\s+tools)?$/i],
      ['projects', /^(?:selected\s+)?(?:personal\s+|academic\s+|technical\s+)?projects?(?:\s*(?:&|and)\s*(?:research|work))?$/i],
    ];
    let active = 'intro';
    const lines = String(rawText || '').replace(/\r/g, '').split('\n').map((line) => line.trim());
    for (const line of lines) {
      const heading = line.replace(/[:—–-]+$/, '').trim();
      const found = heading.length < 48 && headings.find(([, pattern]) => pattern.test(heading));
      if (found) { active = found[0];continue; }
      buckets[active].push(line);
    }
    const text = String(rawText || '');
    result.email = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0] || '';
    result.phone = text.match(/(?:\+?\d[\d\s().-]{8,}\d)/g)?.find((candidate) => candidate.replace(/\D/g, '').length >= 10 && candidate.replace(/\D/g, '').length <= 14)?.trim() || '';
    const inlineUrls = (text.match(/(?:https?:\/\/|www\.)[^\s|,;)<>]+/gi) || []).map((url) => url.replace(/[.)]+$/, ''));
    const collectedLinks = [...(Array.isArray(embeddedLinks) ? embeddedLinks : []).map((item) => typeof item === 'string' ? { url: item, label: '' } : item).filter((item) => item?.url), ...inlineUrls.map((url) => ({ url, label: '' }))];
    result.links = [...new Map(collectedLinks.map((item) => { const href = /^www\./i.test(item.url) ? 'https://' + item.url : item.url; let host = ''; try { host = new URL(href).hostname.replace(/^www\./, ''); } catch {} const guessed = /linkedin/i.test(host) ? 'LinkedIn' : /github/i.test(host) ? 'GitHub' : /behance/i.test(host) ? 'Behance' : /dribbble/i.test(host) ? 'Dribbble' : /portfolio/i.test(host) ? 'Portfolio' : host || 'Website'; return [href, { label: String(item.label || guessed).slice(0, 32), url: href }]; })).values()].slice(0, 10);

    const introLines = buckets.intro.filter(Boolean).filter((line) => !line.includes(result.email) && !/https?:\/\//i.test(line) && !/\b(?:19|20)\d{2}\b/.test(line) && !/^(?:github|linkedin|portfolio|website|behance|dribbble)(?:\s*[:↗→].*)?$/i.test(line.trim()));
    const first = introLines[0] || '';
    const nameParts = first.split(/\s+[|•—–]\s+/).map((part) => part.trim()).filter(Boolean);
    result.name = nameParts[0]?.slice(0, 100) || '';
    const secondIntro = nameParts[1] || introLines.find((line) => line !== first && line.length < 100 && !/\d/.test(line)) || '';
    if (secondIntro.includes('|')) {
      const parts = secondIntro.split('|').map((part) => part.trim()).filter(Boolean);
      result.title = parts[0] || '';
      if (parts.length > 1 && /,/.test(parts.at(-1))) result.location = parts.at(-1);
    } else result.title = secondIntro;
    result.summary = buckets.summary.filter(Boolean).join(' ').replace(/\s+/g, ' ').slice(0, 1800);

    const datePattern = /(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*)?(?:19|20)\d{2}(?:\s*(?:-|–|—|to)\s*(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s*)?(?:(?:19|20)\d{2}|present|current))?/i;
    const experience = [];
    let entry = null;
    const pushExperience = () => { if (entry && (entry.role || entry.company || entry.details)) experience.push({ ...entry, details: entry.details.trim() });entry = null; };
    for (const line of buckets.experience) {
      if (!line) continue;
      const bullet = /^[•●▪*-]\s*/.test(line);
      const dates = line.match(datePattern)?.[0] || '';
      if (dates) {
        if (entry?.details) pushExperience();
        if (!entry) entry = { role: '', company: '', dates: '', details: '' };
        const header = line.replace(datePattern, '').replace(/[|,–—-]+$/, '').trim();
        const parts = header.split(/\s*[|•—–]\s*|\s+,\s+/).map((part) => part.trim()).filter(Boolean);
        if (!entry.role && parts.length) entry.role = parts[0];
        if (!entry.company && parts.length > 1) entry.company = parts[1];
        entry.dates = dates;
      } else if (bullet) {
        if (!entry) entry = { role: '', company: '', dates: '', details: '' };
        entry.details += `${entry.details ? '\n' : ''}${line.replace(/^[•●▪*-]\s*/, '')}`;
      } else if (!entry) {
        entry = { role: line, company: '', dates: '', details: '' };
      } else if (!entry.company && !entry.details) {
        entry.company = line;
      } else if (entry.details) {
        pushExperience();entry = { role: line, company: '', dates: '', details: '' };
      } else {
        entry.details += `${entry.details ? '\n' : ''}${line}`;
      }
    }
    pushExperience();
    result.experience = experience.slice(0, 8);

    const educationLines = buckets.education.filter(Boolean).flatMap((line) => line.split(/\n+/).map((part) => part.trim()).filter(Boolean)).flatMap((line) => line.replace(/\s+(?=(?:Class\s+(?:X|XI|XII|10|12)|B\.?\s?Tech|B\.?\s?E\.?|Bachelor|M\.?\s?Tech|Master|MCA|BCA)\b)/gi, '\n').split(/\n+/).map((part) => part.trim()).filter(Boolean));
    const degreePattern = /\b(?:b\.?\s?tech|b\.?\s?e\.?|bachelor(?:'s)?|b\.?\s?sc|m\.?\s?tech|master(?:'s)?|m\.?\s?sc|mba|ph\.?d|diploma|bca|mca|class\s+(?:x|xi|xii|10|12)|grade\s+(?:10|12)|higher\s+secondary|senior\s+secondary)\b/i;
    const institutionPattern = /\b(?:university|college|institute|school|iit|nit|academy|vidyalaya|polytechnic)\b/i;
    const schoolPattern = /\b(?:school|vidyalaya)\b/i;
    const educationRows = educationLines.map((line, index) => ({ line, index, dates: line.match(datePattern)?.[0] || '' }));
    const institutions = educationRows.filter((row) => institutionPattern.test(row.line));
    const entries = [];
    for (const row of educationRows.filter((item) => degreePattern.test(item.line))) {
      const raw = row.line.replace(datePattern, '').replace(/[|,–—-]+$/, '').trim();
      const classMatch = raw.match(/\bclass\s+(xii|xi|x|12|10)\b/i) || raw.match(/\bgrade\s+(12|10)\b/i);
      let degree = classMatch ? (classMatch[0].replace(/\s+/g, ' ').replace(/^grade/i, 'Class').replace(/\b(xii|xi|x)\b/i, (value) => value.toUpperCase())) : raw.replace(/,?\s*\b(?:Delhi|India)\b.*$/i, '').trim();
      if (!degree) continue;
      const isSchoolGrade = Boolean(classMatch);
      const choices = institutions.filter((candidate) => isSchoolGrade ? schoolPattern.test(candidate.line) : /\b(?:university|college|institute|iit|nit|polytechnic|academy)\b/i.test(candidate.line));
      choices.sort((left, right) => {
        const leftMatch = row.dates && left.dates === row.dates ? -1000 : Math.abs(left.index - row.index);
        const rightMatch = row.dates && right.dates === row.dates ? -1000 : Math.abs(right.index - row.index);
        return leftMatch - rightMatch;
      });
      const schoolRow = choices[0];
      const nearestDateRow = educationRows.filter((candidate) => candidate.dates && Math.abs(candidate.index - row.index) <= 2).sort((left, right) => Math.abs(left.index - row.index) - Math.abs(right.index - row.index))[0];
      const dates = row.dates || nearestDateRow?.dates || schoolRow?.dates || '';
      const school = schoolRow ? schoolRow.line.replace(datePattern, '').replace(/[|,–—-]+$/, '').trim() : '';
      entries.push({ degree, school, dates, detail: '' });
    }
    result.education = entries.slice(0, 8);
    result.skills = [...new Set(buckets.skills.join('\n').split(/[,;|•\n]/).map((skill) => skill.replace(/^[^:]{1,30}:\s*/, '').replace(/^[•●▪*-]\s*/, '').trim()).filter((skill) => skill && skill.length < 48))].slice(0, 35).join(', ');
    const rawProjectLines = buckets.projects.filter(Boolean).flatMap((line) => line.replace(/\s*·\s*/g, '\n').split(/\n+/).map((part) => part.trim()).filter(Boolean));
    const importedProjects = [];
    let project = null;
    const saveProject = () => { if (project && (project.name || project.detail)) importedProjects.push(project); project = null; };
    const beginProject = (line) => { const pipeParts = line.split(/\s*\|\s*/).map((part) => part.trim()).filter(Boolean); const name = (pipeParts[0] || line).replace(/\s*Ongoing\s*$/i, '').trim(); project = { name, detail: '' }; };
    for (const sourceLine of rawProjectLines) {
      const isBullet = /^[-–—•*▪●]\s*/.test(sourceLine);
      const line = sourceLine.replace(/^[-–—•*▪●]\s*/, '').trim();
      if (!line) continue;
      if (isBullet) { if (!project) project = { name: '', detail: '' }; project.detail = [project.detail, '• ' + line].filter(Boolean).join('\n'); continue; }
      if (!project) { beginProject(line); continue; }
      const detailLines = project.detail.split('\n').filter(Boolean);
      const hasBullets = detailLines.some((part) => /^•\s/.test(part));
      const looksLikeTitle = /^[A-Z0-9][^.!?]{2,110}$/.test(line) && !/^(?:and|or|with|using|through|for|in|to|across|which|that)\b/i.test(line);
      if (hasBullets && looksLikeTitle) { saveProject(); beginProject(line); }
      else if (hasBullets) { const lastBullet = detailLines.findLastIndex((part) => /^•\s/.test(part)); if (lastBullet >= 0) detailLines[lastBullet] += ' ' + line; else detailLines.push(line); project.detail = detailLines.join('\n'); }
      else if (!project.detail) project.detail = line;
      else project.detail += '\n' + line;
    }
    saveProject();
    result.projects = importedProjects.filter((item) => item.name || item.detail).slice(0, 12);
    return result;
  }

  async function importResume(file) {
    if (!file) return;
    const status = $('#resume-save-state');
    if (!/\.(pdf|docx|txt)$/i.test(file.name) || file.size > 10 * 1024 * 1024) { status.textContent = 'Choose a PDF, DOCX, or TXT file under 10 MB.';status.classList.add('resume-status-error');return; }
    const hasDraft = Object.values(resume).some((value) => Array.isArray(value) ? value.some((item) => Object.values(item).some(Boolean)) : Boolean(value));
    if (hasDraft && !window.confirm('Import this resume over your current saved draft?')) return;
    status.classList.remove('resume-status-error');
    status.textContent = `Reading ${file.name}…`;
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
      status.textContent = `Extracting text from ${file.name}…`;
      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), 90000);
      let response;
      try {
        response = await fetch('/resume/parse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ file_name: file.name, content_base64: btoa(binary) }), signal: controller.signal });
      } finally { window.clearTimeout(timeoutId); }
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not read this document.');
      status.textContent = 'Organizing resume sections…';
      const imported = parseResumeText(result.parsed?.resume_text || '', result.parsed?.links || []);
      if (!result.parsed?.resume_text?.trim()) throw new Error('No readable text was found. Try a text-based PDF, DOCX, or TXT file.');
      resume = imported;
      fillEditor();scheduleSave();
      status.textContent = `Imported ${file.name} · review the sections before exporting`;
      window.setTimeout(() => { if (status.textContent.startsWith('Imported ')) status.textContent = 'Saved on this device'; }, 5000);
    } catch (error) { status.textContent = `Import failed · ${error.name === 'AbortError' ? 'Parsing took too long. Try a text-based PDF, DOCX, or TXT file.' : error.message}`;status.classList.add('resume-status-error'); }
  }

  let atsAuditTimer;
  let atsAuditRequest = 0;

  function renderATSReport(report) {
    const total = report.check_count || 0;
    const passed = report.pass_count || 0;
    const issues = (report.findings || []).filter((item) => item.status === 'fail').length;
    const warnings = (report.findings || []).filter((item) => item.status === 'warn').length;
    $('#resume-ats-score').textContent = String(passed);
    $('#resume-ats-total').textContent = '/ ' + total + ' checks';
    $('#resume-ats-meter').style.width = (total ? Math.round(passed / total * 100) : 0) + '%';
    $('#resume-ats-caption').textContent = issues + ' issues · ' + warnings + ' warnings · ' + report.word_count + ' words';
    const categories = report.categories || {};
    const dimensions = [['parseability', 'Parsing'], ['structure', 'Structure'], ['content', 'Writing']];
    const dimensionHTML = dimensions.map(([key, label]) => '<div class="resume-ats-dimension"><span>' + label + '</span><strong>' + (categories[key]?.score == null ? '—' : categories[key].score) + '<small>/100</small></strong></div>').join('');
    const findings = (report.findings || []).slice(0, 5);
    const findingsHTML = findings.length ? '<ul class="resume-ats-findings">' + findings.map((item) => '<li class="is-' + escapeHTML(item.status) + '"><strong>' + escapeHTML(item.title) + '</strong><span>' + escapeHTML(item.detail) + '</span></li>').join('') + '</ul>' : '<p class="resume-ats-clean">No issues flagged by these checks.</p>';
    $('#resume-ats-checks').innerHTML = '<div class="resume-ats-dimensions">' + dimensionHTML + '</div>' + findingsHTML;
    const keywordPanel = $('#resume-keyword-score');
    const match = report.keyword_match;
    keywordPanel.hidden = !match;
    keywordPanel.innerHTML = match ? '<span>Literal job keyword overlap</span><strong>' + match.matched_count + '<small> / ' + match.total + ' · ' + match.score + '%</small></strong>' + (match.missing.length ? '<small class="resume-ats-missing">Not found: ' + escapeHTML(match.missing.slice(0, 6).join(', ')) + '</small>' : '') : '';
  }

  function resumeAuditText() {
    const parts = [resume.name, resume.title, [resume.email, resume.phone, resume.location, ...(resume.links || []).map((item) => item.label + ' ' + item.url)].filter(Boolean).join(' · ')];
    if (resume.summary) parts.push('PROFILE\n' + resume.summary);
    const experience = (resume.experience || []).filter((item) => Object.values(item).some(Boolean));
    if (experience.length) parts.push('EXPERIENCE\n' + experience.map((item) => [item.role, item.company, item.dates, item.details].filter(Boolean).join('\n')).join('\n'));
    const education = (resume.education || []).filter((item) => Object.values(item).some(Boolean));
    if (education.length) parts.push('EDUCATION\n' + education.map((item) => [item.degree, item.school, item.dates, item.detail].filter(Boolean).join(' · ')).join('\n'));
    if (resume.skills) parts.push('SKILLS\n' + resume.skills);
    const projects = (resume.projects || []).filter((item) => Object.values(item).some(Boolean));
    if (projects.length) parts.push('PROJECTS\n' + projects.map((item) => [item.name, item.detail].filter(Boolean).join('\n')).join('\n'));
    return parts.filter(Boolean).join('\n');
  }

  function updateATS() {
    clearTimeout(atsAuditTimer);
    const requestId = ++atsAuditRequest;
    const resumeText = resumeAuditText();
    const jobDescription = $('#resume-job-description')?.value || '';
    $('#resume-ats-caption').textContent = 'Checking transparent rules…';
    atsAuditTimer = window.setTimeout(async () => {
      try {
        const response = await fetch('/resume/ats-audit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resume_text: resumeText, job_description: jobDescription }) });
        const report = await response.json();
        if (!response.ok) throw new Error(report.detail || 'Rule check unavailable');
        if (requestId === atsAuditRequest) renderATSReport(report);
      } catch {
        if (requestId === atsAuditRequest) {
          $('#resume-ats-caption').textContent = 'Rule check unavailable · try again in a moment';
          $('#resume-ats-checks').textContent = 'The rule-based audit could not reach AURA’s local service.';
        }
      }
    }, 300);
  }

  function checkKeywords() { updateATS(); }

  form.addEventListener('input', collectForm);
  form.addEventListener('click', (event) => {
    const add = event.target.closest('[data-resume-add]');
    if (add) { addRow(add.dataset.resumeAdd);return; }
    const remove = event.target.closest('[data-resume-remove]');
    if (remove) { const row = remove.closest('[data-resume-group]');const kind = row.dataset.resumeGroup;collectForm();resume[kind].splice([...row.parentElement.children].indexOf(row), 1);fillEditor();scheduleSave(); }
  });
  $('#resume-studio-file').addEventListener('change', (event) => { importResume(event.target.files[0]);event.target.value = ''; });
  $('#resume-new-button').addEventListener('click', () => {
    if (Object.values(resume).some((value) => Array.isArray(value) ? value.length > 0 : Boolean(value)) && !window.confirm('Start a fresh resume? Your current saved resume will be replaced.')) return;
    resume = blankResume();fillEditor();scheduleSave();
  });
  $('#resume-export-button').addEventListener('click', () => { collectForm();window.print(); });
  $('#resume-keyword-toggle').addEventListener('click', () => { const panel = $('#resume-keyword-panel');panel.hidden = !panel.hidden;$('#resume-keyword-toggle span').textContent = panel.hidden ? '＋' : '−';if (!panel.hidden) $('#resume-job-description').focus(); });
  $('#resume-job-description').addEventListener('input', checkKeywords);

  const hasLocalDraft = loadSaved();
  fillEditor();
  loadCloudDraft(hasLocalDraft);
})();
