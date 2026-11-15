from datetime import datetime
from pathlib import Path
import re


def archive_files(base, date, event, files):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('请选择完整日期')
    try:
        day = datetime.strptime(date, '%Y-%m-%d').strftime('%Y%m%d')
    except ValueError:
        raise ValueError('日期无效')
    event = event.strip()
    if not event or len(event.encode('utf-8')) > 220 or any(c in event for c in '/\\:\x00\n\r'):
        raise ValueError('请填写事项，不能包含斜杠、冒号或换行')
    files = list(files)
    if not files:
        raise ValueError('请先添加 PDF')
    for name, content in files:
        if not name or name.startswith('.') or any(c in name for c in '/\\:\x00\n\r') or len(name.encode('utf-8')) > 230:
            raise ValueError('文件名无效：' + name)
        if not name.lower().endswith('.pdf') or b'%PDF-' not in content[:1024]:
            raise ValueError('不是有效的 PDF：' + name)
    base = Path(base).expanduser()
    if not base.is_absolute():
        raise ValueError('归档目录必须是完整路径')
    base = base.resolve()
    folder = base / (day + event)
    if folder.is_symlink() or base not in folder.resolve().parents:
        raise ValueError('Archive folder escapes configured root')
    folder.mkdir(parents=True, exist_ok=True)
    saved = []
    created = []
    try:
        for name, content in files:
            original = Path(name)
            number = 1
            while True:
                target = folder / (name if number == 1 else '{} ({}).pdf'.format(original.stem, number))
                try:
                    f = target.open('xb')
                    break
                except FileExistsError:
                    number += 1
            created.append(target)
            with f:
                f.write(content)
            saved.append(target.name)
    except Exception:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return {'folder': str(folder), 'files': saved}
