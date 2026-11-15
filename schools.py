"""Map-backed heuristic school selection; results are guesses, never visit evidence."""
import json
from pathlib import Path
import re
import subprocess
import sys

from local_config import load_settings

def select_school(candidates):
    local = [x for x in candidates if x.get('name') and x.get('distance_m', 999999)<=30000]
    def score(x):
        name=x['name']
        # Preference heuristic, not an academic ranking.
        return (3 if '大学' in name else 0) + (1 if x.get('website') or x.get('tags',{}).get('wikidata') else 0) - x.get('distance_m',0)/15000
    return max(local,key=score) if local else None

def run_maps(args):
    script = load_settings()['maps_script']
    if not script or not Path(script).is_absolute() or not Path(script).is_file():
        raise ValueError('Configure an absolute maps_script path for unknown regions, or use manual archiving')
    p=subprocess.run([sys.executable,script]+args,capture_output=True,text=True,timeout=95)
    if p.returncode: raise ValueError('地图服务暂时不可用，请稍后重试')
    data=json.loads(p.stdout)
    if data.get('error'): raise ValueError('地图服务暂时不可用')
    return data

def infer_school(analysis):
    text=analysis.get('text','')
    exits=re.findall(r'出口(?:收费站|站)?(?:名称)?\s*[:：]?\s*([^\s,，;；:：]+)',text)
    exits=[x for x in exits if not re.search(r'时间|日期|金额|入口|出口',x)]
    stations=exits or analysis.get('stations',[])
    # The itinerary station list is in entrance -> exit order.
    if not exits and stations: stations=[stations[1] if len(stations)>1 else stations[0]]
    regional=[('上海','复旦大学','https://www.fudan.edu.cn/'),('无锡','江南大学','https://www.jiangnan.edu.cn/'),('小海','南通大学','https://www.ntu.edu.cn/'),('南通','南通大学','https://www.ntu.edu.cn/'),('扬州','扬州大学','https://www.yzu.edu.cn/'),('顾山','江南大学','https://jyxq.jiangnan.edu.cn/xqgk/xqjj.htm')]
    for station in stations:
        for keyword,school,source in regional:
            if keyword in station:
                return {'event':'去'+school+'交流','school':school,'station':station,'basis':'按目的地区域自动推测附近知名大学，非实际访问证明','source':source}
    if not stations: raise ValueError('未识别出收费站，暂无法自动匹配学校')
    # Use the first recorded exit; later exits can be the return journey.
    station=stations[0]
    place=station if '收费站' in station else station+'收费站'
    data=run_maps(['nearby','--near',place+' 中国','--category','university','--radius','30000','--limit','25'])
    candidates=data.get('results',data.get('places',[]))
    school=select_school(candidates)
    if not school: raise ValueError('未找到收费站附近 30 公里内的大学，稍后重试')
    return {'event':'去'+school['name']+'交流','school':school['name'],'station':station,'basis':'按地图附近高校自动推测，非实际访问证明','candidate':school}
