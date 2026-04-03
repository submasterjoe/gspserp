# GSPS ERP — SERP Analyzer Chrome Extension (v2 UI)

Premium-style **glass / soft-depth** popup (400px) and **full options dashboard** with profile, usage streaks, mock analytics, achievements, and SERP hooks.

## Dependencies (all optional / documented)

| Piece | In this build | Optional upgrade |
|--------|----------------|------------------|
| **Tailwind** | Not used (Chrome MV3 CSP + offline). **`css/theme.css`** is hand-authored with the same design tokens. | You can add a local Tailwind build and purge unused classes. |
| **Icons** | Inline **SVG** (no Font Awesome / Lucide CDN). | Drop Lucide as npm package and copy icons into `icons/`. |
| **Charts** | **CSS bar chart** in options (no network). | Add **`chart.umd.min.js`** locally under `lib/` and load before `options.js` if you want Chart.js. |
| **Fonts** | **System stack** + `Inter`/`Segoe UI` fallbacks (no Google Fonts fetch). | Bundle `Inter.woff2` and `@font-face` in `theme.css` for pixel-perfect match offline. |

## Files

- `manifest.json` — MV3, `storage`, `activeTab`, `scripting`, broad `host_permissions` for SERP URLs (tighten for production).
- `popup.html` / `popup.js` — profile teaser, usage ring + bar, recent runs, ripple gradient CTAs.
- `options.html` / `options.js` — sidebar, dashboard, profile, SERP prefs, API stub, billing mock.
- `css/theme.css` — light/dark tokens, glassmorphism, toasts, skeleton, chart bars.
- `js/storage.js` — `chrome.storage.local`, usage + streak + achievements.
- `js/profile-utils.js` — greeting, initials, Unsplash helper URL.
- `js/serp-hooks.js` — **replace with your GSPS/SERP logic**; keep function names/signature.
- `background.js` — minimal; extend for alarms / API.

## Migration steps (from an older build)

1. **Backup** your old folder (zip it) — especially `manifest.json`, any `serp-analysis*.js`, and API keys if stored in `chrome.storage`.
2. Extension sources live under **`coding/gspserp-extension/`** next to the FastAPI app (this repo).
3. **Port logic**: move your real “analyze page / parse SERP” code into **`js/serp-hooks.js`** inside `analyzeActiveTab` and `analyzeKeyword` (and call your backend from `background.js` if needed). **Do not rename** `GspsSerp.*` on `globalThis` without updating `popup.js`.
4. If you stored data under a **different storage key**, add a one-time migration in `storage.js` `loadState()`: read old key, map fields into `gspserp_v2_state`, then remove old key.
5. In Chrome: **Extensions → Developer mode → Load unpacked** → select **`…/coding/gspserp-extension`** (the folder that contains `manifest.json`).
6. In GSPS ERP (web): open **System → SERP extension** (`/tools/serp-extension`) for the install path, status, and how the web UI relates to the extension.
7. **Icons** (optional): add PNGs and reference them in `manifest.json` under `"icons"` / `action.default_icon`.
8. **Tighten permissions**: replace `https://*/*` with your GSPS host only before shipping to users.

## Data model (`chrome.storage.local` key `gspserp_v2_state`)

- `profile` — displayName, email, timezone, avatarMode (`initials`|`url`), avatarUrl  
- `plan` — tier, label, dailyLimit  
- `usage` — dayKey, todayCount, totalAllTime  
- `streak` — count, lastActiveDayKey  
- `preferences` — defaultEngine, defaultCountry, favoriteEngines  
- `recentAnalyses` — `{ keyword, engine, ts, url }[]`  
- `theme` — `light` | `dark`  
- `achievements` — booleans for UI badges  

## Security note

`avatarUrl` is rendered as an `<img src>`. Only allow trusted URLs or use `initials` mode for untrusted input.
