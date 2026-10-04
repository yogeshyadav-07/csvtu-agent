# pip install fastapi uvicorn langchain-core langchain-text-splitters langchain-mistralai langchain-tavily langgraph pypdf python-dotenv
#
# UTD CSVTU AI Assistant - BACKEND (FastAPI + LangGraph + Mistral + Tavily + RAG)
# Created by Yogesh Kumar Yadav.
#
# Project layout:
#   chatbot-csvtu.py        <- this file (backend + agent)
#   .env                    <- MISTRAL_API_KEY, TAVILY_API_KEY
#   static/index.html       <- UI (HTML)
#   static/style.css        <- UI (CSS)
#   static/script.js        <- UI (JavaScript)
#   pdfs/                   <- extra CSVTU PDFs (optional, data only)
#
# Run:   python chatbot-csvtu.py      then open  http://127.0.0.1:8000

import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Literal, TypedDict
from urllib.parse import urlparse

# Speed fix: langchain_text_splitters optionally imports "transformers". If transformers is installed
# on your PC, that import can take minutes (it scans every installed package) and looks like a hang.
# This project does not use transformers, so we block it before LangChain is imported.
sys.modules.setdefault("transformers", None)

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pypdf import PdfReader

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_tavily import TavilySearch
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

# ----------------------------------------------------------------------------
# CONFIGURATION (change things here, in one place)
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PDF_DIR = BASE_DIR / "pdfs"        # optional folder with extra CSVTU PDFs
STATIC_DIR = BASE_DIR / "static"   # folder with index.html, style.css, script.js
HOST = "127.0.0.1"
PORT = 8000

MISTRAL_CHAT_MODEL = "mistral-code-latest"   # change chat model here
MISTRAL_EMBED_MODEL = "mistral-embed"

CHUNK_SIZE = 1000          # characters per chunk
CHUNK_OVERLAP = 150        # overlap between chunks
TOP_K = 6                  # chunks sent to the LLM
EMBED_BATCH_SIZE = 32      # chunks embedded per API call
MAX_HISTORY_TURNS = 6      # previous messages used for context

OFFICIAL_DOMAIN = "csvtu.ac.in"
OWNER_NAME = "Yogesh Kumar Yadav"

# ----------------------------------------------------------------------------
# BUILT-IN UTD KNOWLEDGE
# The assistant "knows" these facts by itself (they are indexed together with the PDFs).
# Only stable facts are kept here. Fees, seats, dates, cutoffs, faculty, results and
# placements change every year, so those are answered from PDFs or web search instead.
# To add or fix a fact, just edit this list.
# ----------------------------------------------------------------------------
UTD_FACTS = [
    (
        "About UTD",
        "UTD stands for University Teaching Department. It is the teaching department run directly by "
        "Chhattisgarh Swami Vivekanand Technical University (CSVTU) on the university's own campus at Newai, "
        "Bhilai. UTD is different from the many colleges that are affiliated to CSVTU.",
    ),
    (
        "UTD location and address",
        "UTD, CSVTU Bhilai is located at Newai, P.O. Newai, District Durg, Chhattisgarh, PIN 491107.",
    ),
    (
        "About CSVTU",
        "Chhattisgarh Swami Vivekanand Technical University (CSVTU) is a state technical university of the "
        "Government of Chhattisgarh, with its main campus at Newai, Bhilai in Durg district. It is commonly "
        "cited as established in 2005. Its official website is csvtu.ac.in. Besides UTD, CSVTU has many "
        "affiliated engineering, pharmacy, management and other colleges.",
    ),
    (
        "UTD history",
        "UTD started in 2016 with PG courses: Master of Design (discontinued from 2017), M.Tech in Energy and "
        "Environmental Engineering, M.Tech in Biomedical Engineering and Bio-Informatics, and M.Tech in "
        "Microelectronics and VLSI. More PG courses, including M.Tech in Structural Engineering, were added "
        "from the 2017-18 session. B.Tech (Honours) programmes started from the 2020-21 session.",
    ),
    (
        "UTD programmes",
        "Programmes listed for UTD on the official CSVTU website. "
        "UG: B.Tech (Honours) in Computer Science Engineering (Artificial Intelligence), B.Tech (Honours) in "
        "Computer Science Engineering (Data Science), and B.Tech (Honours) in Civil Engineering. "
        "PG: M.Tech in Structural Engineering, Environmental and Water Resources Engineering, Energy and "
        "Environmental Engineering, Biomedical Engineering and Bio-Informatics, and Microelectronics and VLSI, "
        "plus M.Plan in Urban Planning. "
        "Diploma: Diploma in Mining Engineering and Diploma in Industrial Safety and Fire Safety Engineering. "
        "A PG Diploma in Industrial Safety and Fire Safety Management was also offered in 2024-25. "
        "The programme list can change from session to session.",
    ),
    (
        "UTD departments and research",
        "Departments listed for UTD on the official CSVTU website include: Energy and Environmental Engineering, "
        "Environmental and Water Resources Engineering, Structural Engineering, Urban Planning, Microelectronics "
        "and VLSI, Biomedical Engineering and Bio-Informatics, and Steel Technology. The B.Tech (Honours) Computer "
        "Science Engineering programmes (AI and Data Science) are also run at UTD. A Research Hub with research "
        "facilities is established at UTD.",
    ),
    (
        "UTD admissions and contact",
        "For UTD admission queries the official email is admissionutd@csvtu.ac.in. In the 2024-25 PG admission "
        "notification, selected candidates had to report at UTD (Visvesvaraya Block), CSVTU Bhilai. Admission "
        "notifications, merit lists and the academic calendar for UTD are published on csvtu.ac.in. B.Tech "
        "admissions generally go through JEE Main / CG PET based counselling and M.Tech admissions through GATE; "
        "always confirm this in the current session's official notification.",
    ),
]


def builtin_documents() -> List[Document]:
    return [
        Document(
            page_content=f"{title}: {text}",
            metadata={"source": "UTD knowledge base", "page_number": None, "doc_type": "Built-in"},
        )
        for title, text in UTD_FACTS
    ]


# ----------------------------------------------------------------------------
# LANGUAGE MODES (chosen in the UI): "en" (default), "hi", "both"
# ----------------------------------------------------------------------------
LANGUAGE_RULES = {
    "english": "Write the answer in English only, even if the user wrote in Hindi or Hinglish.",
    "hindi": "Write the answer in Hindi (Devanagari script). Keep names, course names, codes and technical terms in English.",
    "both": "Write the complete answer first in English. Then add a blank line, a line containing only --- , a blank line, "
    "and the same answer in Hindi (Devanagari script). Keep names, course names and technical terms in English in the Hindi part.",
}

# Shown when the knowledge base AND the web have nothing (never guess!)
NOT_FOUND = {
    "english": "Sorry, I don't have this information right now.",
    "hindi": "क्षमा करें, मुझे अभी इसकी जानकारी उपलब्ध नहीं है।",
    "both": "Sorry, I don't have this information right now.\n\n---\n\nक्षमा करें, मुझे अभी इसकी जानकारी उपलब्ध नहीं है।",
}

# Small status lines shown in the UI while the agent works (they never mention PDFs)
STATUS = {
    "searching_kb": {
        "english": "Looking this up...",
        "hindi": "जानकारी खोज रहा हूँ...",
        "both": "Looking this up... / जानकारी खोज रहा हूँ...",
    },
    "searching_web": {
        "english": "Checking the latest information online...",
        "hindi": "ऑनलाइन ताज़ा जानकारी देख रहा हूँ...",
        "both": "Checking online... / ऑनलाइन देख रहा हूँ...",
    },
}

ANSWER_PROMPT = """You are the AI assistant of UTD (University Teaching Department), CSVTU Bhilai, created by Yogesh Kumar Yadav. \
Answer questions using the provided official CSVTU / UTD context. Do not invent information. \
If the context does not contain the answer, clearly say that the information was not found. \
Use web search only when web context is explicitly provided.

Rules:
- Never invent rules, dates, regulations, syllabus details, fees, eligibility criteria, names or any other official information.
- Context blocks tagged [KB] are trusted official knowledge and always have higher priority than web context.
- Context blocks tagged [WEB-OFFICIAL] come from the official csvtu.ac.in website.
- Context blocks tagged [WEB-UNOFFICIAL] come from other websites. If you use them, clearly say in the answer that this \
information comes from a web source and is not an official CSVTU document.
- Keep knowledge-base information and web information clearly separated.
- Never mention "context", "PDF", "document", "file", "knowledge base" or page numbers. State facts directly, \
for example "According to CSVTU regulations, ...".
- Do not write a "Sources" section; the application adds it automatically.
- The user is most likely a UTD CSVTU student or applicant. When a rule applies to CSVTU in general, say so.

Answer format (always follow this structure, using Markdown):
1. Start with a one-line direct answer.
2. Then give details as short bullet points or a numbered list. For subject lists, schemes or marks use a Markdown table.
3. Make key values bold (numbers, dates, percentages, subject names, form names).
4. If there is a condition or exception, add a short line starting with "Note:".
5. Be concise. No filler sentences.

Language: {language_rule}"""

CASUAL_PROMPT = """You are the friendly AI assistant of UTD (University Teaching Department), CSVTU Bhilai. \
You were created by Yogesh Kumar Yadav.
- If the user greets you, thanks you, says goodbye or makes small talk, reply naturally and briefly (1-2 sentences) like a \
helpful person and invite them to ask about UTD CSVTU: courses, admissions, exams, syllabus, regulations or campus.
- If the user asks who you are or what you can do, explain briefly: you answer questions about UTD CSVTU and CSVTU \
rules, and you can check online when needed.
- If the user asks something unrelated to UTD or CSVTU, politely say you can only help with UTD / CSVTU related questions.
- Never state any UTD or CSVTU facts, rules or dates in this reply.

Language: {language_rule}"""


# ----------------------------------------------------------------------------
# SCHEMAS
# ----------------------------------------------------------------------------
class QueryAnalysis(BaseModel):
    """Output of the 'understand query' step."""

    intent: Literal["greeting_or_smalltalk", "csvtu_question", "off_topic"] = Field(
        description="greeting_or_smalltalk: hello/hi/namaste/thanks/bye/how are you/who are you/who made you/what can you do. "
        "csvtu_question: any request for information about UTD, CSVTU, their courses, syllabus, exams, results, rules, "
        "attendance, admissions, fees, notices, campus, faculty or academic procedures. "
        "off_topic: anything else."
    )
    standalone_query: str = Field(
        description="The question rewritten as a complete standalone English search query, using the chat history to "
        "resolve words like 'it' or 'that'. If the question is about the college, campus, department, courses, "
        "admission or faculty, assume it is about UTD CSVTU Bhilai and include 'UTD CSVTU' in the query. "
        "Keep important terms (branch, semester, exam name)."
    )


class ContextEvaluation(BaseModel):
    """Output of the 'evaluate context' steps."""

    sufficient: bool = Field(
        description="True only if the context directly contains the information needed to answer the question."
    )
    reason: str = Field(description="One short sentence.")


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatTurn] = []
    lang: str = "en"   # "en" | "hi" | "both"


# ----------------------------------------------------------------------------
# KNOWLEDGE BASE (built-in UTD facts + PDFs -> chunks -> embeddings -> in-memory store)
# ----------------------------------------------------------------------------
class KnowledgeBase:
    def __init__(self):
        self.ready = False
        self.building = False
        self.vector_store = None
        self.files: List[Dict] = []
        self.chunks = 0
        self.warnings: List[str] = []


KB = KnowledgeBase()


def infer_doc_type(filename: str) -> str:
    """Guess the document type from the PDF filename."""
    name = filename.lower()
    rules = [
        ("syllabus", "Syllabus"), ("scheme", "Syllabus"), ("ordinance", "Ordinance"),
        ("regulation", "Regulation"), ("calendar", "Academic Calendar"), ("notification", "Notification"),
        ("notice", "Notification"), ("circular", "Notification"), ("admission", "Admission"),
        ("result", "Result"), ("exam", "Examination"), ("time", "Timetable"),
    ]
    for keyword, label in rules:
        if keyword in name:
            return label
    return "General"


def list_pdf_files() -> List[Path]:
    if not PDF_DIR.is_dir():
        return []
    return sorted(p for p in PDF_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def build_knowledge_base():
    """Runs in a background thread so the server starts instantly."""
    KB.building = True
    KB.ready = False
    warnings: List[str] = []
    files: List[Dict] = []
    store = None
    chunk_count = 0
    try:
        if not os.getenv("MISTRAL_API_KEY"):
            warnings.append("MISTRAL_API_KEY is missing in .env, so the knowledge base cannot be built.")
        else:
            to_index: List[Document] = builtin_documents()   # UTD facts are always included

            # 1) Load PDFs (a bad PDF is skipped, not fatal)
            raw_docs: List[Document] = []
            if not PDF_DIR.is_dir():
                warnings.append(f"Folder '{PDF_DIR.name}/' not found. Using built-in UTD knowledge only.")
            else:
                for pdf in list_pdf_files():
                    try:
                        reader = PdfReader(str(pdf))
                        if reader.is_encrypted:
                            reader.decrypt("")
                        kept = 0
                        for page_no, page in enumerate(reader.pages, start=1):
                            text = (page.extract_text() or "").strip()
                            if not text:
                                continue  # empty / scanned page
                            raw_docs.append(
                                Document(
                                    page_content=text,
                                    metadata={"source": pdf.name, "page_number": page_no, "doc_type": infer_doc_type(pdf.name)},
                                )
                            )
                            kept += 1
                        if kept:
                            files.append({"name": pdf.name, "type": infer_doc_type(pdf.name), "pages": kept})
                        else:
                            warnings.append(f"{pdf.name}: no readable text (maybe scanned). Skipped.")
                    except Exception as exc:
                        warnings.append(f"{pdf.name}: could not be read ({exc}). Skipped.")
                if not files:
                    warnings.append(f"No usable PDFs in '{PDF_DIR.name}/'. Using built-in UTD knowledge only.")

            # 2) Split PDF pages into chunks
            if raw_docs:
                splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
                to_index += splitter.split_documents(raw_docs)
            chunk_count = len(to_index)

            # 3) Embed everything into an in-memory vector store
            try:
                store = InMemoryVectorStore(MistralAIEmbeddings(model=MISTRAL_EMBED_MODEL))
                for i in range(0, len(to_index), EMBED_BATCH_SIZE):
                    batch = to_index[i : i + EMBED_BATCH_SIZE]
                    for attempt in range(3):  # simple retry for rate limits
                        try:
                            store.add_documents(batch)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            threading.Event().wait(2 * (attempt + 1))
            except Exception as exc:
                store = None
                warnings.append(f"Embedding failed: {exc}")
    except Exception as exc:
        store = None
        warnings.append(f"Unexpected error while building the knowledge base: {exc}")
    finally:
        KB.vector_store = store
        KB.files = files
        KB.chunks = chunk_count
        KB.warnings = warnings
        KB.ready = True
        KB.building = False
        # Admin info goes to the terminal only, never to the browser
        print(f"[kb] Built-in UTD facts: {len(UTD_FACTS)}")
        for f in files:
            print(f"[kb] Loaded: {f['name']} ({f['pages']} pages, {f['type']})")
        print(f"[kb] Indexed {chunk_count} chunks in total")
        for w in warnings:
            print(f"[kb] WARNING: {w}")


def start_background_build():
    if not KB.building:
        KB.building = True
        threading.Thread(target=build_knowledge_base, daemon=True).start()


# ----------------------------------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------------------------------
def history_to_messages(history: List[Dict[str, str]]):
    out = []
    for h in history[-MAX_HISTORY_TURNS:]:
        out.append(HumanMessage(content=h["content"]) if h["role"] == "user" else AIMessage(content=h["content"]))
    return out


def history_to_text(history: List[Dict[str, str]]) -> str:
    return "\n".join(f"{h['role']}: {h['content'][:300]}" for h in history[-MAX_HISTORY_TURNS:]) or "(none)"


def chunk_text(chunk) -> str:
    content = chunk.content
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)


def stream_llm(llm, messages, writer) -> str:
    """Streams LLM tokens to the browser as they are generated."""
    parts = []
    for chunk in llm.stream(messages):
        text = chunk_text(chunk)
        if text:
            parts.append(text)
            writer({"type": "token", "text": text})
    return "".join(parts)


def tavily_enabled() -> bool:
    return bool(os.getenv("TAVILY_API_KEY"))


def parse_tavily(response, official_only: bool = False) -> List[Dict]:
    results = []
    if not isinstance(response, dict):
        return results
    for item in response.get("results", []):
        url = item.get("url", "")
        host = urlparse(url).netloc.lower()
        official = host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)
        if official_only and not official:
            continue
        results.append(
            {"title": item.get("title", ""), "url": url, "domain": host, "official": official,
             "content": (item.get("content") or "")[:800]}
        )
    return results


def web_sources(results: List[Dict]) -> List[Dict]:
    seen, out = set(), []
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append({"kind": "web", "name": r["domain"], "title": r["title"], "url": r["url"], "official": r["official"]})
    return out


# ----------------------------------------------------------------------------
# LANGGRAPH AGENT
# ----------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    question: str
    history: List[Dict[str, str]]
    language: str            # english | hindi | both  (chosen in the UI)
    intent: str
    standalone_query: str
    docs: List[Document]
    docs_ok: bool
    web_results: List[Dict]
    web_ok: bool
    route: str


def build_graph(llm: ChatMistralAI):
    """
    START -> understand_query
        greeting / off-topic -> casual_reply -> END
        UTD/CSVTU question -> retrieve_kb (built-in UTD facts + PDFs) -> evaluate_kb
            enough -> generate_answer -> END
            else -> web_search -> evaluate_web
                enough -> generate_answer -> END
                else -> not_found -> END
    Every node that talks to the user streams its text through get_stream_writer().
    """

    def judge(question: str, context: str) -> bool:
        if not context.strip():
            return False
        try:
            result = llm.with_structured_output(ContextEvaluation).invoke(
                [
                    SystemMessage(
                        content="You check retrieval quality for a university assistant. Answer sufficient=true ONLY if "
                        "the context directly contains the specific information asked (facts, numbers, dates, subjects). "
                        "Related but non-answering context -> false. If the user asks for latest/current/today "
                        "information and the context does not clearly look current -> false."
                    ),
                    HumanMessage(content=f"Question: {question}\n\nContext:\n{context}"),
                ]
            )
            return result.sufficient
        except Exception:
            return True  # if the judge fails, let the answer step decide (it must not invent)

    # --- 1. Understand the query -------------------------------------------
    def understand_query(state: AgentState) -> AgentState:
        question = state["question"]
        try:
            r = llm.with_structured_output(QueryAnalysis).invoke(
                [
                    SystemMessage(content="Analyze the user's message for the UTD CSVTU university assistant. Use the chat history to resolve references."),
                    HumanMessage(content=f"Chat history:\n{history_to_text(state.get('history', []))}\n\nUser message: {question}"),
                ]
            )
            return {"intent": r.intent, "standalone_query": r.standalone_query or question}
        except Exception:
            return {"intent": "csvtu_question", "standalone_query": question}

    # --- 2a. Greeting / small talk / off-topic ------------------------------
    def casual_reply(state: AgentState) -> AgentState:
        writer = get_stream_writer()
        system = CASUAL_PROMPT.replace("{language_rule}", LANGUAGE_RULES[state["language"]])
        messages = [SystemMessage(content=system)] + history_to_messages(state.get("history", [])) + [HumanMessage(content=state["question"])]
        try:
            stream_llm(llm, messages, writer)
            writer({"type": "done", "sources": [], "route": "casual"})
        except Exception as exc:
            writer({"type": "error", "text": f"Mistral API error: {exc}"})
        return {"route": "casual"}

    # --- 2b. Retrieval: built-in UTD facts + PDFs ---------------------------
    def retrieve_kb(state: AgentState) -> AgentState:
        writer = get_stream_writer()
        writer({"type": "status", "text": STATUS["searching_kb"][state["language"]]})
        store = KB.vector_store
        if store is None:
            return {"docs": []}
        try:
            return {"docs": store.similarity_search(state["standalone_query"], k=TOP_K)}
        except Exception:
            return {"docs": []}

    def evaluate_kb(state: AgentState) -> AgentState:
        context = "\n\n".join(d.page_content for d in state.get("docs", []))
        return {"docs_ok": judge(state["standalone_query"], context)}

    # --- 3. Tavily web search (only when the knowledge base is not enough) ---
    def web_search(state: AgentState) -> AgentState:
        writer = get_stream_writer()
        writer({"type": "status", "text": STATUS["searching_web"][state["language"]]})
        query = state["standalone_query"]
        results: List[Dict] = []
        try:
            official = TavilySearch(max_results=4, include_domains=[OFFICIAL_DOMAIN])
            results = parse_tavily(official.invoke({"query": query}), official_only=True)
            if not results:  # fall back to a general search (labelled as unofficial later)
                general = TavilySearch(max_results=4)
                results = parse_tavily(general.invoke({"query": f"CSVTU {query}"}))
        except Exception:
            results = []
        return {"web_results": results}

    def evaluate_web(state: AgentState) -> AgentState:
        context = "\n\n".join(f"{r['domain']}: {r['content']}" for r in state.get("web_results", []))
        return {"web_ok": judge(state["standalone_query"], context)}

    # --- 4a. Final structured answer (streamed) ------------------------------
    def generate_answer(state: AgentState) -> AgentState:
        writer = get_stream_writer()
        docs = state.get("docs", []) if state.get("docs_ok") else []
        web = state.get("web_results", []) if state.get("web_ok") else []

        # File names and page numbers are deliberately NOT sent to the model, so they can never leak into answers.
        blocks = [f"[KB] topic={d.metadata.get('doc_type', 'General')}\n{d.page_content}" for d in docs]
        for w in web:
            tag = "WEB-OFFICIAL" if w["official"] else "WEB-UNOFFICIAL"
            blocks.append(f"[{tag}] title={w['title']} | url={w['url']}\n{w['content']}")
        context = "\n\n---\n\n".join(blocks)

        system = ANSWER_PROMPT.replace("{language_rule}", LANGUAGE_RULES[state["language"]])
        messages = (
            [SystemMessage(content=system)]
            + history_to_messages(state.get("history", []))
            + [HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['question']}")]
        )
        try:
            stream_llm(llm, messages, writer)
        except Exception as exc:
            writer({"type": "error", "text": f"Mistral API error: {exc}"})
            return {"route": "error"}

        sources = ([{"kind": "kb"}] if docs else []) + web_sources(web)
        route = "kb+web" if docs and web else ("kb" if docs else "web")
        writer({"type": "done", "sources": sources, "route": route})
        return {"route": route}

    # --- 4b. Nothing found anywhere -> say it plainly ------------------------
    def not_found(state: AgentState) -> AgentState:
        writer = get_stream_writer()
        writer({"type": "token", "text": NOT_FOUND[state["language"]]})
        writer({"type": "done", "sources": [], "route": "not_found"})
        return {"route": "not_found"}

    # --- Routing decisions ------------------------------------------------------
    def after_understand(state: AgentState) -> str:
        return "retrieve_kb" if state.get("intent") == "csvtu_question" else "casual_reply"

    def after_evaluate_kb(state: AgentState) -> str:
        if state.get("docs_ok"):
            return "generate_answer"
        return "web_search" if tavily_enabled() else "not_found"

    def after_web_search(state: AgentState) -> str:
        return "evaluate_web" if state.get("web_results") else "not_found"

    def after_evaluate_web(state: AgentState) -> str:
        return "generate_answer" if state.get("web_ok") else "not_found"

    graph = StateGraph(AgentState)
    for name, fn in [
        ("understand_query", understand_query), ("casual_reply", casual_reply), ("retrieve_kb", retrieve_kb),
        ("evaluate_kb", evaluate_kb), ("web_search", web_search), ("evaluate_web", evaluate_web),
        ("generate_answer", generate_answer), ("not_found", not_found),
    ]:
        graph.add_node(name, fn)

    graph.add_edge(START, "understand_query")
    graph.add_conditional_edges("understand_query", after_understand, {"retrieve_kb": "retrieve_kb", "casual_reply": "casual_reply"})
    graph.add_edge("retrieve_kb", "evaluate_kb")
    graph.add_conditional_edges("evaluate_kb", after_evaluate_kb, {"generate_answer": "generate_answer", "web_search": "web_search", "not_found": "not_found"})
    graph.add_conditional_edges("web_search", after_web_search, {"evaluate_web": "evaluate_web", "not_found": "not_found"})
    graph.add_conditional_edges("evaluate_web", after_evaluate_web, {"generate_answer": "generate_answer", "not_found": "not_found"})
    graph.add_edge("casual_reply", END)
    graph.add_edge("generate_answer", END)
    graph.add_edge("not_found", END)
    return graph.compile()


# ----------------------------------------------------------------------------
# FASTAPI APP
# ----------------------------------------------------------------------------
AGENT = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global AGENT
    if os.getenv("MISTRAL_API_KEY"):
        try:
            AGENT = build_graph(ChatMistralAI(model=MISTRAL_CHAT_MODEL, temperature=0))
        except Exception as exc:
            print(f"Could not create the agent: {exc}")
    else:
        print("WARNING: MISTRAL_API_KEY is missing in .env")
    start_background_build()
    yield


app = FastAPI(title="UTD CSVTU AI Assistant", lifespan=lifespan)


def ndjson(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False) + "\n"


@app.get("/api/status")
def status():
    # Only a simple "can the bot answer?" flag. No file names or warnings are exposed to users.
    has_source = KB.vector_store is not None or tavily_enabled()
    return {"ready": KB.ready, "available": AGENT is not None and has_source}


@app.post("/api/chat")
def chat(req: ChatRequest):
    message = req.message.strip()
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    language = {"en": "english", "hi": "hindi", "both": "both"}.get(req.lang, "english")
    history = [
        {"role": t.role, "content": t.content[:1500]}
        for t in req.history[-MAX_HISTORY_TURNS:]
        if t.role in ("user", "assistant") and t.content.strip()
    ]

    def event_stream():
        if AGENT is None:
            yield ndjson({"type": "error", "text": "The assistant is not configured yet. Please try again later."})
            return
        if not KB.ready:
            yield ndjson({"type": "error", "text": "The assistant is still getting ready. Please wait a few seconds and try again."})
            return
        try:
            state = {"question": message, "history": history, "language": language}
            for event in AGENT.stream(state, stream_mode="custom"):
                yield ndjson(event)
        except Exception as exc:
            yield ndjson({"type": "error", "text": f"Something went wrong: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
def index():
    page = STATIC_DIR / "index.html"
    if page.exists():
        return FileResponse(page)
    return HTMLResponse("<h3>static/index.html not found. Create the 'static' folder next to chatbot-csvtu.py.</h3>", status_code=404)


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    print(f"UTD CSVTU AI Assistant running at http://{HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)