# 本地来源契约

GET /captures?url=原始网址 返回全部捕获元信息，本服务是合成网页存档协议，不声称实现某第三方存档产品。at 为 ISO 日期，截止比较按日期包含当日。GET /capture/{id} 读取该记录，返回 X-Original-URL、X-Captured-At、X-Capture-Id；重定向的 Location 按原始 URL 解释。
kind=revisit 的响应是 ref 捕获编号，表示沿用该捕获的内容，不能把 JSON 作为正文。/replay/{日期}/{原始绝对URL} 是正文链接的包装形式，查询目录时应使用其原始 URL。HTML rel=document 表示正文附件，rel=next 表示正文续页，data-edition 是页面声明册别；其他图片为装饰资源。
phase=1 模拟目录仍在而 F1 内容丢失。H1 和 H2 为不同时刻同页，F3 为目录上同地址不同册别。所有 .invalid 地址只作为来源标识，实际字节只可由本地 /capture 获取。

演练来源由 Python 标准库 HTTP 服务启动，默认端口 8765。GET /health 可查询来源时间与阶段；POST /__admin/advance 接收 seconds、phase 推进本地情形；GET /__admin/log 回查实际请求。这些控制只供操作员调试来源，不能替代产品从正常入口取得资料。来源进程重启会清空其演练状态；采集端自己的保存目录由产品独立管理。
