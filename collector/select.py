"""按截止日期与册别挑选捕获。

不变量:所有采用的捕获都不得晚于截止日(含当日);
页面明确声明册别时,只在该册别的捕获里挑选,
不允许用另一册别更晚被抓到的记录顶替。
"""


def select_capture(captures, cutoff, edition=None):
    """从某原始网址的目录记录中挑选一条捕获。

    返回 (capture, None);没有可用记录时返回 (None, 原因dict),
    原因 reason 为 'no-capture'(截止日前没有任何捕获)
    或 'edition-not-archived'(声明册别在截止日前没有捕获)。
    """
    before = [c for c in captures if c.get('at', '') <= cutoff]
    if edition is not None:
        matched = [c for c in before if c.get('edition') == edition]
        if not matched:
            seen = sorted({c.get('edition') for c in captures if c.get('edition')})
            return None, {'reason': 'edition-not-archived',
                          'edition': edition,
                          'available_editions': seen,
                          'captures_before_cutoff': len(before)}
        before = matched
    if not before:
        return None, {'reason': 'no-capture', 'edition': edition}
    before.sort(key=lambda c: (c.get('at', ''), str(c.get('id', ''))))
    return before[-1], None
