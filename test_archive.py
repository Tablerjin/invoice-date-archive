import tempfile
import unittest
from pathlib import Path
from archive import archive_files

class ArchiveTests(unittest.TestCase):
    def test_copy_pdf_into_dated_event(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / '车票.pdf'
            source.write_bytes(b'%PDF-1.4\nexample')
            result = archive_files(root / '会议', '2030-01-03', '去江苏大学交流', [(source.name, source.read_bytes())])
            target = root / '会议' / '20300103去江苏大学交流' / source.name
            self.assertEqual(target.read_bytes(), source.read_bytes())
            self.assertTrue(source.exists())
            self.assertEqual(result['folder'], str(target.parent.resolve()))

    def test_existing_names_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            args = (d, '2030-01-03', '去江苏大学交流', [('票.pdf', b'%PDF-first')])
            archive_files(*args)
            result = archive_files(d, args[1], args[2], [('票.pdf', b'%PDF-second')])
            folder = Path(result['folder'])
            self.assertEqual((folder / '票.pdf').read_bytes(), b'%PDF-first')
            self.assertEqual((folder / '票 (2).pdf').read_bytes(), b'%PDF-second')

    def test_invalid_inputs_do_not_create_folder(self):
        for date, event, files in [
            ('2030-02-30', '交流', [('票.pdf', b'%PDF-test')]),
            ('2030-01-03', '../交流', [('票.pdf', b'%PDF-test')]),
            ('2030-01-03', '', [('票.pdf', b'%PDF-test')]),
            ('2030-01-03', '交流', [('../票.pdf', b'%PDF-test')]),
            ('2030-01-03', '交流', [('票.pdf', b'not a pdf')]),
            ('2030-01-03', '交流', []),
        ]:
            with self.subTest(date=date, event=event, files=files), tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    archive_files(d, date, event, files)
                self.assertEqual(list(Path(d).iterdir()), [])

if __name__ == '__main__':
    unittest.main()
