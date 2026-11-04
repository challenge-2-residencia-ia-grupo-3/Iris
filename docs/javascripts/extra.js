/* ==========================================================================
   Íris — JavaScript Interativo & Micro-Interações para MkDocs
   ========================================================================== */

document.addEventListener("DOMContentLoaded", function () {
  initReadingProgressBar();
  initSearchKeyboardShortcut();
  enhanceRequirementBadges();
  initHeaderScrollElevation();
});

// Suporte à navegação instantânea do MkDocs Material (navigation.instant)
if (typeof document$ !== "undefined") {
  document$.subscribe(function () {
    initReadingProgressBar();
    initSearchKeyboardShortcut();
    enhanceRequirementBadges();
    initHeaderScrollElevation();
  });
}

/**
 * 1. Barra de Progresso de Leitura no topo da tela
 */
function initReadingProgressBar() {
  let progressBar = document.querySelector(".reading-progress-bar");
  if (!progressBar) {
    progressBar = document.createElement("div");
    progressBar.className = "reading-progress-bar";
    document.body.prepend(progressBar);
  }

  window.addEventListener("scroll", function () {
    const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
    if (totalHeight <= 0) {
      progressBar.style.width = "0%";
      return;
    }
    const progress = (window.scrollY / totalHeight) * 100;
    progressBar.style.width = Math.min(Math.max(progress, 0), 100) + "%";
  }, { passive: true });
}

/**
 * 2. Indicador visual de atalho de busca (Cmd+K no Mac / Ctrl+K no Windows/Linux)
 */
function initSearchKeyboardShortcut() {
  const searchInput = document.querySelector(".md-search__input");
  if (!searchInput || searchInput.dataset.hasShortcutBadge) return;

  const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
  const shortcutKey = isMac ? "Cmd+K" : "Ctrl+K";

  const kbdBadge = document.createElement("kbd");
  kbdBadge.textContent = shortcutKey;
  kbdBadge.style.position = "absolute";
  kbdBadge.style.right = "10px";
  kbdBadge.style.top = "50%";
  kbdBadge.style.transform = "translateY(-50%)";
  kbdBadge.style.fontSize = "0.7rem";
  kbdBadge.style.padding = "2px 6px";
  kbdBadge.style.borderRadius = "4px";
  kbdBadge.style.border = "1px solid var(--iris-border-subtle)";
  kbdBadge.style.backgroundColor = "rgba(124, 58, 237, 0.1)";
  kbdBadge.style.color = "var(--iris-primary)";
  kbdBadge.style.pointerEvents = "none";
  kbdBadge.style.fontFamily = "var(--md-code-font-family)";

  const searchForm = document.querySelector(".md-search__form");
  if (searchForm) {
    searchForm.style.position = "relative";
    searchForm.appendChild(kbdBadge);
    searchInput.dataset.hasShortcutBadge = "true";
  }

  // Atalho global Cmd+K / Ctrl+K para focar na busca
  window.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      searchInput.focus();
    }
  });
}

/**
 * 3. Enriquecimento automático de títulos de Requisitos com Badges visuais
 */
function enhanceRequirementBadges() {
  const headings = document.querySelectorAll(".md-typeset h3");
  headings.forEach(function (heading) {
    const text = heading.textContent.trim();

    // Requisitos Funcionais (ex: RF-01: Inserção...)
    if (text.startsWith("RF-") && !heading.querySelector(".badge-rf")) {
      const parts = text.split(":");
      const rfCode = parts[0].trim();
      const rfTitle = parts.slice(1).join(":").trim();

      heading.innerHTML = `
        <span class="badge badge-rf">${rfCode}</span>
        <span style="vertical-align: middle;">${rfTitle}</span>
      `;
    }

    // Requisitos Não Funcionais (ex: RNF-01: Arquitetura...)
    if (text.startsWith("RNF-") && !heading.querySelector(".badge-rnf")) {
      const parts = text.split(":");
      const rnfCode = parts[0].trim();
      const rnfTitle = parts.slice(1).join(":").trim();

      heading.innerHTML = `
        <span class="badge badge-rnf">${rnfCode}</span>
        <span style="vertical-align: middle;">${rnfTitle}</span>
      `;
    }
  });
}

/**
 * 4. Elevação dinâmica do Header ao rolar a página
 */
function initHeaderScrollElevation() {
  const header = document.querySelector(".md-header");
  if (!header) return;

  window.addEventListener("scroll", function () {
    if (window.scrollY > 15) {
      header.classList.add("header-scrolled");
    } else {
      header.classList.remove("header-scrolled");
    }
  }, { passive: true });
}

