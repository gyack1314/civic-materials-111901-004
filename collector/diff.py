"""比较两个日期的交付清单,说明差别来自页面选择、册别还是原件缺失。"""


def _key(entry):
    return (entry['role'], entry['url'])


def diff_collections(manifest_a, manifest_b):
    """返回结构化差别报告;manifest_a 为较早日期,manifest_b 为较晚日期。"""
    entries_a = {_key(e): e for e in manifest_a['entries']}
    entries_b = {_key(e): e for e in manifest_b['entries']}
    rows = []
    for key in sorted(set(entries_a) | set(entries_b)):
        role, url = key
        former, latter = entries_a.get(key), entries_b.get(key)
        if former is None:
            rows.append({'role': role, 'url': url, 'kinds': ['仅后者涉及'],
                         'detail': '前一日期未发现该资源(发现面随页面选择变化)'})
            continue
        if latter is None:
            rows.append({'role': role, 'url': url, 'kinds': ['仅前者涉及'],
                         'detail': '后一日期未发现该资源(发现面随页面选择变化)'})
            continue
        kinds, details = [], []
        cap_a, cap_b = former.get('capture') or {}, latter.get('capture') or {}
        if cap_a.get('id') != cap_b.get('id'):
            if (cap_a.get('edition') or None) != (cap_b.get('edition') or None):
                kinds.append('册别不同')
                details.append('册别: %s(%s) -> %s(%s)' % (
                    cap_a.get('id'), cap_a.get('edition'),
                    cap_b.get('id'), cap_b.get('edition')))
            else:
                kinds.append('捕获选择不同')
                details.append('捕获: %s @ %s -> %s @ %s' % (
                    cap_a.get('id'), cap_a.get('at'),
                    cap_b.get('id'), cap_b.get('at')))
        if former['status'] != latter['status']:
            if 'missing-content' in (former['status'], latter['status']):
                kinds.append('原件缺失变化')
            else:
                kinds.append('状态不同')
            details.append('状态: %s -> %s' % (former['status'], latter['status']))
        digest_a = (former.get('bytes') or {}).get('digest')
        digest_b = (latter.get('bytes') or {}).get('digest')
        if digest_a != digest_b:
            kinds.append('字节不同')
            details.append('字节: %s -> %s' % (digest_a or '无', digest_b or '无'))
        rows.append({'role': role, 'url': url,
                     'kinds': kinds or ['一致'],
                     'detail': ';'.join(details)})
    return {'from': manifest_a['date'], 'to': manifest_b['date'], 'rows': rows}


def render_diff(report):
    lines = ['清单比较: %s -> %s' % (report['from'], report['to'])]
    changed = [row for row in report['rows'] if row['kinds'] != ['一致']]
    for row in changed:
        lines.append('- [%s] %s' % (row['role'], row['url']))
        lines.append('  差别: %s' % '、'.join(row['kinds']))
        if row['detail']:
            lines.append('  ' + row['detail'])
    lines.append('一致 %d 项,有差别 %d 项。'
                 % (len(report['rows']) - len(changed), len(changed)))
    return '\n'.join(lines)
