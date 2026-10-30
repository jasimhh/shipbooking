# Theme

## Token summary
- Colors: navy #102A43 (primary text, hero, footer), navy-700 #243B53, navy-500 #486581 (muted text), navy-300 #829AB1 (borders/inputs), white #FFFFFF, grey #E9EEF2 (dividers), grey-100 #F5F7FA (alt section bg), grey-300 #CBD5DF, teal #187B78 (primary buttons, accents), teal-700 #0F5E5C (hover/links), teal-50 #E3F2F1. Status: amber-50 #FFF6E5 / amber-700 #8A5300 (demo, warnings), red-50 #FDECEC / red-700 #A12828, green-50 #E6F4EA / green-700 #1E6B34. Focus ring #F0B429.
- Font: Inter 400/500/600/700, system-ui fallback. h1 clamp(1.75rem,4vw,2.5rem), h2 clamp(1.3rem,2.5vw,1.6rem), h3 1.1rem, body 1rem/1.6.
- Radius 6px (rectangular, never pill). Shadow: 0 1px 2px rgba(16,42,67,.06), 0 4px 16px rgba(16,42,67,.08).
- Container 1120px, gutter 16px, sections 56px vertical. Breakpoints 640 / 760 / 900 / 960px. Inputs/buttons min-height 44px.
- Motion: only 0.15s colour transitions; prefers-reduced-motion disables them.

## Raw source

```css
/* Ship Booking design system */

:root {
  --navy: #102A43;
  --navy-700: #243B53;
  --navy-500: #486581;
  --navy-300: #829AB1;
  --white: #FFFFFF;
  --grey: #E9EEF2;
  --grey-100: #F5F7FA;
  --grey-300: #CBD5DF;
  --teal: #187B78;
  --teal-700: #0F5E5C;
  --teal-50: #E3F2F1;
  --amber-50: #FFF6E5;
  --amber-700: #8A5300;
  --red-50: #FDECEC;
  --red-700: #A12828;
  --green-50: #E6F4EA;
  --green-700: #1E6B34;

  --text: var(--navy);
  --text-muted: var(--navy-500);
  --border: var(--grey-300);
  --focus: #F0B429;

  --font: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --radius: 6px;
  --shadow: 0 1px 2px rgba(16, 42, 67, .06), 0 4px 16px rgba(16, 42, 67, .08);
  --container: 1120px;
  --gutter: 16px;
}

*, *::before, *::after { box-sizing: border-box; }

html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  font-family: var(--font);
  font-size: 1rem;
  line-height: 1.6;
  color: var(--text);
  background: var(--white);
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

main { flex: 1; }

h1, h2, h3 { line-height: 1.25; margin: 0 0 .5em; font-weight: 700; letter-spacing: -.01em; }
h1 { font-size: clamp(1.75rem, 4vw, 2.5rem); }
h2 { font-size: clamp(1.3rem, 2.5vw, 1.6rem); }
h3 { font-size: 1.1rem; }
p { margin: 0 0 1em; }
a { color: var(--teal-700); text-underline-offset: 2px; }
a:hover { color: var(--navy); }
img { max-width: 100%; height: auto; }

:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }

.icon { width: 1.25em; height: 1.25em; flex: none; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; vertical-align: -.25em; }

.container { width: 100%; max-width: var(--container); margin: 0 auto; padding: 0 var(--gutter); }
.narrow { max-width: 760px; }
.section { padding: 56px 0; }
.section-alt { background: var(--grey-100); }
.muted { color: var(--text-muted); }
.small { font-size: .875rem; }
.visually-hidden { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

.skip-link { position: absolute; left: var(--gutter); top: -100px; background: var(--navy); color: var(--white); padding: 8px 12px; border-radius: var(--radius); z-index: 10; }
.skip-link:focus { top: 8px; color: var(--white); }

/* Header */
.site-header { border-bottom: 1px solid var(--grey); background: var(--white); }
.site-header .container { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 24px; padding-top: 14px; padding-bottom: 14px; }
.brand { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; font-size: 1.15rem; color: var(--navy); text-decoration: none; }
.brand .icon { color: var(--teal); width: 1.6em; height: 1.6em; }
.site-nav ul { display: flex; flex-wrap: wrap; gap: 4px 20px; list-style: none; margin: 0; padding: 0; }
.site-nav a { color: var(--navy); text-decoration: none; font-weight: 500; padding: 6px 0; display: inline-block; border-bottom: 2px solid transparent; }
.site-nav a:hover, .site-nav a[aria-current="page"] { border-bottom-color: var(--teal); }

/* Banners and alerts */
.demo-banner { background: var(--amber-50); color: var(--amber-700); font-size: .875rem; padding: 8px 0; border-bottom: 1px solid #F5DDB0; }
.alert { display: flex; gap: 12px; align-items: flex-start; padding: 14px 16px; border-radius: var(--radius); border: 1px solid; margin: 0 0 16px; }
.alert p:last-child { margin: 0; }
.alert-info { background: var(--teal-50); border-color: #B7DEDC; color: var(--teal-700); }
.alert-warning { background: var(--amber-50); border-color: #F5DDB0; color: var(--amber-700); }
.alert-error { background: var(--red-50); border-color: #F3C1C1; color: var(--red-700); }
.alert-success { background: var(--green-50); border-color: #B9DFC4; color: var(--green-700); }

/* Hero */
.hero { background: var(--navy); color: var(--white); padding: 56px 0 64px; }
.hero h1 { color: var(--white); max-width: 22ch; }
.hero .lead { color: #D9E2EC; font-size: 1.125rem; max-width: 58ch; }

/* Forms */
.card { background: var(--white); color: var(--text); border-radius: var(--radius); box-shadow: var(--shadow); padding: 24px; }
.search-form { display: grid; gap: 16px; grid-template-columns: 1fr; margin-top: 28px; }
@media (min-width: 640px) { .search-form { grid-template-columns: 1fr 1fr; } }
@media (min-width: 960px) { .search-form { grid-template-columns: 1.3fr 1.3fr 1fr .7fr auto; align-items: end; } }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-weight: 600; font-size: .9rem; }
.field .help { font-size: .85rem; color: var(--text-muted); }
.field .error { font-size: .875rem; color: var(--red-700); margin: 0; }
input, select, textarea {
  line-height: 1.4;
  font: inherit; color: inherit; width: 100%;
  padding: 10px 12px; min-height: 44px;
  border: 1px solid var(--navy-300); border-radius: var(--radius); background: var(--white);
}
input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid var(--focus); outline-offset: 0; border-color: var(--navy); }
select { height: 44px; }
[aria-invalid="true"] { border-color: var(--red-700); }
.form-stack { display: grid; gap: 18px; }
.hp { position: absolute; left: -10000px; }

.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 44px; padding: 10px 20px; border: 1px solid transparent; border-radius: var(--radius);
  font: inherit; font-weight: 600; text-decoration: none; cursor: pointer;
  transition: background-color .15s ease;
}
.btn-primary { background: var(--teal); color: var(--white); }
.btn-primary:hover { background: var(--teal-700); color: var(--white); }
.btn-secondary { background: var(--white); color: var(--navy); border-color: var(--navy-300); }
.btn-secondary:hover { background: var(--grey-100); color: var(--navy); }

/* Grids and cards */
.grid { display: grid; gap: 20px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }
.tile { border: 1px solid var(--grey); border-radius: var(--radius); padding: 20px; background: var(--white); }
.tile h3 { display: flex; align-items: center; gap: 8px; }
.tile h3 .icon { color: var(--teal); }
.tile p { color: var(--text-muted); margin: 0; }
a.tile { display: block; text-decoration: none; color: inherit; transition: border-color .15s ease; }
a.tile:hover { border-color: var(--teal); }

.steps-list { counter-reset: step; list-style: none; padding: 0; margin: 0; display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.steps-list li { counter-increment: step; position: relative; padding-top: 44px; }
.steps-list li::before { content: counter(step); position: absolute; top: 0; left: 0; width: 32px; height: 32px; border-radius: var(--radius); background: var(--teal-50); color: var(--teal-700); font-weight: 700; display: grid; place-items: center; }
.steps-list p { color: var(--text-muted); margin: 0; }

/* Search results */
.results-header { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: end; gap: 12px; margin: 32px 0 16px; }
.results-header h1 { font-size: 1.5rem; margin: 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.filters { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; }
.filters .field { min-width: 180px; }
.result-list { list-style: none; margin: 0 0 40px; padding: 0; display: grid; gap: 12px; }
.result { display: grid; gap: 16px; grid-template-columns: 1fr; align-items: center; border: 1px solid var(--grey-300); border-radius: var(--radius); padding: 20px; }
@media (min-width: 760px) { .result { grid-template-columns: 2fr 1fr 1fr auto; } }
.times { display: flex; align-items: center; gap: 12px; font-size: 1.25rem; font-weight: 700; }
.times .icon { color: var(--navy-300); }
.meta { color: var(--text-muted); font-size: .9rem; }
.price { font-size: 1.35rem; font-weight: 700; }
.badge { display: inline-block; font-size: .75rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; padding: 2px 8px; border-radius: 4px; vertical-align: middle; }
.badge-demo { background: var(--amber-50); color: var(--amber-700); border: 1px solid #F5DDB0; }
.badge-ok { background: var(--green-50); color: var(--green-700); }
.badge-warn { background: var(--amber-50); color: var(--amber-700); }
.badge-bad { background: var(--red-50); color: var(--red-700); }

/* Tables */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 12px; border-bottom: 1px solid var(--grey); vertical-align: top; }
th { font-size: .85rem; color: var(--text-muted); font-weight: 600; }
td.num, th.num { text-align: right; white-space: nowrap; }

dl.facts { display: grid; grid-template-columns: max-content 1fr; gap: 8px 24px; margin: 0; }
dl.facts dt { color: var(--text-muted); }
dl.facts dd { margin: 0; font-weight: 500; overflow-wrap: anywhere; }

/* Long-form content */
.prose h2 { margin-top: 1.6em; }
.prose ul, .prose ol { padding-left: 1.3em; }
.prose li { margin-bottom: .5em; }
.layout-sidebar { display: grid; gap: 40px; grid-template-columns: 1fr; padding-top: 40px; padding-bottom: 64px; }
.layout-sidebar > * { min-width: 0; }
@media (min-width: 900px) { .layout-sidebar { grid-template-columns: 1fr 260px; } }
.sidenav h2 { font-size: 1rem; }
.sidenav ul { list-style: none; padding: 0; margin: 0; border-left: 2px solid var(--grey); }
.sidenav a { display: block; padding: 6px 14px; text-decoration: none; color: var(--navy); }
.sidenav a[aria-current="page"] { border-left: 2px solid var(--teal); margin-left: -2px; font-weight: 600; }

.page-header { background: var(--grey-100); padding: 40px 0 32px; border-bottom: 1px solid var(--grey); }
.page-header p { color: var(--text-muted); margin: 0; max-width: 65ch; }
.breadcrumb { font-size: .875rem; margin-bottom: 12px; }
.breadcrumb a { color: var(--text-muted); }

details.faq { border-bottom: 1px solid var(--grey); padding: 16px 0; }
details.faq summary { cursor: pointer; font-weight: 600; list-style-position: outside; }
details.faq p { margin: 12px 0 0; color: var(--navy-700); }

/* Footer */
.site-footer { background: var(--navy); color: #D9E2EC; padding: 48px 0 24px; font-size: .9rem; }
.site-footer h2 { color: var(--white); font-size: .95rem; }
.site-footer a { color: #D9E2EC; text-decoration: none; }
.site-footer a:hover { color: var(--white); text-decoration: underline; }
.footer-grid { display: grid; gap: 32px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.footer-grid ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.footer-bottom { border-top: 1px solid var(--navy-700); margin-top: 32px; padding-top: 20px; color: var(--navy-300); }
.not-configured { color: var(--amber-700); background: var(--amber-50); padding: 0 4px; border-radius: 3px; font-size: .9em; }
.site-footer .not-configured { color: #F0B429; background: transparent; padding: 0; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
}

ul.errorlist { list-style: none; margin: 0; padding: 0; color: var(--red-700); font-size: .875rem; }
.field > div { display: flex; flex-direction: column; gap: 6px; }

```
