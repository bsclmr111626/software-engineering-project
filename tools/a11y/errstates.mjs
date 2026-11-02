// axe-core on pages in their validation-error state, plus checks that every aria-describedby
// target exists (so screen readers announce the error text).
import { launch, BASE } from './cdp.mjs';

let failures = 0;
async function report(c, label) {
  const v = await c.axe();
  const linked = await c.eval(`[...document.querySelectorAll('[aria-describedby]')].every(el => el.getAttribute('aria-describedby').split(' ').every(id => document.getElementById(id)))`);
  const invalid = await c.eval('document.querySelectorAll("[aria-invalid=true]").length');
  const alerts = await c.eval('[...document.querySelectorAll("[role=alert]")].map(a => a.innerText.trim().replace(/\\s+/g, " ").slice(0, 80))');
  const ok = !v.length && linked;
  if (!ok) failures++;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}: axe ${v.map((x) => x.id).join(', ') || 'none'} | describedby targets exist: ${linked} | aria-invalid fields: ${invalid} | alerts: ${JSON.stringify(alerts)}`);
}

let { proc, client } = await launch(9370);
try {
  await client.goto(`${BASE}/accounts/login/`);
  await client.submit({ '#id_username': 'demo_analyst', '#id_password': 'wrong-password' }, 'main form button[type=submit]');
  await report(client, 'failed login');
  await client.goto(`${BASE}/accounts/register/`);
  await client.submit({ '#id_username': 'x', '#id_email': 'not-an-email', '#id_password1': 'short', '#id_password2': 'other' }, 'main form button[type=submit]');
  await report(client, 'invalid registration');
} finally { proc.kill(); }

({ proc, client } = await launch(9371));
try {
  await client.login('demo_analyst');
  await client.goto(`${BASE}/threats/new/`);
  await client.submit({ '#id_name': 'A11y error state', '#id_description': 'x', '#id_rules-0-probability': '150' }, 'main form button[type=submit]');
  await report(client, 'scenario form with an invalid rule probability');
  await client.goto(`${BASE}/simulations/new/?scenario=compromised-developer-account`);
  await client.submit({ '#id_likelihood': '150' }, 'main form[method=post] button[type=submit]');
  await report(client, 'simulation form with likelihood 150');
  await client.goto(`${BASE}/simulations/new/?scenario=compromised-developer-account`);
  await client.submit({ 'input[name=scenario][type=hidden]': 'someone-elses-private-scenario' }, 'main form[method=post] button[type=submit]');
  await report(client, 'unavailable/forged scenario rejected');
} finally { proc.kill(); }
console.log(failures ? `${failures} FAILURE(S)` : 'ALL ERROR-STATE CHECKS PASSED');
process.exitCode = failures ? 1 : 0;
