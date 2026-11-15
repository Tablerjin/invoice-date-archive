"""Preview a per-user macOS LaunchAgent; only --install writes/loads it."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from local_config import state_dir

LABEL = 'local.invoice-date-archive'


def build_plist(project, python, state):
    project, python, state = (Path(x).expanduser().absolute() for x in (project, python, state))
    if not (project / 'app.py').is_file() or not python.is_file():
        raise ValueError('Project app.py and Python interpreter must exist')
    return plistlib.dumps(dict(Label=LABEL, ProgramArguments=[str(python), str(project / 'app.py'), '--no-browser'],
        WorkingDirectory=str(project), RunAtLoad=True, KeepAlive=True,
        EnvironmentVariables={'DATEARCHIVE_STATE_DIR': str(state)},
        StandardOutPath=str(state / 'service.stdout.log'), StandardErrorPath=str(state / 'service.stderr.log')))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Explicitly write and load the LaunchAgent')
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--state', type=Path, default=state_dir())
    args = parser.parse_args(argv)
    payload = build_plist(args.project, args.python, args.state)
    if not args.install:
        print(payload.decode())
        return 0
    if sys.platform != 'darwin':
        parser.error('--install requires macOS')
    target = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    if target.exists():
        parser.error('Service already exists; unload/remove it explicitly before reinstalling')
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    target.chmod(0o600)
    if plistlib.loads(target.read_bytes()) != plistlib.loads(payload):
        raise RuntimeError('Plist readback failed')
    domain = 'gui/' + str(os.getuid())
    subprocess.run(['launchctl', 'bootstrap', domain, str(target)], check=True)
    subprocess.run(['launchctl', 'print', domain + '/' + LABEL], check=True)
    print('Installed:', target)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
