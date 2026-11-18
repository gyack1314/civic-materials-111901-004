# 城市低碳网页历史副本的关联资源采集

这是围绕城市低碳公开资料的本地研发项目。当前内容提供授权合成来源、资料、来源契约和资料收集端；来源不会替收集端作身份、覆盖或交付判断。

## 运行来源

使用 Python 3.11 或 3.12，先执行 python -m pip install -r requirements.txt。

启动命令：python -m source.server --port 8765。浏览器或 HTTP 客户端访问 http://127.0.0.1:8765。接口和资料定义见 docs/source-contract.md。

## 收集资料

collector 包按研究者选定的历史日期，从本地来源收集种子页及从页面发现的关联资料，留下原始网址、捕获时刻、实际字节与引用来路；不连接真实站点，不用现址内容填补缺口。

```bash
python -m collector --store store collect --date 2025-06-01   # 按截止日期收集
python -m collector --store store export --date 2025-06-01 --out out/2025-06-01  # 离线领取
python -m collector --store store diff 2023-06-01 2025-06-01  # 比较两次交付
python -m collector --store store fetch --capture F1          # 独立补收捕获
```

选择规则、保存布局、状态含义与离线包结构见 docs/collector.md。

## 检查来源与收集端

执行 python -m unittest discover -s tests -v。这些检查验证本地来源的真实响应与素材可读性，并核对收集端确实经过存档目录查询与捕获读取、遵守截止日与册别规则。

## 容器

执行 docker build -t climate-web-archive .，然后 docker run --rm -p 8765:8765 climate-web-archive。测试可用 docker run --rm climate-web-archive python -m unittest discover -s tests -v。

source 提供来源服务，collector 是资料收集端，data 保存合成原始资料，tests 核对来源行为与收集端规则；docs 记录字段、交互契约与收集端说明。不要将运行日志、凭据或采集数据提交到版本库。
