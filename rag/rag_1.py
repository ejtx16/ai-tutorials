"""Simple PDF RAG agent: LangChain + Groq + Hugging Face embeddings.

Usage:
    python rag_1.py                          # interactive, asks questions in a loop
    python rag_1.py "What is AI according to the document?"
    python rag_1.py -v "question"            # verbose: show full retrieved chunks
"""

import os
import re
import sys
from collections import Counter

# Quiet Hugging Face / transformers logs. Must be set before those libraries are imported.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

# Windows consoles default to cp1252 and crash on PDF symbols like bullets
sys.stdout.reconfigure(encoding="utf-8")

args = sys.argv[1:]
VERBOSE = bool(args) and args[0] in ("-v", "--verbose")
if VERBOSE:
    args = args[1:]

# 1. Load GROQ_API_KEY (and optional settings) from .env
load_dotenv()

if not os.getenv("GROQ_API_KEY"):
    sys.exit("GROQ_API_KEY missing. Copy .env.example to .env and paste your key from console.groq.com/keys")

PDF_PATH = os.getenv("PDF_PATH", "pdf-sample.pdf")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

if not os.path.exists(PDF_PATH):
    sys.exit(f"PDF not found: {PDF_PATH}. Put your PDF in this folder or set PDF_PATH in .env")

# 2. LLM. reasoning_format="parsed" moves the model's thinking into a separate field.
#    Only qwen3 models accept it on Groq, so skip it for others (e.g. gpt-oss).
model_kwargs = {"reasoning_format": "parsed"} if "qwen3" in GROQ_MODEL else {}
model = ChatGroq(model=GROQ_MODEL, **model_kwargs)

# 3. Load the PDF (one Document per page) and strip running headers / page numbers
print("Loading PDF document...")
PAGE_NUMBER_LINE = re.compile(r"^\s*\d+\s*\|?\s*(P\s*a\s*g\s*e)?\s*$", re.IGNORECASE)

pages = [page.extract_text() or "" for page in PdfReader(PDF_PATH).pages]
first_lines = Counter(text.strip().split("\n", 1)[0].strip() for text in pages if text.strip())
running_header = next((line for line, n in first_lines.most_common(1) if n > len(pages) / 2), None)


def clean(text: str) -> str:
    lines = [ln for ln in text.split("\n") if ln.strip() != running_header and not PAGE_NUMBER_LINE.match(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


docs = [
    Document(page_content=clean(text), metadata={"source": os.path.basename(PDF_PATH), "page": i + 1})
    for i, text in enumerate(pages)
    if clean(text)
]

# 4. Split into overlapping chunks
text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
all_splits = text_splitter.split_documents(docs)
print(f"Loaded {len(pages)} pages -> {len(all_splits)} chunks")

# 5. Embed chunks and store the vectors in memory
print("Building embeddings...")
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vector_store = InMemoryVectorStore.from_documents(all_splits, embeddings)


# 6. Tools. The docstrings tell the agent what each tool does and when to use it.
@tool
def retrieve_context(query: str) -> str:
    """Search the PDF for passages relevant to a specific topic.
    Use short, content-focused keywords (e.g. "types of AI", "AI in healthcare"),
    not words about the document itself like "this pdf". Call again with other
    keywords if the results don't answer the question."""
    # MMR picks relevant but *different* chunks, so overlapping duplicates don't eat the k=3 slots
    similar_docs = vector_store.max_marginal_relevance_search(query, k=3, fetch_k=15)
    data = []
    for doc in similar_docs:
        data.append(f"""Content: {doc.page_content}
Source: {doc.metadata["source"]}, page {doc.metadata["page"]}""")
    return "\n\n".join(data)


@tool
def document_overview() -> str:
    """Get the title and the opening lines of every page of the PDF.
    Use for questions about the whole document: its purpose, topic, summary or structure."""
    lines = [f"Title: {running_header or os.path.basename(PDF_PATH)} ({len(pages)} pages)"]
    for doc in docs:
        lines.append(f"Page {doc.metadata['page']}: {doc.page_content[:150].replace(chr(10), ' ')}")
    return "\n".join(lines)


# 7. Agent = model + tools + system prompt
prompt = (
    "You answer questions about a PDF document using your tools. "
    "Use document_overview for questions about the whole document (purpose, topic, summary). "
    "Use retrieve_context for specific facts; retry with different keywords if the first results miss. "
    "Answer only from tool results and cite page numbers like (p. 4). "
    "If the tools don't contain the answer, say so and mention what the document does cover."
)
agent = create_agent(model, tools=[retrieve_context, document_overview], system_prompt=prompt)


# 8. Ask a question and stream every step (tool call -> tool result -> answer)
def ask(query: str) -> None:
    for step in agent.stream(
        {"messages": [{"role": "user", "content": query}]},
        stream_mode="values",
    ):
        message = step["messages"][-1]
        if VERBOSE:
            message.pretty_print()
        elif message.type == "ai" and message.tool_calls:
            for call in message.tool_calls:
                shown = f'"{call["args"]["query"]}"' if "query" in call["args"] else ""
                print(f"  -> {call['name']} {shown}")
        elif message.type == "tool":
            found = sorted({int(p) for p in re.findall(r"^(?:Source: .*, )?[Pp]age (\d+)", message.content, re.M)})
            print(f"     pages: {', '.join(map(str, found))}")
        elif message.type == "ai":
            print(f"\n{message.content}\n")


if args:
    ask(" ".join(args))
else:
    while True:
        query = input("\nAsk about the PDF (blank to quit): ").strip()
        if not query:
            break
        ask(query)
