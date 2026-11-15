import unittest
from email.message import EmailMessage
from mail_sync import attachment_files

class MailTests(unittest.TestCase):
    def test_select_only_invoice_zip_and_itinerary(self):
        m = EmailMessage()
        m.set_content('发票附件')
        for name in ['通行费电子发票.zip', '通行费电子票据汇总单(行程).pdf', '清单.xlsx']:
            m.add_attachment(b'test', maintype='application', subtype='octet-stream', filename=name)
        self.assertEqual([n for n, b in attachment_files(m.as_bytes())], ['通行费电子发票.zip', '通行费电子票据汇总单(行程).pdf'])

    def test_recovers_itinerary_when_filename_extension_is_corrupt(self):
        m = EmailMessage()
        m.set_content('附件')
        m.add_attachment(b'%PDF-1.4 sample', maintype='application', subtype='octet-stream', filename='通行费电子票据汇总单(行程乱码')
        self.assertEqual(attachment_files(m.as_bytes()), [('通行费电子票据汇总单(行程).pdf', b'%PDF-1.4 sample')])

if __name__ == '__main__': unittest.main()
