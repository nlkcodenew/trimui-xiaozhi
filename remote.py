import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


PAGE = """<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trimui Xiaozhi</title><style>body{font:18px system-ui;background:#08111f;color:#f2f7fc;max-width:800px;margin:auto;padding:20px}main{background:#14253a;border-radius:16px;padding:22px}article{padding:12px;border-bottom:1px solid #456}button,input{font:inherit;padding:12px;margin:5px;border:0;border-radius:8px}button{background:#25d3ca;color:#08111f}input{width:65%}</style><main><h1>Trimui Xiaozhi</h1><p id="status">Đang kết nối</p><div id="history"></div><input id="message" placeholder="Nhập tin nhắn"><button onclick="send()">Gửi</button><br><button onclick="command('start')">Bắt đầu</button><button onclick="command('stop')">Dừng</button></main><script>
const pin=new URLSearchParams(location.search).get('pin')||prompt('PIN trên thiết bị')||'';
async function request(path,data){let response=await fetch(path+'?pin='+encodeURIComponent(pin),data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});if(!response.ok)throw Error(await response.text());return response.json()}
async function refresh(){try{let state=await request('/api/status');document.querySelector('#status').textContent=state.status;let history=document.querySelector('#history');history.replaceChildren();for(let item of state.history){let line=document.createElement('article');line.textContent=(item.role==='U'?'Bạn: ':'Xiaozhi: ')+item.text;history.append(line)}}catch(error){document.querySelector('#status').textContent=error.message}}
async function command(action,text){try{await request('/api/action',{action,text});await refresh()}catch(error){alert(error.message)}}
async function send(){let input=document.querySelector('#message');await command('text',input.value);input.value=''}setInterval(refresh,1500);refresh();</script></html>"""


def start_remote(service):
    if service.remote:
        service.remote.shutdown()
        service.remote.server_close()
        service.remote = None
    if not service.settings["remote_enabled"]:
        return

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format_string, *args):
            logging.info("remote request from %s", self.client_address[0])

        def respond(self, status, content, mime="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", mime + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(content.encode())

        def authorized(self):
            return parse_qs(urlsplit(self.path).query).get("pin", [""])[0] == service.pin

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                self.respond(200, PAGE, "text/html")
            elif not self.authorized():
                self.respond(403, '{"error":"PIN required"}')
            elif path == "/api/status":
                self.respond(200, json.dumps({"status": service.status,
                    "history": service.history[-50:], "active": service.active}, ensure_ascii=False))
            else:
                self.respond(404, '{"error":"not found"}')

        def do_POST(self):
            if not self.authorized() or urlsplit(self.path).path != "/api/action":
                self.respond(403, '{"error":"not allowed"}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 4096:
                    raise ValueError("request too large")
                payload = json.loads(self.rfile.read(size))
                action = payload.get("action")
                if action == "start":
                    if not service.settings["remote_allow_control"]:
                        raise ValueError("remote control disabled")
                    service.listen()
                elif action == "stop":
                    if not service.settings["remote_allow_control"]:
                        raise ValueError("remote control disabled")
                    service.stop()
                elif action == "text":
                    if not service.settings["remote_allow_text"]:
                        raise ValueError("remote text disabled")
                    if not service.send_text(payload.get("text", "")):
                        raise ValueError("Core not ready; start chat and retry")
                else:
                    raise ValueError("unknown action")
                self.respond(200, '{"ok":true}')
            except (ValueError, TypeError) as error:
                self.respond(400, json.dumps({"error": str(error)}))

    try:
        service.remote = ThreadingHTTPServer(("0.0.0.0", int(service.settings["remote_port"])), Handler)
        threading.Thread(target=service.remote.serve_forever, daemon=True).start()
    except OSError:
        logging.exception("Cannot start remote server")
        service.remote = None
