# 采集端说明:按历史日期收集城市低碳资料

collector 包是资料收集端。研究者选定一个历史日期后,它从本地网页存档来源
收集种子页及从页面发现的关联资料(正文附件、续页、装饰资源),留下原始网址、
捕获时刻、实际字节与引用来路,供离线回查。字节只来自来源的 /capture/{id},
不连接任何真实站点,也不用现址内容填补缺口。

## 命令

```bash
# 启动来源(另一个终端)
python -m source.server --port 8765

# 按截止日期收集(含当日);关联资料从来源页面发现,不预设地址表
python -m collector --store store collect --date 2023-06-01
python -m collector --store store collect --date 2025-06-01

# 离线领取:只读本地保存目录,不访问网络
python -m collector --store store export --date 2025-06-01 --out out/2025-06-01

# 比较两个日期的交付,说明差别来自捕获选择、册别还是原件缺失
python -m collector --store store diff 2023-06-01 2025-06-01

# 独立补收单条捕获;只写入保存目录,不改写任何已交付清单
python -m collector --store store fetch --capture F1

# 查看
python -m collector --store store list
python -m collector --store store show --date 2025-06-01
```

`--source` 默认 http://127.0.0.1:8765,`--seed` 默认 https://city.invalid/policy。
已交付的同日期清单不可重做,确需覆盖要显式加 `--force`。

## 选择规则(不变量)

- 所有采用的捕获都不晚于截止日(含当日),交付前由 validate_manifest 自检。
- 页面用 data-edition 声明册别时,正文附件只在该册别的捕获里挑选;
  另一册别即使更晚被抓到也不替换(如 2025-06-01 的附件选 F2 而非 F3)。
- /replay/{日期}/{原始绝对URL} 是包装形式,还原为原始网址后才查目录;
  包装路径不是新的资料身份。相对地址按该次响应的 HTML base 解析,
  重定向 Location 按该次响应的原始网址解析。
- kind=revisit 的记录只有引用,字节读自被沿用的捕获;沿用链成环即停止。
- 重定向成环即停止,并在清单里指出断在哪里(break_at)。
- 目录仍在而内容缺失(/capture 返回 404)时保留事实:选中的捕获编号与
  缺失的捕获编号都写入清单。

## 保存目录布局

```
store/
  objects/<sha256>                 相同内容的字节只存一份,各次选择共享
  collections/<日期>/manifest.json 该日期交付的清单,写定后不随补收改变
  captures/<捕获编号>.json          独立补收的记录
```

清单里每个条目含:role(page/document/next/decorative)、原始网址、状态、
选中的捕获(id/at/kind/edition)、字节(digest/size/提供字节的捕获)、
解析链与沿用链、断点、缺失捕获、引用来路(via/from),以及实际经过的
目录查询与捕获读取路径(trace)。相同内容的字节在 objects 里共享,
但各次日期的清单各自保留完整来路。

## 状态含义

- ok:已取得字节。
- no-capture:截止日前目录中没有该网址的捕获。
- edition-not-archived:声明册别在截止日前没有捕获(其他册别不顶替)。
- missing-content:目录仍在但捕获内容缺失,missing_capture 指出编号。
- redirect-loop / redirect-broken:转址成环或无 Location,break_at 指出断点。
- revisit-loop / revisit-broken:沿用引用成环或为空。

装饰资源(img)缺失记入 gaps.decorative,不与正文断页混为一谈;
其余角色的非 ok 状态都是正文缺口(gaps.body),允许带缺口交付。

## 离线资料包

export 只读本地保存目录,写出:

```
out/
  INDEX.md                 条目、字节、来路与缺口的可读说明
  manifest.json            交付清单原样副本
  files/<主机>/<路径>       ok 条目的原始字节(不改写、不重链)
  files/<路径>.missing.txt  正文缺口的说明(装饰缺失只在 INDEX 里注明)
```

## 检查

`python -m unittest discover -s tests -v` 中 test_collector 一组直接核对
来源的请求日志:收集确实经过 /captures 目录查询与 /capture 读取、先读页面
才发现关联资料、截止日后的捕获未被读取、包装路径未进入任何请求。
