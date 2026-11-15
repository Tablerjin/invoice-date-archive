"""Build standalone per-trip reimbursement summaries from archived invoices."""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
import json
import re

try:
    import pymupdf
except ImportError:
    pymupdf = None
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

CENT = Decimal("0.01")
_CURRENCY = re.compile(r"[¥￥]\s*([0-9,]+(?:\.[0-9]{1,2})?)")
_SCHOOLS = {
    "南通大学": "南通", "扬州大学": "扬州", "江南大学": "无锡",
    "复旦大学": "上海", "江苏大学": "镇江",
}
_STATIONS = {"南通": "南通", "扬州": "扬州", "无锡": "无锡", "上海": "上海", "镇江": "镇江"}


def _money(value):
    return Decimal(value).quantize(CENT)


def _pdf_text(path):
    """Read the actual invoice, falling back when the primary reader fails/empties."""
    if pymupdf:
        try:
            with pymupdf.open(path) as doc:
                text = "\n".join(page.get_text() for page in doc)
            if text.strip():
                return text
        except Exception:
            pass
    if PdfReader:
        try:
            return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        except Exception:
            pass
    return ""


def _amount(text, kind):
    if kind == "rail":
        matches = re.findall(r"[￥¥]\s*([0-9,]+(?:\.[0-9]{1,2})?)", text)
    else:
        labeled = re.findall(r"价税合计\s*(?:（小写）|\(小写\))?\s*[：:]?\s*[¥￥]\s*([0-9,]+(?:\.[0-9]{1,2})?)", text)
        matches = labeled or _CURRENCY.findall(text)
    if not matches:
        return None, "unresolved"
    try:
        vals = [_money(s.replace(",", "")) for s in matches]
    except InvalidOperation:
        return None, "unresolved"
    return max(vals), "extracted" if len(set(vals)) == 1 or kind == "rail" else "ambiguous_max"


def _classify(name, text, item_kind=""):
    value = name + "\n" + text
    if "通行费" in value:
        return "car"
    if "铁路电子客票" in value:
        return "rail"
    if re.search(r"住宿|房费|酒店", value):
        return "lodging"
    return "other"


def _destination(items):
    for item in sorted(items, key=lambda x: min(x.get("dates") or ["9999"])):
        guess = item.get("school_guess") or {}
        station = guess.get("station", "")
        for key, city in _STATIONS.items():
            if key in station:
                return city
        event = str(item.get("event", ""))
        for school, city in _SCHOOLS.items():
            if school in event:
                return city
    return ""


def build_report(folder, items, lodging_records):
    from local_config import load_settings
    settings = load_settings()
    items = list(items)
    dates = sorted({d for item in items for d in list(item.get("dates", [])) + [item.get("start"), item.get("end")] if _valid_date(d)})
    start, end = (dates[0], dates[-1]) if dates else ("", "")
    days = (date.fromisoformat(end) - date.fromisoformat(start)).days + 1 if dates else 0
    warnings = []
    if not dates:
        warnings.append("未能确定出差日期")
    destination = _destination(items)
    if not destination:
        warnings.append("未识别目的城市，请核对")
    event_item = next((x for x in sorted(items, key=lambda x: min(x.get("dates") or ["9999"])) if x.get("event") or x.get("school_guess", {}).get("event")), {})
    reason = event_item.get("event") or event_item.get("school_guess", {}).get("event", "")
    if event_item.get("school_guess"):
        warnings.append("出差事由中的学校为按车站推测，并非实际到访证明")
    audit = []
    sums = {k: Decimal("0.00") for k in ("rail", "car", "lodging", "other")}
    # Count actual PDF invoice files in the trip folder, never summary sheets.
    pdfs = sorted((p for p in Path(folder).glob("*") if p.is_file() and p.suffix.lower() == ".pdf" and "行程" not in p.name and "汇总" not in p.name), key=lambda p: p.name)
    audit_names = {x["name"] for x in audit}
    for p in pdfs:
        if p.name not in audit_names:
            text = _pdf_text(p)
            kind = _classify(p.name, text)
            amount, status = _amount(text, kind)
            if amount is None:
                warnings.append(f"金额待核对：{p.name}")
            else:
                sums[kind] += amount
                if status == "ambiguous_max":
                    warnings.append(f"金额存在多项，按最大含税金额暂计：{p.name}")
            audit.append({"name": p.name, "type": kind, "amount": amount, "status": status})
    car_expenses = sums["car"]
    meals = _money(Decimal(days) * Decimal(str(settings['meal_rate'])))
    traffic = _money(Decimal(days) * (Decimal('0') if car_expenses > 0 else Decimal(str(settings['traffic_rate']))))
    # Each stay is [check-in, check-out), never an invoice-issue date.
    lodging_dates = set()
    stay_labels = []
    hotel_names = {x['name'] for x in audit if x['type'] == 'lodging'}
    dated_names = set()
    for rec in lodging_records or []:
        endpoints = sorted(d for d in rec.get('dates', []) if _valid_date(d))
        if rec.get('basis') != 'stay' or len(endpoints) < 2 or endpoints[0] >= endpoints[-1]:
            continue
        checkin, checkout = map(date.fromisoformat, [endpoints[0], endpoints[-1]])
        if not start or checkin < date.fromisoformat(start) or checkout > date.fromisoformat(end):
            continue
        lodging_dates.update((checkin + timedelta(days=n)).isoformat() for n in range((checkout-checkin).days))
        dated_names.add(rec.get('name', '住宿发票.pdf'))
        stay_labels.append(f'{checkin.isoformat()}入住至{checkout.isoformat()}退房（{(checkout-checkin).days}晚自付）')
    if not hotel_names:
        remark = '对方安排住宿'
    elif not hotel_names.issubset(dated_names):
        remark = '；'.join(stay_labels + ['住宿发票实际住宿日期待核，请核对自付及对方安排的晚数'])
        warnings.append('有住宿发票但缺少可靠入住/退房日期，未推算其余住宿晚数')
    else:
        hosted = max(0, days - 1 - len(lodging_dates))
        remark = '；'.join(stay_labels)
        if hosted:
            remark += f'；其余{hosted}晚对方安排住宿'
    known_subtotal = sum(sums.values(), Decimal('0.00'))
    complete = bool(dates) and all(x['amount'] is not None for x in audit)
    invoice_subtotal = known_subtotal if all(x['amount'] is not None for x in audit) else None
    total = known_subtotal + meals + traffic if complete else None
    return {
        "project": settings["project"], "origin": settings["origin"], "destination": destination,
        "start": start, "end": end, "days": days, "reason": reason,
        "notes": remark, "meal_subsidy": meals, "traffic_subsidy": traffic,
        "rail_expenses": sums["rail"], "car_expenses": car_expenses,
        "lodging_expenses": sums["lodging"], "other_expenses": sums["other"],
        "total": total, "invoice_count": len(pdfs), "invoices": audit,
        "invoice_subtotal": invoice_subtotal, "known_invoice_subtotal": known_subtotal,
        "subsidy_subtotal": meals + traffic, "complete": complete,
        "warnings": warnings, "folder": str(folder),
    }


def _valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def render_report(data):
    serialized = json.dumps({k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()}, ensure_ascii=False, default=str).replace("<", "\\u003c").replace(">", "\\u003e")
    fields = [("project", "项目编号"), ("origin", "出发地"), ("destination", "目的城市"), ("start", "开始日期"), ("end", "结束日期"), ("days", "出差天数"), ("reason", "出差事由"), ("notes", "备注"), ("rail_expenses", "铁路费用"), ("car_expenses", "汽车费用"), ("lodging_expenses", "住宿费用"), ("meal_subsidy", "伙食补助"), ("traffic_subsidy", "交通补助"), ("other_expenses", "其他费用"), ("invoice_subtotal", "发票小计"), ("subsidy_subtotal", "补助小计"), ("total", "报销合计")]
    rows = []
    for key, label in fields:
        value = escape(str(data[key]) if data.get(key) is not None else "待核对（合计不完整）")
        editable = key in ("project", "reason", "notes")
        content = f'<input id="v-{key}" value="{value}" aria-label="{label}">' if editable else f'<span id="v-{key}">{value}</span>'
        rows.append(f'<tr><th>{label}</th><td>{content}</td><td><button type="button" data-copy="{key}" aria-label="复制{label}">复制</button></td></tr>')
    audit = "".join(f'<tr><td>{escape(str(x["name"]))}</td><td>{escape(x["type"])}</td><td>{escape(str(x["amount"] if x["amount"] is not None else "待核对"))}</td><td>{escape(x["status"])}</td></tr>' for x in data.get("invoices", []))
    warning_html = "".join(f"<li>{escape(w)}</li>" for w in data.get("warnings", []))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>报销信息 - {escape(str(data.get('project','')))}</title><style>
*{{box-sizing:border-box}}body{{margin:0;color:#202b33;background:#f3f5f4;font:15px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:900px;margin:24px auto;padding:0 18px}}header{{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #147d72;padding:0 0 14px}}h1{{font-size:22px;margin:0}}button{{cursor:pointer;border:1px solid #b8c8c4;background:#fff;color:#155e55;padding:7px 12px;border-radius:4px}}button:hover{{background:#e7f1ee}}table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #e3e9e7}}th{{width:150px;color:#455b57}}td:last-child{{width:90px}}input{{font:inherit;border:1px solid #b8c8c4;padding:6px;width:min(100%,480px)}}section{{margin-top:26px}}h2{{font-size:17px}}.warning{{color:#8b4c16}}@media print{{body{{background:#fff}}main{{margin:0 auto}}button{{display:none}}input{{border:0;padding:0}}thead{{display:table-header-group}}}}
</style></head><body><main><header><h1>报销信息</h1><button id="download" type="button">Download saved HTML</button></header><table><tbody>{''.join(rows)}</tbody></table><section><h2>发票明细（{int(data.get('invoice_count',0))} 张）</h2><table><thead><tr><th>文件</th><th>类型</th><th>金额</th><th>提取状态</th></tr></thead><tbody>{audit}</tbody></table></section><section class="warning"><h2>核对提醒</h2><ul>{warning_html or '<li>无</li>'}</ul></section></main><script>
const report={serialized};
function values(){{for(const key of ['project','reason','notes']){{const el=document.getElementById('v-'+key);if(el)report[key]=el.value}}}}
async function copyText(text){{try{{await navigator.clipboard.writeText(text)}}catch(e){{const t=document.createElement('textarea');t.value=text;document.body.appendChild(t);t.select();document.execCommand('copy');t.remove()}}}}
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{{values();const el=document.getElementById('v-'+b.dataset.copy);copyText(el?.value??el?.textContent??'')}}));
document.getElementById('download').addEventListener('click',()=>{{values();const clone=document.documentElement.cloneNode(true);for(const key of ['project','reason','notes']){{const e=clone.querySelector('#v-'+key);if(e){{e.setAttribute('value',report[key]);e.setAttribute('data-saved',report[key])}}}}const blob=new Blob(['<!doctype html>'+clone.outerHTML],{{type:'text/html;charset=utf-8'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='报销信息.html';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}});
</script></body></html>'''


def generate_reports(state):
    """Generate one report for each unique archived trip folder and return paths."""
    items = [x for x in state.get("items", []) if x.get("state") == "archived" and x.get("folder")]
    folders = {}
    for item in items:
        folders.setdefault(str(Path(item["folder"]).expanduser().resolve()), []).append(item)
    results = []
    lodgings = state.get("lodging", {})
    for folder, trip_items in folders.items():
        records = []
        for entry in lodgings.values():
            if entry.get("state") == "archived" and Path(entry.get("folder", "")).expanduser().resolve() == Path(folder):
                path = Path(folder) / entry.get("name", "住宿发票.pdf")
                records.append({**entry, "name": path.name, "text": _pdf_text(path) if path.is_file() else ""})
        report = build_report(folder, trip_items, records)
        path = Path(folder) / "报销信息.html"
        from safe_output import replace_output
        replace_output(path, lambda temporary: temporary.write_text(render_report(report), encoding="utf-8"))
        results.append(str(path))
    return results
