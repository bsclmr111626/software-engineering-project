// End-to-end user journey in real Chrome against the running server. The key steps use the
// keyboard only (Tab / Space / Enter). Writes journey.json for tools/authz_live.py.
import { writeFileSync } from 'node:fs';
import { launch, BASE } from './cdp.mjs';

const stamp = Date.now().toString(36);
const user = `student_${stamp}`;
const password = `Journey-pass-${stamp}-42`;
const log = (ok, msg) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${msg}`); if (!ok) process.exitCode = 1; };
const { proc, client } = await launch(9380);
const out = { user, password };

async function clickLink(selectorOrText) {
  const loaded = client.waitFor('Page.loadEventFired');
  await client.eval(`(() => { const t = ${JSON.stringify(selectorOrText)};
    const el = document.querySelector(t) || [...document.querySelectorAll('a')].find(a => a.textContent.trim().startsWith(t));
    if (!el) throw new Error('no link ' + t); el.click(); return true; })()`);
  await loaded;
}
async function tabTo(selector, max = 200) {
  await client.eval('document.activeElement && document.activeElement.blur(); true');
  for (let i = 1; i <= max; i++) {
    await client.key('Tab', 'Tab', 9);
    if (await client.eval(`document.activeElement.matches(${JSON.stringify(selector)})`)) return i;
  }
  throw new Error(`could not reach ${selector} by keyboard`);
}
async function enterAndWait() {
  const loaded = client.waitFor('Page.loadEventFired');
  await client.key('Enter', 'Enter', 13, '\r');
  await loaded;
}
// A figure on the page, found by its label (metric tiles and the result headline).
const stat = (label) => client.eval(`(() => { const l = [...document.querySelectorAll('.cg-metric-label')].find(e => e.textContent.includes(${JSON.stringify(label)}));
  return parseFloat(l.parentElement.querySelector('.cg-hero-figure, .cg-metric-value').textContent.replace('−', '-')); })()`);
// Stage outcomes live on the result's "Stage analysis" tab.
const stageStates = async (run) => {
  await client.goto(`${BASE}${run}stages/`);
  return client.eval(`[...document.querySelectorAll('article.cg-stage')].map(a => a.querySelector('h3').textContent.trim() + '=' + a.querySelector('.cg-badge').textContent.trim())`);
};
// The configuration form is a stepper: move forward with the keyboard (Tab to Next, Enter).
async function nextStep() {
  await tabTo('main [data-step-next]');
  await client.key('Enter', 'Enter', 13, '\r');
}

try {
  // 1. Register
  await client.goto(`${BASE}/accounts/register/`);
  await client.submit({ '#id_username': user, '#id_email': `${user}@example.com`, '#id_password1': password, '#id_password2': password }, 'main form button[type=submit]');
  log(await client.eval('location.pathname') === '/overview/', `registered "${user}" and landed on the dashboard`);
  log((await client.eval("fetch('/settings/account/').then(r => r.text())")).includes('Analyst'), 'server assigned the Analyst role');

  // 2. Select a threat scenario
  await client.goto(`${BASE}/threats/`);
  await clickLink('a[href="/threats/compromised-developer-account/"]');
  log((await client.eval('document.querySelector("h1").textContent')).includes('Compromised Developer Account'), 'opened "Compromised Developer Account" from the threat library');
  await clickLink('Run simulation');

  // 3. Execute (keyboard only): inputs -> controls -> review, then run
  await nextStep();
  await nextStep();
  const tabs = await tabTo('main form[method=post] button[type=submit]');
  await enterAndWait();
  out.baseline = await client.eval('location.pathname');
  log(/^\/simulations\/[0-9a-f-]{36}\/$/.test(out.baseline), `keyboard-only run: ${tabs} x Tab + Enter -> ${out.baseline}`);

  // 4. Inspect propagation
  const before = { inherent: await stat('Inherent risk'), residual: await stat('Residual risk') };
  before.states = await stageStates(out.baseline);
  await client.goto(`${BASE}${out.baseline}paths/`);
  const events = await client.eval(`[...document.querySelectorAll('table[aria-label^="Every propagation"] tbody tr')].map(r => r.cells[1].textContent.trim() + ': ' + r.cells[6].textContent.trim())`);
  log(before.states.filter((s) => /Entry point|Compromised/.test(s)).length === 5, `propagation: ${before.states.join('; ')}`);
  log(events.length === 5, `${events.length} edges evaluated: ${events.join(' | ')}`);
  log(before.inherent === before.residual, `no controls: inherent ${before.inherent} = residual ${before.residual}`);

  // 5. Enable controls with the keyboard and rerun
  await client.goto(`${BASE}${out.baseline}`);
  await clickLink('a[href^="/simulations/new/?rerun="]');
  await nextStep();
  for (const name of ['Multi-factor authentication', 'Protected branches and mandatory code review']) {
    const id = await client.eval(`[...document.querySelectorAll('input[name=controls]')].find(i => i.labels[0].textContent.trim() === ${JSON.stringify(name)}).id`);
    await tabTo(`#${id}`);
    await client.key(' ', 'Space', 32, ' ');
    log(await client.eval(`document.getElementById(${JSON.stringify(id)}).checked`), `ticked "${name}" with Space`);
  }
  await nextStep();
  await tabTo('main form[method=post] button[type=submit]');
  await enterAndWait();
  out.improved = await client.eval('location.pathname');
  const after = { residual: await stat('Residual risk') };
  after.states = await stageStates(out.improved);
  await client.goto(`${BASE}${out.improved}`);
  log(after.residual < before.residual, `with controls: residual ${before.residual} -> ${after.residual}`);
  log(after.states.some((s) => s.includes('Blocked')), `propagation: ${after.states.join('; ')}`);

  // 6. Compare
  await clickLink('Compare with previous run');
  const delta = await stat('Change in residual risk');
  log(Math.abs(delta - (after.residual - before.residual)) < 0.05, `comparison shows ${delta}`);

  // 7. Reopen the saved report from the Reports list
  await client.goto(`${BASE}/reports/`);
  await clickLink(`table a[href="${out.baseline}"]`);
  const reopened = { inherent: await stat('Inherent risk'), residual: await stat('Residual risk') };
  reopened.states = await stageStates(out.baseline);
  log(JSON.stringify(reopened) === JSON.stringify(before), 'reopened report shows exactly the stored results');

  // 8. Private scenario for tools/authz_live.py
  await client.goto(`${BASE}/threats/compromised-cicd-pipeline/`);
  await clickLink('main form[action$="/clone/"] button');
  out.privateScenario = (await client.eval('location.pathname')).split('/')[2];
  log(Boolean(out.privateScenario), `cloned private scenario ${out.privateScenario}`);
} finally {
  writeFileSync(new URL('./journey.json', import.meta.url), JSON.stringify(out, null, 2));
  proc.kill();
}
