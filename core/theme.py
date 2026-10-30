"""The pre-paint theme script and its CSP hash.

The script must run inline in <head>, before the stylesheets apply, so the
page never paints in the wrong theme. The CSP allows exactly this script by
its SHA-256 hash (no 'unsafe-inline'); keeping the source in one constant
means the rendered script and the hash cannot drift apart.

Choice order: a signed-in user's saved preference (rendered by the server as
data-theme-pref on <html>: "light", "dark" or "system"); for visitors, the
theme saved by the toggle (localStorage); otherwise the OS setting
(prefers-color-scheme). data-bs-theme is set too, so Bootstrap's own
widgets (select arrows, close buttons, native controls) follow along.
"""

import base64
import hashlib

STORAGE_KEY = "codeguard-theme"

INIT_SCRIPT = (
    '(function(){var d=document.documentElement,p=d.getAttribute("data-theme-pref"),t=null;'
    'if(p==="light"||p==="dark"){t=p}'
    f'else if(p!=="system"){{try{{t=localStorage.getItem("{STORAGE_KEY}")}}catch(e){{}}}}'
    'if(t!=="light"&&t!=="dark"){t=window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}'
    'd.setAttribute("data-theme",t);d.setAttribute("data-bs-theme",t)})();'
)

INIT_SCRIPT_HASH = f"'sha256-{base64.b64encode(hashlib.sha256(INIT_SCRIPT.encode()).digest()).decode()}'"
