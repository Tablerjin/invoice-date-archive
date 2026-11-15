import io
import unittest
import zipfile
from unittest.mock import patch


def zipped(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return out.getvalue()


PDF = b'%PDF-1.4\nfixture'


class ExtractionTests(unittest.TestCase):
    def test_itineraries_allowlisted_and_duplicate_names_preserved(self):
        import toll
        data = zipped([('行程.pdf', PDF), ('other.pdf', PDF)])
        files = toll.extract_pdfs([('行程.pdf', PDF), ('汇聚.zip', data),
                                   ('汇总.zip', data), ('other.zip', data),
                                   ('other.pdf', PDF)])
        self.assertEqual([n for n, _ in files], ['行程.pdf', '行程_2.pdf', '行程_3.pdf'])

    def test_rejects_unsafe_paths_and_expansion_limit(self):
        import toll
        for path in ('../PDF/a.pdf', '/PDF/a.pdf', 'PDF/../../a.pdf',
                     'PDF\\..\\a.pdf', 'C:/PDF/a.pdf'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                toll.extract_pdfs([('通行费电子发票.zip', zipped([(path, PDF)]))])
        with patch.object(toll, 'MAX_EXPANDED', 10):
            with self.assertRaises(ValueError):
                toll.extract_pdfs([('通行费电子发票.zip', zipped([('ignored.xml', b'x' * 11)]))])
            with self.assertRaises(ValueError):
                toll.extract_pdfs([('行程.pdf', PDF)])
        with self.assertRaises(ValueError):
            toll.extract_pdfs([('汇总.zip', b'broken')])

    def test_invoice_zip_selects_only_pdf_folder(self):
        import toll
        data = zipped([('root/PdF/a.pdf', PDF), ('xml/a.xml', b'xml'),
                       ('root/a.pdf', PDF), ('PDF/not.pdf', b'bad')])
        self.assertEqual(toll.extract_pdfs([('通行费电子发票 (4).zip', data)]), [('a.pdf', PDF)])


def text_pdf(text):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
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


class AnalysisTests(unittest.TestCase):
    def test_detached_issue_date_excluded_and_compact_travel_dates(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        data = text_pdf('开票日期：\n2030年10月22日\n通行日期起 通行日期止\n20300103\n20300104\n入口收费站：南京\n出口站：镇江')
        result = toll.analyze_pdfs([('行程.pdf', data)])
        self.assertEqual(result['dates'], ['2030-01-03', '2030-01-04'])
        self.assertEqual(result['stations'], ['南京', '镇江'])
        self.assertTrue(result['warnings'])

    def test_unresolved_invalid_and_text_limit(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        result = toll.analyze_pdfs([('行程.pdf', text_pdf('开票日期：2030-01-03\n通行日期：2030-02-30\n' + 'x' * 41000))])
        self.assertEqual(result['dates'], [])
        self.assertEqual(len(result['text']), 40000)
        self.assertTrue(any('unresolved' in w for w in result['warnings']))
        with self.assertLogs('pypdf', level='WARNING'):
            result = toll.analyze_pdfs([('bad.pdf', b'%PDF-invalid')])
        self.assertEqual(result['dates'], [])
        self.assertTrue(any('failed' in w for w in result['warnings']))

    def test_unlabeled_dates_remain_unresolved(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        result = toll.analyze_pdfs([('行程.pdf', text_pdf('2030-01-03\n收费站：南京'))])
        self.assertEqual(result['dates'], [])
        self.assertEqual(result['stations'], ['南京'])

    def test_invoice_layout_does_not_treat_detached_issue_date_as_trip(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        text = '开票日期：\n名称：\n通行日期起 通行日期止\n2030年10月22日\n客车\n20300103\n20300103'
        result = toll.analyze_pdfs([('invoice.pdf', text_pdf(text))])
        self.assertEqual(result['dates'], ['2030-01-03'])

    def test_station_labels_without_colons_and_split_lines(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        result = toll.analyze_pdfs([('行程.pdf', text_pdf('通行日期：2030-01-03\n入口 南京收费站\n出口站\n镇江收费站\n收费站名称：苏州'))])
        self.assertEqual(result['stations'], ['南京收费站', '镇江收费站', '苏州'])

    def test_prefers_itinerary_trip_dates_not_invoice_issue_date(self):
        import toll
        try:
            import pypdf
        except ImportError:
            self.skipTest('pypdf not installed')
        files = [('invoice.pdf', text_pdf('开票日期：2030年02月01日\n通行日期：2025-12-31\n出口：旧站')),
                 ('行程.pdf', text_pdf('开票日期：2030-02-01\n通行日期：2030年1月3日\n入口：南京收费站\n出口：镇江收费站'))]
        result = toll.analyze_pdfs(files)
        self.assertEqual(result['dates'], ['2030-01-03'])
        self.assertEqual(result['stations'], ['南京收费站', '镇江收费站'])
        self.assertIn('开票日期', result['text'])
        self.assertEqual(result['warnings'], [])


if __name__ == '__main__':
    unittest.main()
