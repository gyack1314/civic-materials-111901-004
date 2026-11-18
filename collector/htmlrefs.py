"""解析存档页面中的引用:正文附件、续页、装饰图与 HTML base。

关联资料只能从来源页面里发现,不预设地址表。
rel=document 是正文附件(data-edition 为页面声明的册别),
rel=next 是正文续页,其余 img 为装饰资源。
"""
from html.parser import HTMLParser


class PageRefs:
    def __init__(self):
        self.base = None
        self.documents = []  # [{'href':..., 'edition':...}]
        self.nexts = []      # [href]
        self.images = []     # [src]


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = PageRefs()

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'base' and self.refs.base is None and a.get('href'):
            self.refs.base = a['href']
        elif tag == 'a':
            rel = set(a.get('rel', '').lower().split())
            if 'document' in rel and a.get('href'):
                self.refs.documents.append(
                    {'href': a['href'], 'edition': a.get('data-edition') or None})
            if 'next' in rel and a.get('href'):
                self.refs.nexts.append(a['href'])
        elif tag == 'img' and a.get('src'):
            self.refs.images.append(a['src'])


def parse_page(html_text):
    """从页面正文提取引用。html_text 为已解码的页面文本。"""
    parser = _Parser()
    parser.feed(html_text)
    parser.close()
    return parser.refs
