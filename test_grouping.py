import unittest
from grouping import groups, rail_details
from test_lodging import text_pdf
class GroupTests(unittest.TestCase):
 def test_three_day_gap(self):
  a=[{'id':'a','dates':['2030-10-23']},{'id':'b','dates':['2030-10-26']},{'id':'c','dates':['2030-10-30']}]
  self.assertEqual([len(x) for x in groups(a,3)],[2,1])
 def test_five_day_rail_window(self):
  a=[{'id':'a','dates':['2030-08-26']},{'id':'b','dates':['2030-08-31']},{'id':'c','dates':['2030-09-06']}]
  self.assertEqual([len(x) for x in groups(a,5)],[2,1])
 def test_rail_date_not_issue_date(self):
  a=rail_details(text_pdf('开票日期:2030年09月14日\n无锡站\n上海站\nG8273\n2030年08月26日\n12:39开'))
  self.assertEqual(a['dates'],['2030-08-26']);self.assertEqual(a['stations'],['无锡站','上海站'])
if __name__=='__main__':unittest.main()
