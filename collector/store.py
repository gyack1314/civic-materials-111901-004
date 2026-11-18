"""采集保存目录:字节对象、按日期交付的清单、独立补收记录。

布局:
  objects/<sha256>                 相同内容的字节只存一份,各次选择共享
  collections/<日期>/manifest.json 该日期交付的清单,写定后不随补收改变
  captures/<捕获编号>.json          独立补收的记录,不改动已交付清单
"""
import hashlib
import json
from pathlib import Path


class Store:
    def __init__(self, root):
        self.root = Path(root)

    # -- 字节对象:相同内容只存一份,但各次历史选择各自保留来路 --
    def put_object(self, data):
        digest = hashlib.sha256(data).hexdigest()
        path = self.root / 'objects' / digest
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + '.tmp')
            tmp.write_bytes(data)
            tmp.replace(path)
        return 'sha256:' + digest

    def _object_path(self, digest):
        return self.root / 'objects' / digest.split(':', 1)[1]

    def read_object(self, digest):
        return self._object_path(digest).read_bytes()

    def has_object(self, digest):
        return self._object_path(digest).exists()

    # -- 按日期交付的清单 --
    def save_collection(self, date, manifest, force=False):
        directory = self.root / 'collections' / date
        path = directory / 'manifest.json'
        if path.exists() and not force:
            raise FileExistsError(
                '日期 %s 的清单已交付;确需重做请显式使用 --force' % date)
        directory.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        return path

    def load_collection(self, date):
        path = self.root / 'collections' / date / 'manifest.json'
        if not path.exists():
            raise FileNotFoundError('没有日期 %s 的交付清单' % date)
        return json.loads(path.read_text(encoding='utf-8'))

    def list_collections(self):
        directory = self.root / 'collections'
        if not directory.exists():
            return []
        return sorted(p.name for p in directory.iterdir()
                      if (p / 'manifest.json').exists())

    # -- 捕获补收记录:独立保存,不改写任何已交付清单 --
    def save_capture_record(self, capture_id, record):
        directory = self.root / 'captures'
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (capture_id + '.json')
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        return path

    def load_capture_record(self, capture_id):
        path = self.root / 'captures' / (capture_id + '.json')
        if not path.exists():
            raise FileNotFoundError('本地没有捕获 %s 的补收记录' % capture_id)
        return json.loads(path.read_text(encoding='utf-8'))

    def list_capture_records(self):
        directory = self.root / 'captures'
        if not directory.exists():
            return []
        return sorted(p.stem for p in directory.glob('*.json'))
