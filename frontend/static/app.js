/* ============================================================
   Gema — Frontend SPA
   ============================================================ */

const API = '';   // Same origin — nginx proxies /api/*

/* ── State ──────────────────────────────────────────────────────── */
const state = {
  page: 'dashboard',
  models: [],
  agents: [],
  conversations: [],
  knowledgeBases: [],
  tasks: [],
  mcpServers: [],
  stats: {},
  // Chat
  currentConversationId: null,
  currentMessages: [],
  selectedModel: 'gpt-4o',
  selectedAgentId: null,
  chatStreaming: false,
  pendingDataFile: null,
};

/* ── Utilities ───────────────────────────────────────────────────── */
async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API error');
  }
  return res.json();
}

function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icon = type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ';
  el.innerHTML = `<span class="font-bold">${icon}</span><span>${msg}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function openModal(title, bodyHtml) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function closeModal(e) {
  if (!e || e.target === document.getElementById('modal-overlay')) {
    document.getElementById('modal-overlay').classList.add('hidden');
  }
}

function statusBadge(status) {
  const map = {
    completed: 'badge-green', running: 'badge-yellow', failed: 'badge-red',
    pending: 'badge-blue', ready: 'badge-green', processing: 'badge-yellow',
  };
  return `<span class="badge ${map[status] || 'badge-gray'}">${status}</span>`;
}

function timeAgo(dateStr) {
  const diff = (Date.now() - new Date(dateStr)) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function truncate(str, n = 60) {
  return str && str.length > n ? str.slice(0, n) + '…' : str || '';
}

/* ── Navigation ──────────────────────────────────────────────────── */
function navigate(page) {
  state.page = page;

  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.page === page);
  });

  const titles = {
    dashboard: ['Dashboard', 'Overview of your AI workspace'],
    chat: ['Chat', 'Talk to any AI model or agent'],
    agents: ['Agents', 'Create and manage AI agents'],
    knowledge: ['Knowledge Base', 'Upload documents for RAG'],
    tasks: ['Tasks', 'Automate workflows with AI'],
    models: ['Models', 'Browse available AI models'],
    mcp: ['MCP Servers', 'Connect external tools via Model Context Protocol'],
  };
  const [title, subtitle] = titles[page] || [page, ''];
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = subtitle;

  const pages = { dashboard, chat, agents, knowledge, tasks, models, mcp };
  if (pages[page]) pages[page]();
}

/* ════════════════════════════════════════════════════════════════
   DASHBOARD
   ════════════════════════════════════════════════════════════════ */
async function dashboard() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = '';
  content.innerHTML = `<div class="flex items-center gap-2"><div class="spinner"></div><span class="text-slate-400">Loading…</span></div>`;

  try {
    const stats = await api('/api/stats');
    state.stats = stats;

    content.innerHTML = `
      <!-- Stats grid -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        ${statCard('Available Models', stats.available_models, 'Across all providers')}
        ${statCard('Agents', stats.agents, 'Active AI assistants')}
        ${statCard('Conversations', stats.conversations, `${stats.messages} messages`)}
        ${statCard('Tasks Done', stats.tasks_completed, `${stats.tasks} total`)}
      </div>
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        ${statCard('Knowledge Bases', stats.knowledge_bases, `${stats.documents} documents`)}
      </div>

      <!-- Quick actions -->
      <h2 class="text-lg font-semibold text-white mb-4">Quick Start</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        ${quickAction('💬', 'Start a Chat', 'Talk to any of 30+ AI models', 'chat')}
        ${quickAction('🤖', 'Create an Agent', 'Build a custom AI assistant', 'agents')}
        ${quickAction('📚', 'Add Knowledge', 'Upload docs for RAG search', 'knowledge')}
        ${quickAction('⚡', 'Run a Task', 'Automate with AI workflows', 'tasks')}
        ${quickAction('🔍', 'Browse Models', 'See all connected providers', 'models')}
        ${quickAction('�', 'MCP Servers', 'Connect external tool servers', 'mcp')}
        ${quickAction('�📖', 'API Docs', 'Explore the REST API', null, '/docs')}
      </div>
    `;
  } catch (e) {
    content.innerHTML = `<div class="text-red-400">Error loading dashboard: ${e.message}</div>`;
  }
}

function statCard(label, value, sub) {
  return `<div class="stat-card">
    <div class="label">${label}</div>
    <div class="value">${value ?? '—'}</div>
    <div class="sub">${sub}</div>
  </div>`;
}

function quickAction(icon, title, desc, page, href) {
  const action = href
    ? `onclick="window.open('${href}','_blank')"`
    : `onclick="navigate('${page}')"`;
  return `<div class="card p-5 cursor-pointer hover:border-indigo-500 transition-colors" ${action}>
    <div class="text-3xl mb-2">${icon}</div>
    <div class="font-semibold text-white mb-1">${title}</div>
    <div class="text-sm text-slate-400">${desc}</div>
  </div>`;
}

/* ════════════════════════════════════════════════════════════════
   CHAT
   ════════════════════════════════════════════════════════════════ */
async function chat() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = `
    <button class="btn btn-secondary btn-sm" onclick="newConversation()">+ New Chat</button>
  `;

  // Fetch data in parallel
  const [modelsData, agentsData, convsData] = await Promise.all([
    api('/api/models/').catch(() => ({ models: [] })),
    api('/api/agents/').catch(() => []),
    api('/api/chat/conversations').catch(() => []),
  ]);

  state.models = modelsData.models;
  state.agents = agentsData;
  state.conversations = convsData;

  const availableModels = state.models.filter(m => m.available);

  content.innerHTML = `
    <div class="flex h-full gap-4" style="height: calc(100vh - 11rem)">
      <!-- Sidebar: Conversations -->
      <div class="w-64 flex-shrink-0 flex flex-col gap-3">
        <div class="card p-3">
          <div class="form-label mb-2">Model / Agent</div>
          <select class="form-select mb-2" id="chat-model-select" onchange="state.selectedModel = this.value; state.selectedAgentId = null;">
            <optgroup label="── Models">
              ${availableModels.map(m => `<option value="${m.id}" ${m.id === state.selectedModel ? 'selected' : ''}>${m.name}</option>`).join('')}
            </optgroup>
          </select>
          ${state.agents.length ? `
          <select class="form-select" id="chat-agent-select" onchange="state.selectedAgentId = this.value || null">
            <option value="">No agent</option>
            ${state.agents.map(a => `<option value="${a.id}">${a.name}</option>`).join('')}
          </select>` : ''}
        </div>

        <div class="card flex-1 overflow-y-auto p-2">
          <div class="text-xs text-slate-500 px-2 py-1 uppercase font-semibold tracking-wide mb-1">History</div>
          <div id="conv-list">
            ${state.conversations.length === 0
              ? '<div class="text-xs text-slate-500 px-2">No conversations yet</div>'
              : state.conversations.map(c => `
                <div class="px-2 py-2 rounded-lg cursor-pointer hover:bg-slate-700 text-sm flex items-center justify-between group ${c.id === state.currentConversationId ? 'bg-slate-700' : ''}" onclick="loadConversation('${c.id}')">
                  <span class="truncate text-slate-300">${truncate(c.title, 28)}</span>
                  <button class="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-opacity" onclick="event.stopPropagation(); deleteConversation('${c.id}')">✕</button>
                </div>`).join('')}
          </div>
        </div>
      </div>

      <!-- Chat window -->
      <div class="flex-1 flex flex-col card overflow-hidden">
        <div id="chat-messages" class="flex-1 overflow-y-auto p-4 space-y-3 flex flex-col">
          <div class="m-auto text-center text-slate-500">
            <div class="text-5xl mb-3">💬</div>
            <div class="font-semibold text-slate-400">Start a conversation</div>
            <div class="text-sm mt-1">Select a model or agent and send a message</div>
          </div>
        </div>

        <!-- Input area -->
        <div class="border-t border-slate-700 p-4">
          <div id="data-file-badge-wrap" class="mb-2"></div>
          <div class="flex gap-2 items-end">
            <label class="btn btn-secondary btn-sm self-end cursor-pointer" title="Attach CSV or JSON data file" style="padding:0.45rem 0.65rem;flex-shrink:0">
              <svg xmlns="http://www.w3.org/2000/svg" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"/></svg>
              <input type="file" id="data-file-input" accept=".csv,.json,.tsv" class="hidden" onchange="handleDataFile(event)">
            </label>
            <textarea
              id="chat-input"
              class="form-textarea flex-1"
              placeholder="Ask anything, or attach a CSV/JSON to generate a dashboard…"
              rows="2"
              onkeydown="handleChatKey(event)"
              style="resize:none"
            ></textarea>
            <button id="chat-send-btn" class="btn btn-primary self-end" onclick="sendMessage()">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

async function newConversation() {
  try {
    const conv = await api('/api/chat/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: 'New Conversation', model: state.selectedModel }),
    });
    state.currentConversationId = conv.id;
    state.currentMessages = [];
    await chat();
    await loadConversation(conv.id);
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function loadConversation(id) {
  state.currentConversationId = id;
  const msgs = await api(`/api/chat/conversations/${id}/messages`).catch(() => []);
  state.currentMessages = msgs;

  const container = document.getElementById('chat-messages');
  if (!container) return;

  container.innerHTML = '';
  if (msgs.length === 0) {
    container.innerHTML = `<div class="m-auto text-center text-slate-500"><div class="text-3xl mb-2">👋</div><div>No messages yet — say hello!</div></div>`;
  } else {
    msgs.forEach(m => appendMessageBubble(m.role, m.content));
  }
  container.scrollTop = container.scrollHeight;

  // Update conv list highlight
  document.querySelectorAll('#conv-list > div').forEach(el => {
    el.classList.toggle('bg-slate-700', el.getAttribute('onclick')?.includes(id));
  });
}

async function deleteConversation(id) {
  if (!confirm('Delete this conversation?')) return;
  await api(`/api/chat/conversations/${id}`, { method: 'DELETE' }).catch(() => {});
  if (state.currentConversationId === id) {
    state.currentConversationId = null;
    state.currentMessages = [];
  }
  await chat();
}

function appendMessageBubble(role, content) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const isUser = role === 'user';

  // Remove placeholder
  const placeholder = container.querySelector('.m-auto');
  if (placeholder) placeholder.remove();

  const wrapper = document.createElement('div');
  wrapper.className = `flex ${isUser ? 'justify-end' : 'justify-start'} gap-2`;

  if (!isUser) {
    wrapper.innerHTML = `
      <div class="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold mt-1">G</div>
      <div class="chat-bubble assistant" id="bubble-${Date.now()}">${marked.parse(content || '')}</div>
    `;
  } else {
    wrapper.innerHTML = `<div class="chat-bubble user">${escapeHtml(content)}</div>`;
  }

  container.appendChild(wrapper);
  container.scrollTop = container.scrollHeight;
  const bubble = wrapper.querySelector('.chat-bubble');
  if (!isUser && content) injectArtifacts(bubble);
  return bubble;
}

function escapeHtml(text) {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function sendMessage() {
  if (state.chatStreaming) return;
  const input = document.getElementById('chat-input');
  let content = input.value.trim();
  if (!content && !state.pendingDataFile) return;

  input.value = '';

  if (state.pendingDataFile) {
    const { name, dataText } = state.pendingDataFile;
    const trimmed = dataText.length > 8000 ? dataText.slice(0, 8000) + '\n... [truncated]' : dataText;
    const userQuery = content || 'Please analyse this data and create an interactive HTML dashboard with charts to visualise it. Use Chart.js from CDN and make it look professional.';
    content = `${userQuery}\n\n**Attached: ${name}**\n\`\`\`\n${trimmed}\n\`\`\``;
    clearDataFile();
  }
  const sendBtn = document.getElementById('chat-send-btn');
  sendBtn.disabled = true;
  state.chatStreaming = true;

  // Ensure we have a conversation
  if (!state.currentConversationId) {
    try {
      const conv = await api('/api/chat/conversations', {
        method: 'POST',
        body: JSON.stringify({
          title: content.slice(0, 50),
          model: state.selectedModel,
          agent_id: state.selectedAgentId || undefined,
        }),
      });
      state.currentConversationId = conv.id;
    } catch (e) {
      toast('Failed to create conversation', 'error');
      state.chatStreaming = false;
      sendBtn.disabled = false;
      return;
    }
  }

  // Show user bubble
  appendMessageBubble('user', content);

  // Show assistant bubble with spinner
  const container = document.getElementById('chat-messages');
  const thinkingWrapper = document.createElement('div');
  thinkingWrapper.className = 'flex justify-start gap-2';
  thinkingWrapper.innerHTML = `
    <div class="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex-shrink-0 flex items-center justify-center text-white text-xs font-bold mt-1">G</div>
    <div class="chat-bubble assistant flex items-center gap-2"><div class="spinner"></div><span class="text-slate-400 text-sm">Thinking…</span></div>
  `;
  container.appendChild(thinkingWrapper);
  container.scrollTop = container.scrollHeight;

  const agentId = state.selectedAgentId || null;
  const model = agentId ? undefined : state.selectedModel;

  const payload = {
    messages: [{ role: 'user', content }],
    stream: true,
    conversation_id: state.currentConversationId,
    ...(agentId ? { agent_id: agentId } : { model }),
  };

  try {
    const res = await fetch(`${API}/api/chat/completions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      throw new Error((await res.json().catch(() => ({}))).detail || 'Request failed');
    }

    // Replace thinking bubble with real content
    thinkingWrapper.remove();
    const assistantBubble = appendMessageBubble('assistant', '');
    let fullText = '';

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const lines = decoder.decode(value).split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') break;
        try {
          const { content: chunk } = JSON.parse(data);
          fullText += chunk;
          assistantBubble.innerHTML = marked.parse(fullText);
          container.scrollTop = container.scrollHeight;
        } catch {}
      }
    }
    injectArtifacts(assistantBubble);
  } catch (e) {
    thinkingWrapper.remove();
    appendMessageBubble('assistant', `⚠️ Error: ${e.message}`);
    toast(e.message, 'error');
  } finally {
    state.chatStreaming = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

/* ════════════════════════════════════════════════════════════════
   AGENTS
   ════════════════════════════════════════════════════════════════ */
async function agents() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = `
    <button class="btn btn-secondary" onclick="createPresetAgent('data-analyst')">📊 Data Analyst Preset</button>
    <button class="btn btn-primary" onclick="showAgentModal()">+ New Agent</button>
  `;

  const [agentsData, modelsData, mcpData] = await Promise.all([
    api('/api/agents/').catch(() => []),
    api('/api/models/').catch(() => ({ models: [] })),
    api('/api/mcp/').catch(() => []),
  ]);
  state.agents = agentsData;
  state.models = modelsData.models;
  state.mcpServers = mcpData;

  content.innerHTML = agentsData.length === 0
    ? emptyState('🤖', 'No agents yet', 'Create your first AI agent to get started.', 'showAgentModal()')
    : `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        ${agentsData.map(agentCard).join('')}
      </div>`;
}

const AGENT_PRESETS = {
  'data-analyst': {
    name: 'Data Analyst',
    description: 'Analyses data and generates interactive HTML dashboards with charts',
    system_prompt: `You are an expert data analyst and data visualisation engineer.

When given data (CSV, JSON, or tabular text):
1. Analyse the data structure, types, and key metrics.
2. Generate a complete, self-contained HTML page (with embedded CSS and JavaScript) that visualises the data interactively using Chart.js loaded from CDN.
3. The dashboard should include: a title, summary statistics cards, at least 2 relevant chart types, and a clean professional dark theme.
4. Always wrap your HTML output in a fenced \`\`\`html code block so it renders as a live preview.
5. After the HTML, briefly explain your key findings.

When asked a general data question without a file, answer it clearly with insights, formulas, or example code as needed.`,
  },
};

async function createPresetAgent(presetKey) {
  const preset = AGENT_PRESETS[presetKey];
  if (!preset) return;
  try {
    const modelsData = await api('/api/models/').catch(() => ({ models: [] }));
    const firstModel = (modelsData.models || []).find(m => m.available);
    await api('/api/agents/', {
      method: 'POST',
      body: JSON.stringify({
        name: preset.name,
        description: preset.description,
        system_prompt: preset.system_prompt,
        model: firstModel?.id || 'gpt-4o',
        temperature: 0.3,
        max_tokens: 4096,
        knowledge_base_ids: [],
        mcp_server_ids: [],
      }),
    });
    toast(`"${preset.name}" agent created!`, 'success');
    agents();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function agentCard(a) {
  return `
    <div class="card p-5 flex flex-col gap-3">
      <div class="flex items-start justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg" style="background:${a.avatar_color}">${a.name[0].toUpperCase()}</div>
          <div>
            <div class="font-semibold text-white">${escapeHtml(a.name)}</div>
            <div class="text-xs text-slate-400">${a.model}</div>
          </div>
        </div>
        <span class="badge ${a.is_active ? 'badge-green' : 'badge-gray'}">${a.is_active ? 'active' : 'inactive'}</span>
      </div>
      ${a.description ? `<p class="text-sm text-slate-400">${truncate(a.description, 80)}</p>` : ''}
      <div class="text-xs text-slate-500 bg-slate-900 rounded-lg p-2 line-clamp-2 font-mono">${truncate(a.system_prompt, 100)}</div>
      <div class="flex gap-2 mt-auto">
        <button class="btn btn-secondary btn-sm flex-1" onclick="chatWithAgent('${a.id}')">💬 Chat</button>
        <button class="btn btn-ghost btn-sm" onclick="showAgentModal(${JSON.stringify(a).replace(/"/g, '&quot;')})">Edit</button>
        <button class="btn btn-ghost btn-sm text-red-400" onclick="deleteAgent('${a.id}')">Delete</button>
      </div>
    </div>`;
}

function chatWithAgent(agentId) {
  state.selectedAgentId = agentId;
  navigate('chat');
}

function showAgentModal(agent) {
  const isEdit = !!agent;
  const availableModels = state.models.filter(m => m.available);

  openModal(isEdit ? 'Edit Agent' : 'New Agent', `
    <form onsubmit="saveAgent(event, '${isEdit ? agent.id : ''}')">
      <div class="form-group">
        <label class="form-label">Name *</label>
        <input class="form-input" name="name" required value="${isEdit ? escapeHtml(agent.name) : ''}" placeholder="My Assistant">
      </div>
      <div class="form-group">
        <label class="form-label">Description</label>
        <input class="form-input" name="description" value="${isEdit ? escapeHtml(agent.description || '') : ''}" placeholder="What does this agent do?">
      </div>
      <div class="form-group">
        <label class="form-label">Model *</label>
        <select class="form-select" name="model">
          ${availableModels.map(m => `<option value="${m.id}" ${isEdit && agent.model === m.id ? 'selected' : ''}>${m.name} (${m.provider})</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">System Prompt</label>
        <textarea class="form-textarea" name="system_prompt" rows="4" placeholder="You are a helpful assistant.">${isEdit ? escapeHtml(agent.system_prompt || '') : 'You are a helpful assistant.'}</textarea>
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div class="form-group">
          <label class="form-label">Temperature</label>
          <input class="form-input" name="temperature" type="number" step="0.1" min="0" max="2" value="${isEdit ? agent.temperature : 0.7}">
        </div>
        <div class="form-group">
          <label class="form-label">Max Tokens</label>
          <input class="form-input" name="max_tokens" type="number" min="1" max="200000" value="${isEdit ? agent.max_tokens : 4096}">
        </div>
      </div>
      ${state.mcpServers.length ? `
      <div class="form-group">
        <label class="form-label">MCP Servers (tool calling)</label>
        <div class="space-y-1 max-h-32 overflow-y-auto border border-slate-600 rounded-lg p-2">
          ${state.mcpServers.map(s => `
            <label class="flex items-center gap-2 cursor-pointer hover:bg-slate-700 rounded px-2 py-1">
              <input type="checkbox" name="mcp_server_ids" value="${s.id}"
                ${isEdit && agent.mcp_server_ids && agent.mcp_server_ids.includes(s.id) ? 'checked' : ''}>
              <span class="text-sm text-slate-300">${escapeHtml(s.name)}</span>
              <span class="text-xs text-slate-500">(${s.transport})</span>
            </label>`).join('')}
        </div>
      </div>` : ''}
      <div class="flex gap-3 justify-end mt-4">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">${isEdit ? 'Save Changes' : 'Create Agent'}</button>
      </div>
    </form>
  `);
}

async function saveAgent(e, agentId) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    name: fd.get('name'),
    description: fd.get('description') || null,
    model: fd.get('model'),
    system_prompt: fd.get('system_prompt'),
    temperature: parseFloat(fd.get('temperature')),
    max_tokens: parseInt(fd.get('max_tokens')),
    mcp_server_ids: fd.getAll('mcp_server_ids'),
  };
  try {
    if (agentId) {
      await api(`/api/agents/${agentId}`, { method: 'PATCH', body: JSON.stringify(body) });
      toast('Agent updated', 'success');
    } else {
      await api('/api/agents/', { method: 'POST', body: JSON.stringify(body) });
      toast('Agent created', 'success');
    }
    closeModal();
    agents();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteAgent(id) {
  if (!confirm('Delete this agent?')) return;
  try {
    await api(`/api/agents/${id}`, { method: 'DELETE' });
    toast('Agent deleted', 'success');
    agents();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ════════════════════════════════════════════════════════════════
   KNOWLEDGE BASE
   ════════════════════════════════════════════════════════════════ */
async function knowledge() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = `
    <button class="btn btn-primary" onclick="showKbModal()">+ New Knowledge Base</button>
  `;

  const kbs = await api('/api/knowledge/').catch(() => []);
  state.knowledgeBases = kbs;

  content.innerHTML = kbs.length === 0
    ? emptyState('📚', 'No knowledge bases', 'Upload documents and let your agents search them.', 'showKbModal()')
    : `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        ${kbs.map(kbCard).join('')}
      </div>`;
}

function kbCard(kb) {
  return `
    <div class="card p-5">
      <div class="flex items-start justify-between mb-3">
        <div>
          <div class="font-semibold text-white text-lg">${escapeHtml(kb.name)}</div>
          ${kb.description ? `<div class="text-sm text-slate-400 mt-1">${escapeHtml(kb.description)}</div>` : ''}
        </div>
        <span class="text-2xl">📚</span>
      </div>
      <div class="text-sm text-slate-400 mb-4">${kb.document_count} document${kb.document_count !== 1 ? 's' : ''}</div>
      <div class="flex gap-2">
        <button class="btn btn-secondary btn-sm flex-1" onclick="showKbDocuments('${kb.id}', '${escapeHtml(kb.name)}')">View Docs</button>
        <button class="btn btn-ghost btn-sm" onclick="uploadDocument('${kb.id}')">Upload</button>
        <button class="btn btn-ghost btn-sm text-red-400" onclick="deleteKb('${kb.id}')">Delete</button>
      </div>
    </div>`;
}

function showKbModal() {
  openModal('New Knowledge Base', `
    <form onsubmit="saveKb(event)">
      <div class="form-group">
        <label class="form-label">Name *</label>
        <input class="form-input" name="name" required placeholder="My Knowledge Base">
      </div>
      <div class="form-group">
        <label class="form-label">Description</label>
        <textarea class="form-textarea" name="description" placeholder="What documents does this contain?"></textarea>
      </div>
      <div class="flex gap-3 justify-end mt-4">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Create</button>
      </div>
    </form>
  `);
}

async function saveKb(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    await api('/api/knowledge/', {
      method: 'POST',
      body: JSON.stringify({ name: fd.get('name'), description: fd.get('description') || null }),
    });
    toast('Knowledge base created', 'success');
    closeModal();
    knowledge();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteKb(id) {
  if (!confirm('Delete this knowledge base and all its documents?')) return;
  try {
    await api(`/api/knowledge/${id}`, { method: 'DELETE' });
    toast('Knowledge base deleted', 'success');
    knowledge();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function showKbDocuments(kbId, kbName) {
  const docs = await api(`/api/knowledge/${kbId}/documents`).catch(() => []);
  openModal(`Documents — ${kbName}`, `
    <div class="space-y-2 max-h-96 overflow-y-auto mb-4">
      ${docs.length === 0
        ? '<div class="text-slate-400 text-sm text-center py-4">No documents yet</div>'
        : docs.map(d => `
          <div class="flex items-center justify-between bg-slate-900 rounded-lg p-3">
            <div>
              <div class="text-sm text-white font-medium">${escapeHtml(d.filename)}</div>
              <div class="text-xs text-slate-500">${d.chunks_count} chunks · ${statusBadge(d.status)}</div>
            </div>
            <button class="btn btn-ghost btn-sm text-red-400" onclick="deleteDoc('${kbId}','${d.id}')">✕</button>
          </div>`).join('')}
    </div>
    <button class="btn btn-primary w-full" onclick="uploadDocument('${kbId}')">+ Upload Document</button>
  `);
}

function uploadDocument(kbId) {
  openModal('Upload Document', `
    <form onsubmit="submitUpload(event, '${kbId}')">
      <div class="form-group">
        <label class="form-label">File</label>
        <input type="file" class="form-input" name="file" accept=".pdf,.txt,.md,.docx,.csv,.json" required>
        <div class="text-xs text-slate-500 mt-1">Supported: PDF, TXT, MD, DOCX, CSV, JSON (max 50 MB)</div>
      </div>
      <div class="flex gap-3 justify-end mt-4">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Upload & Process</button>
      </div>
    </form>
  `);
}

async function submitUpload(e, kbId) {
  e.preventDefault();
  const fd = new FormData(e.target);
  try {
    const res = await fetch(`${API}/api/knowledge/${kbId}/documents`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed');
    toast('Document uploaded and processing…', 'success');
    closeModal();
    knowledge();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteDoc(kbId, docId) {
  if (!confirm('Delete this document?')) return;
  try {
    await api(`/api/knowledge/${kbId}/documents/${docId}`, { method: 'DELETE' });
    toast('Document deleted', 'success');
    closeModal();
    knowledge();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ════════════════════════════════════════════════════════════════
   TASKS
   ════════════════════════════════════════════════════════════════ */
async function tasks() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = `
    <button class="btn btn-primary" onclick="showTaskModal()">+ New Task</button>
  `;

  const [tasksData, agentsData] = await Promise.all([
    api('/api/tasks/').catch(() => []),
    api('/api/agents/').catch(() => []),
  ]);
  state.tasks = tasksData;
  state.agents = agentsData;

  content.innerHTML = `
    <div class="card overflow-hidden">
      <table class="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Agent</th>
            <th>Status</th>
            <th>Last Run</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${tasksData.length === 0
            ? `<tr><td colspan="5" class="text-center text-slate-500 py-8">No tasks yet. <button class="text-indigo-400 hover:underline" onclick="showTaskModal()">Create one</button></td></tr>`
            : tasksData.map(taskRow).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function taskRow(t) {
  const agentName = state.agents.find(a => a.id === t.agent_id)?.name || '—';
  return `<tr>
    <td>
      <div class="font-medium text-white">${escapeHtml(t.name)}</div>
      ${t.description ? `<div class="text-xs text-slate-500">${truncate(t.description, 50)}</div>` : ''}
    </td>
    <td>${agentName}</td>
    <td>${statusBadge(t.status)}</td>
    <td class="text-slate-500 text-xs">${t.updated_at ? timeAgo(t.updated_at) : '—'}</td>
    <td>
      <div class="flex gap-2">
        <button class="btn btn-secondary btn-sm" onclick="runTask('${t.id}')">▶ Run</button>
        <button class="btn btn-ghost btn-sm" onclick="viewTaskOutput('${t.id}')">Output</button>
        <button class="btn btn-ghost btn-sm text-red-400" onclick="deleteTask('${t.id}')">Del</button>
      </div>
    </td>
  </tr>`;
}

function showTaskModal() {
  openModal('New Task', `
    <form onsubmit="saveTask(event)">
      <div class="form-group">
        <label class="form-label">Name *</label>
        <input class="form-input" name="name" required placeholder="Summarise weekly report">
      </div>
      <div class="form-group">
        <label class="form-label">Description</label>
        <input class="form-input" name="description" placeholder="What does this task do?">
      </div>
      <div class="form-group">
        <label class="form-label">Agent</label>
        <select class="form-select" name="agent_id">
          <option value="">No agent (uses default model)</option>
          ${state.agents.map(a => `<option value="${a.id}">${a.name}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Prompt Template *</label>
        <textarea class="form-textarea" name="prompt_template" rows="5" required
          placeholder="Summarise the following text in 3 bullet points:&#10;&#10;{{text}}"></textarea>
        <div class="text-xs text-slate-500 mt-1">Use <code class="bg-slate-900 px-1 rounded">{{variable}}</code> for dynamic inputs</div>
      </div>
      <div class="flex gap-3 justify-end mt-4">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">Create Task</button>
      </div>
    </form>
  `);
}

async function saveTask(e) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = {
    name: fd.get('name'),
    description: fd.get('description') || null,
    agent_id: fd.get('agent_id') || null,
    prompt_template: fd.get('prompt_template'),
    input_data: {},
  };
  try {
    await api('/api/tasks/', { method: 'POST', body: JSON.stringify(body) });
    toast('Task created', 'success');
    closeModal();
    tasks();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function runTask(id) {
  const task = state.tasks.find(t => t.id === id);
  if (!task) return;

  // Parse template variables
  const vars = [...(task.prompt_template.match(/\{\{(\w+)\}\}/g) || [])]
    .map(v => v.replace(/\{\{|\}\}/g, ''));

  if (vars.length > 0) {
    const inputs = vars.map(v => `
      <div class="form-group">
        <label class="form-label">${v}</label>
        <input class="form-input" name="${v}" placeholder="Value for {{${v}}}">
      </div>`).join('');

    openModal(`Run: ${task.name}`, `
      <form onsubmit="submitRunTask(event, '${id}')">
        ${inputs}
        <div class="flex gap-3 justify-end mt-4">
          <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
          <button type="submit" class="btn btn-primary">▶ Run Now</button>
        </div>
      </form>
    `);
  } else {
    await submitRunTask(null, id, {});
  }
}

async function submitRunTask(e, taskId, inputData) {
  if (e) e.preventDefault();
  let data = inputData || {};
  if (e) {
    const fd = new FormData(e.target);
    for (const [k, v] of fd.entries()) data[k] = v;
  }
  try {
    await api(`/api/tasks/${taskId}/run`, { method: 'POST', body: JSON.stringify({ input_data: data }) });
    toast('Task dispatched to worker', 'info');
    closeModal();
    tasks();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function viewTaskOutput(id) {
  const task = await api(`/api/tasks/${id}`).catch(() => null);
  if (!task) return;
  openModal(`Output: ${task.name}`, `
    <div class="mb-2 flex items-center gap-2">${statusBadge(task.status)}<span class="text-xs text-slate-400">${task.updated_at ? timeAgo(task.updated_at) : ''}</span></div>
    ${task.output
      ? `<div class="bg-slate-900 rounded-lg p-4 text-sm text-slate-300 max-h-80 overflow-y-auto">${marked.parse(task.output)}</div>`
      : task.error_message
        ? `<div class="bg-red-900/30 border border-red-700 rounded-lg p-3 text-sm text-red-300">${escapeHtml(task.error_message)}</div>`
        : '<div class="text-slate-400 text-sm">No output yet</div>'}
  `);
}

async function deleteTask(id) {
  if (!confirm('Delete this task?')) return;
  try {
    await api(`/api/tasks/${id}`, { method: 'DELETE' });
    toast('Task deleted', 'success');
    tasks();
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ════════════════════════════════════════════════════════════════
   MODELS
   ════════════════════════════════════════════════════════════════ */
async function models() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = '';

  const [modelsData, providersData] = await Promise.all([
    api('/api/models/').catch(() => ({ models: [] })),
    api('/api/models/providers').catch(() => ({ providers: [] })),
  ]);

  state.models = modelsData.models;
  const providers = providersData.providers;

  const categories = [...new Set(modelsData.models.map(m => m.category))];

  content.innerHTML = `
    <!-- Provider status -->
    <h2 class="text-lg font-semibold text-white mb-3">Providers</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
      ${providers.map(p => `
        <div class="card p-4 flex items-center gap-3">
          <div class="w-2.5 h-2.5 rounded-full ${p.configured ? 'bg-green-400' : 'bg-slate-600'}"></div>
          <div>
            <div class="font-medium text-white text-sm">${p.name}</div>
            <div class="text-xs text-slate-400">${p.model_count} models · ${p.is_local ? 'Local' : p.configured ? 'Configured' : '<span class="text-amber-400">No key</span>'}</div>
          </div>
        </div>`).join('')}
    </div>

    <!-- Models by category -->
    ${categories.map(cat => `
      <h2 class="text-lg font-semibold text-white mb-3 capitalize">${cat} Models</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-8">
        ${modelsData.models.filter(m => m.category === cat).map(modelCard).join('')}
      </div>
    `).join('')}
  `;
}

function modelCard(m) {
  const ctxK = m.ctx >= 1_000_000 ? `${(m.ctx / 1_000_000).toFixed(1)}M` : `${Math.round(m.ctx / 1000)}K`;
  return `
    <div class="model-card ${m.available ? '' : 'opacity-50'}">
      <div class="flex items-center justify-between mb-2">
        <div class="font-medium text-white text-sm">${escapeHtml(m.name)}</div>
        <div class="flex items-center gap-1.5">
          ${m.vision ? '<span class="badge badge-blue text-xs">vision</span>' : ''}
          <div class="w-2 h-2 rounded-full ${m.available ? 'bg-green-400' : 'bg-slate-600'}"></div>
        </div>
      </div>
      <div class="text-xs text-slate-500 mb-3">${m.provider} · ${ctxK} ctx</div>
      ${m.available
        ? `<button class="btn btn-primary btn-sm w-full" onclick="state.selectedModel='${m.id}'; navigate('chat')">Chat with this model</button>`
        : `<div class="text-xs text-amber-400">Set ${m.provider.toUpperCase()} API key to enable</div>`}
    </div>`;
}

/* ── Shared helpers ──────────────────────────────────────────────── */
function emptyState(icon, title, desc, action) {
  return `<div class="flex flex-col items-center justify-center py-20 text-center">
    <div class="text-6xl mb-4">${icon}</div>
    <div class="text-xl font-semibold text-white mb-2">${title}</div>
    <div class="text-slate-400 mb-6">${desc}</div>
    <button class="btn btn-primary" onclick="${action}">Get started</button>
  </div>`;
}

/* ════════════════════════════════════════════════════════════════
   MCP SERVERS
   ════════════════════════════════════════════════════════════════ */
async function mcp() {
  const content = document.getElementById('page-content');
  document.getElementById('header-actions').innerHTML = `
    <button class="btn btn-primary" onclick="showMcpModal()">+ Add MCP Server</button>
  `;

  const servers = await api('/api/mcp/').catch(() => []);
  state.mcpServers = servers;

  content.innerHTML = servers.length === 0
    ? emptyState('🔌', 'No MCP servers', 'Add an MCP server to give agents access to external tools.', 'showMcpModal()')
    : `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        ${servers.map(mcpCard).join('')}
      </div>`;
}

function mcpCard(s) {
  return `
    <div class="card p-5 flex flex-col gap-3">
      <div class="flex items-start justify-between">
        <div>
          <div class="font-semibold text-white text-lg">${escapeHtml(s.name)}</div>
          ${s.description ? `<div class="text-sm text-slate-400 mt-1">${truncate(s.description, 60)}</div>` : ''}
        </div>
        <div class="flex flex-col items-end gap-1">
          <span class="badge ${s.transport === 'stdio' ? 'badge-blue' : 'badge-green'}">${s.transport}</span>
          <span class="badge ${s.is_active ? 'badge-green' : 'badge-gray'}">${s.is_active ? 'active' : 'off'}</span>
        </div>
      </div>
      <div class="text-xs text-slate-500 font-mono bg-slate-900 rounded-lg p-2 truncate">
        ${s.transport === 'stdio' ? escapeHtml(s.command || '') + ' ' + (s.args || []).join(' ') : escapeHtml(s.url || '')}
      </div>
      <div class="flex gap-2 mt-auto">
        <button class="btn btn-secondary btn-sm flex-1" onclick="testMcpServer('${s.id}', '${escapeHtml(s.name)}')">Test</button>
        <button class="btn btn-secondary btn-sm flex-1" onclick="listMcpTools('${s.id}', '${escapeHtml(s.name)}')">Tools</button>
        <button class="btn btn-ghost btn-sm" onclick="showMcpModal(${JSON.stringify(s).replace(/"/g, '&quot;')})">Edit</button>
        <button class="btn btn-ghost btn-sm text-red-400" onclick="deleteMcpServer('${s.id}')">Delete</button>
      </div>
    </div>`;
}

function showMcpModal(server) {
  const isEdit = !!server;
  openModal(isEdit ? 'Edit MCP Server' : 'Add MCP Server', `
    <form onsubmit="saveMcpServer(event, '${isEdit ? server.id : ''}')">
      <div class="form-group">
        <label class="form-label">Name *</label>
        <input class="form-input" name="name" required value="${isEdit ? escapeHtml(server.name) : ''}" placeholder="My MCP Server">
      </div>
      <div class="form-group">
        <label class="form-label">Description</label>
        <input class="form-input" name="description" value="${isEdit ? escapeHtml(server.description || '') : ''}" placeholder="What does this server provide?">
      </div>
      <div class="form-group">
        <label class="form-label">Transport *</label>
        <select class="form-select" name="transport" id="mcp-transport-select" onchange="toggleMcpTransportFields(this.value)">
          <option value="sse" ${isEdit && server.transport === 'sse' ? 'selected' : ''}>SSE / HTTP (remote server)</option>
          <option value="stdio" ${isEdit && server.transport === 'stdio' ? 'selected' : ''}>Stdio (local process)</option>
        </select>
      </div>
      <div id="mcp-sse-fields" ${isEdit && server.transport === 'stdio' ? 'class="hidden"' : ''}>
        <div class="form-group">
          <label class="form-label">Server URL *</label>
          <input class="form-input" name="url" value="${isEdit ? escapeHtml(server.url || '') : ''}" placeholder="http://localhost:3000/sse">
        </div>
      </div>
      <div id="mcp-stdio-fields" ${!isEdit || server.transport !== 'stdio' ? 'class="hidden"' : ''}>
        <div class="form-group">
          <label class="form-label">Command *</label>
          <input class="form-input" name="command" value="${isEdit ? escapeHtml(server.command || '') : ''}" placeholder="npx">
        </div>
        <div class="form-group">
          <label class="form-label">Arguments (space-separated)</label>
          <input class="form-input" name="args_str" value="${isEdit ? (server.args || []).join(' ') : ''}" placeholder="@modelcontextprotocol/server-filesystem /data">
        </div>
      </div>
      <div class="flex gap-3 justify-end mt-4">
        <button type="button" class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        <button type="submit" class="btn btn-primary">${isEdit ? 'Save Changes' : 'Add Server'}</button>
      </div>
    </form>
  `);
}

function toggleMcpTransportFields(val) {
  document.getElementById('mcp-sse-fields').classList.toggle('hidden', val !== 'sse');
  document.getElementById('mcp-stdio-fields').classList.toggle('hidden', val !== 'stdio');
}

async function saveMcpServer(e, serverId) {
  e.preventDefault();
  const fd = new FormData(e.target);
  const transport = fd.get('transport');
  const argsStr = fd.get('args_str') || '';
  const body = {
    name: fd.get('name'),
    description: fd.get('description') || null,
    transport,
    url: transport === 'sse' ? (fd.get('url') || null) : null,
    command: transport === 'stdio' ? (fd.get('command') || null) : null,
    args: transport === 'stdio' ? argsStr.split(/\s+/).filter(Boolean) : [],
    env: {},
    headers: {},
  };
  try {
    if (serverId) {
      await api(`/api/mcp/${serverId}`, { method: 'PATCH', body: JSON.stringify(body) });
      toast('MCP server updated', 'success');
    } else {
      await api('/api/mcp/', { method: 'POST', body: JSON.stringify(body) });
      toast('MCP server added', 'success');
    }
    closeModal();
    mcp();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function deleteMcpServer(id) {
  if (!confirm('Delete this MCP server?')) return;
  try {
    await api(`/api/mcp/${id}`, { method: 'DELETE' });
    toast('MCP server deleted', 'success');
    mcp();
  } catch (e) {
    toast(e.message, 'error');
  }
}

async function testMcpServer(id, name) {
  toast(`Testing connection to ${name}…`, 'info');
  try {
    const result = await api(`/api/mcp/${id}/test`, { method: 'POST' });
    openModal(`Test Result — ${name}`, `
      <div class="space-y-3">
        <div class="flex items-center gap-2 text-green-400 font-semibold">
          <span>✓</span><span>Connection successful</span>
        </div>
        <div class="text-slate-400 text-sm">${result.tool_count} tool${result.tool_count !== 1 ? 's' : ''} found</div>
        <div class="space-y-1 max-h-48 overflow-y-auto">
          ${(result.tools || []).map(t => `<div class="text-xs text-slate-300 bg-slate-900 rounded px-2 py-1 font-mono">${escapeHtml(t)}</div>`).join('')}
        </div>
        <button class="btn btn-secondary w-full mt-2" onclick="closeModal()">Close</button>
      </div>
    `);
  } catch (e) {
    openModal(`Test Failed — ${name}`, `
      <div class="space-y-3">
        <div class="flex items-center gap-2 text-red-400 font-semibold"><span>✗</span><span>Connection failed</span></div>
        <div class="text-sm text-slate-400">${escapeHtml(e.message)}</div>
        <button class="btn btn-secondary w-full mt-2" onclick="closeModal()">Close</button>
      </div>
    `);
  }
}

async function listMcpTools(id, name) {
  try {
    const result = await api(`/api/mcp/${id}/tools`);
    openModal(`Tools — ${name}`, `
      <div class="space-y-2 max-h-96 overflow-y-auto">
        ${(result.tools || []).length === 0
          ? '<div class="text-slate-400 text-sm text-center py-4">No tools found</div>'
          : (result.tools || []).map(t => `
            <div class="bg-slate-900 rounded-lg p-3">
              <div class="text-sm font-medium text-white font-mono">${escapeHtml(t.name)}</div>
              ${t.description ? `<div class="text-xs text-slate-400 mt-1">${escapeHtml(t.description)}</div>` : ''}
            </div>`).join('')}
      </div>
      <button class="btn btn-secondary w-full mt-3" onclick="closeModal()">Close</button>
    `);
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ════════════════════════════════════════════════════════════════
   ARTIFACTS — sandboxed HTML preview panel
   ════════════════════════════════════════════════════════════════ */

window._artifactStore = {};

function injectArtifacts(bubble) {
  if (!bubble) return;
  // Find all fenced ```html blocks rendered by marked → <pre><code class="language-html">
  bubble.querySelectorAll('pre > code').forEach((codeEl, i) => {
    const cls = codeEl.className || '';
    const isHtml = cls.includes('language-html') || cls.includes('language-HTML');
    const text = codeEl.textContent || '';
    const looksLikeHtml = text.trimStart().startsWith('<!DOCTYPE') || text.trimStart().startsWith('<html') || (text.includes('<head') && text.includes('<body'));
    if (!isHtml && !looksLikeHtml) return;

    const pre = codeEl.parentElement;
    const artifactId = `artifact-${Date.now()}-${i}`;
    window._artifactStore[artifactId] = text;

    const panel = document.createElement('div');
    panel.className = 'artifact-panel';
    panel.innerHTML = `
      <div class="artifact-tabs">
        <button class="artifact-tab active" data-view="preview" data-id="${artifactId}">▶ Preview</button>
        <button class="artifact-tab" data-view="code" data-id="${artifactId}">{ } Code</button>
        <span class="artifact-label">HTML Artifact</span>
      </div>
      <div id="${artifactId}-preview" class="artifact-preview"></div>
      <div id="${artifactId}-code" class="artifact-code" style="display:none"><pre style="margin:0;white-space:pre-wrap;word-break:break-all;font-size:0.78rem">${escapeHtml(text)}</pre></div>
      <div class="artifact-actions">
        <button class="btn btn-ghost btn-sm" onclick="copyArtifactCode('${artifactId}')">📋 Copy</button>
        <button class="btn btn-ghost btn-sm" onclick="openArtifactFullscreen('${artifactId}')">⛶ Full screen</button>
      </div>
    `;

    // Inject iframe safely via srcdoc (no attribute encoding needed)
    const iframe = document.createElement('iframe');
    iframe.sandbox = 'allow-scripts allow-same-origin';
    iframe.style.cssText = 'width:100%;border:none;min-height:340px;background:#fff;display:block';
    iframe.srcdoc = text;
    panel.querySelector(`#${artifactId}-preview`).appendChild(iframe);

    // Tab switching
    panel.querySelectorAll('.artifact-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        panel.querySelectorAll('.artifact-tab').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        panel.querySelector(`#${artifactId}-preview`).style.display = view === 'preview' ? '' : 'none';
        panel.querySelector(`#${artifactId}-code`).style.display = view === 'code' ? '' : 'none';
      });
    });

    pre.insertAdjacentElement('afterend', panel);
    pre.style.display = 'none';
  });
}

function copyArtifactCode(artifactId) {
  const code = window._artifactStore[artifactId];
  if (!code) return;
  navigator.clipboard.writeText(code)
    .then(() => toast('Copied to clipboard', 'success'))
    .catch(() => toast('Copy failed — try selecting and copying manually', 'error'));
}

function openArtifactFullscreen(artifactId) {
  const code = window._artifactStore[artifactId];
  if (!code) return;
  const w = window.open('about:blank', '_blank');
  w.document.open();
  w.document.write(code);
  w.document.close();
}

/* ════════════════════════════════════════════════════════════════
   DATA FILE UPLOAD — CSV / JSON → AI dashboard generator
   ════════════════════════════════════════════════════════════════ */

function handleDataFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    let dataText = e.target.result;
    let preview = '';
    if (file.name.endsWith('.json')) {
      try {
        const parsed = JSON.parse(dataText);
        dataText = JSON.stringify(parsed, null, 2);
        preview = Array.isArray(parsed) ? `${parsed.length} rows` : 'JSON object';
      } catch {
        toast('Invalid JSON file', 'error');
        return;
      }
    } else {
      const rows = dataText.trim().split('\n').length;
      preview = `${rows} rows`;
    }
    state.pendingDataFile = { name: file.name, dataText, preview };
    const wrap = document.getElementById('data-file-badge-wrap');
    if (wrap) wrap.innerHTML = `
      <span class="data-badge">
        📊 ${escapeHtml(file.name)} — ${preview}
        <button onclick="clearDataFile()" style="margin-left:0.3rem;opacity:0.7;cursor:pointer" title="Remove">✕</button>
      </span>`;
  };
  reader.readAsText(file);
}

function clearDataFile() {
  state.pendingDataFile = null;
  const wrap = document.getElementById('data-file-badge-wrap');
  if (wrap) wrap.innerHTML = '';
  const inp = document.getElementById('data-file-input');
  if (inp) inp.value = '';
}

/* ── Bootstrap ───────────────────────────────────────────────────── */
navigate('dashboard');
