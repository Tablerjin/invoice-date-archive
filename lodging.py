"""Read lodging invoice PDFs in memory; never write attachment or trip files."""
import io
import re
from datetime import date

from pypdf import PdfReader


# A hotel seller name alone does not establish an accommodation service.
_SERVICE = re.compile(r'住宿|房费|客房|酒店\s*服务')
_STAY = re.compile(r'入住(?:日期|时间)?|离店(?:日期|时间)?|住宿日期')
_ISSUED = re.compile(r'开票日期')
_DATE = re.compile(
    r'(?<!\d)(?P<y>20\d{2})(?:'
    r'\s*[-年/.]\s*(?P<m>\d{1,2})\s*[-月/.]\s*(?P<d>\d{1,2})\s*日?'
    r'|(?P<cm>\d{2})(?P<cd>\d{2}))(?!\d)'
)
_PUNCT = re.compile(r'[\s:：]*')
_RANGE = re.compile(r'\s*(?:至|到|~|～|—|–|－|-)\s*')


def _normalized(match):
    try:
        return date(int(match['y']), int(match['m'] or match['cm']),
                    int(match['d'] or match['cd'])).isoformat()
    except ValueError:
        return None


def _labeled_dates(text, labels):
    """Read adjacent values only, including paired headers and split date lines."""
    found = set()
    for label in labels.finditer(text):
        pos = _PUNCT.match(text, label.end()).end()
        # PDF tables sometimes extract both headers before either value.
        paired = None
        if labels is _STAY:
            paired = labels.match(text, pos)
            if paired:
                pos = _PUNCT.match(text, paired.end()).end()
        first = _DATE.match(text, pos)
        if not first:
            continue
        value = _normalized(first)
        if value:
            found.add(value)
        # A stay field may hold a range; invoice issue fields hold one date.
        if labels is _STAY:
            separator = _RANGE.match(text, first.end())
            pos = (separator.end() if separator else
                   _PUNCT.match(text, first.end()).end() if paired else None)
            second = _DATE.match(text, pos) if pos is not None else None
            if second:
                value = _normalized(second)
                if value:
                    found.add(value)
    return sorted(found)


def analyze_lodging(files):
    """Return lodging records for (name, PDF bytes) pairs.

    Each record contains name, original data, sorted unique ISO dates, basis
    ('stay' or 'invoice_date'), and extracted text capped at 8000 characters.
    Stay dates are labeled endpoints, not an expansion into individual nights.
    If no labeled stay is available, use labeled invoice dates; if neither is
    available, retain the lodging record with dates=[] and basis='invoice_date'.
    Unreadable PDFs and non-PDF attachments are skipped. No OCR is performed.
    """
    results = []
    for name, data in files:
        if not name.lower().endswith('.pdf') or not data.startswith(b'%PDF-'):
            continue
        try:
            reader = PdfReader(io.BytesIO(data))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        except Exception:
            # One damaged/encrypted attachment must not hide valid invoices.
            continue
        if not _SERVICE.search(text):
            continue
        dates = _labeled_dates(text, _STAY)
        # Huazhu layouts detach the issue value and omit years in order dates.
        order=re.search(r'订单日期\s*[:：]\s*(\d{1,2})[-月/.](\d{1,2})日?\s*至\s*(\d{1,2})[-月/.](\d{1,2})',text)
        if not dates and order:
            anchors=[m for m in _DATE.finditer(text) if _normalized(m)]
            years={int(m['y']) for m in anchors}
            if len(years)==1:
                year=next(iter(years));m1,d1,m2,d2=map(int,order.groups())
                try:
                    end=date(year,m2,d2)
                    start=date(year-1 if (m1,d1)>(m2,d2) else year,m1,d1)
                    dates=[start.isoformat(),end.isoformat()]
                except ValueError: pass
        basis = 'stay' if dates else 'invoice_date'
        if not dates:
            dates = _labeled_dates(text, _ISSUED)
        results.append({'name': name, 'data': data, 'dates': dates,
                        'basis': basis, 'text': text[:8000]})
    return results


def match_trip(dates, trips):
    """Return the unique containing trip's id, or None for no/ambiguous match.

    dates: iterable of ISO YYYY-MM-DD strings.
    trips: iterable of dicts with id, start, end (ISO date strings).
    Both trip boundaries are inclusive; every lodging date must fit.
    """
    try:
        values = [date.fromisoformat(value) for value in dates]
    except (TypeError, ValueError):
        return None
    if not values:
        return None
    matches = []
    for trip in trips:
        try:
            start = date.fromisoformat(trip['start'])
            end = date.fromisoformat(trip['end'])
            if all(start <= value <= end for value in values):
                matches.append(trip['id'])
        except (KeyError, TypeError, ValueError):
            continue
    return matches[0] if len(matches) == 1 else None
