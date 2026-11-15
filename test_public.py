"""Public export contracts; all input is synthetic and local."""
import importlib
import os
from pathlib import Path
import pytest


def test_config_is_isolated_and_requires_mail_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv('DATEARCHIVE_STATE_DIR', str(tmp_path / 'state'))
    config = importlib.import_module('local_config')
    settings = config.load_settings()
    assert settings['account'] == ''
    assert settings['imap_server'] == 'imap.example.com'
    assert settings['project'] == settings['origin'] == ''
    assert settings['base'] == str(Path.home() / 'Documents/InvoiceArchive')
    assert config.state_dir() == tmp_path / 'state'
    with pytest.raises(ValueError):
        config.require_mail(settings)
    config.save_settings(dict(settings, account='demo@example.com', imap_server='imap.example.org'))
    assert config.load_settings()['account'] == 'demo@example.com'
    from automation import Automation
    auto = Automation(config.state_dir())
    assert auto.status()['account'] == 'demo@example.com'
    auto.configure({'base': str(tmp_path / 'archive'), 'enabled': False, 'account': 'other@example.com', 'imap_server': 'mail.example.org'})
    assert auto.status()['account'] == 'other@example.com'
    assert auto.status()['imap_server'] == 'mail.example.org'
    assert 'password' not in auto.status()
    with pytest.raises(ValueError):
        config.save_settings(dict(settings, password='do-not-store'))


def test_report_uses_configured_example_rates(tmp_path, monkeypatch):
    monkeypatch.setenv('DATEARCHIVE_MEAL_RATE', '12.50')
    monkeypatch.setenv('DATEARCHIVE_TRAFFIC_RATE', '7.25')
    monkeypatch.setenv('DATEARCHIVE_PROJECT', 'EXAMPLE-PROJECT')
    monkeypatch.setenv('DATEARCHIVE_ORIGIN', 'Example City')
    from reimbursement import build_report
    report = build_report(tmp_path, [{'dates': ['2030-01-01', '2030-01-02']}], [])
    assert str(report['meal_subsidy']) == '25.00'
    assert str(report['traffic_subsidy']) == '14.50'
    assert report['project'] == 'EXAMPLE-PROJECT'
    assert report['origin'] == 'Example City'

