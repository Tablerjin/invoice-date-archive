"""Reimbursement policy and standalone HTML regression tests."""
from decimal import Decimal
from pathlib import Path
import json
import os
import tempfile

import pymupdf
import pytest

from reimbursement import build_report, render_report, generate_reports


@pytest.fixture
def trip_folder():
    scratch = Path(tempfile.gettempdir()).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        yield Path(folder)


def pdf(folder, name, text):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 40), text, fontname='china-s', fontsize=11)
        doc.save(folder / name)


def item(**overrides):
    return dict({'dates': ['2030-10-23'], 'event': '去复旦大学交流', 'kind': 'rail', 'files': [],
                 'school_guess': {'station': '上海站', 'basis': '自动推测，非实际访问证明'}}, **overrides)


def test_mixed_rail_and_positive_car_cost_waives_daily_traffic_subsidy(trip_folder):
    pdf(trip_folder, 'rail.pdf', '铁路电子客票 ￥62.00')
    pdf(trip_folder, 'toll.pdf', '通行费 价税合计（小写）¥47.98')
    report = build_report(trip_folder, [item(files=['rail.pdf', 'toll.pdf'])], [])
    assert report['origin'] == ''
    assert report['traffic_subsidy'] == Decimal('0.00')
    assert report['car_expenses'] == Decimal('47.98')
    assert report['total'] == Decimal('209.98')


def test_zero_car_total_still_gets_subsidy_regardless_kind(trip_folder):
    pdf(trip_folder, 'toll.pdf', '通行费 价税合计（小写）¥0.00')
    report = build_report(trip_folder, [item(kind='toll', files=['toll.pdf'])], [])
    assert report['traffic_subsidy'] == Decimal('80.00')
    assert report['total'] == Decimal('180.00')


def test_invoice_count_and_toll_inclusive_total_are_actual_files(trip_folder):
    pdf(trip_folder, 'toll.pdf', '通行费\n¥44.02\n¥47.98\n¥3.96\n¥47.98')
    pdf(trip_folder, '行程汇总.pdf', '通行费 ¥999.00')
    (trip_folder / '报销信息.html').write_text('old')
    report = build_report(trip_folder, [item(kind='toll')], [])
    assert report['invoice_count'] == 1
    assert report['car_expenses'] == Decimal('47.98')
    assert report['invoices'][0]['status'] == 'ambiguous_max'
    assert report['warnings']


def test_unreadable_pdf_does_not_fall_back_to_whole_batch_text(trip_folder):
    (trip_folder / 'broken.pdf').write_bytes(b'broken')
    report = build_report(trip_folder, [item(files=['broken.pdf'], text='通行费 ¥47.98')], [])
    assert report['invoices'][0]['amount'] is None
    assert report['invoices'][0]['status'] == 'unresolved'
    assert report['total'] is None
    assert report['invoice_subtotal'] is None
    assert report['known_invoice_subtotal'] == Decimal('0.00')
    assert report['complete'] is False


def test_group_bounds_include_start_end_and_reason_is_earliest(trip_folder):
    report = build_report(trip_folder, [
        item(dates=['2030-10-24'], event='去江南大学交流'),
        item(dates=['2030-10-23'], start='2030-10-22', end='2030-10-25', event='去复旦大学交流')], [])
    assert (report['start'], report['end'], report['days']) == ('2030-10-22', '2030-10-25', 4)
    assert report['meal_subsidy'] == Decimal('400.00')
    assert report['reason'] == '去复旦大学交流'
    assert report['destination'] == '上海'
    assert '非实际' in ' '.join(report['warnings'])


def test_checkout_is_exclusive_and_remaining_nights_hosted(trip_folder):
    pdf(trip_folder, '住宿发票.pdf', '住宿费 价税合计（小写）¥242.78')
    report = build_report(trip_folder, [item(dates=['2030-10-23', '2030-10-25'])], [
        {'name': '住宿发票.pdf', 'basis': 'stay', 'dates': ['2030-10-23', '2030-10-24']}])
    assert report['lodging_expenses'] == Decimal('242.78')
    assert '2030-10-23' in report['notes']
    assert '2030-10-24' in report['notes']
    assert '其余1晚' in report['notes']
    assert report['invoice_subtotal'] == Decimal('242.78')
    assert report['subsidy_subtotal'] == Decimal('540.00')
    assert report['total'] == Decimal('782.78')


def test_missing_stay_dates_never_invents_hosted_nights(trip_folder):
    pdf(trip_folder, '住宿发票.pdf', '住宿费 ¥242.78')
    report = build_report(trip_folder, [item(dates=['2030-10-23', '2030-10-25'])], [
        {'name': '住宿发票.pdf', 'basis': 'invoice_date', 'dates': ['2030-10-25']}])
    assert '晚对方安排' not in report['notes']
    assert '日期待核' in report['notes']
    assert any('住宿' in w for w in report['warnings'])


def test_single_day_without_hotel_uses_requested_hosting_remark(trip_folder):
    report = build_report(trip_folder, [item()], [])
    assert report['notes'] == '对方安排住宿'


def test_unknown_city_blank_warn_and_first_event_mapping(trip_folder):
    report = build_report(trip_folder, [item(school_guess={}, event='参加研讨')], [])
    assert report['destination'] == ''
    assert any('城市' in w for w in report['warnings'])
    mapped = build_report(trip_folder, [item(school_guess={'station': '顾山站'}, event='去江南大学交流')], [])
    assert mapped['destination'] == '无锡'


def test_render_has_copy_fallback_editable_export_print_and_escaped_data(trip_folder):
    report = build_report(trip_folder, [item(event='去复旦大学交流 </script><script>alert(1)</script>')], [])
    report['notes'] = '<b>note</b>'
    html = render_report(report)
    assert 'data-copy' in html
    assert 'navigator.clipboard' in html and 'execCommand' in html
    assert 'v-project' in html
    assert 'Download saved HTML' in html
    assert '@media print' in html
    assert 'setAttribute(\'value\'' in html
    assert 'setAttribute(\'data-saved' in html
    assert '</script><script>alert' not in html
    for key in ['project', 'reason', 'notes']:
        assert f'id="v-{key}"' in html


def test_generate_one_report_per_unique_archived_folder(trip_folder):
    items = [item(state='archived', folder=str(trip_folder)), item(state='archived', folder=str(trip_folder)), item(state='pending')]
    paths = generate_reports({'items': items, 'lodging': {}})
    assert paths == [str(trip_folder / '报销信息.html')]
    assert Path(paths[0]).read_text().startswith('<!doctype html>')


def test_invoice_audit_handles_duplicate_source_names_and_uppercase_pdf(trip_folder):
    pdf(trip_folder, 'rail.PDF', '铁路电子客票 ￥62.00')
    pdf(trip_folder, 'return.pdf', '铁路电子客票 ￥59.00')
    report = build_report(trip_folder, [item(files=['rail.PDF']), item(files=['rail.PDF'])], [])
    assert report['invoice_count'] == 2
    assert report['rail_expenses'] == Decimal('121.00')
    assert report['total'] == Decimal('301.00')


def test_lodging_filename_is_sufficient_classification(trip_folder):
    pdf(trip_folder, '住宿发票.pdf', '价税合计（小写）¥242.78')
    report = build_report(trip_folder, [item()], [])
    assert report['lodging_expenses'] == Decimal('242.78')
    assert any('住宿' in w for w in report['warnings'])

