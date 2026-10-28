// Reader choices shared by the home page and broadcast schedule; no DOM work.
const SejmomatInterests = (() => {
const INTERESTS_KEY = "sejmomat-interests";
const REMIND_DAYS = 30;

const daysBetween = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 86400000);

// ---- interests
const readInterests = (storage) => {
  try {
    const s = JSON.parse(storage.getItem(INTERESTS_KEY) || "null");
    return s && typeof s === "object" ? s : null;
  } catch {
    return null;
  }
};
const writeInterests = (storage, value) => {
  try {
    storage.setItem(INTERESTS_KEY, JSON.stringify(value));
  } catch {
    // storage unavailable: the choice lasts for this page only
  }
  return value;
};
// saving (or confirming) starts a new 30-day period; skipping keeps nothing but the skip
const saveInterests = (ids, today) => ({ ids: [...new Set(ids)], saved: today, asked: today });
const confirmInterests = (state, today) => ({ ...state, asked: today });
const skipInterests = (today) => ({ ids: [], skipped: today });
const reminderDue = (state, today) =>
  !!(state && state.ids?.length && state.asked && daysBetween(state.asked, today) >= REMIND_DAYS);


  return { INTERESTS_KEY, REMIND_DAYS, daysBetween, readInterests, writeInterests,
    saveInterests, confirmInterests, skipInterests, reminderDue };
})();
if (typeof module !== "undefined" && module.exports) module.exports = SejmomatInterests;
else window.SejmomatInterests = SejmomatInterests;
