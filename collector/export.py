"""把某个日期的交付清单物化为离线目录。

只使用本地保存目录里的清单与字节对象,不访问任何网络来源;
缺失项保留缺失说明,不用现址内容填补。
"""
import json
from pathlib import Path
from urllib.parse import urlsplit


def _safe_path(url):
    parts = urlsplit(url)
    host = parts.netloc or 'unknown'
    segments = [s for s in parts.path.split('/') if s not in ('', '.', '..')]
    return Path(host, *segments) if segments else Path(host, 'index')


def _missing_note(entry):
    lines = ['该资料在本次历史选择中未能取得存档字节。',
             '原始网址: %s' % entry['url'],
             '状态: %s' % entry['status']]
    capture = entry.get('capture') or {}
    if capture.get('id'):
        lines.append('选中捕获: %s @ %s' % (capture['id'], capture.get('at')))
    if entry.get('missing_capture'):
        lines.append('目录仍在但内容缺失的捕获: %s' % entry['missing_capture'])
    if entry.get('break_at'):
        lines.append('断在: %s' % entry['break_at'])
    if entry.get('edition_declared'):
        lines.append('页面声明册别: %s' % entry['edition_declared'])
    lines.append('按项目规则,未用现址内容填补。')
    return '\n'.join(lines) + '\n'


def export_collection(store, date, out_dir):
    """导出 date 的交付清单到 out_dir,返回输出目录 Path。"""
    manifest = store.load_collection(date)
    out = Path(out_dir)
    files = out / 'files'
    files.mkdir(parents=True, exist_ok=True)
    lines = ['# 离线资料包 %s' % manifest['date'], '',
             '种子: %s' % manifest['seed'],
             '收集时刻: %s' % manifest['collected_at'],
             '来源: %s' % manifest['source'], '',
             '## 条目']
    for entry in manifest['entries']:
        rel = _safe_path(entry['url'])
        capture = entry.get('capture') or {}
        if entry['status'] == 'ok' and entry.get('bytes'):
            target = files / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(store.read_object(entry['bytes']['digest']))
            local = str(rel)
        elif entry['role'] != 'decorative':
            target = files / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            note = target.with_name(target.name + '.missing.txt')
            note.write_text(_missing_note(entry), encoding='utf-8')
            local = str(rel) + '.missing.txt'
        else:
            local = '(装饰资源,无本地文件)'
        lines.append('- [%s] %s' % (entry['role'], entry['url']))
        lines.append('  状态: %s;捕获: %s @ %s;本地: %s'
                     % (entry['status'], capture.get('id', '-'),
                        capture.get('at', '-'), local))
        if entry.get('bytes'):
            data = entry['bytes']
            lines.append('  字节: %s(%d 字节,经捕获 %s @ %s)'
                         % (data['digest'], data['size'],
                            data['via_capture'], data.get('via_at')))
        provenance = entry.get('provenance') or {}
        lines.append('  来路: %s%s' % (
            provenance.get('via', '?'),
            ' 来自条目 ' + provenance['from'] if provenance.get('from') else ''))
    lines += ['', '## 缺口']
    body = manifest['gaps']['body']
    if not body:
        lines.append('正文无缺口。')
    for gap in body:
        detail = '- 正文缺口: %s(%s)' % (gap['url'], gap['status'])
        if gap.get('missing_capture'):
            detail += ';缺失捕获 ' + gap['missing_capture']
        if gap.get('break_at'):
            detail += ';断在 ' + gap['break_at']
        lines.append(detail)
    for gap in manifest['gaps']['decorative']:
        lines.append('- 装饰资源缺失(不影响正文): %s(%s)'
                     % (gap['url'], gap['status']))
    lines += ['', '缺失项保持缺失,未用现址内容填补。']
    (out / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return out
