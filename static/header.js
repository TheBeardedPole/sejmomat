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
  // Escape, a click elsewhere or focus leaving one closes it. Below 1360px they are
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
  // "Grafiki do udostępnienia": the window is on every page (templates/base.html), its
  // scripts (static/card.js, static/share.js) load on the first click; #grafiki in the
  // address opens it (the header's link on Sejmdle's page leads there).
  const shareBox = document.getElementById("grafiki");
  if (shareBox) {
    let loading = null;
    const openShare = () => {
      loading ??= Promise.all((shareBox.dataset.scripts || "").split(" ").filter(Boolean).map((src) => new Promise((resolve, reject) => {
        const tag = Object.assign(document.createElement("script"), { src, async: false });
        tag.onload = resolve;
        tag.onerror = reject;
        document.head.append(tag);
      }))).catch((e) => { loading = null; throw e; });
      loading.then(() => window.SejmomatShare?.open()).catch(() => {});
      if (topBar?.classList.contains("nav-open") && navToggle) navToggle.click();
    };
    document.addEventListener("click", (e) => {
      if (e.target.closest?.("[data-share-open]")) openShare();
    });
    if (location.hash === "#grafiki") openShare();
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
  const setTheme = (theme) => {
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
  };
  // The style: Sejmomat's own, or "Klasyczny" (static/klasyczny.css on top of style.css), kept
  // like the theme and written into the page by the inline script in <head> (templates/base.html).
  // Pages without it (Sejmdle) leave the style out of the menu.
  const STYLE_KEY = "sejmomat-style";
  const styleHref = document.querySelector('meta[name="sejmomat-style"]')?.content;
  const setStyle = (style) => {
    document.getElementById("style-klasyczny")?.remove();
    if (style === "klasyczny" && styleHref) {
      const link = Object.assign(document.createElement("link"), { rel: "stylesheet", id: "style-klasyczny", href: styleHref });
      document.querySelector('link[rel="stylesheet"][href*="style.css"]')?.after(link);
      document.documentElement.dataset.style = style;
    } else {
      delete document.documentElement.dataset.style;
    }
    try {
      if (style) localStorage.setItem(STYLE_KEY, style);
      else localStorage.removeItem(STYLE_KEY);
    } catch {
      // as for the theme
    }
  };
  // pages built before the "Wygląd" menu: the button switches light and dark, as it did
  document.querySelectorAll(".theme-switch").forEach((btn) => {
    if (btn.closest(".look")) return;
    const sync = () => {
      btn.setAttribute("aria-pressed", String(isDark()));
      syncBar();
    };
    sync();
    systemDark.addEventListener("change", sync);
    btn.addEventListener("click", () => {
      setTheme(isDark() ? "light" : "dark");
      sync();
    });
  });
  // the "Wygląd" button opens a small menu with both choices
  document.querySelectorAll(".look").forEach((look) => {
    const btn = look.querySelector(".theme-switch"), menu = look.querySelector(".look-menu");
    if (!btn || !menu) return;
    const styleGroup = menu.querySelector(".look-style");
    if (styleGroup && !styleHref) styleGroup.hidden = true;
    const sync = () => {
      menu.querySelectorAll("[data-theme-pick]").forEach((b) => b.setAttribute("aria-checked", String((b.dataset.themePick === "dark") === isDark())));
      const style = document.documentElement.dataset.style || "";
      menu.querySelectorAll("[data-style-pick]").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.stylePick === style)));
      syncBar();
    };
    const open = (yes) => {
      menu.hidden = !yes;
      btn.setAttribute("aria-expanded", String(yes));
      if (yes) sync();
    };
    sync();
    systemDark.addEventListener("change", sync);
    btn.addEventListener("click", () => open(menu.hidden));
    menu.addEventListener("click", (e) => {
      const pick = e.target.closest("[data-theme-pick], [data-style-pick]");
      if (!pick) return;
      if (pick.dataset.themePick) setTheme(pick.dataset.themePick);
      else setStyle(pick.dataset.stylePick);
      sync();
    });
    document.addEventListener("click", (e) => { if (!menu.hidden && !look.contains(e.target)) open(false); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !menu.hidden) {
        open(false);
        btn.focus();
      }
    });
  });
})();
