import pathlib
import typer
from rich import print as rprint
from rich.table import Table

from .data_prep import prepare_from_excel, normalize_company_name
from .config import get_settings
from .twitter_api import TwitterAPI
from .accounts import search_account_for_company
from .storage import save_accounts_csv, load_accounts_csv, AccountInfo
from .sentiment import sentiment_score
from .utils_date import (
    today_range,
    this_week_range,
    this_month_range,
    this_quarter_range,
    this_half_year_range,
    this_year_range,
    recent_days_range,
)

app = typer.Typer(help="Twitter 爬取与分析工具（CLI）")
prep_app = typer.Typer(help="数据准备与清洗")
app.add_typer(prep_app, name="prep")

accounts_app = typer.Typer(help="账号查找与管理")
app.add_typer(accounts_app, name="accounts")

tweets_app = typer.Typer(help="推文抓取与分析")
app.add_typer(tweets_app, name="tweets")

counts_app = typer.Typer(help="推文数量查询")
app.add_typer(counts_app, name="counts")

batch_app = typer.Typer(help="批量任务")
app.add_typer(batch_app, name="batch")

@prep_app.command("companies")
def prep_companies(
    input: str = typer.Option(..., "--input", "-i", help="公司样本 Excel 文件路径（例如：推特公司样本.xlsx）"),
    output: str = typer.Option("normalized_companies.csv", "--output", "-o", help="标准化公司名称输出 CSV"),
    mapping: str = typer.Option("name_mapping.csv", "--mapping", "-m", help="原始->标准化 名称映射 CSV"),
):
    """
    扣子1：数据准备与清洗
    - 读取 Excel 第一列公司名称
    - 去除空格、统一大小写、去重
    - 生成原始名称 -> 标准化名称映射表
    """
    excel_path = pathlib.Path(input)
    names_csv = pathlib.Path(output)
    mapping_csv = pathlib.Path(mapping)

    rprint(f"[bold cyan]读取 Excel：[/bold cyan]{excel_path}")
    unique_names, mapping_dict = prepare_from_excel(excel_path, names_csv, mapping_csv)

    rprint(f"[bold green]完成！[/bold green] 标准化公司数：{len(unique_names)}")
    rprint(f"名称列表保存至：{names_csv}")
    rprint(f"映射表保存至：{mapping_csv}")

    # 预览前 10 条
    preview = unique_names[:10]
    if preview:
        table = Table(title="标准化公司名称（前10条预览）")
        table.add_column("normalized_name")
        for n in preview:
            table.add_row(n)
        rprint(table)

@accounts_app.command("find")
def accounts_find(
    names: str = typer.Option(..., "--names", "-n", help="以逗号分隔的公司名称列表"),
    output: str = typer.Option("company_account_map.csv", "--output", "-o", help="保存账号映射 CSV"),
):
    """
    扣子2：按公司名称查找推特账号（verified 优先），多候选时可手动确认
    """
    api = TwitterAPI()
    company_list = [normalize_company_name(x) for x in names.split(",") if x.strip()]
    results: list[AccountInfo] = []
    for comp in company_list:
        acc = search_account_for_company(api, comp)
        if acc:
            results.append(acc)
    save_accounts_csv(results, output)
    rprint(f"[bold green]完成！[/bold green] 保存至 {output}，共 {len(results)} 条")

@accounts_app.command("export")
def accounts_export(
    file: str = typer.Option("company_account_map.csv", "--file", "-f", help="导出路径")
):
    """
    示例导出（如果你已有内存对象可直接保存；此处仅提示用法）
    """
    rprint("[yellow]提示：[/yellow]请使用 find 指令生成映射后再导出，或将已有对象写入此文件。")

@accounts_app.command("import")
def accounts_import(
    file: str = typer.Option(..., "--file", "-f", help="导入已保存的账号映射 CSV")
):
    data = load_accounts_csv(file)
    rprint(f"[bold green]导入成功[/bold green]：{len(data)} 条")

@accounts_app.command("edit")
def accounts_edit(
    company: str = typer.Option(..., "--company", "-c", help="标准化公司名"),
    username: str = typer.Option(..., "--username", "-u", help="Twitter 用户名（不含@）"),
    file: str = typer.Option("company_account_map.csv", "--file", "-f", help="账号映射 CSV"),
):
    rows = load_accounts_csv(file)
    found = False
    for r in rows:
        if r.company_normalized == normalize_company_name(company):
            r.username = username
            found = True
            break
    if not found:
        rows.append(AccountInfo(company_normalized=normalize_company_name(company), twitter_id=None, username=username, name=None, verified=None))
    save_accounts_csv(rows, file)
    rprint(f"[bold green]已更新[/bold green]：{company} -> @{username}")

@tweets_app.command("fetch")
def tweets_fetch(
    by: str = typer.Option(..., "--by", help="account 或 keyword"),
    value: str = typer.Option(..., "--value", help="账号名（不含@）或关键字"),
    start: str = typer.Option(None, "--start", help="开始日期（YYYY-MM-DD）"),
    end: str = typer.Option(None, "--end", help="结束日期（YYYY-MM-DD）"),
    include_retweets: bool = typer.Option(True, "--include-retweets", help="是否包含转推"),
    output: str = typer.Option("tweets_with_sentiment.csv", "--output", "-o"),
):
    """
    扣子3：抓取推文并做情绪分析（VADER）
    """
    import pandas as pd
    from datetime import datetime
    api = TwitterAPI()

    if by not in ("account", "keyword"):
        raise typer.BadParameter("by 必须为 account 或 keyword")

    query = ""
    if by == "account":
        query = f"from:{value}"
    else:
        query = value
    if include_retweets:
        # 保留原推 + 转推
        pass
    else:
        query += " -is:retweet"

    # 日期转 ISO8601
    start_iso = f"{start}T00:00:00Z" if start else None
    end_iso = f"{end}T23:59:59Z" if end else None

    all_rows = []
    next_token = None
    while True:
        resp = api.search_tweets(
            query=query,
            start_time=start_iso,
            end_time=end_iso,
            expansions=["author_id"],
            max_results=100,
        )
        data = resp.get("data", [])
        users = {u["id"]: u for u in resp.get("includes", {}).get("users", [])}
        for t in data:
            author = users.get(t.get("author_id"))
            text = t.get("text", "")
            score = sentiment_score(text)
            company_name = value if by == "account" else ""
            all_rows.append({
                "company": company_name,
                "text": text,
                "created_at": t.get("created_at"),
                "sentiment": score,
                "username": author.get("username") if author else None,
            })
        next_token = resp.get("meta", {}).get("next_token")
        if not next_token:
            break

    pd.DataFrame(all_rows).to_csv(output, index=False, encoding="utf-8")
    rprint(f"[bold green]完成！[/bold green] 共 {len(all_rows)} 条，保存至 {output}")

@counts_app.command("query")
def counts_query(
    company: str = typer.Option(..., "--company", "-c"),
    preset: str = typer.Option(None, "--preset", help="当天 this_day / 这周 this_week / 当月 this_month / 当前季度 this_quarter / 当前半年 this_half / 今年 this_year"),
    recent: str = typer.Option(None, "--recent", help="最近一天 last_day / 一周 last_week / 一月 last_month / 一季度 last_quarter / 半年 last_half / 一年 last_year"),
):
    """
    扣子4：推文数量查询（演示生成时间范围；实际计数需对接 counts 端点或分页统计）
    """
    api = TwitterAPI()
    if preset:
        if preset == "this_day":
            start, end = today_range()
        elif preset == "this_week":
            start, end = this_week_range()
        elif preset == "this_month":
            start, end = this_month_range()
        elif preset == "this_quarter":
            start, end = this_quarter_range()
        elif preset == "this_half":
            start, end = this_half_year_range()
        elif preset == "this_year":
            start, end = this_year_range()
        else:
            raise typer.BadParameter("未知 preset")
    elif recent:
        mapping = {
            "last_day": 1,
            "last_week": 7,
            "last_month": 30,
            "last_quarter": 90,
            "last_half": 180,
            "last_year": 365,
        }
        days = mapping.get(recent)
        if not days:
            raise typer.BadParameter("未知 recent")
        start, end = recent_days_range(days)
    else:
        raise typer.BadParameter("请使用 --preset 或 --recent 选择时间范围")

    query = f"from:{company} -is:reply"
    # 简化：以搜索条数近似（严格计数应分页累积或使用 counts 端点）
    resp = api.search_tweets(query=query, start_time=start, end_time=end, max_results=100)
    total = resp.get("meta", {}).get("result_count", 0)
    rprint(f"[bold green]时间范围[/bold green]：{start} ~ {end}，近似数量：{total}")

@batch_app.command("accounts")
def batch_accounts(
    input: str = typer.Option(..., "--input", "-i", help="推特公司样本.xlsx"),
    output: str = typer.Option("company_account_map.csv", "--output", "-o"),
):
    """
    扣子5：批量账号查找与管理
    """
    import pandas as pd
    from .data_prep import read_first_column_as_list
    api = TwitterAPI()
    companies = read_first_column_as_list(input)
    results: list[AccountInfo] = []
    for comp in companies:
        acc = search_account_for_company(api, comp)
        if acc:
            results.append(acc)
    save_accounts_csv(results, output)
    rprint(f"[bold green]完成！[/bold green] 批量账号映射保存至 {output}（{len(results)} 条）")

@batch_app.command("counts")
def batch_counts(
    input: str = typer.Option(..., "--input", "-i", help="推特公司样本_1570.xlsx（需包含公司名与日期）"),
    output: str = typer.Option("counts_结果.csv", "--output", "-o"),
):
    """
    扣子6：批量推文数量查询（按指定日期与 ±180 天窗口）
    """
    import pandas as pd
    from datetime import datetime, timedelta
    from .data_prep import read_first_column_as_list
    api = TwitterAPI()

    df = pd.read_excel(input, engine="openpyxl")
    company_col = df.columns[0]
    date_col = df.columns[1]
    rows = []
    for _, row in df.iterrows():
        company = normalize_company_name(str(row[company_col]))
        the_date = pd.to_datetime(row[date_col]).date()
        start = f"{(the_date - timedelta(days=180)).strftime('%Y-%m-%d')}T00:00:00Z"
        end = f"{(the_date + timedelta(days=180)).strftime('%Y-%m-%d')}T23:59:59Z"
        query = f"from:{company} -is:reply"
        resp = api.search_tweets(query=query, start_time=start, end_time=end, max_results=100)
        count_180 = resp.get("meta", {}).get("result_count", 0)
        # 指定日期当天
        day_start = f"{the_date.strftime('%Y-%m-%d')}T00:00:00Z"
        day_end = f"{the_date.strftime('%Y-%m-%d')}T23:59:59Z"
        resp_day = api.search_tweets(query=query, start_time=day_start, end_time=day_end, max_results=100)
        count_day = resp_day.get("meta", {}).get("result_count", 0)
        rows.append({
            "company": company,
            "date": str(the_date),
            "count_day": count_day,
            "count_±180d": count_180,
        })
    pd.DataFrame(rows).to_csv(output, index=False, encoding="utf-8")
    rprint(f"[bold green]完成！[/bold green] 批量数量结果保存至 {output}（{len(rows)} 条）")

@batch_app.command("contents")
def batch_contents(
    input: str = typer.Option(..., "--input", "-i", help="推特公司样本_详细.xlsx（需包含公司名与日期）"),
    window: int = typer.Option(180, "--window", "-w", help="窗口天数，默认 180"),
    output: str = typer.Option("contents_结果.csv", "--output", "-o"),
):
    """
    扣子7：批量推文内容查询（±window 天），并做情绪分析
    """
    import pandas as pd
    from datetime import timedelta
    api = TwitterAPI()

    df = pd.read_excel(input, engine="openpyxl")
    company_col = df.columns[0]
    date_col = df.columns[1]

    all_rows = []
    for _, row in df.iterrows():
        comp = normalize_company_name(str(row[company_col]))
        the_date = pd.to_datetime(row[date_col]).date()
        start_iso = f"{(the_date - timedelta(days=window)).strftime('%Y-%m-%d')}T00:00:00Z"
        end_iso = f"{(the_date + timedelta(days=window)).strftime('%Y-%m-%d')}T23:59:59Z"
        query = f"from:{comp}"
        while True:
            resp = api.search_tweets(query=query, start_time=start_iso, end_time=end_iso, expansions=["author_id"], max_results=100)
            data = resp.get("data", [])
            for t in data:
                text = t.get("text", "")
                all_rows.append({
                    "company": comp,
                    "text": text,
                    "created_at": t.get("created_at"),
                    "sentiment": sentiment_score(text),
                })
            next_token = resp.get("meta", {}).get("next_token")
            if not next_token:
                break

    pd.DataFrame(all_rows).to_csv(output, index=False, encoding="utf-8")
    rprint(f"[bold green]完成！[/bold green] 批量内容结果保存至 {output}（{len(all_rows)} 条）")

def main():
    app()


if __name__ == "__main__":
    main()


