"""Optional local filesystem-only invoice handoff; never imports the running app.

scan(state, work) returns events for a separate connected-tools agent. Upsert by
trip_key (SHA-256 of the resolved archive folder), NOT event id. Folder merge or
rename deliberately creates a new key; old pages are not deleted by this probe.
The agent must read back its Notion write before atomically storing
work/receipts/<trip_key>.json containing fingerprint, page_id and database_id.
Snapshots live at work/tasks/<fingerprint>/record.json. No receipt is written here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from datetime import date

from local_config import state_dir
DEFAULT_STATE = state_dir() / 'toll/state.json'
DEFAULT_WORK = state_dir() / 'notion'
REPORT = '报销信息.html'
WORKBOOK = '科研经费差旅报销审批-明细表.xlsx'


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _atomic_record(path, record):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.record-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(_json(record) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _dates(items):
    dates = set()
    for item in items:
        values = [item.get(key) for key in ('start', 'end', 'date')]
        values += item.get('dates', []) if isinstance(item.get('dates'), list) else []
        for value in values:
            try:
                dates.add(date.fromisoformat(value).isoformat())
            except (ValueError, TypeError):
                pass
    return (min(dates), max(dates)) if dates else (None, None)


def _workbook_hash(path):
    # Hash cell values/formulas, never ZIP timestamps or generated core metadata.
    # Values may be private: only the digest leaves this function.
    from openpyxl import load_workbook
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        content = [(sheet.title, [[str(cell) if isinstance(cell, (date,)) else cell
                                  for cell in row]
                                 for row in sheet.iter_rows(values_only=True)])
                   for sheet in book.worksheets]
        return _hash(_json(content).encode())
    finally:
        book.close()


def scan(state=DEFAULT_STATE, work=DEFAULT_WORK):
    """Read only archive metadata; create private pending snapshots, no API calls."""
    state, work = Path(state).expanduser(), Path(work).expanduser().resolve()
    if not state.is_file():
        return []
    data = json.loads(state.read_text(encoding='utf-8'))
    folders = {}
    for item in data.get('items', []):
        if isinstance(item, dict) and item.get('state') == 'archived' and item.get('folder'):
            folder = Path(item['folder']).expanduser().resolve()
            folders.setdefault(folder, []).append(item)
    events = []
    for folder, items in sorted(folders.items()):
        if not folder.is_dir() or not all((folder / name).is_file() for name in (REPORT, WORKBOOK)):
            continue
        files = sorted(path for path in folder.iterdir() if path.is_file() and not path.name.startswith('.'))
        pdfs = [path for path in files if path.suffix.lower() == '.pdf' and not any(word in path.stem.lower() for word in ('汇总', '清单', '行程', 'summary', 'itinerary'))]
        start, end = _dates(items)
        match = re.search(r'去(.+?(?:大学|学院))交流', folder.name)
        record = {
            'trip_key': _hash(str(folder).encode()), 'name': folder.name,
            'start': start, 'end': end,
            'school': {'name': match.group(1) if match else None, 'inferred': True,
                       'basis': '从归档文件夹名称推测，非实际访问证明'},
            'files': [path.name for path in files], 'invoice_count': len(pdfs),
        }
        fingerprint = _hash(_json({'record': record, 'pdfs': [_hash(path.read_bytes()) for path in files if path.suffix.lower() == '.pdf'],
                                   'report': _hash((folder / REPORT).read_bytes()),
                                   'workbook': _workbook_hash(folder / WORKBOOK)}).encode())
        record.update(fingerprint=fingerprint, last_sync=data.get('last_sync') or None,
                      last_sync_label='归档同步完成时间（非出行日期）')
        receipt_path = work / 'receipts' / (record['trip_key'] + '.json')
        try:
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            receipt = None
        if (isinstance(receipt, dict) and receipt.get('fingerprint') == fingerprint
                and all(isinstance(receipt.get(key), str) and receipt[key].strip()
                        for key in ('page_id', 'database_id'))):
            continue
        path = work / 'tasks' / fingerprint / 'record.json'
        _atomic_record(path, record)
        events.append({'type': 'invoices.notion.ready', 'subject': record['trip_key'],
                       'id': fingerprint, 'detail': _json({'record_path': str(path)})})
    return events


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--work', type=Path, default=DEFAULT_WORK)
    args = parser.parse_args(argv)
    events = scan(args.state, args.work)
    if events:
        print('```agent-autoloop')
        print(_json({'events': events}))
        print('```')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
