<div align="center">

# Gema — Self-Hosted AI Platform

**Chat · Agents · RAG · MCP Tools · Task Automation · Live Dashboards**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)](backend/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python)](backend/)

</div>

**Gema** is a fully self-hosted AI orchestration platform. Run it with a single `docker compose up` command and get a production-ready environment for chatting with any major AI model, building custom agents, indexing your documents for RAG, connecting external tools via MCP, automating tasks on a schedule, and generating live data dashboards — all from one clean web UI.

---

## Features

| | Feature | Description |
|---|---|---|
| 💬 | **Multi-provider Chat** | OpenAI, Anthropic, Google, Mistral, Groq, Cohere, Together AI, HuggingFace — all from one UI |
| 🤖 | **AI Agents** | Custom agents with system prompts, model selection, temperature, RAG knowledge bases, and MCP tools |
| 🧠 | **Agent Memory** | Short-term session memory (last N turns) + long-term cross-session memory stored in MongoDB with vector search |
| 📚 | **RAG Knowledge Base** | Upload PDF, DOCX, TXT — chunks are embedded and stored in MongoDB Atlas Local for vector search |
| 🔌 | **MCP Tool Support** | Connect any [Model Context Protocol](https://modelcontextprotocol.io) server (stdio or SSE); agents call tools automatically |
| 📊 | **Live Data Dashboards** | Attach a CSV/JSON file in chat; AI generates an interactive Chart.js dashboard rendered live in the browser |
| ⚙️ | **Task Automation** | Prompt templates with `{{variable}}` placeholders; run manually or on a cron schedule via Celery |
| 🔄 | **Streaming** | Real-time token streaming via Server-Sent Events |
| 📜 | **Conversation History** | All chats persisted in PostgreSQL; resume any session |
| 🧩 | **Artifact Preview** | HTML code blocks from AI responses render as sandboxed live previews in-chat |

---

## Architecture

```
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│  Browser │────▶│    Nginx     │────▶│  FastAPI  :8000 │
│  (SPA)   │     │    :80       │     └────────┬────────┘
└──────────┘     └──────────────┘              │
                                    ┌──────────┼──────────┐
                             ┌──────▼──────┐   │   ┌──────▼──────┐
                             │ PostgreSQL  │   │   │   MongoDB   │
                             │  (data)     │   │   │ Atlas Local │
                             └─────────────┘   │   │ (RAG+memory)│
                                          ┌────▼──┐└─────────────┘
                                          │ Redis │
                                          │(queue)│
                                          └───┬───┘
                                        ┌─────▼──────┐
                                        │   Celery   │
                                        │ Worker+Beat│
                                        └────────────┘
```

| Service | Image | Role |
|---|---|---|
| `api` | Python 3.11 + FastAPI | REST API, SSE streaming, MCP orchestration |
| `worker` | Python 3.11 + Celery | Background task execution |
| `beat` | Python 3.11 + Celery Beat | Scheduled task triggering (cron) |
| `db` | `postgres:16-alpine` | Relational storage (agents, conversations, tasks) |
| `redis` | `redis:7-alpine` | Message broker + model catalog cache |
| `mongo` | `mongodb/mongodb-atlas-local` | Vector store for RAG chunks and long-term memory |
| `nginx` | `nginx:1.25-alpine` | Reverse proxy + SPA serving |

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2
- At least one AI provider API key (free tier works — e.g. Groq or Google AI Studio)

### 1. Clone and configure

```bash
git clone https://github.com/mardhiahnajwa/gema.git
cd gema
cp env.example .env
```

Edit `.env` and paste in at least one API key:

```env
# Free options to get started quickly:
GROQ_API_KEY=gsk_...          # https://console.groq.com/keys
GOOGLE_API_KEY=...             # https://aistudio.google.com/app/apikey

# Full list of supported providers:
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
MISTRAL_API_KEY=...
COHERE_API_KEY=...
TOGETHER_API_KEY=...
HUGGINGFACE_API_KEY=hf_...
```

### 2. Start all services

```bash
docker compose up -d --build
```

> First build downloads images and installs Python dependencies — takes 3–5 minutes.

### 3. Open Gema

Navigate to **[http://localhost](http://localhost)**

---

## Usage Guide

### Chat

1. Click **Chat** in the sidebar.
2. Pick a model from the dropdown (only models with a valid API key show as available).
3. Type a message and press **Enter** — response streams token by token.
4. Previous conversations appear in the history panel on the left.

**Keyboard shortcuts:**
- `Enter` — send message
- `Shift+Enter` — newline in the textarea

---

### Agents

Agents are reusable AI personas with a fixed system prompt, model, and optional tools.

**Create an agent:**

1. Go to **Agents** → **+ New Agent**
2. Fill in name, system prompt, model, and temperature
3. (Optional) Attach knowledge bases or MCP servers
4. Click **Save**

**Example — Customer Support agent system prompt:**

```
You are a helpful customer support agent for Acme Corp.
Always be polite and concise. If you do not know the answer,
say so rather than guessing. Escalate billing issues to billing@acme.com.
```

**One-click presets:**

| Button | What it creates |
|---|---|
| 📊 Data Analyst Preset | Agent that turns CSV/JSON into live Chart.js dashboards |

---

### RAG Knowledge Base

Give an agent access to your own documents.

1. Go to **Knowledge Base** → **+ New Knowledge Base**
2. Upload PDF, DOCX, or TXT files — they are chunked and embedded automatically
3. When creating/editing an agent, select the knowledge base under **Knowledge Bases**
4. Chat with the agent — relevant document snippets are injected into every message

**Supported file types:** `.pdf` · `.docx` · `.txt` · `.md` · `.csv`

---

### MCP Tool Servers

Connect any external tool server that speaks [Model Context Protocol](https://modelcontextprotocol.io).

1. Go to **MCP Servers** → **+ Add MCP Server**
2. Choose transport:
   - **stdio** — command-line server (e.g. `npx -y @modelcontextprotocol/server-filesystem /tmp`)
   - **SSE** — URL-based server (e.g. `http://my-server:3000/sse`)
3. Click **Test** to verify the connection and see discovered tools
4. Attach the server to an agent under **MCP Servers** when editing the agent

**Example — Filesystem MCP server (stdio):**

```
Transport: stdio
Command:   npx
Args:      -y @modelcontextprotocol/server-filesystem /Users/me/Documents
```

Once attached, the agent will automatically call `read_file`, `list_directory`, etc. when relevant.

---

### Live Data Dashboards

Turn any CSV or JSON file into an interactive dashboard — no code needed.

1. Go to **Chat**, select the **Data Analyst** agent (create it from the preset button on the Agents page)
2. Click the 📎 attachment button and select a `.csv` or `.json` file
3. Optionally type a custom request (e.g. *"Show monthly trends as a bar chart"*)
4. Send — the AI generates a Chart.js dashboard that renders **live in the chat window**

**Dashboard features:**
- Summary statistics cards
- Multiple chart types (bar, line, pie, etc.)
- Dark-themed, responsive layout
- **Preview** / **Code** tabs to inspect and copy the HTML
- **Full screen** button to open in a new tab

**Example prompts after attaching a CSV:**
- *"Show sales by region as a pie chart and monthly revenue as a line chart"*
- *"Create an executive summary dashboard for this data"*
- *"What are the top 5 performing products? Visualise with a bar chart"*

---

### Artifact Preview

Whenever the AI responds with a `\`\`\`html` code block, Gema automatically renders it as a live sandboxed preview:

- **Preview tab** — runs the HTML/JavaScript in a safe iframe
- **Code tab** — shows the raw source
- 📋 **Copy** button
- ⛶ **Full screen** — opens in a new browser tab

This works for any HTML, not just dashboards — demo sites, slideshows, interactive forms, games, etc.

---

### Task Automation

Automate repetitive AI workflows.

1. Go to **Tasks** → **+ New Task**
2. Write a prompt template using `{{variable}}` syntax:

```
Translate the following text to {{target_language}}:

{{text}}
```

3. Set a model and optionally a cron schedule (e.g. `0 9 * * 1` for every Monday at 9am)
4. Click **Run** to execute immediately, or let Celery Beat trigger it on schedule

---

### Agent Memory

Memory is built-in and automatic — no configuration needed.

- **Short-term** — The last 6 conversation turns (12 messages) are always included as context
- **Long-term** — Key facts from each conversation are extracted and stored in MongoDB. In future sessions with the same agent and user, relevant memories are retrieved via vector search and injected into the system prompt

To use long-term memory, pass a stable `user_id` in the API payload:

```json
{
  "messages": [{ "role": "user", "content": "..." }],
  "agent_id": "...",
  "user_id": "user-123",
  "conversation_id": "..."
}
```

---

## API Reference

Base URL: `http://localhost/api`

<details>
<summary><strong>Chat</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat/completions` | Send a message (`stream: true` for SSE) |
| `GET` | `/chat/conversations` | List conversations |
| `POST` | `/chat/conversations` | Create a conversation |
| `DELETE` | `/chat/conversations/{id}` | Delete a conversation |
| `GET` | `/chat/conversations/{id}/messages` | Get messages |

**Streaming example:**

```bash
curl -N -X POST http://localhost/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Explain quantum computing in 3 sentences"}],
    "model": "gpt-4o",
    "stream": true
  }'
```

</details>

<details>
<summary><strong>Agents</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/agents/` | List agents |
| `POST` | `/agents/` | Create agent |
| `GET` | `/agents/{id}` | Get agent |
| `PATCH` | `/agents/{id}` | Update agent |
| `DELETE` | `/agents/{id}` | Delete agent |

**Create agent example:**

```bash
curl -X POST http://localhost/api/agents/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support Bot",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-3-5-sonnet-20241022",
    "temperature": 0.5
  }'
```

</details>

<details>
<summary><strong>Knowledge Base</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/knowledge/` | List knowledge bases |
| `POST` | `/knowledge/` | Create knowledge base |
| `POST` | `/knowledge/{id}/documents` | Upload document |
| `DELETE` | `/knowledge/{id}/documents/{doc_id}` | Delete document |
| `POST` | `/knowledge/query` | Query knowledge bases |

**Upload a document:**

```bash
curl -X POST http://localhost/api/knowledge/{kb_id}/documents \
  -F "file=@report.pdf"
```

</details>

<details>
<summary><strong>MCP Servers</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/mcp/` | List MCP servers |
| `POST` | `/mcp/` | Add MCP server |
| `PATCH` | `/mcp/{id}` | Update server |
| `DELETE` | `/mcp/{id}` | Remove server |
| `POST` | `/mcp/{id}/test` | Test connection |
| `GET` | `/mcp/{id}/tools` | List available tools |

</details>

<details>
<summary><strong>Tasks</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/tasks/` | List tasks |
| `POST` | `/tasks/` | Create task |
| `PATCH` | `/tasks/{id}` | Update task |
| `DELETE` | `/tasks/{id}` | Delete task |
| `POST` | `/tasks/{id}/run` | Run immediately |

</details>

<details>
<summary><strong>Models</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/models/` | List all models (cached) |
| `GET` | `/models/?refresh=true` | Force refresh from providers |
| `GET` | `/models/providers` | Provider status and API key check |
| `GET` | `/models/categories` | Model counts by category |

</details>

---

## Configuration

All settings live in `.env` (copy from `env.example`).

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | *(required)* | Random secret for the app — change before production |
| `POSTGRES_PASSWORD` | `gema_secret` | PostgreSQL password |
| `MONGODB_URL` | `mongodb://mongo:27017/` | MongoDB connection string |
| `MONGODB_DB` | `gema` | MongoDB database name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model for embeddings |
| `EMBEDDING_DIMENSIONS` | `384` | Embedding vector size (must match model) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection |
| `NGINX_PORT` | `80` | Port Nginx listens on |
| `DEBUG` | `false` | Enable FastAPI debug mode |

---

## Makefile Commands

```bash
make up          # Build and start all services
make down        # Stop and remove containers
make build       # Rebuild images
make logs        # Tail logs from all services
make logs-api    # API logs only
make logs-worker # Worker logs only
make restart     # Restart all services
make shell-api   # Shell into the API container
make shell-db    # psql session in the DB container
make status      # Show container status
make clean       # Remove containers, volumes, and images
```

---

## Supported AI Providers

| Provider | Model discovery | Example models |
|---|---|---|
| **OpenAI** | Live from API | `gpt-4o`, `gpt-4o-mini`, `o3`, `o1` |
| **Anthropic** | Curated list | `claude-3-5-sonnet`, `claude-3-opus`, `claude-3-haiku` |
| **Google** | Live from API | `gemini-2.0-flash`, `gemini-1.5-pro` |
| **Mistral** | Live from API | `mistral-large-latest`, `codestral-latest` |
| **Groq** | Live from API | `llama-3.3-70b`, `mixtral-8x7b`, `gemma2-9b` |
| **Cohere** | Live from API | `command-r-plus`, `command-r` |
| **Together AI** | Live from API | `Llama-3`, `Falcon`, `Mixtral`, 200+ models |
| **HuggingFace** | Curated list | `mistralai/Mixtral`, `Qwen/Qwen2.5` |

The model catalog is cached in Redis for 1 hour. Refresh from the **Models** page or:
```bash
curl -X POST http://localhost/api/models/refresh
```

---

## Deployment Notes

**Change the secret key before exposing to the internet:**
```env
SECRET_KEY=<output of: openssl rand -hex 32>
```

**Run on a different port:**
```env
NGINX_PORT=8080
```

**First-time disk requirements:** ~3 GB for all Docker images (includes MongoDB Atlas Local and sentence-transformers).

**Upgrading:**
```bash
git pull
docker compose up -d --build
```

---

## License

[MIT](LICENSE) — free to use, modify, and self-host.
