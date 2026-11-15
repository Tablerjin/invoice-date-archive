import unittest
from toll import analyze_pdfs
from test_toll import text_pdf

class Routes(unittest.TestCase):
    def test_joined_dates_and_wrapped_route(self):
        text='通行日期\n起止 出入口信息\n1 2030102920301029\n苏·江苏太\n湖湾收费站\n至\n苏·江苏扬\n州开发区站\n83.58'
        a=analyze_pdfs([('行程.pdf',text_pdf(text))])
        self.assertEqual(a['dates'],['2030-10-29'])
        self.assertIn('扬州开发区站',a['stations'])

if __name__=='__main__':unittest.main()
