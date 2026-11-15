from openpyxl import load_workbook
import pytest
from expense_excel import fill_workbook


def test_blank_generated_template_and_totals(tmp_path):
    report=dict(start='2030-01-01',end='2030-01-02',origin='Example City',destination='Example Destination',rail_expenses=10,car_expenses=20,lodging_expenses=30,meal_subsidy=40,traffic_subsidy=0,other_expenses=5,total=105,notes='Example')
    out=tmp_path/'expense.xlsx'
    fill_workbook(None,out,report)
    wb=load_workbook(out,data_only=True)
    s=wb.active
    assert s['D2'].value=='Example City'
    assert sum(s.cell(2,i).value for i in range(6,13))==s['M2'].value==105
    assert s['N2'].value is None
    assert s.max_row==2
    wb.close()
    report['total'] = 999
    with pytest.raises(ValueError, match='total'):
        fill_workbook(None, tmp_path/'invalid.xlsx', report)


def test_invalid_template_and_total_rejected(tmp_path):
    from openpyxl import Workbook
    bad=tmp_path/'bad.xlsx'
    Workbook().save(bad)
    with pytest.raises(ValueError, match='模板'):
        fill_workbook(bad,tmp_path/'out.xlsx',{'total': 1})
