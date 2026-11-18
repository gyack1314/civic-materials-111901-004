"""采集端行为检查:真实经过本地来源的目录查询与捕获读取。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.cli import main as cli_main
from collector.client import SourceClient
from collector.collect import Collector, validate_manifest
from collector.diff import diff_collections
from collector.export import export_collection
from collector.fetch import fetch_capture
from collector.htmlrefs import parse_page
from collector.links import resolve_href
from collector.select import select_capture
from collector.store import Store
from source.server import running_source

SEED = 'https://city.invalid/policy'
DOC = 'https://city.invalid/docs/2023.txt'


def collect(base, store, date, seed=SEED):
    return Collector(SourceClient(base), store, date, seed).run()


def log_paths(source):
    return [r['path'] for r in source.log]


def by_role(manifest, role):
    return next(e for e in manifest['entries'] if e['role'] == role)


class Collect2023(unittest.TestCase):
    def test_cutoff_selection_and_real_archive_reads(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2023-06-01')
            self.assertEqual(validate_manifest(manifest), [])

            page = by_role(manifest, 'page')
            self.assertEqual(page['capture']['id'], 'H1')
            self.assertEqual(page['status'], 'ok')

            doc = by_role(manifest, 'document')
            self.assertEqual(doc['capture']['id'], 'F1')
            self.assertEqual(doc['edition_declared'], '2023')
            data = store.read_object(doc['bytes']['digest'])
            self.assertEqual(data.decode(), '历史合成原件 2023')

            paths = log_paths(source)
            # 实际经过目录查询与捕获读取,且目录查询用的是原始网址
            self.assertIn('/captures?url=https%3A%2F%2Fcity.invalid%2Fpolicy', paths)
            self.assertIn('/captures?url=https%3A%2F%2Fcity.invalid%2Fdocs%2F2023.txt', paths)
            self.assertIn('/capture/H1', paths)
            self.assertIn('/capture/F1', paths)
            # 截止日之后的捕获一律不得读取
            for late in ('/capture/H2', '/capture/F2', '/capture/F3'):
                self.assertNotIn(late, paths)
            # 包装路径不是资料身份,不进入任何请求
            for path in paths:
                self.assertNotIn('/replay/', path)

    def test_discovery_comes_from_page_not_a_table(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            collect(base, store, '2023-06-01')
            paths = log_paths(source)
            read_page = paths.index('/capture/H1')
            query_doc = paths.index(
                '/captures?url=https%3A%2F%2Fcity.invalid%2Fdocs%2F2023.txt')
            query_next = paths.index(
                '/captures?url=https%3A%2F%2Fcity.invalid%2Fnext')
            # 先读到页面字节,才发现并查询附件与续页
            self.assertLess(read_page, query_doc)
            self.assertLess(read_page, query_next)


class Collect2025(unittest.TestCase):
    def test_declared_edition_is_not_replaced_by_later_one(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2025-06-01')
            self.assertEqual(validate_manifest(manifest), [])

            page = by_role(manifest, 'page')
            self.assertEqual(page['capture']['id'], 'H2')

            doc = by_role(manifest, 'document')
            # F3(2025 册)虽在截止日前且更近,但页面声明 2023 册,不得替换
            self.assertEqual(doc['capture']['id'], 'F2')
            self.assertEqual(doc['capture'].get('edition'), '2023')
            self.assertEqual(doc['status'], 'ok')
            # 沿用记录只有引用,字节来自被沿用的 F1
            self.assertEqual(doc['bytes']['via_capture'], 'F1')
            self.assertEqual(doc['revisit_chain'], [{'capture': 'F2', 'ref': 'F1'}])
            self.assertEqual(store.read_object(doc['bytes']['digest']).decode(),
                             '历史合成原件 2023')
            paths = log_paths(source)
            self.assertIn('/capture/F2', paths)
            self.assertIn('/capture/F1', paths)
            self.assertNotIn('/capture/F3', paths)

    def test_shared_bytes_keep_separate_provenance(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            m_old = collect(base, store, '2023-06-01')
            m_new = collect(base, store, '2025-06-01')
            doc_old = by_role(m_old, 'document')
            doc_new = by_role(m_new, 'document')
            # 相同内容共享一份字节
            self.assertEqual(doc_old['bytes']['digest'], doc_new['bytes']['digest'])
            # 但两次历史选择各自的来路都在
            self.assertEqual(doc_old['capture']['id'], 'F1')
            self.assertEqual(doc_new['capture']['id'], 'F2')
            self.assertEqual(doc_old['provenance']['via'], 'rel=document')
            self.assertEqual(doc_new['provenance']['from'], 'r1')


class RedirectAndDecorative(unittest.TestCase):
    def test_redirect_loop_stops_and_points_out_break(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2023-06-01')
            nxt = by_role(manifest, 'next')
            self.assertEqual(nxt['status'], 'redirect-loop')
            self.assertEqual(nxt['break_at'], 'https://city.invalid/next')
            chain = [(s['capture'], s['location']) for s in nxt['chain']]
            self.assertEqual(chain, [
                ('L1', 'https://city.invalid/loop'),
                ('L2', 'https://city.invalid/next'),
            ])
            # 断链是正文缺口,且没有继续空转读取
            self.assertEqual(log_paths(source).count('/capture/L1'), 1)
            body_urls = [g['url'] for g in manifest['gaps']['body']]
            self.assertIn('https://city.invalid/next', body_urls)

    def test_decorative_missing_is_not_a_body_gap(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2023-06-01')
            deco = by_role(manifest, 'decorative')
            self.assertEqual(deco['url'], 'https://city.invalid/docs/decor.png')
            self.assertEqual(deco['status'], 'no-capture')
            self.assertEqual([g['id'] for g in manifest['gaps']['decorative']],
                             [deco['id']])
            body_ids = [g['id'] for g in manifest['gaps']['body']]
            self.assertNotIn(deco['id'], body_ids)


class MissingContent(unittest.TestCase):
    def test_directory_alive_but_content_gone_is_recorded(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            from tests.test_source import SourceContract
            contract = SourceContract()
            contract.post(base + '/__admin/advance', {'phase': 1})
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2025-06-01')
            doc = by_role(manifest, 'document')
            # 目录选择 F2 的事实保留,其沿用的 F1 内容缺失也保留
            self.assertEqual(doc['capture']['id'], 'F2')
            self.assertEqual(doc['status'], 'missing-content')
            self.assertEqual(doc['missing_capture'], 'F1')
            gap = next(g for g in manifest['gaps']['body'] if g['id'] == doc['id'])
            self.assertEqual(gap['missing_capture'], 'F1')

            store.save_collection('2025-06-01', manifest)
            out = Path(tmp) / 'out'
            export_collection(store, '2025-06-01', out)
            # 缺口不被现址内容悄悄填上
            self.assertFalse((out / 'files' / 'city.invalid' / 'docs' / '2023.txt').exists())
            note = out / 'files' / 'city.invalid' / 'docs' / '2023.txt.missing.txt'
            self.assertTrue(note.exists())
            self.assertIn('F1', note.read_text(encoding='utf-8'))


class ExportOffline(unittest.TestCase):
    def test_export_writes_original_bytes_and_gap_notes(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2025-06-01')
            store.save_collection('2025-06-01', manifest)
            out = Path(tmp) / 'out'
            export_collection(store, '2025-06-01', out)

            page = by_role(manifest, 'page')
            page_file = out / 'files' / 'city.invalid' / 'policy'
            self.assertEqual(page_file.read_bytes(),
                             store.read_object(page['bytes']['digest']))
            doc_file = out / 'files' / 'city.invalid' / 'docs' / '2023.txt'
            self.assertEqual(doc_file.read_text(encoding='utf-8'), '历史合成原件 2023')
            index = (out / 'INDEX.md').read_text(encoding='utf-8')
            self.assertIn('redirect-loop', index)
            self.assertIn('装饰资源缺失', index)
            self.assertTrue((out / 'manifest.json').exists())


class FetchRecollection(unittest.TestCase):
    def test_fetch_does_not_change_delivered_collection(self):
        with running_source() as (base, source), tempfile.TemporaryDirectory() as tmp:
            from tests.test_source import SourceContract
            contract = SourceContract()
            contract.post(base + '/__admin/advance', {'phase': 1})
            store = Store(Path(tmp) / 'store')
            manifest = collect(base, store, '2023-06-01')
            store.save_collection('2023-06-01', manifest)
            self.assertEqual(by_role(manifest, 'document')['status'], 'missing-content')

            contract.post(base + '/__admin/advance', {'phase': 0})
            records = fetch_capture(SourceClient(base), store, 'F1')
            self.assertEqual(records[0]['kind'], 'content')
            self.assertTrue(store.has_object(records[0]['digest']))

            # 已交付的日期选择不受补收影响
            delivered = store.load_collection('2023-06-01')
            self.assertEqual(by_role(delivered, 'document')['status'],
                             'missing-content')

    def test_fetch_revisit_stores_reference_and_bytes(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            records = fetch_capture(SourceClient(base), store, 'F2')
            kinds = {r['id']: r['kind'] for r in records}
            self.assertEqual(kinds, {'F2': 'revisit', 'F1': 'content'})
            revisit = store.load_capture_record('F2')
            self.assertEqual(revisit['ref'], 'F1')
            content = store.load_capture_record('F1')
            self.assertEqual(store.read_object(content['digest']).decode(),
                             '历史合成原件 2023')


class DiffReport(unittest.TestCase):
    def test_difference_is_attributed(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'store')
            store.save_collection('2023-06-01', collect(base, store, '2023-06-01'))
            store.save_collection('2025-06-01', collect(base, store, '2025-06-01'))
            report = diff_collections(store.load_collection('2023-06-01'),
                                      store.load_collection('2025-06-01'))
            rows = {(r['role'], r['url']): r for r in report['rows']}
            page = rows[('page', SEED)]
            self.assertIn('捕获选择不同', page['kinds'])
            doc = rows[('document', DOC)]
            self.assertIn('捕获选择不同', doc['kinds'])
            # 同一册别同一内容:差别只能来自捕获选择,不是册别或字节
            self.assertNotIn('册别不同', doc['kinds'])
            self.assertNotIn('字节不同', doc['kinds'])
            for row in report['rows']:
                self.assertNotIn('原件缺失变化', row['kinds'])


class Units(unittest.TestCase):
    def test_select_capture_rules(self):
        caps = [
            {'id': 'a', 'at': '2023-05-01', 'edition': '2023'},
            {'id': 'b', 'at': '2024-01-01', 'edition': '2023'},
            {'id': 'c', 'at': '2025-01-01', 'edition': '2025'},
        ]
        chosen, _ = select_capture(caps, '2024-06-01', edition='2023')
        self.assertEqual(chosen['id'], 'b')
        chosen, _ = select_capture(caps, '2023-05-01', edition='2023')
        self.assertEqual(chosen['id'], 'a')  # 截止含当日
        chosen, err = select_capture(caps, '2022-01-01')
        self.assertIsNone(chosen)
        self.assertEqual(err['reason'], 'no-capture')
        chosen, err = select_capture(caps, '2024-06-01', edition='2024')
        self.assertIsNone(chosen)
        self.assertEqual(err['reason'], 'edition-not-archived')
        self.assertEqual(err['available_editions'], ['2023', '2025'])

    def test_links_resolve_to_original_urls(self):
        self.assertEqual(
            resolve_href('/replay/2023/https://city.invalid/docs/2023.txt',
                         'https://city.invalid/docs/'),
            DOC)
        self.assertEqual(resolve_href('decor.png', 'https://city.invalid/docs/'),
                         'https://city.invalid/docs/decor.png')
        self.assertEqual(resolve_href('/loop', 'https://city.invalid/next'),
                         'https://city.invalid/loop')

    def test_parser_extracts_declared_references(self):
        refs = parse_page(
            '<base href="https://other.invalid/lib/">'
            '<a rel="document" data-edition="2021" href="/replay/2021/https://other.invalid/lib/a.txt">a</a>'
            '<a rel="next" href="p2">n</a><img src="i.png">')
        self.assertEqual(refs.base, 'https://other.invalid/lib/')
        self.assertEqual(refs.documents,
                         [{'href': '/replay/2021/https://other.invalid/lib/a.txt',
                           'edition': '2021'}])
        self.assertEqual(refs.nexts, ['p2'])
        self.assertEqual(refs.images, ['i.png'])

    def test_validate_manifest_rejects_late_capture(self):
        bad = {'date': '2023-06-01',
               'entries': [{'id': 'r1', 'role': 'page',
                            'capture': {'id': 'H2', 'at': '2025-06-01'},
                            'chain': [], 'bytes': None}]}
        self.assertTrue(validate_manifest(bad))


class CliEndToEnd(unittest.TestCase):
    def test_collect_export_diff_fetch(self):
        with running_source() as (base, _), tempfile.TemporaryDirectory() as tmp:
            store = str(Path(tmp) / 'store')
            out = str(Path(tmp) / 'out')
            rc = cli_main(['--source', base, '--store', store,
                           'collect', '--date', '2025-06-01'])
            self.assertEqual(rc, 0)
            rc = cli_main(['--source', base, '--store', store,
                           'collect', '--date', '2023-06-01'])
            self.assertEqual(rc, 0)
            # 已交付清单默认不可重做
            rc = cli_main(['--source', base, '--store', store,
                           'collect', '--date', '2023-06-01'])
            self.assertEqual(rc, 1)
            self.assertEqual(cli_main(['--store', store, 'export',
                                       '--date', '2025-06-01', '--out', out]), 0)
            self.assertEqual(cli_main(['--store', store, 'diff',
                                       '2023-06-01', '2025-06-01']), 0)
            # 补收另一册别,不改变已交付的选择
            self.assertEqual(cli_main(['--source', base, '--store', store,
                                       'fetch', '--capture', 'F3']), 0)
            delivered = json.loads(
                (Path(store) / 'collections' / '2025-06-01' / 'manifest.json')
                .read_text(encoding='utf-8'))
            doc = next(e for e in delivered['entries'] if e['role'] == 'document')
            self.assertEqual(doc['capture']['id'], 'F2')
            self.assertEqual(cli_main(['--store', store, 'list']), 0)
            self.assertEqual(cli_main(['--store', store, 'show',
                                       '--date', '2025-06-01']), 0)


if __name__ == '__main__':
    unittest.main()
