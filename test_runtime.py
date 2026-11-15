import importlib
import json
import plistlib
from pathlib import Path
import pytest


def test_service_plist_uses_actual_absolute_paths(tmp_path):
    service = importlib.import_module('install_service')
    project = tmp_path / 'project with spaces'
    project.mkdir()
    (project / 'app.py').write_text('# fixture')
    python = Path(__import__('sys').executable)
    payload = service.build_plist(project, python, tmp_path / 'state')
    value = plistlib.loads(payload)
    assert value['ProgramArguments'] == [str(python.absolute()), str(project / 'app.py'), '--no-browser']
    assert value['WorkingDirectory'] == str(project)
    assert value['EnvironmentVariables']['DATEARCHIVE_STATE_DIR'] == str(tmp_path / 'state')
    assert value['Label'] == 'local.invoice-date-archive'


def test_external_paths_and_symlink_escape_rejected(tmp_path):
    app = importlib.import_module('app')
    root = tmp_path / 'archive'
    root.mkdir()
    inside = root / 'trip'
    inside.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    assert app.within_archive(inside, root) == inside
    for path in (outside, root / 'escape'):
        with pytest.raises(ValueError):
            app.within_archive(path, root)


def test_unconfigured_map_fallback_is_actionable(monkeypatch):
    monkeypatch.setenv('DATEARCHIVE_MAPS_SCRIPT', '')
    import schools
    with pytest.raises(ValueError, match='maps_script'):
        schools.run_maps([])


def test_archive_rejects_existing_folder_symlink(tmp_path):
    from archive import archive_files
    base = tmp_path / 'archive'
    base.mkdir()
    outside = tmp_path / 'outside'
    outside.mkdir()
    (base / '20300101Example').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        archive_files(base, '2030-01-01', 'Example', [('invoice.pdf', b'%PDF-1.4 example')])
    assert not list(outside.iterdir())


def test_merge_rejects_symlink_destination_before_deleting_sources(tmp_path):
    from automation import Automation
    root = tmp_path / 'archive'
    root.mkdir()
    source = root / '20300101Example'
    source.mkdir()
    original = source / 'invoice.pdf'
    original.write_bytes(b'%PDF-source')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (root / '20300101Example2').symlink_to(outside, target_is_directory=True)
    automation = Automation(tmp_path / 'state')
    automation.data.update(base=str(root), items=[
        {'id': 'one', 'kind': 'toll', 'dates': ['2030-01-01'], 'state': 'archived', 'event': 'Example', 'folder': str(source)},
        {'id': 'two', 'kind': 'toll', 'dates': ['2030-01-02'], 'state': 'archived', 'event': 'Example', 'folder': str(root / '20300101Example2')},
    ])
    with pytest.raises(ValueError, match='outside configured root'):
        automation.merge_groups()
    assert original.read_bytes() == b'%PDF-source'
    assert list(outside.iterdir()) == []


def test_notion_rule_draft_is_disabled_and_quotes_paths(tmp_path):
    from notion_rules import draft
    import shlex
    rule = draft(tmp_path / 'space project', Path(__import__('sys').executable), tmp_path / 'state.json', tmp_path / 'work')
    assert rule['enabled'] is False
    command = shlex.split(rule['probe_command'])
    assert command[1] == str(tmp_path / 'space project/notion_probe.py')
    assert command[-4:] == ['--state', str(tmp_path / 'state.json'), '--work', str(tmp_path / 'work')]

