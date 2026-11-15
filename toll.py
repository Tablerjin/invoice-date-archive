"""Selective, in-memory toll attachment extraction and conservative trip analysis."""
import io
import re
import zipfile
from pathlib import PurePosixPath

MAX_EXPANDED = 150 * 1024 * 1024


def extract_pdfs(attachments):
    """Return flattened (filename, bytes) PDF pairs; never write to disk.

    Allow invoice ZIP PDFs only below a PDF directory, and itinerary PDFs
    directly or in 汇聚/汇总 ZIPs. Nested ZIPs are deliberately ignored.
    Invalid signatures are skipped; duplicate basenames receive _2, _3, ... .
    Unsafe paths, malformed ZIPs, or total expanded size above 150 MiB raise
    ValueError. The size budget includes ignored ZIP members and direct PDFs.
    """
    result = []
    expanded = 0
    used = set()

    def safe_path(name):
        path = PurePosixPath(name.replace('\\', '/'))
        if path.is_absolute() or '..' in path.parts or ':' in name or '\x00' in name:
            raise ValueError('Unsafe attachment path: ' + repr(name))
        return path

    def add(name, content):
        if not content.startswith(b'%PDF-'):
            return
        path = PurePosixPath(name)
        candidate = path.name
        index = 2
        while candidate.casefold() in used:
            candidate = '{}_{}{}'.format(path.stem, index, path.suffix)
            index += 1
        used.add(candidate.casefold())
        result.append((candidate, content))

    for name, data in attachments:
        path = safe_path(name)
        name = path.name
        if name.lower().endswith('.pdf') and '行程' in name:
            expanded += len(data)
            if expanded > MAX_EXPANDED:
                raise ValueError('Expanded attachments exceed 150 MB')
            add(name, data)
        elif name.lower().endswith('.zip'):
            invoice = name.startswith('通行费电子发票')
            itinerary = '汇聚' in name or '汇总' in name
            if not (invoice or itinerary):
                continue
            try:
                archive = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile as exc:
                raise ValueError('Invalid ZIP: ' + name) from exc
            with archive:
                # Preflight every member, including ignored files: no partial return.
                for info in archive.infolist():
                    safe_path(info.filename)
                    expanded += info.file_size
                    if expanded > MAX_EXPANDED:
                        raise ValueError('Expanded attachments exceed 150 MB')
                for info in archive.infolist():
                    path = safe_path(info.filename)
                    selected = (invoice and 'pdf' in [part.lower() for part in path.parts[:-1]]) or (itinerary and '行程' in path.name)
                    if selected and path.suffix.lower() == '.pdf':
                        add(path.name, archive.read(info))
    return result


def analyze_pdfs(files):
    """Return dates/stations/text/warnings; never infer a single trip or schools.

    pypdf is imported lazily so extraction works without third-party packages.
    Readable itineraries take precedence over invoice evidence.
    """
    from datetime import date
    from pypdf import PdfReader

    warnings = []
    documents = []
    for name, data in files:
        try:
            reader = PdfReader(io.BytesIO(data))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            if not text.strip():
                warnings.append(name + ': no extractable text; OCR may be required')
            documents.append((name, text))
        except Exception as exc:
            warnings.append(name + ': PDF read failed (' + type(exc).__name__ + ')')
    preferred = [(n, t) for n, t in documents if '行程' in n and t.strip()]
    sources = preferred or documents
    dates = set()
    stations = []
    date_pattern = re.compile(r'(?<!\d)(20\d{2})\s*(?:[-/.年]\s*)(\d{1,2})\s*(?:[-/.月]\s*)(\d{1,2})(?:日)?(?!\d)')
    compact_pattern = re.compile(r'(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)')
    for name, text in sources:
        if '行程' in name and '通行日期' in text:
            for pair in re.finditer(r'(?<!\d)(20\d{6})(20\d{6})(?!\d)', text):
                for value in pair.groups():
                    try: dates.add(date(int(value[:4]),int(value[4:6]),int(value[6:])).isoformat())
                    except ValueError: pass
            for route in re.finditer(r'(?:苏|浙|皖|沪|鲁)·(?:江苏|浙江|安徽|上海|山东)?([\u4e00-\u9fff\s]{1,28}?站)', text):
                station=re.sub(r'\s+','',route.group(1))
                if station not in stations: stations.append(station)
        skip_issue_value = False
        travel_table = bool(re.search(r'通行日期|通行时间|交易时间|入口时间|出口时间|入站时间|出站时间', text))
        for line in text.splitlines():
            if re.search(r'开票|出票|签发|打印|生成', line):
                skip_issue_value = not (date_pattern.search(line) or compact_pattern.search(line))
                continue
            if skip_issue_value and (date_pattern.search(line) or compact_pattern.search(line)):
                skip_issue_value = False
                continue
            labeled = re.search(r'通行日期|通行时间|交易时间|入口时间|出口时间|入站时间|出站时间', line)
            standalone = re.fullmatch(r'\s*(?:20\d{6}|20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?\s*', line)
            if labeled or ('行程' in name and travel_table) or (travel_table and standalone):
                for match in list(date_pattern.finditer(line)) + list(compact_pattern.finditer(line)):
                    try:
                        dates.add(date(*map(int, match.groups())).isoformat())
                    except ValueError:
                        pass
        station_pattern = r'(?:^|[\s,，;；])(?:出口|入口|收费站)(?:收费站|站)?(?:名称|站名)?(?:\s*[:：]\s*|\s+)([^\s,，;；:：]+)'
        for match in re.finditer(station_pattern, text):
            station = match.group(1)
            if not re.search(r'入口|出口|日期|时间|金额|收费站名称', station) and station not in stations:
                stations.append(station)
    if not dates:
        warnings.append('Trip dates unresolved: no explicit travel date evidence')
    if len(dates) > 1:
        warnings.append('Multiple trip dates found; archive as a continuous date range')
    return {'dates': sorted(dates), 'stations': stations,
            'text': '\n\n'.join(t for _, t in documents)[:40000], 'warnings': warnings}
