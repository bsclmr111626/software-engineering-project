// Minimal Chrome DevTools Protocol client (Node 22+ built-in WebSocket); no Puppeteer needed.
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

export const CHROME = process.env.CHROME_PATH
  || (process.platform === 'win32' ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'google-chrome');
export const BASE = process.env.CODEGUARD_URL || 'http://127.0.0.1:8000';
// CODEGUARD_THEME=dark audits the dark theme: the OS preference is emulated, which is what a
// first-time visitor's theme follows (fresh Chrome profile, so no saved toggle choice).
export const THEME = process.env.CODEGUARD_THEME === 'dark' ? 'dark' : 'light';
export const DEMO_PASSWORD = process.env.DEMO_PASSWORD || 'CodeGuard-demo-2024'; // development-only demo accounts
export const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const axeSource = readFileSync(new URL('./node_modules/axe-core/axe.min.js', import.meta.url), 'utf8');

export async function launch(port) {
  const profile = mkdtempSync(join(tmpdir(), 'cg-chrome-'));
  const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`, '--window-size=1280,900', 'about:blank'], { stdio: 'ignore' });
  for (let i = 0; i < 100; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) {
        const client = new CDP(page.webSocketDebuggerUrl);
        await client.opened;
        await client.send('Page.enable');
        await client.send('Runtime.enable');
        await client.send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: THEME }] });
        return { proc, client };
      }
    } catch { /* Chrome not ready yet */ }
    await sleep(150);
  }
  throw new Error(`Chrome did not start (CHROME_PATH=${CHROME})`);
}

export class CDP {
  constructor(url) {
    this.ws = new WebSocket(url);
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Set();
    this.consoleErrors = [];
    this.opened = new Promise((resolve) => { this.ws.onopen = resolve; });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
        return;
      }
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
        this.consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '));
      }
      if (msg.method === 'Runtime.exceptionThrown') this.consoleErrors.push(msg.params.exceptionDetails.text);
      for (const listener of this.listeners) listener(msg);
    };
  }
  send(method, params = {}) {
    const id = ++this.nextId;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }
  waitFor(method, timeout = 15000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.listeners.delete(fn); reject(new Error(`timeout waiting for ${method}`)); }, timeout);
      const fn = (msg) => { if (msg.method === method) { clearTimeout(timer); this.listeners.delete(fn); resolve(msg.params); } };
      this.listeners.add(fn);
    });
  }
  async goto(url) {
    const loaded = this.waitFor('Page.loadEventFired');
    await this.send('Page.navigate', { url });
    await loaded;
  }
  async eval(expression) {
    const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
    return r.result.value;
  }
  // Fill fields and click a submit button the way a user would, then wait for the next page.
  async submit(fields, buttonSelector) {
    const loaded = this.waitFor('Page.loadEventFired');
    await this.eval(`(() => { const f = ${JSON.stringify(fields)};
      for (const [sel, val] of Object.entries(f)) {
        const el = document.querySelector(sel);
        if (!el) throw new Error('missing ' + sel);
        if (el.type === 'checkbox') el.checked = !!val; else el.value = val;
      }
      document.querySelector(${JSON.stringify(buttonSelector)}).click(); return true; })()`);
    await loaded;
  }
  async key(key, code, keyCode, text) {
    await this.send('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: keyCode, ...(text ? { text } : {}) });
    await this.send('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: keyCode });
  }
  async login(username, password = DEMO_PASSWORD) {
    await this.goto(`${BASE}/accounts/login/`);
    await this.submit({ '#id_username': username, '#id_password': password }, 'main form button[type=submit]');
    const at = await this.eval('location.pathname');
    if (at !== '/overview/') throw new Error(`login failed for ${username} (at ${at})`);
  }
  async axe() {
    await this.eval(axeSource + ';true');
    return this.eval(`axe.run(document, {runOnly: {type: 'tag', values: ${JSON.stringify(TAGS)}}}).then(r => r.violations.map(v => ({
      id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
      examples: v.nodes.slice(0, 3).map(n => ({ target: n.target.join(' '), html: n.html.slice(0, 160) }))
    })))`);
  }
}
