"""Non-secret local settings. Secrets belong exclusively to the OS keyring."""
import json
import os
from pathlib import Path
import sys
from decimal import Decimal

KEYRING_SERVICE = 'DateArchivePublic-IMAP'


def state_dir():
    override = os.environ.get('DATEARCHIVE_STATE_DIR')
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            raise ValueError('State directory must be absolute')
        return path
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/DateArchivePublic'
    return Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'DateArchivePublic'


def load_settings():
    defaults = dict(account='', imap_server='imap.example.com', imap_port=993,
                    base=str(Path.home() / 'Documents/InvoiceArchive'), project='', origin='',
                    meal_rate='100', traffic_rate='80', notion_enabled=False, maps_script='')
    path = state_dir() / 'config.json'
    if path.exists():
        stored = json.loads(path.read_text(encoding='utf-8'))
        if set(stored) - set(defaults):
            raise ValueError('Unknown or secret configuration field')
        defaults.update(stored)
    for key in defaults:
        value = os.environ.get('DATEARCHIVE_' + key.upper())
        if value is not None:
            defaults[key] = value.lower() in ('1', 'true', 'yes') if isinstance(defaults[key], bool) else value
    return defaults


def save_settings(settings):
    allowed = {'account','imap_server','imap_port','base','project','origin','meal_rate','traffic_rate','notion_enabled','maps_script'}
    if set(settings) - allowed:
        raise ValueError('Unknown or secret configuration field')
    if not Path(settings['base']).expanduser().is_absolute():
        raise ValueError('Archive directory must be absolute')
    for key in ('meal_rate','traffic_rate'):
        number = Decimal(str(settings[key]))
        if not number.is_finite() or number < 0:
            raise ValueError('Rates must be finite and nonnegative')
    if not 1 <= int(settings['imap_port']) <= 65535:
        raise ValueError('Invalid IMAP port')
    root = state_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    path = root / 'config.json'
    temporary = root / 'config.tmp'
    temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)


def require_mail(settings):
    if not settings['account'].strip() or settings['imap_server'].strip() in ('', 'imap.example.com'):
        raise ValueError('Configure your account and IMAP server first')
