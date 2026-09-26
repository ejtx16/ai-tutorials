# Implementation Plan: Simple PDF RAG Agent

Based on [pdf-rag.md](pdf-rag.md) (StatLearn Tech — LangChain + Groq RAG tutorial).

## Goal

A Python agent that answers questions about `pdf-sample.pdf` by retrieving the 3 most relevant chunks and letting a Groq-hosted LLM answer from them.

## Architecture

```
pdf-sample.pdf
   │ PyPDFLoader              (34 pages)
   ▼
RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200 → 79 chunks)
   │
   ▼
HuggingFaceEmbeddings (all-MiniLM-L6-v2, runs locally, free)
   │
   ▼
InMemoryVectorStore
   ▲
   │ similarity_search(k=3)
retrieve_context  @tool  ◄── agent (create_agent) ◄── ChatGroq (openai/gpt-oss-20b)
                                   ▲
                               your question
```

## Files

| File | Purpose |
|---|---|
| `rag_1.py` | The RAG agent |
| `requirements.txt` | Python packages |
| `.env.example` | Template for your secrets/config |
| `.env` | **You create this** — holds your Groq key (git-ignored) |
| `.gitignore` | Keeps `.env` and `.venv/` out of git |
| `pdf-sample.pdf` | The document to query |

## Steps you need to do

### 1. Get a Groq API key (free)

1. Open https://console.groq.com/keys
2. Sign in (Google/Gmail login works).
3. Click **Create API Key**, give it a name (e.g. `pdf-rag`), click **Submit**.
4. Copy the key right away (starts with `gsk_`). Groq only shows it once — if you lose it, delete it and create a new one.

### 2. Create your `.env`

In the `rag` folder:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace the placeholder:

```
GROQ_API_KEY=gsk_your_real_key
```

Rules: no quotes, no spaces around `=`, variable name exactly `GROQ_API_KEY`. Never commit this file (already in `.gitignore`).

Optional settings in the same file:

- `GROQ_MODEL` — any chat model listed at https://console.groq.com/docs/models. Default `openai/gpt-oss-20b`. If Groq retires it (error `model_decommissioned`), pick a current model from that page.
- `PDF_PATH` — use a different PDF. Default `pdf-sample.pdf`.

### 3. Python environment (already done in this folder)

A `.venv` was created and packages installed. To redo it from scratch:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks `Activate.ps1`, run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

### 4. Run it

```powershell
.venv\Scripts\Activate.ps1
python rag_1.py "What is AI according to the document?"
```

Or without a question for interactive mode (blank line quits):

```powershell
python rag_1.py
```

Expected output: `Loading PDF document...` → `Building embeddings...` → `-> retrieve_context "..."` → `pages: 3, 4, 11` → answer with page citations. Add `-v` (`python rag_1.py -v "question"`) to see full messages and retrieved chunks.

First run downloads the embedding model (~90 MB) once; later runs are faster.

## Build steps (what the code does)

1. `load_dotenv()` loads `GROQ_API_KEY`; script exits with a clear message if missing or PDF not found.
2. `ChatGroq(model=..., reasoning_format="parsed")` — reasoning kept out of the answer (only passed for qwen3 models, others reject it).
3. `PyPDFLoader` loads pages.
4. `RecursiveCharacterTextSplitter(1000, 200)` makes overlapping chunks (video didn't give exact values; these are common defaults).
5. `HuggingFaceEmbeddings` + `InMemoryVectorStore.from_documents` builds the index.
6. `@tool retrieve_context` returns top-3 chunks as one string with source + page.
7. `create_agent(model, tools, system_prompt)` wires everything.
8. `agent.stream(..., stream_mode="values")` prints each step.

## Changes vs. the video

- Model changed: video's `qwen/qwen3-32b` no longer exists on Groq (`model_not_found`). `qwen/qwen3.8-27b` exists but returned broken tool calls (`tool_use_failed`). Default is now `openai/gpt-oss-20b`.
- Default model/PDF configurable via `.env`.
- Page number added to tool output; system prompt tells the agent to answer only from context.
- `sys.stdout.reconfigure(encoding="utf-8")` — Windows console otherwise crashes on PDF bullet characters (`UnicodeEncodeError: 'charmap' codec ...`), hit during testing.
- PDF loaded with `pypdf` directly instead of `PyPDFLoader` (`langchain-community` is deprecated). Running header (`ARTIFICIAL INTELLIGENCE`) and `N | P a g e` lines stripped before chunking.
- Retrieval uses MMR (`max_marginal_relevance_search`, k=3, fetch_k=15) so overlapping duplicate chunks don't fill the 3 slots.
- Second tool `document_overview` (title + opening lines of each page) for whole-document questions like "what is the purpose of this PDF" — plain similarity search can't answer those.
- Answers cite pages `(p. 4)`; when info is missing the agent says what the doc does cover.
- Compact output by default (tool call, pages found, answer). `-v` shows full messages like the video.
- Hugging Face / transformers logs silenced via env vars.

## Verification status

- Load + split + embed + retrieve: tested, works (34 pages → 79 chunks, relevant hits).
- Full run with real key + `openai/gpt-oss-20b`: works (tool call → 3 chunks → answer from the PDF).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `GROQ_API_KEY missing` | `.env` not created or wrong variable name |
| `401 Invalid API Key` | Key typo/revoked — make a new one |
| `model_decommissioned` / `model_not_found` | Set `GROQ_MODEL` to a current model from Groq docs |
| `tool_use_failed` | Model can't do tool calls reliably — switch `GROQ_MODEL` (gpt-oss works) |
| `429 rate limit` | Free tier limit — wait a minute |
| Symlink warning from Hugging Face on Windows | Harmless; enable Developer Mode to silence |
| Tokenizer / `LangChainDeprecationWarning` logs | Harmless, ignore |
