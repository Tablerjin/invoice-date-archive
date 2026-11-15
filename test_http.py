"""Exercise the real headless process without any mailbox connection."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


def test_headless_http_and_duplicate_instance(tmp_path):
    root = Path(__file__).resolve().parent
    state, archive = tmp_path / 'state', tmp_path / 'archive'
    env = dict(os.environ, DATEARCHIVE_STATE_DIR=str(state), DATEARCHIVE_BASE=str(archive), BROWSER='false')
    process = subprocess.Popen([sys.executable, str(root / 'app.py'), '--no-browser'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if (state / 'url').exists():
                break
            if process.poll() is not None:
                raise AssertionError(process.communicate())
            time.sleep(.05)
        url = (state / 'url').read_text()
        html = urllib.request.urlopen(url, timeout=5).read().decode()
        token = re.search(r"token='([^']+)'", html).group(1)
        assert 'mailAccount' in html and 'mailServer' in html
        def post(route, data, auth=True):
            headers = {'Content-Type': 'application/json'}
            if auth:
                headers['X-Archive-Token'] = token
            req = urllib.request.Request(url + 'api/' + route, json.dumps(data).encode(), headers)
            return json.loads(urllib.request.urlopen(req, timeout=5).read())
        try:
            post('mail/status', {}, False)
            assert False, 'Unauthenticated request was accepted'
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
        status = post('mail/status', {})
        assert status['enabled'] is False and status['account'] == ''
        assert status['base'] == str(archive)
        result = post('archive', dict(base=str(archive),date='2030-01-01',event='Example',files=[dict(name='invoice.pdf',data=base64.b64encode(b'%PDF-1.4 synthetic').decode())]))
        assert (Path(result['folder']) / 'invoice.pdf').read_bytes() == b'%PDF-1.4 synthetic'
        try:
            post('archive', dict(base=str(tmp_path),date='2030-01-01',event='Escape',files=[]))
            assert False
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
        duplicate = subprocess.run([sys.executable, str(root / 'app.py'), '--no-browser'],env=env,capture_output=True,timeout=5)
        assert duplicate.returncode == 0, duplicate.stderr
        assert process.poll() is None
    finally:
        process.terminate()
        process.communicate(timeout=5)
