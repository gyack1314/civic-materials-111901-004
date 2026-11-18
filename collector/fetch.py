"""独立补收单条捕获:只写入保存目录,不改动任何已交付的日期清单。"""
import json
from datetime import datetime, timezone


class FetchError(Exception):
    """补收中止(内容缺失、成环或目标不是内容捕获)。"""


def fetch_capture(client, store, capture_id):
    """读取捕获(含沿用链)并把字节与记录存入保存目录。

    返回保存的记录列表。沿用(revisit)记录只保存引用关系,
    字节记录在被沿用的内容捕获上;成环或内容缺失时抛出 FetchError。
    """
    records = []
    seen = set()
    current = capture_id
    while True:
        if current in seen:
            raise FetchError('沿用引用成环于 ' + current)
        seen.add(current)
        resp, _ = client.capture(current)
        if resp.status == 404:
            raise FetchError('捕获 %s 内容缺失' % current)
        if resp.status in (301, 302, 303, 307, 308):
            raise FetchError('捕获 %s 是重定向,补收请针对内容捕获' % current)
        record = {'id': current,
                  'url': resp.headers.get('x-original-url'),
                  'at': resp.headers.get('x-captured-at'),
                  'fetched_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  'source': client.base}
        data = None
        if 'json' in resp.headers.get('content-type', ''):
            try:
                data = json.loads(resp.body.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                data = None
        if data and data.get('record_type') == 'revisit':
            record['kind'] = 'revisit'
            record['ref'] = data.get('ref')
            records.append(record)
            current = data.get('ref') or ''
            if not current:
                raise FetchError('捕获 %s 的沿用引用为空' % record['id'])
            continue
        record['kind'] = 'content'
        record['digest'] = store.put_object(resp.body)
        record['size'] = len(resp.body)
        records.append(record)
        break
    for record in records:
        store.save_capture_record(record['id'], record)
    return records
