"""Generate a generic expense workbook or validate a user-supplied template."""
from pathlib import Path
from decimal import Decimal
from openpyxl import load_workbook, Workbook

TEMPLATE = None  # No institutional binary is distributed.

def fill_workbook(template, output, report):
    if report['total'] is None:
        raise ValueError('发票金额未全部识别，不能生成上传明细表')
    wb=load_workbook(template) if template else Workbook()
    sheet=wb.active
    expected=['序号','开始时间','结束时间','出发地','到达地','火车','汽车','飞机','市内交通','住宿费','伙食补助费','其他费用','报销金额','报销审定金额','备注']
    if template is None:
        sheet.title = 'Expense Draft'
        sheet.append(expected)
    if [sheet.cell(1,i).value for i in range(1,16)]!=expected:
        raise ValueError('明细表模板表头不匹配')
    values=[1,report['start'],report['end'],report['origin'],report['destination'],report['rail_expenses'],report['car_expenses'],0,0,report['lodging_expenses'],report['meal_subsidy'],Decimal(str(report['traffic_subsidy']))+Decimal(str(report['other_expenses'])),report['total'],None,report['notes']]
    if sum(Decimal(str(v)) for v in values[5:12]) != Decimal(str(report['total'])):
        raise ValueError('Expense columns do not sum to total')
    for i,value in enumerate(values,1):
        if isinstance(value,Decimal):value=float(value)
        sheet.cell(2,i).value=value
        if 6<=i<=13:sheet.cell(2,i).number_format='0.00'
    if sheet.max_row>2:sheet.delete_rows(3,sheet.max_row-2)
    from safe_output import replace_output
    replace_output(output, wb.save)
    return str(output)

def generate_workbooks(state):
    from reimbursement import build_report
    grouped={}
    for x in state.get('items',[]):
        if x.get('state')=='archived' and x.get('folder'):
            grouped.setdefault(x['folder'],[]).append(x)
    outputs=[]
    for folder,items in grouped.items():
        lodging=[r for r in state.get('lodging',{}).values() if r.get('state')=='archived' and r.get('folder')==folder]
        report=build_report(folder,items,lodging)
        output=Path(folder)/'科研经费差旅报销审批-明细表.xlsx'
        outputs.append(fill_workbook(TEMPLATE,output,report))
    return outputs
