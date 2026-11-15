"""Persistent toll-mail queue, reviewed route rules and periodic read-only sync."""
import hashlib
import json
from pathlib import Path
import threading
import time
import keyring
from archive import archive_files
from mail_sync import fetch_messages

from local_config import load_settings, save_settings, require_mail, KEYRING_SERVICE
DEFAULT_BASE = load_settings()['base']

class Automation:
    def __init__(self, state):
        self.root = Path(state) / 'toll'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.sync_lock = threading.Lock()
        self.data = {'base': DEFAULT_BASE, 'enabled': False, 'days': 90, 'rules': {}, 'items': [], 'last_sync': '', 'error': ''}
        if (self.root / 'state.json').exists():
            self.data.update(json.loads((self.root / 'state.json').read_text()))

    def save(self):
        tmp = self.root / 'state.tmp'
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
        tmp.replace(self.root / 'state.json')

    def status(self):
        with self.lock:
            return dict(self.data, **{k: v for k, v in load_settings().items() if k != 'base'}, syncing=self.sync_lock.locked())

    def configure(self, payload):
        with self.lock:
            base = Path(payload.get('base', self.data['base'])).expanduser()
            if not base.is_absolute(): raise ValueError('请选择完整归档路径')
            settings = load_settings()
            settings.update({k: payload[k] for k in settings if k in payload})
            settings['base'] = str(base)
            if payload.get('enabled') or payload.get('password'):
                require_mail(settings)
            save_settings(settings)
            if payload.get('password'):
                keyring.set_password(KEYRING_SERVICE, settings['account'], payload['password'])
            self.data.update(base=str(base), enabled=bool(payload.get('enabled')), days=max(1,min(3650,int(payload.get('days',90)))))
            self.save()
        return self.status()

    def sync(self):
        if not self.sync_lock.acquire(False): return
        try:
            from toll import extract_pdfs, analyze_pdfs
            settings = load_settings()
            require_mail(settings)
            account = settings['account']
            password = keyring.get_password(KEYRING_SERVICE, account)
            if not password: raise ValueError('请先在设置中填写 IMAP 授权码')
            for msg in fetch_messages(account, password, self.data['days']):
                ident = hashlib.sha256(msg['id'].encode()).hexdigest()[:24]
                with self.lock:
                    if any(x['id']==ident for x in self.data['items']): continue
                files = extract_pdfs(msg['files'])
                if not files: continue
                analysis = analyze_pdfs(files)
                dest = self.root / ident
                dest.mkdir(exist_ok=True)
                for name, content in files: (dest / name).write_bytes(content)
                stations = analysis.get('stations', [])
                item = {'id':ident, 'subject':msg['subject'], 'files':[n for n,b in files], 'dates':analysis.get('dates',[]), 'stations':stations, 'text':analysis.get('text',''), 'warnings':analysis.get('warnings',[]), 'state':'pending'}
                with self.lock:
                    self.data['items'].insert(0,item)
                    self.save()
            from grouping import rail_details
            for msg in fetch_messages(account,password,self.data['days'],rail=True):
                for name,content in msg['files']:
                    ident=hashlib.sha256(content).hexdigest()[:24]
                    if any(x['id']==ident for x in self.data['items']):continue
                    analysis=rail_details(content)
                    dest=self.root/ident;dest.mkdir(exist_ok=True)
                    name='高铁发票.pdf';(dest/name).write_bytes(content)
                    self.data['items'].append(dict(analysis,id=ident,subject=msg['subject'],files=[name],state='pending'))
                    self.save()
            # Retry unresolved routes on each sync, including previously downloaded mail.
            for item in list(self.data['items']):
                if item['state'] != 'pending': continue
                if not item['dates']:
                    item['auto_error'] = '尚未识别出行程日期'
                    continue
                try:
                    from schools import infer_school
                    key = '|'.join(sorted(item['stations']))
                    rule = self.data['rules'].get(key) if key else None
                    if rule:
                        event = rule
                    else:
                        guess = infer_school(item)
                        item['school_guess'] = guess
                        event = guess['event']
                    self.confirm({'id':item['id'],'date':item['dates'][0],'event':event,'remember':False})
                    item.pop('auto_error',None)
                except Exception as e:
                    item['auto_error'] = str(e)
            self.merge_groups()
            self.sync_lodging(password)
            from reimbursement import generate_reports
            generate_reports(self.data)
            from expense_excel import generate_workbooks
            generate_workbooks(self.data)
            with self.lock:
                self.data['last_sync'] = time.strftime('%Y-%m-%d %H:%M:%S')
                self.data['error'] = ''
                self.save()
        except Exception as e:
            with self.lock:
                self.data['error'] = str(e)
                self.save()
        finally:
            self.sync_lock.release()

    def confirm(self, payload):
        with self.lock:
            item = next(x for x in self.data['items'] if x['id']==payload['id'])
            if item['state']=='archived': raise ValueError('这批文件已经归档')
            files = [(n,(self.root / item['id'] / n).read_bytes()) for n in item['files']]
            from trips import trip_details
            trip = trip_details(item, payload['event'])
            result = archive_files(self.data['base'],trip['start'],trip['event'],files)
            item.update(state='archived', folder=result['folder'], event=payload['event'], date=trip['start'], start=trip['start'], end=trip['end'], days=trip['days'])
            if payload.get('remember') and item['stations']:
                self.data['rules']['|'.join(sorted(item['stations']))]=payload['event']
            self.save()
            return result

    def merge_groups(self):
        from grouping import groups
        from trips import trip_details
        configured_base = Path(self.data['base']).expanduser()
        if not configured_base.is_absolute(): raise ValueError('Configured archive root must be absolute')
        base = configured_base.resolve()
        for kind,gap in [('toll',3),('rail',5)]:
            items=[x for x in self.data['items'] if x.get('kind','toll')==kind and x.get('dates') and x['state']=='archived']
            for batch in groups(items,gap):
                first=batch[0]
                if not first.get('event'):continue
                dates=sorted({d for x in batch for d in x['dates']})
                trip=trip_details({'dates':dates},first['event'])
                target=base/(trip['start'].replace('-','')+trip['event'])
                oldfolders={Path(x['folder']).expanduser() for x in batch if x.get('folder')}
                lodging_folders={Path(h['folder']).expanduser() for h in self.data.get('lodging',{}).values() if h.get('folder') and Path(h['folder']).expanduser() in oldfolders}
                paths=[target, *oldfolders, *lodging_folders]
                for path in paths:
                    resolved=path.resolve()
                    if path.is_symlink() or (resolved != base and base not in resolved.parents):
                        raise ValueError('Merge path outside configured root: '+str(path))
                for old in oldfolders:
                    if not old.is_dir(): raise ValueError('Merge source is not a directory: '+str(old))
                target.mkdir(parents=True,exist_ok=True)
                for old in oldfolders:
                    if old==target:continue
                    for source in list(old.iterdir()):
                        if source.name=='.DS_Store':continue
                        if not source.is_file():raise ValueError('归档文件夹中有子目录，未移动：'+str(source))
                        dest=target/source.name;n=2
                        while dest.exists():
                            if dest.read_bytes()==source.read_bytes():break
                            dest=target/(source.stem+' ('+str(n)+')'+source.suffix);n+=1
                        if not dest.exists():source.rename(dest)
                        else:source.unlink()
                    if (old/'.DS_Store').exists():(old/'.DS_Store').unlink()
                    old.rmdir()
                for x in batch:
                    x.update(folder=str(target),state='archived',start=trip['start'],end=trip['end'],days=trip['days'],group_id=first['id'])
                for h in self.data.get('lodging',{}).values():
                    if h.get('folder') and Path(h['folder']) in oldfolders:h['folder']=str(target)
                self.save()

    def sync_lodging(self, password):
        from lodging import analyze_lodging, match_trip
        grouped={}
        for x in self.data['items']:
            if x['state']=='archived' and x['dates']:
                ident=x.get('group_id',x['id'])
                grouped[ident]=dict(id=ident,start=x.get('start',min(x['dates'])),end=x.get('end',max(x['dates'])))
        trips=list(grouped.values())
        seen=self.data.setdefault('lodging',{})
        from datetime import date
        earliest=min((x['start'] for x in trips),default=None)
        history_days=max(self.data['days'],(date.today()-date.fromisoformat(earliest)).days+14 if earliest else 90)
        for msg in fetch_messages(load_settings()['account'],password,history_days,lodging=True):
            for hotel in analyze_lodging(msg['files']):
                ident=hashlib.sha256(hotel['data']).hexdigest()
                if seen.get(ident,{}).get('state')=='archived': continue
                trip_id=match_trip(hotel['dates'],trips)
                if not trip_id:
                    seen[ident]={'state':'unmatched','dates':hotel['dates'],'subject':msg['subject']}
                    continue
                item=next(x for x in self.data['items'] if x['id']==trip_id)
                folder=Path(item['folder'])
                name='住宿发票.pdf';number=2
                while (folder/name).exists():
                    name='住宿发票 ('+str(number)+').pdf';number+=1
                with (folder/name).open('xb') as f: f.write(hotel['data'])
                if (folder/name).read_bytes()!=hotel['data']: raise ValueError('住宿发票写入校验失败')
                seen[ident]={'state':'archived','folder':str(folder),'name':name,'dates':hotel['dates'],'basis':hotel['basis']}
                item.setdefault('lodging_files',[]).append(name)
                with self.lock: self.save()

    def start(self):
        def loop():
            while True:
                if self.data['enabled']: self.sync()
                time.sleep(900)
        threading.Thread(target=loop,daemon=True).start()
