"""Verdant sponsor portal: paste a voucher, see if it is valid, redeem it once.
Stdlib only. Reuses sign() from verdant.py. Deploy on Render (see render.yaml)."""
import hmac, json, os
from http.server import BaseHTTPRequestHandler, HTTPServer
from verdant import sign

REDEEMED = set()  # in-memory; resets on restart (free tier). Use a DB for production.

PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
<title>Verdant</title>
<body style="font-family:system-ui,sans-serif;max-width:640px;margin:2rem auto;padding:0 1rem;color:#1f2937">
<h1 style="margin-bottom:.2rem;color:#14532d">Verdant</h1>
<p style="margin-top:0;color:#6b7280;font-size:1.05rem">Real miles. Real rewards. <span style="color:#9ca3af">· Sponsor Portal</span></p>
<hr style="border:none;border-top:1px solid #e5e7eb;margin:1.2rem 0">
<p>Paste a participant's voucher (<code>voucher.json</code>) below. Each voucher is cryptographically signed and can be redeemed only once.</p>
<textarea id=v rows=12 placeholder="Paste voucher JSON here" style="width:100%;font-family:monospace;padding:.6rem;border:1px solid #d1d5db;border-radius:6px"></textarea><br><br>
<button onclick="go()" style="padding:.7rem 1.4rem;font-size:1rem;background:#166534;color:#fff;border:none;border-radius:6px;cursor:pointer">Verify &amp; redeem</button>
<pre id=out style="font-size:1.05rem;white-space:pre-wrap;margin-top:1.2rem"></pre>
<p style="margin-top:3rem;font-size:.85rem;color:#9ca3af">Powered by open-source AI &middot; Verdant</p>
<script>
async function go(){
  const out=document.getElementById('out');
  try{
    const r=await fetch('/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:document.getElementById('v').value});
    const d=await r.json(); out.textContent=d.message;
  }catch(e){out.textContent='Could not read that voucher. Paste the full JSON.';}
}
</script></body>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(200, PAGE, "text/html; charset=utf-8")

    def do_POST(self):
        try:
            v = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            p, sig = v["payload"], v["sig"]
            if not hmac.compare_digest(sig, sign(p)):
                return self._send(200, json.dumps({"message": "INVALID: signature does not match."}))
            if sig in REDEEMED:
                return self._send(200, json.dumps({"message": "ALREADY REDEEMED: do not ship again."}))
            REDEEMED.add(sig)
            r = p["reward"]
            msg = f"VALID\nQuest: {p['title']}\nTier: {p['tier']}\nShip: {r['reward']} (from {r['sponsor']})"
            self._send(200, json.dumps({"message": msg}))
        except Exception:
            self._send(400, json.dumps({"message": "Bad voucher format."}))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Sponsor portal on http://localhost:{port}")
    HTTPServer(("0.0.0.0", port), H).serve_forever()
