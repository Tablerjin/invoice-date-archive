from datetime import date
import re
import pymupdf

def groups(items,gap):
    ordered=sorted([x for x in items if x.get('dates')],key=lambda x:(min(x['dates']),x.get('departure',''),x['id']))
    result=[]
    for item in ordered:
        if not result or (date.fromisoformat(min(item['dates']))-date.fromisoformat(max(d for x in result[-1] for d in x['dates']))).days>gap:
            result.append([])
        result[-1].append(item)
    return result

def rail_details(content):
    import io
    try:
        from pypdf import PdfReader
        text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(content)).pages)
    except Exception:
        with pymupdf.open(stream=content,filetype='pdf') as doc:text='\n'.join(p.get_text() for p in doc)
    dates=[]
    for line in text.splitlines():
        if '开票' in line:continue
        for m in re.finditer(r'(20\d{2})年(\d{1,2})月(\d{1,2})日',line):
            dates.append(date(*map(int,m.groups())).isoformat())
    stations=re.findall(r'^([\u4e00-\u9fff]{1,15}站)\s*$',text,re.M)
    times=re.findall(r'(\d{2}:\d{2})开',text)
    return {'dates':sorted(set(dates)),'stations':stations[:2],'departure':times[0] if times else '', 'text':text,'warnings':[],'kind':'rail'}
