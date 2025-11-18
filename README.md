# 推特抓取与分析工具（CLI）

面向“推特公司样本”系列数据的命令行工具，支持：数据准备与清洗、账号查找与管理、推文抓取与情绪分析、推文数量查询、批量任务等。

## 环境准备
1) 创建并激活虚拟环境：
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
2) 配置环境变量（建议建立 `.env`）：
```
TWITTER_BEARER_TOKEN=你的TwitterBearerToken
# 是否使用全量历史搜索（需 Academic）
USE_SEARCH_ALL=true
# 速率限制相关（可在界面修改）
RATE_LIMIT_MAX_RETRIES=5
RATE_LIMIT_BASE_DELAY_SECONDS=1.5
RATE_LIMIT_MAX_DELAY_SECONDS=60
REQUESTS_PER_MINUTE=30
```

## 快速开始
查看命令帮助：
```
python -m twitter_crawler.cli --help
```

## 图形界面（Streamlit）
启动：
```
streamlit run app.py
```
功能覆盖七个“扣子”：数据准备、账号查找、推文抓取与情绪、数量查询、批量账号与批量统计/内容等；支持文件上传、结果预览与 CSV 导出。
侧边栏可查看默认的 API/速率设置，并可实时更改（Bearer Token、是否使用全量历史、每分钟请求数、最大重试、基础/最大退避秒数）。

### 扣子1：数据准备与清洗
读取 Excel 第一列 → 统一格式（去空格、统一大写）→ 去重 → 生成映射表
```
python -m twitter_crawler.cli prep companies \
  --input 推特公司样本.xlsx \
  --output normalized_companies.csv \
  --mapping name_mapping.csv
```
输出：
- 标准化公司名称列表：`normalized_companies.csv`
- 原始→标准化映射：`name_mapping.csv`

### 扣子2：推特账号查找与管理
- 单个或批量按公司名搜索账号，优先 verified
- 支持模糊搜索（关键字）
- 多结果时 CLI 手动确认
- 映射关系导入/导出/编辑

示例：
```
# 按公司名查找（支持多值）
python -m twitter_crawler.cli accounts find --names "Apple, Microsoft"

# 模糊搜索
python -m twitter_crawler.cli accounts search --keyword "appl"

# 导出/导入/编辑映射
python -m twitter_crawler.cli accounts export --file company_account_map.csv
python -m twitter_crawler.cli accounts import --file company_account_map.csv
python -m twitter_crawler.cli accounts edit --company "APPLE" --username "Apple"
```

### 扣子3：推文抓取与情绪分析
- 支持按账号或关键字
- 时间范围：2006–2022（需要 Twitter API v2 Academic 访问，可用 `tweets/search/all`）
- 抓取原始推文与转发
- 情绪分析：VADER，输出带正负号的分数
```
python -m twitter_crawler.cli tweets fetch \
  --by account --value Apple \
  --start 2006-01-01 --end 2022-12-31 \
  --include-retweets true \
  --output tweets_with_sentiment.csv
```
输出字段：公司名称、推文内容、发布时间、情绪分数

### 扣子4：推文数量查询模块
- 通过公司名（映射到账号）查询推文数量
- 时间区间筛选：开始-结束，或使用预设
  - 下拉1：当天、这周、当月、当前季度、当前半年、今年
  - 下拉2：最近一天、一周、一月、一季度、半年、一年
```
python -m twitter_crawler.cli counts query \
  --company "APPLE" \
  --preset this_month

python -m twitter_crawler.cli counts query \
  --company "APPLE" \
  --recent last_quarter
```

### 扣子5：批量账号查找与管理
- 从 `推特公司样本.xlsx` 导入公司名
- 批量查找、保存映射（含 verified、id、username）
```
python -m twitter_crawler.cli batch accounts \
  --input 推特公司样本.xlsx \
  --output company_account_map.csv
```

### 扣子6：批量推文数量查询（基于 推特公司样本_1570.xlsx）
- 读取公司名称与推文日期
- 关联公司名 ↔ 推特账号
- 查询指定日期的推文数，并计算 ±180 天窗口内数量
```
python -m twitter_crawler.cli batch counts \
  --input 推特公司样本_1570.xlsx \
  --output counts_结果.csv
```

### 扣子7：批量推文内容查询（基于 推特公司样本_详细.xlsx）
- 读取公司名称与推文日期
- 查询该日期 ±180 天内推文内容，可自定义窗口
- 结果含情绪分析
```
python -m twitter_crawler.cli batch contents \
  --input 推特公司样本_详细.xlsx \
  --window 180 \
  --output contents_结果.csv
```

## 说明
- 账号/推文接口基于 Twitter API v2。若需 2006–2022 全量历史，请确保拥有 Academic Research 权限并使用 `tweets/search/all`。
- 本工具在 CLI 下提供手动确认交互；亦可扩展为 GUI。


