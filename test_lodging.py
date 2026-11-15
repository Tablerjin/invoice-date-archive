"""Lodging analysis tests using real, in-memory PDFs."""
import io
import unittest

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def text_pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    chars = list(dict.fromkeys(text.replace('\n', '')))
    codes = {c: i + 1 for i, c in enumerate(chars)}
    cmap = DecodedStreamObject()
    mappings = '\n'.join('<{:04x}> <{}>'.format(codes[c], c.encode('utf-16-be').hex()) for c in chars)
    cmap.set_data(('begincmap\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n' + str(len(chars)) + ' beginbfchar\n' + mappings + '\nendbfchar\nendcmap').encode())
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type0'), NameObject('/BaseFont'): NameObject('/Test'), NameObject('/Encoding'): NameObject('/Identity-H'), NameObject('/ToUnicode'): writer._add_object(cmap)})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
    stream = DecodedStreamObject()
    commands = ['BT /F1 12 Tf 10 780 Td']
    for line in text.split('\n'):
        commands.append('<' + ''.join('{:04x}'.format(codes[c]) for c in line) + '> Tj 0 -16 Td')
    stream.set_data(('\n'.join(commands) + '\nET').encode())
    page[NameObject('/Contents')] = writer._add_object(stream)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


class LodgingTests(unittest.TestCase):
    def test_only_explicit_lodging_pdf_content(self):
        from lodging import analyze_lodging
        files = [(str(i) + '.PDF', text_pdf(t)) for i, t in enumerate([
            '住宿服务', '房费', '客房服务', '酒店服务',
            '销售方：某某酒店\n餐饮服务\n开票日期：2030-01-03'])]
        files += [('住宿.pdf', text_pdf('餐饮服务')), ('住宿.txt', text_pdf('住宿')), ('bad.pdf', b'not a PDF')]
        result = analyze_lodging(files)
        self.assertEqual([r['name'] for r in result], ['0.PDF', '1.PDF', '2.PDF', '3.PDF'])
        self.assertEqual(result[0]['data'], files[0][1])
        self.assertEqual(set(result[0]), {'name', 'data', 'dates', 'basis', 'text'})

    def test_stay_ranges_exclude_invoice_and_unlabeled_dates(self):
        from lodging import analyze_lodging
        for label in ['入住：2030-01-03\n离店：2030-01-05',
                      '住宿日期：20300103至20300105',
                      '住宿日期：2030-01-03 - 2030-01-05',
                      '入住日期 离店日期\n20300103 20300105']:
            with self.subTest(label=label):
                text = '住宿服务\n开票日期：\n2030年10月22日\n' + label + '\n2030-11-01'
                result = analyze_lodging([('invoice.pdf', text_pdf(text))])[0]
                self.assertEqual(result['dates'], ['2030-01-03', '2030-01-05'])
                self.assertEqual(result['basis'], 'stay')

    def test_invoice_fallback_split_lines_is_conservative(self):
        from lodging import analyze_lodging, match_trip
        for label in ['开票日期：2030-01-04', '开票日期：\n20300104',
                      '开票日期：\n2030年\n1月\n4日']:
            with self.subTest(label=label):
                result = analyze_lodging([('a.pdf', text_pdf('客房服务\n' + label))])[0]
                self.assertEqual(result['dates'], ['2030-01-04'])
                self.assertEqual(result['basis'], 'invoice_date')
                self.assertEqual(match_trip(result['dates'], [{'id': 'middle', 'start': '2030-01-03', 'end': '2030-01-05'}]), 'middle')
        result = analyze_lodging([('a.pdf', text_pdf('住宿\n入住：\n开票日期：\n2030-01-04'))])[0]
        self.assertEqual(result['basis'], 'invoice_date')
        self.assertEqual(result['dates'], ['2030-01-04'])
        result = analyze_lodging([('a.pdf', text_pdf('住宿\n开票日期：\n购买方：\n2030-01-04'))])[0]
        self.assertEqual(result['dates'], [])

    def test_huazhu_detached_issue_and_short_order_range(self):
        from lodging import analyze_lodging
        text='开票日期：\n购买方信息\n11111111111111111111\n2030年10月24日\n订单日期:10-23至10-24,共1天\n*生产生活服务*住宿费'
        result=analyze_lodging([('a.pdf',text_pdf(text))])[0]
        self.assertEqual(result['dates'],['2030-10-23','2030-10-24'])
        self.assertEqual(result['basis'],'stay')

    def test_no_date_invalid_dates_and_text_limit(self):
        from lodging import analyze_lodging, match_trip
        for suffix in ['', '\n2030-01-04', '\n住宿日期：2030-02-30\n开票日期：2030-13-01']:
            with self.subTest(suffix=suffix):
                result = analyze_lodging([('a.pdf', text_pdf('房费' + suffix + '\n' + 'x' * 8100))])[0]
                self.assertEqual(result['dates'], [])
                self.assertEqual(result['basis'], 'invoice_date')
                self.assertEqual(len(result['text']), 8000)
                self.assertIsNone(match_trip(result['dates'], [{'id': 1, 'start': '2030-01-01', 'end': '2030-01-31'}]))

    def test_match_trip_requires_all_dates_and_unique_overlap(self):
        from lodging import match_trip
        trips = [{'id': 'a', 'start': '2030-01-03', 'end': '2030-01-05'},
                 {'id': 'b', 'start': '2030-01-05', 'end': '2030-01-07'}]
        self.assertEqual(match_trip(['2030-01-03', '2030-01-05'], trips), 'a')
        self.assertIsNone(match_trip(['2030-01-05'], trips))
        self.assertIsNone(match_trip(['2030-01-03', '2030-01-07'], trips))
        self.assertIsNone(match_trip(['invalid'], trips))
        self.assertIsNone(match_trip([], trips))
        self.assertIsNone(match_trip(['2030-01-04'], []))


if __name__ == '__main__':
    unittest.main()
