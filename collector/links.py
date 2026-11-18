"""把页面中的链接还原为目录查询用的原始网址。

/replay/{日期}/{原始绝对URL} 只是正文链接的包装形式,不是新的资料身份;
相对地址依赖该次响应的 HTML base,重定向 Location 依赖该次响应的原始网址。
"""
from urllib.parse import urljoin, urlsplit


def unwrap_replay(href):
    """包装路径还原为原始网址;非包装路径返回 None。"""
    if not href:
        return None
    parts = urlsplit(href)
    path = parts.path if (parts.scheme or parts.netloc) else href
    if not path.startswith('/replay/'):
        return None
    rest = path[len('/replay/'):]
    slash = rest.find('/')
    if slash < 0:
        return None
    original = rest[slash + 1:]
    if original.startswith(('http://', 'https://')):
        return original
    return None


def resolve_href(href, base_url):
    """把页面里出现的 href 解析为原始网址(包装路径先还原,相对地址按 base 拼接)。"""
    original = unwrap_replay(href)
    if original:
        return original
    return urljoin(base_url, href)
