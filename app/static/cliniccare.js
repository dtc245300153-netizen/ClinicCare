(() => {
  const sidebarToggle = document.querySelector(".menu-toggle");
  const closeSidebar = () => {
    document.body.classList.remove("sidebar-open");
    sidebarToggle?.setAttribute("aria-expanded", "false");
  };

  sidebarToggle?.addEventListener("click", () => {
    const isOpen = document.body.classList.toggle("sidebar-open");
    sidebarToggle.setAttribute("aria-expanded", String(isOpen));
  });

  document.querySelector("[data-close-sidebar]")?.addEventListener("click", closeSidebar);
  document.querySelectorAll(".side-nav a").forEach((link) => {
    link.addEventListener("click", closeSidebar);
  });

  const search = document.querySelector("#table-search");
  const searchBox = document.querySelector(".global-search");
  document.querySelector("[data-toggle-search]")?.addEventListener("click", () => {
    searchBox?.classList.toggle("search-open");
    if (searchBox?.classList.contains("search-open")) search?.focus();
  });

  let lastFocusedElement;
  const openModal = (modal) => {
    if (!modal) return;
    lastFocusedElement = document.activeElement;
    modal.classList.add("open");
    document.body.classList.add("modal-open");
    modal.querySelector("input, select, textarea, button")?.focus();
  };

  const closeModal = (modal) => {
    if (!modal) return;
    modal.classList.remove("open");
    if (!document.querySelector(".modal-backdrop.open")) {
      document.body.classList.remove("modal-open");
      lastFocusedElement?.focus();
    }
  };

  document.querySelectorAll("[data-open-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      openModal(document.getElementById(button.dataset.openModal));
    });
  });

  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.closest(".modal-backdrop")));
  });

  document.querySelectorAll("[data-modal-backdrop]").forEach((backdrop) => {
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) closeModal(backdrop);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      const openBackdrop = document.querySelector(".modal-backdrop.open");
      if (openBackdrop) closeModal(openBackdrop);
      closeSidebar();
      searchBox?.classList.remove("search-open");
    }

    if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const target = event.target;
      if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        document.querySelector("#table-search")?.focus();
      }
    }
  });

  document.querySelectorAll(".alert-close").forEach((button) => {
    button.addEventListener("click", () => button.closest(".alert")?.remove());
  });

  const tables = [...document.querySelectorAll("table[data-page-size]")];

  const updateTable = (table) => {
    const query = search?.value.trim().toLocaleLowerCase("vi") ?? "";
    const rows = [...table.querySelectorAll("tbody .filter-row")];
    const matches = rows.filter((row) =>
      row.textContent.toLocaleLowerCase("vi").includes(query)
    );
    const pageSize = Number(table.dataset.pageSize) || 8;
    const state = table._clinicCarePage ?? { page: 0 };
    const pageCount = Math.max(1, Math.ceil(matches.length / pageSize));
    state.page = Math.min(state.page, pageCount - 1);
    table._clinicCarePage = state;

    rows.forEach((row) => {
      row.hidden = !matches.includes(row);
    });
    matches.forEach((row, index) => {
      row.hidden = index < state.page * pageSize || index >= (state.page + 1) * pageSize;
    });

    const footer = table.closest(".data-panel")?.querySelector(".table-footer");
    const count = footer?.querySelector(".table-count");
    const pagination = footer?.querySelector(".pagination");
    if (!count || !pagination) return;

    const start = matches.length ? state.page * pageSize + 1 : 0;
    const end = Math.min((state.page + 1) * pageSize, matches.length);
    count.textContent = `Hiển thị ${start}–${end} trên ${matches.length} kết quả`;
    pagination.replaceChildren();

    const addPageButton = (label, page, disabled, current = false) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `page-button${current ? " current" : ""}`;
      button.textContent = label;
      button.disabled = disabled;
      if (current) button.setAttribute("aria-current", "page");
      button.addEventListener("click", () => {
        state.page = page;
        updateTable(table);
      });
      pagination.append(button);
    };

    addPageButton("‹", state.page - 1, state.page === 0);
    for (let page = 0; page < pageCount; page += 1) {
      addPageButton(String(page + 1), page, false, page === state.page);
    }
    addPageButton("›", state.page + 1, state.page >= pageCount - 1);
  };

  tables.forEach((table) => updateTable(table));
  search?.addEventListener("input", () => {
    tables.forEach((table) => {
      table._clinicCarePage = { page: 0 };
      updateTable(table);
    });
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const submitButton = form.querySelector('button[type="submit"]');
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.setAttribute("aria-busy", "true");
      }
    });
  });
})();
