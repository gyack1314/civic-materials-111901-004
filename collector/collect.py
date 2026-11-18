"""按截止日期收集种子页及其关联资料的存档副本。

不变量:
- 所有采用的捕获都不晚于截止日(含当日);
- 正文声明的册别不会被更晚捕获的其他册别替换;
- 包装路径(/replay/...)还原为原始网址后再查目录,包装不是新的资料身份;
- 字节只来自来源的 /capture/{id};目录仍在而内容缺失时保留事实,不用现址填补;
- 沿用(revisit)与转址成环时停止并指出断在哪里。
"""
import json
from datetime import datetime, timezone

from .htmlrefs import parse_page
from .links import resolve_href
from .select import select_capture

REDIRECT_STATUSES = (301, 302, 303, 307, 308)


class Collector:
    """一次针对某个截止日期的收集。client 只访问本地来源,store 只负责落盘。"""

    def __init__(self, client, store, cutoff, seed, max_resources=64):
        self.client = client
        self.store = store
        self.cutoff = cutoff
        self.seed = seed
        self.max_resources = max_resources
        self.entries = []
        self._counter = 0
        self._seen = set()

    # -- 来源访问,逐条留下实际经过的查询轨迹 --
    def _directory(self, url, trace):
        captures, path = self.client.captures(url)
        trace['directory'].append(path)
        return captures

    def _read(self, capture_id, trace):
        resp, path = self.client.capture(capture_id)
        trace['reads'].append(path)
        return resp

    def _new_entry(self, role, url, provenance, edition=None):
        self._counter += 1
        entry = {
            'id': 'r%d' % self._counter,
            'role': role,                    # page / document / next / decorative
            'url': url,                      # 原始网址(包装路径已还原)
            'edition_declared': edition,     # 页面声明的册别(仅正文附件)
            'status': None,
            'capture': None,                 # 本网址在截止日前选中的捕获
            'bytes': None,                   # 实际字节的 digest 与提供该字节的捕获
            'chain': [],                     # 解析过程中依次读取的捕获(含转址)
            'revisit_chain': [],             # 沿用引用的跟随过程
            'resolved_url': None,            # 转址后最终提供内容的原始网址
            'break_at': None,                # 成环或断链的位置
            'missing_capture': None,         # 目录仍在但内容缺失的捕获编号
            'provenance': provenance,        # 引用来路:从哪个条目、经什么关系发现
            'trace': {'directory': [], 'reads': []},
        }
        self.entries.append(entry)
        return entry

    def run(self):
        queue = [('page', self.seed, {'via': 'seed', 'from': None}, None)]
        while queue and len(self.entries) < self.max_resources:
            role, url, provenance, edition = queue.pop(0)
            key = (role, url, edition)
            if key in self._seen:
                continue
            self._seen.add(key)
            entry = self._new_entry(role, url, provenance, edition)
            queue.extend(self._resolve(entry))
        return self._manifest()

    # -- 单个资源的解析:目录挑选 -> 读取 -> 转址/沿用 -> 字节 --
    def _resolve(self, entry):
        caps = self._directory(entry['url'], entry['trace'])
        edition = entry['edition_declared'] if entry['role'] == 'document' else None
        chosen, err = select_capture(caps, self.cutoff, edition)
        if chosen is None:
            entry['status'] = err['reason']
            entry['selection'] = err
            return []
        entry['capture'] = {k: chosen[k]
                            for k in ('id', 'at', 'kind', 'edition') if k in chosen}
        return self._read_chain(entry, chosen, {entry['url']})

    def _read_chain(self, entry, capture, seen):
        current = capture
        while True:
            resp = self._read(current['id'], entry['trace'])
            step = {'url': current.get('url'), 'capture': current['id'],
                    'at': current.get('at'), 'status': resp.status}
            entry['chain'].append(step)
            if resp.status == 404:
                # 目录仍在而内容缺失:保留事实,不作填补
                entry['status'] = 'missing-content'
                entry['missing_capture'] = current['id']
                return []
            if resp.status in REDIRECT_STATUSES:
                location = resp.headers.get('location')
                original = resp.headers.get('x-original-url') or current.get('url')
                target = resolve_href(location, original) if location else None
                step['location'] = target
                if target is None:
                    entry['status'] = 'redirect-broken'
                    entry['break_at'] = current.get('url')
                    return []
                if target in seen:
                    entry['status'] = 'redirect-loop'
                    entry['break_at'] = target
                    return []
                seen.add(target)
                caps = self._directory(target, entry['trace'])
                nxt, err = select_capture(caps, self.cutoff)
                if nxt is None:
                    entry['status'] = err['reason']
                    entry['break_at'] = target
                    return []
                current = nxt
                continue
            if current.get('url') and current['url'] != entry['url']:
                entry['resolved_url'] = current['url']
            return self._read_body(entry, current, resp, ())

    def _read_body(self, entry, capture, resp, seen_revisit):
        content_type = resp.headers.get('content-type', '')
        body = resp.body
        if 'json' in content_type:
            data = None
            try:
                data = json.loads(body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                data = None
            if data and data.get('record_type') == 'revisit':
                # 沿用先前内容:该记录只有引用,字节要读被沿用的捕获
                ref = data.get('ref')
                entry['revisit_chain'].append({'capture': capture['id'], 'ref': ref})
                if not ref:
                    entry['status'] = 'revisit-broken'
                    entry['break_at'] = capture['id']
                    return []
                if ref in seen_revisit or ref == capture['id']:
                    entry['status'] = 'revisit-loop'
                    entry['break_at'] = ref
                    return []
                ref_resp = self._read(ref, entry['trace'])
                if ref_resp.status == 404:
                    entry['status'] = 'missing-content'
                    entry['missing_capture'] = ref
                    return []
                ref_capture = {'id': ref,
                               'url': ref_resp.headers.get('x-original-url'),
                               'at': ref_resp.headers.get('x-captured-at')}
                return self._read_body(entry, ref_capture, ref_resp,
                                       seen_revisit + (capture['id'],))
        digest = self.store.put_object(body)
        entry['bytes'] = {'digest': digest, 'size': len(body),
                          'via_capture': capture['id'], 'via_at': capture.get('at')}
        entry['status'] = 'ok'
        if entry['role'] in ('page', 'next') and 'html' in content_type:
            return self._discover(entry, body)
        return []

    def _discover(self, entry, body):
        """从页面正文发现关联资料;相对地址按该次响应的 base 解析。"""
        refs = parse_page(body.decode('utf-8', errors='replace'))
        base = resolve_href(refs.base, entry['url']) if refs.base else entry['url']
        found = []
        for doc in refs.documents:
            found.append(('document', resolve_href(doc['href'], base),
                          {'via': 'rel=document', 'from': entry['id']},
                          doc['edition']))
        for href in refs.nexts:
            found.append(('next', resolve_href(href, base),
                          {'via': 'rel=next', 'from': entry['id']}, None))
        for src in refs.images:
            found.append(('decorative', resolve_href(src, base),
                          {'via': 'img', 'from': entry['id']}, None))
        return found

    def _manifest(self):
        body_gaps, decorative_gaps = [], []
        for entry in self.entries:
            if entry['status'] == 'ok':
                continue
            gap = {'id': entry['id'], 'url': entry['url'],
                   'role': entry['role'], 'status': entry['status']}
            for key in ('missing_capture', 'break_at', 'edition_declared'):
                if entry.get(key):
                    gap[key] = entry[key]
            if entry['role'] == 'decorative':
                decorative_gaps.append(gap)
            else:
                body_gaps.append(gap)
        return {
            'format': 1,
            'date': self.cutoff,
            'seed': self.seed,
            'source': self.client.base,
            'collected_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'entries': self.entries,
            'gaps': {'body': body_gaps, 'decorative': decorative_gaps},
        }


def validate_manifest(manifest):
    """交付前自检:任何采用的捕获都不得晚于截止日,册别不得被替换。"""
    problems = []
    date = manifest['date']
    for entry in manifest['entries']:
        capture = entry.get('capture')
        if capture and capture.get('at') and capture['at'] > date:
            problems.append('%s 采用的捕获 %s 晚于截止日'
                            % (entry['id'], capture['id']))
        for step in entry.get('chain', []):
            if step.get('at') and step['at'] > date:
                problems.append('%s 读取的捕获 %s 晚于截止日'
                                % (entry['id'], step['capture']))
        data = entry.get('bytes')
        if data and data.get('via_at') and data['via_at'] > date:
            problems.append('%s 的字节来自 %s,晚于截止日'
                            % (entry['id'], data['via_capture']))
        declared = entry.get('edition_declared')
        if entry['role'] == 'document' and declared and capture:
            if capture.get('edition') not in (None, declared):
                problems.append('%s 声明册别 %s 却采用了 %s'
                                % (entry['id'], declared, capture.get('edition')))
    return problems
