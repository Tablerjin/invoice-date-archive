# Invoice Date Archive

A local Chinese-language invoice archiver with read-only IMAP retrieval, toll/rail trip grouping, lodging matching, editable reimbursement HTML and generic Excel drafts. Runs on macOS and Linux with Python 3.10–3.13.

See [INSTALL.md](INSTALL.md) for setup and [SECURITY.md](SECURITY.md) for the local trust boundary. No invoices, personal settings, original institutional workbook, credentials, environment or history are distributed.

## Quick start

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

The browser opens a loopback-only control page. The default archive is `~/Documents/InvoiceArchive`; edit and save the archive location in settings before using another location. Manual PDF archiving works without mailbox configuration. Mail sync starts disabled: enter your own account, IMAP SSL server and app authorization code to enable it. Secrets are stored only through the OS keyring; an unavailable keyring fails visibly rather than falling back to plaintext.

Project identifier and departure city start blank and are editable. Daily meal **100** and traffic **80** are configurable example amounts, **not official reimbursement policy**. Inclusive trip days multiply these rates; a positive car/toll total suppresses traffic subsidy for the trip. Decimal arithmetic is used. Missing invoice amounts leave totals incomplete; ambiguous multi-amount extraction is flagged for review. Review every draft before claiming reimbursement.

Toll travel gaps of up to three days and railway gaps of up to five days form continuous trips. Lodging matches one unique overlapping trip; paid nights exclude checkout. Public regional school dictionaries support a limited set of Chinese routes. School labels are inferred, never evidence of a visit. Unknown regions remain pending unless a user-supplied maps helper or route rule is configured; manual archiving remains available.

Excel files are created from a blank workbook in code. They are generic drafts, not guaranteed accepted by any institution. `fill_workbook(template, output, report)` also accepts a user's own XLSX with the exact 15 headers documented in INSTALL. There is no original binary template in this repository.

Optional agent-led Notion integration is documented in [NOTION.md](NOTION.md). It is disabled by default, has no database identifiers or credentials, and does not make direct Notion API calls.

## Tests

```sh
.venv/bin/python -m pytest -q
```

The suite builds synthetic PDF/XLSX fixtures, verifies grouping and calculations, starts an isolated headless process, checks token enforcement, writes a synthetic PDF and exercises duplicate startup. It does not access your real mailbox or archive. CI covers macOS/Ubuntu and Python 3.10–3.13. LaunchAgent installation and real mailbox/Notion authentication are opt-in local steps, not CI operations.

Project code is MIT licensed; see [LICENSE](LICENSE). The optional runtime dependency PyMuPDF is separately licensed under AGPL-3.0-or-later or a commercial license; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The repository does not bundle PyMuPDF. The MIT license applies to project code, not third-party dependencies.
