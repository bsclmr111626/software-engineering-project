// Accessibility audit of every main page: axe-core (WCAG 2.0/2.1/2.2 A+AA + best practice) at
// 1280px and 390px, visible keyboard focus on every tab stop, reflow (no horizontal page scroll
// at 390px) and console/CSP errors.
//
// Prerequisites: server running (DJANGO_DEBUG=true), `seed_codeguard --demo-users`, and
// demo_analyst owning at least two runs and one private scenario (see README "Verification").
// Optional: CODEGUARD_ERROR_URL=http://127.0.0.1:8001 for a DEBUG=false server so the real 404
// page is audited (Django shows its technical 404 page when DEBUG is true).
import { writeFileSync } from 'node:fs';
import { launch, BASE, THEME } from './cdp.mjs';

const ERROR_BASE = process.env.CODEGUARD_ERROR_URL;

async function discover(client) {
  // Find demo_analyst's own reports and private scenario from the app itself.
  return client.eval(`(async () => {
    const parse = async (url) => new DOMParser().parseFromString(await (await fetch(url)).text(), 'text/html');
    const runs = [...(await parse('/reports/?scope=mine')).querySelectorAll('table a[href^="/simulations/"]')]
      .map(a => a.getAttribute('href')).filter((h, i, all) => all.indexOf(h) === i);
    const priv = (await parse('/threats/?visibility=private&status=all')).querySelector('tbody a[href^="/threats/"]');
    const item = (await parse('/remediation/?status=all')).querySelector('tbody a[href^="/remediation/"]');
    return { runs, privateScenario: priv && priv.getAttribute('href'), remediationItem: item && item.getAttribute('href') };
  })()`);
}

async function keyboard(c) {
  await c.eval('document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); true');
  const stops = [];
  for (let i = 0; i < 120; i++) {
    await c.key('Tab', 'Tab', 9);
    const info = await c.eval(`(() => {
      const e = document.activeElement;
      if (!e || e === document.body) return null;
      const s = getComputedStyle(e);
      // Focus inside a native control's own UI (e.g. the calendar button of a date input) leaves the
      // input as activeElement without matching :focus; the browser draws that ring itself, which a
      // screenshot confirmed (2026-10-26), so it is not counted as missing focus.
      const nativePart = e.tagName === 'INPUT' && !e.matches(':focus');
      const visible = nativePart || (s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== 'none');
      const r = e.getBoundingClientRect();
      const label = (e.getAttribute('aria-label') || e.labels?.[0]?.innerText || e.innerText || e.value || '').trim().replace(/\\s+/g, ' ').slice(0, 40);
      return { tag: e.tagName.toLowerCase(), label, visible, onscreen: r.width > 0 && r.height > 0, path: e.id || String(e.className) };
    })()`);
    if (!info) break;
    const key = `${info.tag}|${info.path}|${info.label}`;
    if (stops.length && stops[0].key === key) break;
    stops.push({ ...info, key });
  }
  return stops;
}

async function auditPage(client, url) {
  client.consoleErrors = [];
  await client.goto(url);
  const violations = await client.axe();
  const stops = await keyboard(client);
  await client.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await client.goto(url);
  const innerWidth = await client.eval('innerWidth');  // > 390 means the mobile browser had to zoom out
  const mobileViolations = await client.axe();
  await client.send('Emulation.clearDeviceMetricsOverride');
  return {
    violations, mobileViolations, reflowOverflowPx: innerWidth - 390, tabStops: stops.length,
    invisibleFocus: stops.filter((s) => !s.visible).map((s) => `${s.tag}:${s.label || s.path}`),
    consoleErrors: client.consoleErrors,
  };
}

const report = {};
const groups = [
  ['anonymous', BASE, ['/', '/help/', '/accounts/login/', '/accounts/register/', '/accounts/password/reset/']],
  ['demo_analyst', BASE, null],
  ['demo_admin', BASE, ['/settings/users/', '/settings/organization/', '/audit/', '/audit/?view=table']],
];
if (ERROR_BASE) groups.push(['anonymous', ERROR_BASE, ['/no-such-page/', '/threats/']]);

let port = 9350;
for (const [user, base, fixed] of groups) {
  const { proc, client } = await launch(port++);
  try {
    if (user !== 'anonymous') await client.login(user);
    let paths = fixed;
    if (!paths) {
      const found = await discover(client);
      const [latest, previous] = found.runs;
      paths = ['/overview/', '/supply-chain/', '/supply-chain/cicd/', '/threats/', '/threats/compromised-developer-account/',
        '/threats/new/', '/threats/controls/', '/threats/controls/mfa/', '/simulations/',
        '/simulations/new/?scenario=compromised-developer-account', '/simulations/results/', '/risk/',
        '/simulations/compare/', '/remediation/', '/reports/', '/audit/', '/notifications/', '/accounts/password/change/',
        '/settings/profile/', '/settings/account/', '/settings/appearance/', '/settings/typography/', '/settings/display/',
        '/settings/accessibility/', '/settings/notifications/', '/settings/privacy/', '/settings/security/',
        '/settings/sessions/'];
      if (found.remediationItem) paths.push(found.remediationItem);
      if (latest) {
        paths.push(latest, `/reports/${latest.split('/')[2]}/`);
        for (const section of ['stages', 'paths', 'controls', 'method']) paths.push(`${latest}${section}/`);
      }
      if (latest && previous) paths.push(`/simulations/compare/?a=${previous.split('/')[2]}&b=${latest.split('/')[2]}`);
      if (found.privateScenario) paths.push(`${found.privateScenario}edit/`, `${found.privateScenario}delete/`);
      if (!latest || !found.privateScenario) console.warn('NOTE: demo_analyst has no runs or private scenario; those pages were skipped.');
    }
    for (const path of paths) report[`${user} ${base === BASE ? '' : base}${path}`] = await auditPage(client, base + path);
  } finally {
    proc.kill();
  }
}

const reportName = THEME === 'dark' ? 'audit-report-dark.json' : 'audit-report.json';
writeFileSync(new URL(`./${reportName}`, import.meta.url), JSON.stringify(report, null, 2));
let problems = 0;
for (const [page, r] of Object.entries(report)) {
  const fmt = (list) => list.map((x) => `${x.id}(${x.impact},${x.count})`).join(' ') || 'none';
  const bad = r.violations.length + r.mobileViolations.length + r.invisibleFocus.length + r.consoleErrors.length + (r.reflowOverflowPx > 0 ? 1 : 0);
  problems += bad;
  console.log(`${bad ? 'FAIL' : 'PASS'} ${page}\n     axe@1280: ${fmt(r.violations)} | axe@390: ${fmt(r.mobileViolations)} | tab stops: ${r.tabStops}, without visible focus: ${r.invisibleFocus.length} | reflow overflow: ${r.reflowOverflowPx}px | console errors: ${r.consoleErrors.length}`);
}
console.log(`\n${Object.keys(report).length} pages audited (${THEME} theme), ${problems} problem(s). Details: tools/a11y/${reportName}`);
process.exitCode = problems ? 1 : 0;
