'use strict';

(() => {
  const PAGE_SIZE = 50;
  const REFRESH_MS = 60_000;
  const numberFormat = new Intl.NumberFormat('ru-RU');
  const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  const elements = Object.fromEntries([
    'total-chats', 'total-detail', 'total-members', 'members-detail', 'total-online', 'online-detail',
    'goal-current', 'goal-target', 'goal-progress', 'goal-fill', 'goal-detail', 'heading-count', 'chat-list',
    'search-input', 'sort-select', 'export-button', 'load-more', 'results-detail', 'notice', 'notice-message',
    'retry-button', 'connection-pill', 'connection-label', 'updated-at', 'schedule-detail', 'workflow-link', 'year',
  ].map(id => [id, document.getElementById(id)]));
  const state = { chats: [], target: 1500, generatedAt: null, status: null, category: 'all', query: '', sort: 'members', visible: PAGE_SIZE, loaded: false, loading: false, fetchError: false };

  function count(value) { return Number.isSafeInteger(value) && value >= 0 ? value : null; }
  function date(value) { const result = typeof value === 'string' ? new Date(value) : null; return result && !Number.isNaN(result.getTime()) ? result : null; }
  function formattedDate(value) { const parsed = date(value); return parsed ? dateFormat.format(parsed) : 'нет данных'; }
  function safeUrl(value, host) {
    try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && (!host || url.hostname === host) ? url.href : null; } catch { return null; }
  }
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function normalizeChats(payload) {
    if (!payload || !Array.isArray(payload.chats)) throw new Error('Неверный формат каталога');
    const seenNames = new Set();
    const seenIds = new Set();
    return payload.chats.flatMap(chat => {
      if (!chat || chat.verified !== true || typeof chat.username !== 'string') return [];
      const username = chat.username.replace(/^@/, '').trim();
      const nameKey = username.toLowerCase();
      if (!/^[a-zA-Z][a-zA-Z0-9_]{2,63}$/.test(username) || seenNames.has(nameKey)) return [];
      const id = typeof chat.id === 'string' || Number.isSafeInteger(chat.id) ? String(chat.id) : null;
      if (id && seenIds.has(id)) return [];
      seenNames.add(nameKey);
      if (id) seenIds.add(id);
      return [{ ...chat, username, title: typeof chat.title === 'string' && chat.title.trim() ? chat.title.trim() : `@${username}`, description: typeof chat.description === 'string' ? chat.description : '', category: ['crypto', 'gifts', 'mixed'].includes(chat.category) ? chat.category : 'mixed', members: count(chat.members), online: count(chat.online) }];
    });
  }
  function categoryLabel(category) { return { crypto: 'Криптовалюты', gifts: 'Подарки / NFT', mixed: 'OTC' }[category] || 'OTC'; }
  function currentChats() {
    const query = state.query.toLocaleLowerCase('ru-RU').replace(/^@/, '').trim();
    return state.chats.filter(chat => (state.category === 'all' || chat.category === state.category || chat.category === 'mixed') && (!query || `${chat.title} ${chat.username} ${chat.description}`.toLocaleLowerCase('ru-RU').includes(query))).sort((a, b) => {
      if (state.sort === 'name') return a.title.localeCompare(b.title, 'ru');
      if (state.sort === 'recent') return (date(b.last_checked)?.getTime() || 0) - (date(a.last_checked)?.getTime() || 0) || a.username.localeCompare(b.username);
      return (b[state.sort] ?? -1) - (a[state.sort] ?? -1) || a.username.localeCompare(b.username);
    });
  }
  function sumKnown(field) {
    const known = state.chats.filter(chat => chat[field] !== null);
    return { value: known.length ? known.reduce((sum, chat) => sum + chat[field], 0) : null, known: known.length };
  }
  function renderMetrics() {
    const total = state.chats.length;
    const members = sumKnown('members');
    const online = sumKnown('online');
    elements['total-chats'].textContent = numberFormat.format(total);
    elements['total-detail'].textContent = 'Подтверждённые публичные группы';
    elements['heading-count'].textContent = numberFormat.format(total);
    elements['total-members'].textContent = members.value === null ? '—' : numberFormat.format(members.value);
    elements['members-detail'].textContent = members.known ? `Данные ${numberFormat.format(members.known)} из ${numberFormat.format(total)} чатов` : 'Количество участников пока недоступно';
    elements['total-online'].textContent = online.value === null ? '—' : numberFormat.format(online.value);
    elements['online-detail'].textContent = online.known ? `На момент проверки · ${numberFormat.format(online.known)} из ${numberFormat.format(total)} чатов` : 'Публичные данные об онлайне недоступны';
    elements['goal-current'].textContent = numberFormat.format(total);
    elements['goal-target'].textContent = numberFormat.format(state.target);
    const percent = Math.min(100, total / state.target * 100);
    elements['goal-progress'].setAttribute('aria-valuemax', state.target);
    elements['goal-progress'].setAttribute('aria-valuenow', Math.min(total, state.target));
    elements['goal-fill'].style.width = `${percent}%`;
    elements['goal-detail'].textContent = total >= state.target ? 'Цель достигнута · продолжаем проверку' : `${numberFormat.format(Math.max(0, state.target - total))} чатов до цели`;
    elements['updated-at'].textContent = state.generatedAt ? `Снимок данных: ${formattedDate(state.generatedAt)}` : 'Дата снимка недоступна';
  }
  function renderStatus() {
    const status = state.status;
    const statusState = state.fetchError ? 'error' : status?.state || (state.loaded ? 'ok' : 'waiting');
    const labels = { ok: 'Каталог обновлён', partial: 'Частичное обновление', error: state.fetchError ? 'Нет связи с данными' : 'Ошибка сборщика', waiting: 'Ожидаем первый сбор' };
    elements['connection-pill'].dataset.state = statusState;
    elements['connection-label'].textContent = labels[statusState] || 'Данные загружены';
    const minutes = count(status?.refresh_minutes);
    if (minutes && minutes > 0) elements['schedule-detail'].textContent = `плановый интервал — ${numberFormat.format(minutes)} мин.`;
    const runUrl = safeUrl(status?.run_url, 'github.com');
    elements['workflow-link'].hidden = !runUrl;
    if (runUrl) elements['workflow-link'].href = runUrl;
  }
  function makeChatRow(chat, index) {
    const url = `https://t.me/${chat.username}`;
    const row = node('article', 'chat-row');
    const community = node('div', 'community');
    const avatar = node('span', 'community-avatar', chat.title.replace(/[^\p{L}\p{N}]/gu, '').slice(0, 2).toLocaleUpperCase('ru-RU') || 'OT');
    avatar.dataset.tone = String(index % 4);
    avatar.setAttribute('aria-hidden', 'true');
    const copy = node('div', 'community-copy');
    const title = node('a', 'community-title', chat.title);
    title.href = url; title.target = '_blank'; title.rel = 'noopener noreferrer'; title.title = chat.description || chat.title;
    const subline = node('div', 'community-subline');
    subline.append(node('span', 'community-username', `@${chat.username}`), node('span', 'community-category', categoryLabel(chat.category)));
    copy.append(title, subline); community.append(avatar, copy);
    const members = node('div', 'members-cell');
    members.append(node('span', 'mobile-cell-label', 'УЧАСТНИКИ'), node('span', chat.members === null ? 'cell-muted' : 'cell-value', chat.members === null ? 'нет данных' : numberFormat.format(chat.members)));
    const online = node('div', 'online-cell');
    online.append(node('span', 'mobile-cell-label', 'ОНЛАЙН'));
    if (chat.online === null) online.append(node('span', 'cell-muted', 'нет данных'));
    else { const onlineNumber = node('span', 'cell-value online-value'); onlineNumber.append(node('span', 'status-dot'), document.createTextNode(numberFormat.format(chat.online))); online.append(onlineNumber); }
    const checked = node('div', 'checked-cell');
    const checkedTime = node('time', '', formattedDate(chat.last_checked));
    if (date(chat.last_checked)) checkedTime.dateTime = new Date(chat.last_checked).toISOString();
    checked.append(checkedTime);
    const evidence = safeUrl(chat.evidence_url);
    if (evidence) { const source = node('a', 'evidence-link', 'Источник ↗'); source.href = evidence; source.target = '_blank'; source.rel = 'noopener noreferrer'; checked.append(source); }
    const open = node('a', 'chat-open', '↗');
    open.href = url; open.target = '_blank'; open.rel = 'noopener noreferrer'; open.setAttribute('aria-label', `Открыть ${chat.title} в Telegram`);
    row.append(community, members, online, checked, open);
    return row;
  }
  function renderList() {
    const chats = currentChats();
    const visible = chats.slice(0, state.visible);
    const fragment = document.createDocumentFragment();
    if (!chats.length) {
      const empty = node('div', 'empty-state');
      const filtered = state.chats.length > 0;
      empty.append(node('span', 'empty-icon', filtered ? '⌕' : '◎'), node('h3', '', filtered ? 'Ничего не нашлось' : 'Каталог только начинает расти'), node('p', '', filtered ? 'Попробуйте другое название или выберите все категории.' : 'Подтверждённые чаты появятся здесь после успешной проверки сборщиком. Счётчик показывает только реальные записи.'));
      fragment.append(empty);
    } else visible.forEach((chat, index) => fragment.append(makeChatRow(chat, index)));
    elements['chat-list'].replaceChildren(fragment);
    elements['chat-list'].setAttribute('aria-busy', 'false');
    elements['results-detail'].textContent = `Показано ${numberFormat.format(visible.length)} из ${numberFormat.format(chats.length)}${chats.length !== state.chats.length ? ` · всего в каталоге ${numberFormat.format(state.chats.length)}` : ''}`;
    elements['load-more'].hidden = visible.length >= chats.length;
    elements['export-button'].disabled = !chats.length;
  }
  function showNotice(message, level = 'warning', allowRetry = true) {
    elements.notice.hidden = !message;
    elements.notice.dataset.level = level;
    elements['notice-message'].textContent = message;
    elements['retry-button'].hidden = !allowRetry;
  }
  async function fetchJson(path) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 25_000);
    try {
      const response = await fetch(`${path}?t=${Date.now()}`, { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally { clearTimeout(timeout); }
  }
  async function refresh() {
    if (state.loading) return;
    state.loading = true;
    elements['retry-button'].disabled = true;
    try {
      const [chatsResult, statusResult] = await Promise.allSettled([fetchJson('./data/chats.json'), fetchJson('./data/status.json')]);
      if (statusResult.status === 'fulfilled' && statusResult.value && typeof statusResult.value === 'object' && !Array.isArray(statusResult.value)) state.status = statusResult.value;
      if (chatsResult.status !== 'fulfilled') throw new Error('Каталог недоступен');
      state.chats = normalizeChats(chatsResult.value);
      state.target = count(chatsResult.value.target) > 0 ? chatsResult.value.target : 1500;
      state.generatedAt = date(chatsResult.value.generated_at) ? chatsResult.value.generated_at : null;
      state.loaded = true;
      state.fetchError = false;
      renderMetrics(); renderList(); renderStatus();
      if (state.status?.state === 'error') showNotice('Последний запуск сборщика завершился с ошибкой. Показан последний опубликованный каталог. Подробности доступны по ссылке на запуск.', 'warning', false);
      else if (state.status?.state === 'partial') showNotice('Сбор завершён частично. Для части чатов проверка не удалась; время успешной проверки указано у каждой записи.', 'warning', false);
      else if (statusResult.status === 'rejected') showNotice('Каталог загружен, но статус последнего запуска пока недоступен.');
      else showNotice('');
    } catch {
      state.fetchError = true;
      renderStatus();
      showNotice(state.loaded ? 'Не удалось получить обновление. Сохраняем последний загруженный список; следующая попытка — через минуту.' : 'Данные пока недоступны. Если проект опубликован впервые, дождитесь завершения первого запуска сборщика.', 'error');
      elements['chat-list'].setAttribute('aria-busy', 'false');
      if (!state.loaded) {
        const empty = node('div', 'empty-state');
        empty.append(node('span', 'empty-icon', '◎'), node('h3', '', 'Ожидаем опубликованный каталог'), node('p', '', 'Проверяем данные каждую минуту. Чаты появятся после первого успешного сбора.'));
        elements['chat-list'].replaceChildren(empty);
      }
    } finally { state.loading = false; elements['retry-button'].disabled = false; }
  }
  function csvCell(value) {
    let text = String(value ?? '');
    if (/^[\s\u0000-\u001f]*[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  }
  function exportCsv() {
    const rows = [['Название', 'Username', 'Категория', 'Участники', 'Онлайн', 'Проверено', 'Ссылка'], ...currentChats().map(chat => [chat.title, chat.username, categoryLabel(chat.category), chat.members, chat.online, chat.last_checked, `https://t.me/${chat.username}`])];
    const csv = '\uFEFF' + rows.map(row => row.map(csvCell).join(';')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = node('a'); link.href = url; link.download = `otc-radar-${new Date().toISOString().slice(0, 10)}.csv`; document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  elements['search-input'].addEventListener('input', event => { state.query = event.target.value; state.visible = PAGE_SIZE; if (state.loaded) renderList(); });
  elements['sort-select'].addEventListener('change', event => { state.sort = event.target.value; state.visible = PAGE_SIZE; if (state.loaded) renderList(); });
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    state.category = button.dataset.category; state.visible = PAGE_SIZE;
    document.querySelectorAll('[data-category]').forEach(tab => { const active = tab === button; tab.classList.toggle('active', active); tab.setAttribute('aria-pressed', String(active)); });
    if (state.loaded) renderList();
  }));
  elements['load-more'].addEventListener('click', () => { state.visible += PAGE_SIZE; renderList(); });
  elements['retry-button'].addEventListener('click', refresh);
  elements['export-button'].addEventListener('click', exportCsv);
  document.addEventListener('keydown', event => { if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName) && !document.activeElement?.isContentEditable) { event.preventDefault(); elements['search-input'].focus(); } });
  elements.year.textContent = new Date().getFullYear();
  refresh();
  setInterval(refresh, REFRESH_MS);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
