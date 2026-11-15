#!/usr/bin/python3
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from archive import archive_files
from automation import Automation
AUTO = None

ROOT = Path(__file__).resolve().parent
from local_config import load_settings, state_dir
DEFAULT = load_settings()['base']
TOKEN = secrets.token_urlsafe(32)
STATE = state_dir()

def within_archive(path, base):
    path, base = Path(path).expanduser().resolve(), Path(base).expanduser().resolve()
    if path != base and base not in path.parents:
        raise ValueError('Path is outside the configured archive')
    return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host') not in ('127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)):
            self.reply(403, {'error': 'Invalid host'})
            return
        if self.path != '/':
            self.reply(404, {'error': 'Not found'})
            return
        body = (ROOT / 'index.html').read_text().replace('__TOKEN__', TOKEN).replace('__DEFAULT__', __import__('html').escape(str(DEFAULT), quote=True)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if host not in ('127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)) or (origin and origin != 'http://' + host):
            self.reply(403, {'error': 'Invalid request origin'})
            return
        if not secrets.compare_digest(self.headers.get('X-Archive-Token', ''), TOKEN):
            self.reply(403, {'error': '请刷新页面后重试'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > 280 * 1024 * 1024:
                raise ValueError('每批文件请控制在 200 MB 以内')
            data = json.loads(self.rfile.read(length))
            if self.path == '/api/mail/status':
                self.reply(200, AUTO.status())
            elif self.path == '/api/mail/config':
                self.reply(200, AUTO.configure(data))
            elif self.path == '/api/mail/sync':
                threading.Thread(target=AUTO.sync, daemon=True).start()
                self.reply(200, {'ok': True})
            elif self.path == '/api/mail/confirm':
                self.reply(200, AUTO.confirm(data))
            elif self.path == '/api/archive':
                files = [(f['name'], base64.b64decode(f['data'], validate=True)) for f in data['files']]
                base = Path(data['base']).expanduser().resolve()
                if base != Path(AUTO.data['base']).expanduser().resolve():
                    raise ValueError('Save the archive location in settings first')
                within_archive(base / (data['date'].replace('-', '') + data['event']), base)
                result = archive_files(str(base), data['date'], data['event'], files)
                self.reply(200, result)
            elif self.path == '/api/report':
                from reimbursement import generate_reports
                target = within_archive(data['folder'], AUTO.data['base']) / '报销信息.html'
                allowed = {str(Path(x['folder'])) for x in AUTO.data['items'] if x.get('folder')}
                if str(target.parent) not in allowed or not target.is_file():
                    raise ValueError('未找到此行程的报销信息')
                subprocess.run((['open'] if os.sys.platform == 'darwin' else ['xdg-open']) + [str(target)], check=True)
                self.reply(200, {'path': str(target)})
            elif self.path == '/api/open':
                target = within_archive(data['folder'], AUTO.data['base'])
                if not target.is_absolute() or not target.is_dir():
                    raise ValueError('目录不存在或尚未同步到本机')
                subprocess.run((['open'] if os.sys.platform == 'darwin' else ['xdg-open']) + [str(target)], check=True)
                self.reply(200, {'ok': True})
            elif self.path == '/api/choose':
                if os.sys.platform != 'darwin':
                    raise ValueError('Enter the archive path in settings on this platform')
                script = 'POSIX path of (choose folder with prompt "选择归档位置")'
                proc = subprocess.run(['/usr/bin/osascript', '-e', script], capture_output=True, text=True)
                self.reply(200, {'path': proc.stdout.strip() if proc.returncode == 0 else ''})
            else:
                self.reply(404, {'error': 'Not found'})
        except Exception as e:
            message = str(e)
            if isinstance(e, OSError) and e.errno == 11:
                message = '归档目录暂时不可用，请确认目录已下载到本机且具有访问权限。'
            self.reply(400, {'error': message})


def main():
    import fcntl
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    lock = (STATE / 'app.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if '--no-browser' not in os.sys.argv:
            webbrowser.open((STATE / 'url').read_text())
        return
    global AUTO
    AUTO = Automation(STATE)
    AUTO.start()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    (STATE / 'url').write_text('http://127.0.0.1:{}/'.format(server.server_port))
    if '--no-browser' not in os.sys.argv:
        webbrowser.open((STATE / 'url').read_text())
    server.serve_forever()

if __name__ == '__main__':
    main()
