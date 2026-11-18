"""命令行入口:收集、补收、离线领取、比较与查看。

用法示例:
  python -m collector collect --date 2025-06-01 --store store
  python -m collector export --date 2025-06-01 --store store --out out/2025-06-01
  python -m collector diff 2023-06-01 2025-06-01 --store store
  python -m collector fetch --capture F1 --store store
"""
import argparse
from datetime import datetime
import sys

from .client import SourceClient, SourceError
from .collect import Collector, validate_manifest
from .diff import diff_collections, render_diff
from .export import export_collection
from .fetch import FetchError, fetch_capture
from .store import Store

DEFAULT_SOURCE = 'http://127.0.0.1:8765'
DEFAULT_SEED = 'https://city.invalid/policy'


def _check_date(text):
    try:
        datetime.strptime(text, '%Y-%m-%d')
    except ValueError:
        raise argparse.ArgumentTypeError('日期须为 YYYY-MM-DD: ' + text)
    return text


def cmd_collect(args):
    client = SourceClient(args.source)
    store = Store(args.store)
    collector = Collector(client, store, args.date, args.seed,
                          max_resources=args.max_resources)
    manifest = collector.run()
    problems = validate_manifest(manifest)
    if problems:
        for problem in problems:
            print('清单自检未通过: ' + problem, file=sys.stderr)
        return 1
    try:
        path = store.save_collection(args.date, manifest, force=args.force)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    ok = sum(1 for e in manifest['entries'] if e['status'] == 'ok')
    body = manifest['gaps']['body']
    decorative = manifest['gaps']['decorative']
    print('已交付日期 %s 的清单: %s' % (args.date, path))
    print('条目 %d(成功 %d);正文缺口 %d,装饰缺失 %d'
          % (len(manifest['entries']), ok, len(body), len(decorative)))
    for gap in body:
        detail = '  正文缺口: %s(%s)' % (gap['url'], gap['status'])
        if gap.get('missing_capture'):
            detail += ';缺失捕获 ' + gap['missing_capture']
        if gap.get('break_at'):
            detail += ';断在 ' + gap['break_at']
        print(detail)
    for gap in decorative:
        print('  装饰缺失(不影响正文): %s(%s)' % (gap['url'], gap['status']))
    return 0


def cmd_fetch(args):
    client = SourceClient(args.source)
    store = Store(args.store)
    try:
        records = fetch_capture(client, store, args.capture)
    except FetchError as exc:
        print('补收未完成: %s' % exc, file=sys.stderr)
        return 1
    for record in records:
        if record['kind'] == 'revisit':
            print('已保存沿用记录 %s(引用 %s)' % (record['id'], record['ref']))
        else:
            print('已保存捕获 %s 的字节 %s(%d 字节)'
                  % (record['id'], record['digest'], record['size']))
    print('补收只写入保存目录,不改写任何已交付的日期清单。')
    return 0


def cmd_export(args):
    store = Store(args.store)
    try:
        out = export_collection(store, args.date, args.out)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print('离线资料包已写出: %s(入口 INDEX.md,清单 manifest.json)' % out)
    return 0


def cmd_diff(args):
    store = Store(args.store)
    try:
        manifest_a = store.load_collection(args.former)
        manifest_b = store.load_collection(args.latter)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(render_diff(diff_collections(manifest_a, manifest_b)))
    return 0


def cmd_list(args):
    store = Store(args.store)
    dates = store.list_collections()
    print('已交付日期: %s' % ('、'.join(dates) if dates else '(无)'))
    records = store.list_capture_records()
    print('补收记录: %s' % ('、'.join(records) if records else '(无)'))
    return 0


def cmd_show(args):
    store = Store(args.store)
    try:
        manifest = store.load_collection(args.date)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print('日期 %s;种子 %s;收集于 %s'
          % (manifest['date'], manifest['seed'], manifest['collected_at']))
    for entry in manifest['entries']:
        capture = entry.get('capture') or {}
        print('- [%s] %s' % (entry['role'], entry['url']))
        print('  状态 %s;捕获 %s @ %s'
              % (entry['status'], capture.get('id', '-'), capture.get('at', '-')))
    body = manifest['gaps']['body']
    print('正文缺口 %d 项,装饰缺失 %d 项。'
          % (len(body), len(manifest['gaps']['decorative'])))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='python -m collector',
        description='按历史日期从本地存档来源收集城市低碳资料')
    parser.add_argument('--source', default=DEFAULT_SOURCE,
                        help='本地资料来源地址(默认 %(default)s)')
    parser.add_argument('--store', default='store',
                        help='采集保存目录(默认 %(default)s)')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('collect', help='按截止日期收集种子页及关联资料')
    p.add_argument('--date', required=True, type=_check_date,
                   help='截止日期 YYYY-MM-DD(含当日)')
    p.add_argument('--seed', default=DEFAULT_SEED,
                   help='研究者选定的种子页原始网址(默认 %(default)s)')
    p.add_argument('--max-resources', type=int, default=64,
                   help='单次收集的资源上限(默认 %(default)s)')
    p.add_argument('--force', action='store_true',
                   help='允许重做并覆盖已交付的同日期清单')
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser('fetch', help='独立补收单条捕获,不改写已交付清单')
    p.add_argument('--capture', required=True, help='捕获编号,如 F1')
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser('export', help='把某日期的交付清单物化为离线目录')
    p.add_argument('--date', required=True, type=_check_date)
    p.add_argument('--out', required=True, help='输出目录')
    p.set_defaults(func=cmd_export)

    p = sub.add_parser('diff', help='比较两个日期的交付清单')
    p.add_argument('former', type=_check_date, help='较早日期')
    p.add_argument('latter', type=_check_date, help='较晚日期')
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser('list', help='列出已交付日期与补收记录')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('show', help='查看某日期交付清单的摘要')
    p.add_argument('--date', required=True, type=_check_date)
    p.set_defaults(func=cmd_show)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SourceError as exc:
        print('来源访问失败: %s' % exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
