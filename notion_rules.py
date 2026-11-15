"""Emit a disabled, host-neutral Autoloop draft; never installs agent rules."""
import argparse
import json
from pathlib import Path
import shlex
import sys
from local_config import state_dir


def draft(project, python, state, work):
    command = [str(Path(python).absolute()), str(Path(project).absolute() / 'notion_probe.py'), '--state', str(Path(state).absolute()), '--work', str(Path(work).absolute())]
    return {'enabled': False, 'event_type': 'invoices.notion.ready',
            'probe_command': shlex.join(command), 'interval_seconds': 900,
            'instructions_file': str(Path(project).absolute() / 'NOTION.md'),
            'note': 'Draft only. Host agent must translate to its installed scheduler schema after user Notion connection and schema discovery.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=state_dir() / 'toll/state.json')
    parser.add_argument('--work', type=Path, default=state_dir() / 'notion')
    args = parser.parse_args(argv)
    print(json.dumps(draft(Path(__file__).parent, sys.executable, args.state, args.work), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
