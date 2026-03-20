const state = {
  query: "",
  scope: "both",
  conferences: [],
  years: [],
  page: 1,
  perPage: 25,
};

let searchTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  fetchResults();
});


function bindEvents() {
  const input = document.getElementById("search-input");
  input.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      state.query = input.value;
      state.page = 1;
      fetchResults();
    }, 300);
  });

  document.querySelectorAll(".scope-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".scope-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.scope = btn.dataset.scope;
      state.page = 1;
      fetchResults();
    });
  });

  document.querySelectorAll(".conf-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      const conf = btn.dataset.conf;
      const idx = state.conferences.indexOf(conf);
      if (idx >= 0) {
        state.conferences.splice(idx, 1);
      } else {
        state.conferences.push(conf);
      }
      state.page = 1;
      fetchResults();
    });
  });

  document.querySelectorAll(".year-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.classList.toggle("active");
      const year = parseInt(btn.dataset.year);
      const idx = state.years.indexOf(year);
      if (idx >= 0) {
        state.years.splice(idx, 1);
      } else {
        state.years.push(year);
      }
      state.page = 1;
      fetchResults();
    });
  });
}


async function fetchResults() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.conferences.length) params.set("conference", state.conferences.join(","));
  if (state.years.length) params.set("year", state.years.join(","));
  params.set("scope", state.scope);
  params.set("page", state.page);
  params.set("per_page", state.perPage);

  const resultsEl = document.getElementById("results");
  resultsEl.innerHTML = `
    <div class="loading">
      <div class="loading-spinner"></div>
      <p>Searching papers...</p>
    </div>`;

  try {
    const res = await fetch(`/api/search?${params}`);
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    resultsEl.innerHTML = `
      <div class="no-results">
        <h3>Error loading results</h3>
        <p>${err.message}</p>
      </div>`;
  }
}


function renderResults(data) {
  const resultsEl = document.getElementById("results");
  const countEl = document.getElementById("results-count");
  const badge = document.getElementById("total-badge");

  countEl.textContent = `${data.total.toLocaleString()} result${data.total !== 1 ? "s" : ""}`;
  badge.textContent = `${data.total.toLocaleString()} papers`;

  if (data.papers.length === 0) {
    resultsEl.innerHTML = `
      <div class="no-results">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="2"/>
          <line x1="16" y1="16" x2="32" y2="32" stroke="currentColor" stroke-width="2"/>
          <line x1="32" y1="16" x2="16" y2="32" stroke="currentColor" stroke-width="2"/>
        </svg>
        <h3>No papers found</h3>
        <p>Try adjusting your search or filters</p>
      </div>`;
    renderPagination(data, "pagination-top");
    renderPagination(data, "pagination-bottom");
    return;
  }

  resultsEl.innerHTML = data.papers
    .map((p, i) => paperCard(p, i))
    .join("");

  resultsEl.querySelectorAll(".toggle-abstract").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".paper-card");
      const abs = card.querySelector(".paper-abstract");
      abs.classList.toggle("visible");
      btn.textContent = abs.classList.contains("visible")
        ? "Hide abstract"
        : "Show abstract";
    });
  });

  renderPagination(data, "pagination-top");
  renderPagination(data, "pagination-bottom");
}


function paperCard(paper, index) {
  const confClass = paper.conference
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace("&", "");

  const title = highlightText(escapeHtml(paper.title));
  const authors = escapeHtml(paper.authors);
  const abstract = paper.abstract
    ? highlightText(escapeHtml(paper.abstract))
    : "<em>Abstract not available</em>";

  return `
    <article class="paper-card" style="animation-delay: ${index * 30}ms">
      <div class="paper-meta">
        <span class="conf-label ${confClass}">${escapeHtml(paper.conference)}</span>
        <span class="year-label">${paper.year}</span>
      </div>
      <h3 class="paper-title">${title}</h3>
      <p class="paper-authors">${authors}</p>
      ${paper.abstract
        ? `<button class="toggle-abstract">Show abstract</button>
           <div class="paper-abstract">${abstract}</div>`
        : `<div class="paper-abstract visible" style="border-top:none;margin-top:6px;padding-top:0">
             <em style="color:var(--text-muted)">Abstract not available</em>
           </div>`
      }
    </article>`;
}


function renderPagination(data, containerId) {
  const container = document.getElementById(containerId);
  if (data.pages <= 1) {
    container.innerHTML = "";
    return;
  }

  const maxButtons = 7;
  let startPage = Math.max(1, data.page - Math.floor(maxButtons / 2));
  let endPage = Math.min(data.pages, startPage + maxButtons - 1);
  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  let html = `<button class="page-btn" ${data.page <= 1 ? "disabled" : ""}
    onclick="goToPage(${data.page - 1})">Prev</button>`;

  if (startPage > 1) {
    html += `<button class="page-btn" onclick="goToPage(1)">1</button>`;
    if (startPage > 2) html += `<span style="color:var(--text-muted);padding:0 4px">...</span>`;
  }

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="page-btn ${i === data.page ? "active" : ""}"
      onclick="goToPage(${i})">${i}</button>`;
  }

  if (endPage < data.pages) {
    if (endPage < data.pages - 1) html += `<span style="color:var(--text-muted);padding:0 4px">...</span>`;
    html += `<button class="page-btn" onclick="goToPage(${data.pages})">${data.pages}</button>`;
  }

  html += `<button class="page-btn" ${data.page >= data.pages ? "disabled" : ""}
    onclick="goToPage(${data.page + 1})">Next</button>`;

  container.innerHTML = html;
}


function goToPage(page) {
  state.page = page;
  fetchResults();
  window.scrollTo({ top: 0, behavior: "smooth" });
}


function highlightText(text) {
  if (!state.query) return text;
  const words = state.query.split(/\s+/).filter(Boolean);
  let result = text;
  for (const word of words) {
    const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp(`(${escaped})`, "gi");
    result = result.replace(re, "<mark>$1</mark>");
  }
  return result;
}


function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
