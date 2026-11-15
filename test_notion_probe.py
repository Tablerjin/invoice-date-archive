"""Private local Notion handoff: real filesystem fixtures, no network."""
import importlib
import json
from pathlib import Path
import tempfile

import pymupdf
import pytest
from openpyxl import Workbook


@pytest.fixture
def archive():
    scratch = Path(tempfile.gettempdir()).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        root = Path(temporary)
        folder = root / '20301107至20301108共2天去江南大学交流'
        folder.mkdir()
        for name in ['发票.pdf', '住宿发票.pdf', '行程汇总.pdf']:
            with pymupdf.open() as document:
                document.new_page()
                document.save(folder / name)
        (folder / '报销信息.html').write_text('<span id="v-start">2030-11-07</span>', encoding='utf-8')
        book = Workbook()
        book.active.append(['原有报销合计', 123])
        book.save(folder / '科研经费差旅报销审批-明细表.xlsx')
        state = root / 'state.json'
        data = {
            'last_sync': '2030-11-15 23:30:33',
            'password': 'SECRET-PASSWORD',
            'items': [
                {'state': 'archived', 'folder': str(folder), 'start': '2030-11-07',
                 'end': '2030-11-08', 'event': '去江南大学交流', 'text': 'payment SECRET-ACCOUNT address private@example.com'},
                {'state': 'archived', 'folder': str(folder / '..' / folder.name),
                 'start': '2030-11-07', 'end': '2030-11-08', 'event': '去别的大学交流'},
            ],
        }
        state.write_text(json.dumps(data), encoding='utf-8')
        yield root, folder, state, data


def probe():
    assert importlib.util.find_spec('notion_probe') is not None, 'local probe module is missing'
    return importlib.import_module('notion_probe')


@pytest.mark.parametrize('receipt', [None, {}, [], 'broken-json', {'fingerprint': 'old', 'page_id': 'p', 'database_id': 'd'}, {'fingerprint': 'MATCH', 'page_id': '', 'database_id': 'd'}, {'fingerprint': 'MATCH', 'page_id': 'p', 'database_id': 'd'}])
def test_only_verified_matching_receipt_suppresses_pending(archive, receipt):
    root, folder, state, data = archive
    work = root / 'notion'
    event = probe().scan(state, work)[0]
    receipts = work / 'receipts'
    receipts.mkdir()
    if isinstance(receipt, dict) and receipt.get('fingerprint') == 'MATCH':
        receipt['fingerprint'] = event['id']
    if receipt is not None:
        (receipts / (event['subject'] + '.json')).write_text('not json' if receipt == 'broken-json' else json.dumps(receipt))
    events = probe().scan(state, work)
    valid = isinstance(receipt, dict) and receipt.get('fingerprint') == event['id'] and bool(receipt.get('page_id'))
    assert bool(events) is not valid
    if valid:
        (folder / '报销信息.html').write_text('changed report')
        changed = probe().scan(state, work)[0]
        assert changed['subject'] == event['subject']
        assert changed['id'] != event['id']
        assert Path(json.loads(event['detail'])['record_path']).exists()


def test_workbook_semantics_not_zip_metadata_and_sync_time_drive_fingerprint(archive):
    from openpyxl import load_workbook
    root, folder, state, data = archive
    work = root / 'notion'
    first = probe().scan(state, work)[0]
    workbook = folder / '科研经费差旅报销审批-明细表.xlsx'
    book = load_workbook(workbook)
    book.properties.description = 'regenerated at a different time'
    book.save(workbook)
    data['last_sync'] = '2030-11-16 00:01:02'
    state.write_text(json.dumps(data))
    assert probe().scan(state, work)[0]['id'] == first['id']
    book.active['B1'] = 456
    book.save(workbook)
    changed = probe().scan(state, work)[0]
    assert changed['id'] != first['id']
    assert changed['subject'] == first['subject']


@pytest.mark.parametrize('missing', [None, '报销信息.html', '科研经费差旅报销审批-明细表.xlsx', 'folder'])
def test_empty_missing_or_incomplete_archives_emit_nothing(archive, missing):
    import shutil
    root, folder, state, data = archive
    if missing is None:
        data['items'] = []
        state.write_text(json.dumps(data))
    elif missing == 'folder':
        shutil.rmtree(folder)
    else:
        (folder / missing).unlink()
    assert probe().scan(state, root / 'notion') == []
    assert not (root / 'notion').exists()
    assert probe().scan(root / 'no-state.json', root / 'notion') == []


def test_cli_emits_only_fenced_events_and_empty_scan_is_silent(archive):
    import subprocess
    import sys
    root, folder, state, data = archive
    command = [sys.executable, str(Path(__file__).with_name('notion_probe.py')),
               '--state', str(state), '--work', str(root / 'notion')]
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    assert result.stderr == ''
    assert result.stdout.startswith('```agent-autoloop\n')
    assert result.stdout.endswith('\n```\n')
    envelope = json.loads(result.stdout.split('\n', 1)[1].rsplit('\n```', 1)[0])
    event, = envelope['events']
    assert set(event) == {'type', 'subject', 'id', 'detail'}
    assert set(json.loads(event['detail'])) == {'record_path'}
    data['items'] = []
    state.write_text(json.dumps(data))
    assert subprocess.run(command, capture_output=True, check=True).stdout == b''


def test_all_pdf_content_changes_requeue_but_do_not_change_trip_key(archive):
    root, folder, state, data = archive
    work = root / 'notion'
    event = probe().scan(state, work)[0]
    with (folder / '行程汇总.pdf').open('ab') as stream:
        stream.write(b'\n% modified summary')
    changed = probe().scan(state, work)[0]
    assert changed['id'] != event['id']
    assert changed['subject'] == event['subject']
    assert json.loads(Path(json.loads(changed['detail'])['record_path']).read_text())['invoice_count'] == 2
    with (folder / '发票.pdf').open('ab') as stream:
        stream.write(b'\n% modified original')
    assert probe().scan(state, work)[0]['id'] != changed['id']


def test_scan_groups_actual_folders_writes_only_private_projection(archive):
    root, folder, state, data = archive
    before = state.read_bytes()
    events = probe().scan(state, root / 'notion')
    assert len(events) == 1
    event = events[0]
    assert event['type'] == 'invoices.notion.ready'
    assert len(event['subject']) == len(event['id']) == 64
    assert set(json.loads(event['detail'])) == {'record_path'}
    record_path = Path(json.loads(event['detail'])['record_path'])
    assert record_path == root / 'notion' / 'tasks' / event['id'] / 'record.json'
    record = json.loads(record_path.read_text())
    assert record['trip_key'] == event['subject']
    assert record['fingerprint'] == event['id']
    assert record['name'] == folder.name
    assert record['start'] == '2030-11-07'
    assert record['end'] == '2030-11-08'
    assert record['school'] == {'name': '江南大学', 'inferred': True, 'basis': '从归档文件夹名称推测，非实际访问证明'}
    assert record['invoice_count'] == 2
    assert sorted(record['files']) == sorted(path.name for path in folder.iterdir())
    assert record['last_sync'] == data['last_sync']
    assert record['last_sync_label'] == '归档同步完成时间（非出行日期）'
    assert set(record) == {'trip_key', 'fingerprint', 'name', 'start', 'end', 'school', 'files', 'invoice_count', 'last_sync', 'last_sync_label'}
    assert 'SECRET' not in record_path.read_text()
    assert 'private@example.com' not in record_path.read_text()
    assert state.read_bytes() == before
