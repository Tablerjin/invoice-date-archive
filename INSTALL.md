# Installation and configuration

Install Python 3.10–3.13, create a virtual environment and install `requirements.txt` as shown in README. On Linux provide a working Secret Service or other secure keyring backend, an unlocked desktop session, and `xdg-open` to open folders/reports. macOS uses Keychain and `open`. No plaintext secret fallback is provided.

## Local settings

The web settings form handles account, SSL IMAP server/port, archive path, project, origin and example rates. State lives independently at `~/Library/Application Support/DateArchivePublic` on macOS or `$XDG_STATE_HOME/DateArchivePublic` (default `~/.local/state/DateArchivePublic`) on Linux. The keyring service is `DateArchivePublic-IMAP`, keyed by account.

`local_config.py` reads non-secret `config.json` in this state directory. Environment overrides are `DATEARCHIVE_STATE_DIR`, `DATEARCHIVE_BASE`, `DATEARCHIVE_ACCOUNT`, `DATEARCHIVE_IMAP_SERVER`, `DATEARCHIVE_IMAP_PORT`, `DATEARCHIVE_PROJECT`, `DATEARCHIVE_ORIGIN`, `DATEARCHIVE_MEAL_RATE`, `DATEARCHIVE_TRAFFIC_RATE`, `DATEARCHIVE_MAPS_SCRIPT`, and `DATEARCHIVE_NOTION_ENABLED`. Never put authorization codes/passwords in config files or environment variables. Unknown/secret config keys are rejected. Environment overrides take precedence; remove an override to use saved UI values.

Mail retrieval uses TLS, INBOX read-only, BODY.PEEK and optional advertised IMAP ID. The default `imap.example.com` is a placeholder that must be replaced. Providers requiring OAuth instead of app passwords need a separate authentication implementation. Chinese toll/rail/lodging subject filters are intentionally specific; this is not a universal invoice importer. Scanned PDFs need OCR outside this app.

An optional absolute `maps_script` points to a compatible user-supplied Python helper accepting `nearby --near PLACE --category university --radius 30000 --limit 25` and returning JSON `results`/`places` entries with `name`, `distance_m` and optional `website`/`tags`. No host-agent filesystem dependency is assumed.

## Background mode on macOS

```sh
.venv/bin/python app.py --no-browser
.venv/bin/python install_service.py
```

The second command only prints a dry-run plist. Inspect it, then explicitly install with:

```sh
.venv/bin/python install_service.py --install
```

The helper writes `~/Library/LaunchAgents/local.invoice-date-archive.plist`, uses absolute project/interpreter paths, `--no-browser`, a separate state directory and separate logs, bootstraps it, and reads launchctl status. It refuses to overwrite an existing service. A duplicate `--no-browser` invocation exits without opening a browser. Read the current UI address from the state's `url` file. State and logs can contain private metadata; do not publish them.

To remove: `launchctl bootout gui/$(id -u)/local.invoice-date-archive`, then remove that exact plist. macOS may require user consent for archive folders. This export does not change any existing app or service.

## User-supplied XLSX template

Call `expense_excel.fill_workbook(template_path, output_path, report)` from Python. Header row must be exactly:

`序号, 开始时间, 结束时间, 出发地, 到达地, 火车, 汽车, 飞机, 市内交通, 住宿费, 伙食补助费, 其他费用, 报销金额, 报销审定金额, 备注`

The example row is replaced, remaining example rows removed, approval amount left blank, and numeric expense sum validated. Use `None` for a generated blank generic workbook. The automated sync uses this generic mode. Confirm your institution's required format before upload.
