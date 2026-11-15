from datetime import date

def trip_details(item, event):
    dates=sorted(set(item['dates']))
    if not dates: raise ValueError('尚未识别出行程日期')
    start,end=dates[0],dates[-1]
    days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
    stations=item.get('stations',[])
    return {'start':start,'end':end,'days':days,'destination':stations[1] if len(stations)>1 else (stations[0] if stations else ''),'event':('至'+end.replace('-','')+'共'+str(days)+'天' if days>1 else '')+event}
