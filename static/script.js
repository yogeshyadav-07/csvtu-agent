"use strict";

// ---------------------------------------------------------------------------
// UTD CSVTU AI Assistant - frontend logic
// Backend endpoints: POST /api/chat (streamed), GET /api/status
// ---------------------------------------------------------------------------

// ====== EDIT THIS: creator details shown in the footer ======
// Paste your full links between the quotes. A link left empty ("") is hidden automatically.
const OWNER = {
  name: "Yogesh Kumar Yadav",
  portfolio: "",   // e.g. "https://your-portfolio.com"
  github: "",      // e.g. "https://github.com/your-username"
  linkedin: "",    // e.g. "https://www.linkedin.com/in/your-profile"
};

// ---------------------------------------------------------------------------
// UI text in English and Hindi
// ---------------------------------------------------------------------------
const I18N = {
  en: {
    title: "UTD CSVTU AI Assistant",
    subtitle: "University Teaching Department · CSVTU, Bhilai",
    placeholder: "Type your question...",
    send: "Send",
    stop: "Stop",
    hint: "Please verify important dates and fees on csvtu.ac.in.",
    rights: "All rights reserved.",
    heroBadge: "AI assistant for UTD CSVTU",
    heroTitle: "Hi! How can I help you today?",
    heroText: "Ask about courses, admissions, exams, syllabus and rules at the University Teaching Department, CSVTU Bhilai.",
    source: "Source",
    copy: "Copy",
    copied: "Copied ✓",
    kbSource: "UTD CSVTU knowledge base",
    webOfficial: "Official CSVTU website",
    webUnofficial: "Web source, not an official CSVTU document",
    preparing: "The assistant is getting ready... please wait a moment.",
    unavailable: "The assistant is currently unavailable. Please try again later.",
    offline: "Cannot connect to the server.",
    stopped: "Stopped.",
    topics: [
      { icon: "🎓", title: "Programmes at UTD", desc: "Explore the courses offered", prompt: "What programmes does UTD CSVTU offer?" },
      { icon: "📝", title: "Admissions", desc: "How to get admission at UTD", prompt: "How can I get admission at UTD CSVTU?" },
      { icon: "📅", title: "Exams & Attendance", desc: "Exam rules and attendance", prompt: "What is the minimum attendance required to appear in CSVTU exams?" },
      { icon: "📚", title: "Syllabus", desc: "Subjects by branch and semester", prompt: "What subjects are there in the 6th semester of B.Tech CSE (Data Science) at CSVTU?" },
      { icon: "🏛️", title: "About UTD", desc: "History, departments and research", prompt: "Tell me about the University Teaching Department of CSVTU." },
      { icon: "📍", title: "Location & Contact", desc: "Address and admission contact", prompt: "Where is UTD CSVTU located and how can I contact the admission office?" },
    ],
  },
  hi: {
    title: "UTD CSVTU AI सहायक",
    subtitle: "विश्वविद्यालय शिक्षण विभाग · CSVTU, भिलाई",
    placeholder: "अपना सवाल लिखिए...",
    send: "भेजें",
    stop: "रोकें",
    hint: "कृपया ज़रूरी तारीख़ें और शुल्क csvtu.ac.in पर जाँच लें।",
    rights: "सर्वाधिकार सुरक्षित।",
    heroBadge: "UTD CSVTU के लिए AI सहायक",
    heroTitle: "नमस्ते! आज मैं आपकी कैसे मदद करूँ?",
    heroText: "विश्वविद्यालय शिक्षण विभाग, CSVTU भिलाई के कोर्स, प्रवेश, परीक्षा, सिलेबस और नियमों के बारे में पूछिए।",
    source: "स्रोत",
    copy: "कॉपी",
    copied: "कॉपी हो गया ✓",
    kbSource: "UTD CSVTU ज्ञान-आधार",
    webOfficial: "आधिकारिक CSVTU वेबसाइट",
    webUnofficial: "वेब स्रोत, आधिकारिक CSVTU दस्तावेज़ नहीं",
    preparing: "सहायक तैयार हो रहा है... कृपया थोड़ा इंतज़ार करें।",
    unavailable: "सहायक अभी उपलब्ध नहीं है। कृपया बाद में कोशिश करें।",
    offline: "सर्वर से कनेक्ट नहीं हो पा रहा।",
    stopped: "रोक दिया गया।",
    topics: [
      { icon: "🎓", title: "UTD के कोर्स", desc: "उपलब्ध कोर्स देखिए", prompt: "UTD CSVTU में कौन-कौन से कोर्स उपलब्ध हैं?" },
      { icon: "📝", title: "प्रवेश", desc: "UTD में एडमिशन कैसे लें", prompt: "UTD CSVTU में एडमिशन कैसे मिलता है?" },
      { icon: "📅", title: "परीक्षा और उपस्थिति", desc: "परीक्षा के नियम और अटेंडेंस", prompt: "CSVTU की परीक्षा में बैठने के लिए न्यूनतम उपस्थिति कितनी चाहिए?" },
      { icon: "📚", title: "सिलेबस", desc: "ब्रांच और सेमेस्टर के अनुसार विषय", prompt: "CSVTU में B.Tech CSE (Data Science) के 6वें सेमेस्टर में कौन-कौन से विषय हैं?" },
      { icon: "🏛️", title: "UTD के बारे में", desc: "इतिहास, विभाग और रिसर्च", prompt: "CSVTU के विश्वविद्यालय शिक्षण विभाग (UTD) के बारे में बताइए।" },
      { icon: "📍", title: "पता और संपर्क", desc: "पता और एडमिशन संपर्क", prompt: "UTD CSVTU कहाँ स्थित है और एडमिशन ऑफिस से कैसे संपर्क करें?" },
    ],
  },
};

// ---------------------------------------------------------------------------
// Elements and state
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const inputEl = $("input");
const sendBtn = $("sendBtn");
const formEl = $("chatForm");
const bannerEl = $("banner");
const toBottomBtn = $("toBottom");
const themeBtn = $("themeBtn");

const MAX_HISTORY = 6;

let lang = "en";            // "en" | "hi" | "both"  (default English)
let theme = "light";        // default light
let history = [];           // [{role: "user"|"assistant", content: "..."}]
let busy = false;
let chatStarted = false;
let controller = null;      // AbortController for the Stop button

try {
  const savedLang = localStorage.getItem("utd-lang");
  if (["en", "hi", "both"].includes(savedLang)) lang = savedLang;
  if (localStorage.getItem("utd-theme") === "dark") theme = "dark";
} catch (e) { /* storage not available: keep defaults */ }

const uiKey = () => (lang === "hi" ? "hi" : "en");   // "both" uses English UI text
const t = (key) => I18N[uiKey()][key];

// ---------------------------------------------------------------------------
// Tiny, safe Markdown renderer (headings, bold, lists, tables, links)
// ---------------------------------------------------------------------------
function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const out = [];
  let list = null; // "ul" | "ol" | null
  let para = [];

  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\*)/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

  const flushPara = () => {
    if (para.length) { out.push("<p>" + para.map(inline).join("<br>") + "</p>"); para = []; }
  };
  const closeList = () => {
    if (list) { out.push("</" + list + ">"); list = null; }
  };
  const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l || "");
  const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;

    if (!line.trim()) { flushPara(); closeList(); continue; }

    if (line.includes("|") && isTableSep(lines[i + 1])) {
      flushPara(); closeList();
      let html = "<div class='table-wrap'><table><thead><tr>" +
        cells(line).map((c) => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
        html += "<tr>" + cells(lines[i]).map((c) => "<td>" + inline(c) + "</td>").join("") + "</tr>";
        i++;
      }
      i--;
      out.push(html + "</tbody></table></div>");
      continue;
    }

    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { flushPara(); closeList(); out.push("<h4>" + inline(m[2]) + "</h4>"); continue; }
    if (/^-{3,}\s*$/.test(line.trim())) { flushPara(); closeList(); out.push("<hr>"); continue; }

    if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
      flushPara();
      if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; }
      out.push("<li>" + inline(m[1]) + "</li>");
      continue;
    }
    if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushPara();
      if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; }
      out.push("<li>" + inline(m[1]) + "</li>");
      continue;
    }

    closeList();
    para.push(line);
  }
  flushPara(); closeList();
  return out.join("");
}

// ---------------------------------------------------------------------------
// Theme and language
// ---------------------------------------------------------------------------
function applyTheme() {
  document.documentElement.setAttribute("data-theme", theme);
  themeBtn.textContent = theme === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("utd-theme", theme); } catch (e) { /* ignore */ }
}

function applyLanguage() {
  document.documentElement.lang = lang === "hi" ? "hi" : "en";
  document.title = t("title");

  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });

  document.querySelectorAll(".seg-btn").forEach((b) => {
    const on = b.dataset.lang === lang;
    b.classList.toggle("active", on);
    b.setAttribute("aria-checked", on ? "true" : "false");
  });

  $("copyright").textContent = "© " + new Date().getFullYear() + " " + OWNER.name + ". " + t("rights");
  setBusy(busy);                       // refresh Send / Stop label
  if (!chatStarted) renderHero();      // re-draw the welcome cards in the new language
  try { localStorage.setItem("utd-lang", lang); } catch (e) { /* ignore */ }
}

function initFooterLinks() {
  [["linkPortfolio", "portfolio"], ["linkGithub", "github"], ["linkLinkedin", "linkedin"]].forEach(([id, key]) => {
    const a = $(id);
    const url = (OWNER[key] || "").trim();
    if (/^https?:\/\//i.test(url)) { a.href = url; a.classList.remove("hidden"); }
  });
}

// ---------------------------------------------------------------------------
// Chat UI helpers
// ---------------------------------------------------------------------------
function nearBottom() {
  return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 120;
}
function scrollToBottom(smooth) {
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: smooth ? "smooth" : "auto" });
}

function renderHero() {
  messagesEl.innerHTML = "";
  const hero = document.createElement("section");
  hero.className = "hero";
  hero.id = "hero";
  hero.innerHTML =
    '<span class="badge">' + escapeHtml(t("heroBadge")) + "</span>" +
    "<h2>" + escapeHtml(t("heroTitle")) + "</h2>" +
    "<p>" + escapeHtml(t("heroText")) + "</p>" +
    '<div class="cards"></div>';
  const cards = hero.querySelector(".cards");
  t("topics").forEach((tp) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "card";
    b.innerHTML = '<span class="ico">' + tp.icon + '</span><span class="ttl">' + escapeHtml(tp.title) +
      '</span><span class="dsc">' + escapeHtml(tp.desc) + "</span>";
    b.addEventListener("click", () => sendMessage(tp.prompt));
    cards.appendChild(b);
  });
  messagesEl.appendChild(hero);
}

function addUserMessage(text) {
  const row = document.createElement("div");
  row.className = "msg user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollToBottom(false);
}

function addBotMessage() {
  const row = document.createElement("div");
  row.className = "msg bot";
  row.innerHTML =
    '<div class="avatar">U</div>' +
    '<div class="bubble">' +
    '<div class="status"><span class="dots"><i></i><i></i><i></i></span><span class="status-text"></span></div>' +
    '<div class="content"></div>' +
    '<div class="sources hidden"></div>' +
    '<div class="actions hidden"><button type="button" class="act copy"></button></div>' +
    "</div>";
  const parts = {
    row,
    statusBox: row.querySelector(".status"),
    statusText: row.querySelector(".status-text"),
    content: row.querySelector(".content"),
    sources: row.querySelector(".sources"),
    actions: row.querySelector(".actions"),
    copyBtn: row.querySelector(".copy"),
  };
  parts.copyBtn.textContent = t("copy");
  messagesEl.appendChild(row);
  scrollToBottom(false);
  return parts;
}

function renderSources(box, sources) {
  if (!sources || !sources.length) { box.classList.add("hidden"); return; }
  const items = sources.map((s) => {
    if (s.kind === "kb") return "<li>📚 " + escapeHtml(t("kbSource")) + "</li>";
    const label = s.official ? t("webOfficial") : t("webUnofficial");
    const safeUrl = /^https?:\/\//.test(s.url) ? escapeHtml(s.url) : "#";
    return '<li>🌐 <a href="' + safeUrl + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(s.name) +
      '</a> <span class="tag">· ' + escapeHtml(label) + "</span></li>";
  });
  box.innerHTML = "<strong>" + escapeHtml(t("source")) + ":</strong><ul>" + items.join("") + "</ul>";
  box.classList.remove("hidden");
}

async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e2) { /* ignore */ }
    ta.remove();
  }
  btn.textContent = t("copied");
  setTimeout(() => { btn.textContent = t("copy"); }, 1500);
}

function setBusy(value) {
  busy = value;
  sendBtn.textContent = value ? t("stop") : t("send");
  sendBtn.classList.toggle("stop", value);
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
}

// ---------------------------------------------------------------------------
// Sending a message and reading the streamed reply
// ---------------------------------------------------------------------------
async function sendMessage(rawText) {
  const text = (rawText || "").trim();
  if (!text || busy) return;

  if (!chatStarted) {
    chatStarted = true;
    messagesEl.innerHTML = "";   // remove the welcome cards
  }

  addUserMessage(text);
  inputEl.value = "";
  autoGrow();

  const bot = addBotMessage();
  bot.row.classList.add("streaming");
  setBusy(true);
  controller = new AbortController();

  let full = "";
  let gotToken = false;
  let hadError = false;
  let pending = false;

  // Re-render at most once per animation frame while tokens arrive
  const scheduleRender = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      const stick = nearBottom();
      bot.content.innerHTML = renderMarkdown(full);
      if (stick) scrollToBottom(false);
    });
  };

  const handleEvent = (ev) => {
    if (ev.type === "status") {
      bot.statusText.textContent = ev.text;
    } else if (ev.type === "token") {
      if (!gotToken) { gotToken = true; bot.statusBox.classList.add("hidden"); }
      full += ev.text;
      scheduleRender();
    } else if (ev.type === "done") {
      bot.statusBox.classList.add("hidden");
      renderSources(bot.sources, ev.sources);
    } else if (ev.type === "error") {
      hadError = true;
      bot.statusBox.classList.add("hidden");
      bot.content.innerHTML = renderMarkdown(full) + '<p class="error">⚠️ ' + escapeHtml(ev.text) + "</p>";
    }
  };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, history: history.slice(-MAX_HISTORY), lang }),
      signal: controller.signal,
    });
    if (!res.ok || !res.body) throw new Error("Server error (" + res.status + ")");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();   // keep the incomplete last line
      for (const line of lines) {
        if (!line.trim()) continue;
        try { handleEvent(JSON.parse(line)); } catch (e) { /* ignore a broken line */ }
      }
    }
  } catch (err) {
    hadError = true;
    bot.statusBox.classList.add("hidden");
    const msg = err.name === "AbortError" ? t("stopped") : t("offline") + " " + err.message;
    bot.content.innerHTML = renderMarkdown(full) + '<p class="error">' + escapeHtml(msg) + "</p>";
  } finally {
    bot.row.classList.remove("streaming");
    if (!hadError) bot.content.innerHTML = renderMarkdown(full);
    if (full.trim()) {
      bot.actions.classList.remove("hidden");
      bot.copyBtn.addEventListener("click", () => copyText(full, bot.copyBtn));
      history.push({ role: "user", content: text });
      history.push({ role: "assistant", content: full });
      history = history.slice(-MAX_HISTORY * 2);
    }
    setBusy(false);
    controller = null;
    scrollToBottom(false);
    inputEl.focus();
  }
}

// ---------------------------------------------------------------------------
// Service status banner (no file or document names are ever shown to the user)
// ---------------------------------------------------------------------------
async function checkStatus() {
  try {
    const res = await fetch("/api/status");
    const st = await res.json();
    let note = "";
    if (!st.ready) note = t("preparing");
    else if (!st.available) note = t("unavailable");
    bannerEl.textContent = note;
    bannerEl.classList.toggle("hidden", !note);
    if (!st.ready) setTimeout(checkStatus, 2000);
  } catch (e) {
    bannerEl.textContent = t("offline");
    bannerEl.classList.remove("hidden");
    setTimeout(checkStatus, 4000);
  }
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------
formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  if (busy) { if (controller) controller.abort(); return; }
  sendMessage(inputEl.value);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    if (!busy) sendMessage(inputEl.value);
  }
});
inputEl.addEventListener("input", autoGrow);

document.querySelectorAll(".seg-btn").forEach((b) => {
  b.addEventListener("click", () => { lang = b.dataset.lang; applyLanguage(); });
});

themeBtn.addEventListener("click", () => {
  theme = theme === "dark" ? "light" : "dark";
  applyTheme();
});

$("clearBtn").addEventListener("click", () => {
  if (controller) controller.abort();
  history = [];
  chatStarted = false;
  renderHero();
});

messagesEl.addEventListener("scroll", () => { toBottomBtn.classList.toggle("hidden", nearBottom()); });
toBottomBtn.addEventListener("click", () => scrollToBottom(true));

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
applyTheme();
initFooterLinks();
applyLanguage();   // also draws the welcome cards
autoGrow();
checkStatus();