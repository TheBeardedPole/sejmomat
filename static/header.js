// The site's header (templates/_header.html, static/header.css): the Menu fold on
// narrow screens, the submenus and the light/dark switch. Loaded by every page of
// the site and by Sejmdle (games/sejmdle), so it needs nothing from static/app.js.
(() => {
  // On narrow screens the sections fold behind "Menu" (static/header.css); Escape or a
  // click outside the header closes them again.
  const topBar = document.querySelector("header.top");
  const navToggle = topBar?.querySelector(".nav-toggle");
  if (navToggle) {
    const setOpen = (open) => {
      navToggle.setAttribute("aria-expanded", String(open));
      topBar.classList.toggle("nav-open", open);
    };
    navToggle.addEventListener("click", () => setOpen(navToggle.getAttribute("aria-expanded") !== "true"));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && topBar.classList.contains("nav-open")) {
        setOpen(false);
        navToggle.focus();
      }
    });
    document.addEventListener("click", (e) => {
      if (topBar.classList.contains("nav-open") && !topBar.contains(e.target)) setOpen(false);
    });
  }
  // Submenus in the header (Posiedzenia, Ustawy, Posłowie): open on hover with a mouse
  // (static/header.css) and with their ▾ button from the keyboard or a touch screen;
  // Escape, a click elsewhere or focus leaving one closes it. Below 1060px they are
  // listed open under their section in the folded menu, and the buttons are hidden.
  const subToggles = [...document.querySelectorAll("header.top .sub-toggle")];
  const closeSubs = (except) => subToggles.forEach((b) => {
    if (b !== except) {
      b.setAttribute("aria-expanded", "false");
      b.parentElement.classList.remove("open");
    }
  });
  subToggles.forEach((b) => {
    const item = b.parentElement;
    b.addEventListener("click", () => {
      const open = b.getAttribute("aria-expanded") !== "true";
      closeSubs(b);
      b.setAttribute("aria-expanded", String(open));
      item.classList.toggle("open", open);
    });
    item.addEventListener("focusout", (e) => {
      if (!item.contains(e.relatedTarget)) closeSubs();
    });
  });
  if (subToggles.length) {
    document.addEventListener("keydown", (e) => {
      const open = subToggles.find((b) => b.getAttribute("aria-expanded") === "true");
      if (e.key === "Escape" && open) {
        closeSubs();
        open.focus();
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest?.("header.top .nav-item")) closeSubs();
    });
  }
  // Search folds into its button (static/header.css): opened, the field takes the
  // sections' place; Escape, or leaving it empty, folds it again.
  const search = topBar?.querySelector(".site-search");
  const searchToggle = search?.querySelector(".search-toggle");
  if (searchToggle) {
    const field = search.querySelector("input");
    const setSearch = (open) => {
      topBar.classList.toggle("search-open", open);
      searchToggle.setAttribute("aria-expanded", String(open));
      if (open) {
        if (topBar.classList.contains("nav-open") && navToggle) navToggle.click();
        field.focus();
      }
    };
    searchToggle.addEventListener("click", () => setSearch(true));
    field.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        field.value = "";
        setSearch(false);
        searchToggle.focus();
      }
    });
    field.addEventListener("blur", () => {
      if (!field.value.trim()) setSearch(false);
    });
  }
  // Light/dark switch in the header. The choice is kept in localStorage (a
  // setting the reader asked for, so no consent needed) and applied by the
  // inline script in <head> before the page is drawn; with no choice made the
  // page follows the system setting.
  const THEME_KEY = "sejmomat-theme";
  const systemDark = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => (document.documentElement.dataset.theme || (systemDark.matches ? "dark" : "light")) === "dark";
  // The browser's bar follows the theme: the accent in light mode, the header's
  // surface in dark mode (a bright blue bar above a dark page glares).
  const themeColor = document.querySelector('meta[name="theme-color"]');
  const lightBar = themeColor?.content;
  const syncBar = () => {
    if (themeColor) themeColor.content = isDark() ? getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() : lightBar;
  };
  syncBar();
  systemDark.addEventListener("change", syncBar);
  document.querySelectorAll(".theme-switch").forEach((btn) => {
    const sync = () => {
      btn.setAttribute("aria-pressed", String(isDark()));
      syncBar();
    };
    sync();
    systemDark.addEventListener("change", sync);
    btn.addEventListener("click", () => {
      const theme = isDark() ? "light" : "dark";
      document.documentElement.dataset.theme = theme;
      try {
        // picking what the system already shows means "follow the system"
        if (theme === (systemDark.matches ? "dark" : "light")) {
          delete document.documentElement.dataset.theme;
          localStorage.removeItem(THEME_KEY);
        } else {
          localStorage.setItem(THEME_KEY, theme);
        }
      } catch {
        // storage unavailable: the choice lasts for this page only
      }
      sync();
    });
  });
})();
