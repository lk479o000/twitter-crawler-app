import io
import time
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

from twitter_crawler.data_prep import prepare_from_excel, normalize_company_name, read_first_column_as_list
from twitter_crawler.twitter_api import TwitterAPI
from twitter_crawler.accounts import search_account_for_company
from twitter_crawler.sentiment import sentiment_score
from twitter_crawler.storage import AccountInfo, save_accounts_csv, load_accounts_csv
from twitter_crawler.utils_date import (
    today_range, this_week_range, this_month_range, this_quarter_range,
    this_half_year_range, this_year_range, recent_days_range
)
from twitter_crawler.config import get_settings, Settings


st.set_page_config(page_title="推特抓取与分析工具", page_icon="🧩", layout="wide")
st.title("🧩 推特抓取与分析工具（Streamlit）")
st.caption("支持：数据准备、账号查找、推文抓取与情绪、数量查询、批量任务")

# 侧边栏：API 与速率限制设置（显示默认值并允许修改）
st.sidebar.header("API 与速率限制设置")
default_settings = get_settings()
if "api_settings" not in st.session_state:
    st.session_state.api_settings = default_settings

with st.sidebar.expander("查看/修改设置", expanded=True):
    token = st.text_input("Bearer Token（留空则使用环境变量）", value="", type="password")
    use_all = st.checkbox("使用全量历史 /tweets/search/all（需 Academic）", value=st.session_state.api_settings.use_search_all)
    rpm = st.number_input("每分钟请求数（Requests Per Minute）", min_value=1, max_value=300, value=st.session_state.api_settings.requests_per_minute, step=1)
    max_retries = st.number_input("最大重试次数", min_value=0, max_value=20, value=st.session_state.api_settings.rate_limit_max_retries, step=1)
    base_delay = st.number_input("基础退避秒数", min_value=0.0, max_value=120.0, value=float(st.session_state.api_settings.rate_limit_base_delay_seconds), step=0.5)
    max_delay = st.number_input("最大退避秒数", min_value=0.0, max_value=600.0, value=float(st.session_state.api_settings.rate_limit_max_delay_seconds), step=1.0)
    apply_cfg = st.button("应用设置")
    if apply_cfg:
        st.session_state.api_settings = Settings(
            twitter_bearer_token=token or default_settings.twitter_bearer_token,
            use_search_all=use_all,
            rate_limit_max_retries=int(max_retries),
            rate_limit_base_delay_seconds=float(base_delay),
            rate_limit_max_delay_seconds=float(max_delay),
            requests_per_minute=int(rpm),
        )
        st.success("设置已应用")

# 构造 API 客户端（使用当前设置）
api = TwitterAPI(
    bearer_token=st.session_state.api_settings.twitter_bearer_token,
    settings=st.session_state.api_settings
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "1：数据准备与清洗",
    "2：推特账号查找与管理",
    "3：推文抓取与情绪分析",
    "4：推文数量查询",
    "5：批量账号查找与管理",
    "6：批量推文数量查询",
    "7：批量推文内容查询"
])

with tab1:
    st.subheader("1：数据准备与清洗")
    excel_file = st.file_uploader("上传『推特公司样本.xlsx』", type=["xlsx"])
    col_a, col_b = st.columns(2)
    with col_a:
        run_prep = st.button("开始清洗并生成映射")
    if run_prep and excel_file:
        with st.spinner("处理中..."):
            buf = io.BytesIO(excel_file.read())
            # 将上传文件写到临时 DataFrame 处理
            df = pd.read_excel(buf, engine="openpyxl")
            temp_path = "临时_推特公司样本.xlsx"
            df.to_excel(temp_path, index=False)
            unique_names, mapping = prepare_from_excel(temp_path, "normalized_companies.csv", "name_mapping.csv")
        st.success(f"完成！标准化公司数：{len(unique_names)}")
        st.download_button("下载 标准化公司列表 CSV", data=open("normalized_companies.csv","rb").read(), file_name="normalized_companies.csv")
        st.download_button("下载 名称映射 CSV", data=open("name_mapping.csv","rb").read(), file_name="name_mapping.csv")

with tab2:
    st.subheader("2：推特账号查找与管理")
    st.caption("优先 verified；多结果可在 CLI 中确认。此处提供基础快速匹配。")
    names_input = st.text_area("输入公司名称（每行一个）")
    col1, col2 = st.columns(2)
    with col1:
        run_find = st.button("查找账号")
    with col2:
        uploaded_map = st.file_uploader("导入现有账号映射 CSV（可选）", type=["csv"])
    results_df = None
    if run_find and names_input.strip():
        names = [normalize_company_name(x) for x in names_input.splitlines() if x.strip()]
        results: list[AccountInfo] = []
        try:
            with st.spinner("正在查找..."):
                for comp in names:
                    try:
                        acc = search_account_for_company(api, comp)
                        if acc:
                            results.append(acc)
                    except requests.exceptions.HTTPError as e:
                        if "401" in str(e):
                            st.error(f"认证失败：请检查Bearer Token是否有效。")
                            break
                        elif "429" in str(e):
                            st.warning(f"查找{comp}时遇到速率限制，将暂停一段时间后继续...")
                            time.sleep(5)  # 暂停5秒再继续
                        else:
                            st.warning(f"查找{comp}时出错：{str(e)}")
                            continue
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()
        if results:
            results_df = pd.DataFrame([a.__dict__ for a in results])
            st.dataframe(results_df, use_container_width=True)
            save_accounts_csv(results, "company_account_map.csv")
            st.download_button("下载账号映射 CSV", data=open("company_account_map.csv","rb").read(), file_name="company_account_map.csv")
        else:
            st.info("未找到任何账号，请尝试不同名称。")
    if uploaded_map is not None:
        df_map = pd.read_csv(uploaded_map)
        st.dataframe(df_map, use_container_width=True)

with tab3:
    st.subheader("3：推文抓取与情绪分析")
    by = st.selectbox("查询方式", ["按账号", "按关键字"])
    value = st.text_input("账号（不含@）或关键字")
    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("开始日期", datetime(2006,1,1).date())
    with col2:
        end_date = st.date_input("结束日期", datetime(2022,12,31).date())
    with col3:
        include_retweets = st.checkbox("包含转推", value=True)
    run_fetch = st.button("抓取并分析")
    if run_fetch and value.strip():
        query = f"from:{value}" if by == "按账号" else value
        if not include_retweets:
            query += " -is:retweet"
        start_iso = f"{start_date.strftime('%Y-%m-%d')}T00:00:00Z"
        end_iso = f"{end_date.strftime('%Y-%m-%d')}T23:59:59Z"
        all_rows = []
        try:
            with st.spinner("抓取推文..."):
                while True:
                    try:
                        resp = api.search_tweets(
                            query=query,
                            start_time=start_iso,
                            end_time=end_iso,
                            expansions=["author_id"],
                            max_results=100,
                        )
                        data = resp.get("data", [])
                        for t in data:
                            text = t.get("text","").replace("\n", " ")
                            all_rows.append({
                                "公司名称": value if by == "按账号" else "",
                                "推文内容": text,
                                "发布时间": t.get("created_at"),
                                "情绪分数": sentiment_score(text),
                            })
                        next_token = resp.get("meta", {}).get("next_token")
                        if not next_token:
                            break
                    except requests.exceptions.HTTPError as e:
                        if "401" in str(e):
                            st.error(f"认证失败：请检查Bearer Token是否有效。")
                            break
                        elif "429" in str(e):
                            st.warning("遇到速率限制，将暂停一段时间后继续...")
                            time.sleep(10)  # 暂停10秒再继续
                        else:
                            st.error(f"抓取推文时出错：{str(e)}")
                            break
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()
        if all_rows:
            out_df = pd.DataFrame(all_rows)
            st.dataframe(out_df, use_container_width=True)
            out_df.to_csv("tweets_with_sentiment.csv", index=False, encoding="utf-8")
            st.download_button("下载结果 CSV", data=open("tweets_with_sentiment.csv","rb").read(), file_name="tweets_with_sentiment.csv")
        else:
            st.info("未抓取到推文。")

with tab4:
    st.subheader("4：推文数量查询模块")
    st.caption("注：此处为近似统计，严格计数需分页累积或官方 counts 端点。")
    company = st.text_input("公司账号（username，不含@）")
    preset = st.selectbox("时间区间（预设）", ["", "当天", "这周", "当月", "当前季度", "当前半年", "今年"])
    recent = st.selectbox("最近区间", ["", "最近一天", "最近一周", "最近一月", "最近一季度", "最近半年", "最近一年"])
    run_count = st.button("查询")
    if run_count and company.strip():
        if preset:
            mapping = {
                "当天": today_range,
                "这周": this_week_range,
                "当月": this_month_range,
                "当前季度": this_quarter_range,
                "当前半年": this_half_year_range,
                "今年": this_year_range,
            }
            start, end = mapping[preset]()
        elif recent:
            mapping_days = {
                "最近一天": 1,
                "最近一周": 7,
                "最近一月": 30,
                "最近一季度": 90,
                "最近半年": 180,
                "最近一年": 365,
            }
            start, end = recent_days_range(mapping_days[recent])
        else:
            st.warning("请选择预设或最近区间")
            start = end = None
        if start and end:
            query = f"from:{company} -is:reply"
            resp = api.search_tweets(query=query, start_time=start, end_time=end, max_results=100)
            total = resp.get("meta", {}).get("result_count", 0)
            st.metric("近似推文数量", total)

with tab5:
    st.subheader("5：批量账号查找与管理")
    excel_batch = st.file_uploader("上传『推特公司样本.xlsx』", type=["xlsx"], key="batch_accounts_xlsx")
    run_batch_accounts = st.button("批量查找")
    if run_batch_accounts and excel_batch:
        buf = io.BytesIO(excel_batch.read())
        df = pd.read_excel(buf, engine="openpyxl")
        temp_path = "临时_批量账号.xlsx"
        df.to_excel(temp_path, index=False)
        companies = read_first_column_as_list(temp_path)
        results: list[AccountInfo] = []
        error_count = 0
        try:
            with st.spinner("批量查找中..."):
                for i, comp in enumerate(companies):
                    try:
                        acc = search_account_for_company(api, comp)
                        if acc:
                            results.append(acc)
                    except requests.exceptions.HTTPError as e:
                        if "401" in str(e):
                            st.error(f"认证失败：请检查Bearer Token是否有效。")
                            break
                        elif "429" in str(e):
                            st.warning(f"查找{comp}时遇到速率限制，将暂停一段时间后继续...")
                            time.sleep(10)  # 暂停10秒再继续
                            # 重试一次当前公司
                            try:
                                acc = search_account_for_company(api, comp)
                                if acc:
                                    results.append(acc)
                            except Exception:
                                error_count += 1
                        else:
                            error_count += 1
                            st.warning(f"查找{comp}时出错：{str(e)}")
                            continue
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()
        if error_count > 0:
            st.warning(f"完成批量查找，但有 {error_count} 个公司处理出错。")
        if results:
            out_df = pd.DataFrame([r.__dict__ for r in results])
            out_df.to_csv("company_account_map.csv", index=False, encoding="utf-8")
            st.dataframe(out_df, use_container_width=True)
            st.download_button("下载账号映射 CSV", data=open("company_account_map.csv","rb").read(), file_name="company_account_map.csv")
        else:
            st.info("未找到任何账号。")

with tab6:
    st.subheader("6：批量推文数量查询（基于『推特公司样本_1570.xlsx』）")
    excel_counts = st.file_uploader("上传 Excel（需包含公司名与日期两列）", type=["xlsx"], key="batch_counts_xlsx")
    run_batch_counts = st.button("开始统计")
    if run_batch_counts and excel_counts:
        buf = io.BytesIO(excel_counts.read())
        df = pd.read_excel(buf, engine="openpyxl")
        company_col = df.columns[0]
        date_col = df.columns[1]
        rows = []
        error_count = 0
        try:
            with st.spinner("统计中..."):
                for i, row in df.iterrows():
                    company = normalize_company_name(str(row[company_col]))
                    the_date = pd.to_datetime(row[date_col]).date()
                    try:
                        # ±180 天
                        start_iso = f"{(the_date - timedelta(days=180)).strftime('%Y-%m-%d')}T00:00:00Z"
                        end_iso = f"{(the_date + timedelta(days=180)).strftime('%Y-%m-%d')}T23:59:59Z"
                        query = f"from:{company} -is:reply"
                        resp_180 = api.search_tweets(query=query, start_time=start_iso, end_time=end_iso, max_results=100)
                        count_180 = resp_180.get("meta", {}).get("result_count", 0)
                        # 当天
                        day_start = f"{the_date.strftime('%Y-%m-%d')}T00:00:00Z"
                        day_end = f"{the_date.strftime('%Y-%m-%d')}T23:59:59Z"
                        resp_day = api.search_tweets(query=query, start_time=day_start, end_time=day_end, max_results=100)
                        count_day = resp_day.get("meta", {}).get("result_count", 0)
                        rows.append({"公司名称": company, "日期": str(the_date), "当天推文数": count_day, "±180天推文数": count_180})
                    except requests.exceptions.HTTPError as e:
                        if "401" in str(e):
                            st.error(f"认证失败：请检查Bearer Token是否有效。")
                            break
                        elif "429" in str(e):
                            st.warning(f"统计{company}时遇到速率限制，将暂停一段时间后继续...")
                            time.sleep(15)  # 批量操作中暂停更久
                            error_count += 1
                        else:
                            error_count += 1
                            continue
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()
        if error_count > 0:
            st.warning(f"完成批量统计，但有 {error_count} 条记录处理出错。")
        out_df = pd.DataFrame(rows)
        out_df.to_csv("counts_结果.csv", index=False, encoding="utf-8")
        st.dataframe(out_df, use_container_width=True)
        st.download_button("下载统计结果 CSV", data=open("counts_结果.csv","rb").read(), file_name="counts_结果.csv")

with tab7:
    st.subheader("7：批量推文内容查询（基于『推特公司样本_详细.xlsx』）")
    excel_contents = st.file_uploader("上传 Excel（需包含公司名与日期两列）", type=["xlsx"], key="batch_contents_xlsx")
    window = st.number_input("窗口天数（±window）", value=180, min_value=1, max_value=365)
    run_batch_contents = st.button("开始抓取")
    if run_batch_contents and excel_contents:
        buf = io.BytesIO(excel_contents.read())
        df = pd.read_excel(buf, engine="openpyxl")
        company_col = df.columns[0]
        date_col = df.columns[1]
        all_rows = []
        error_count = 0
        try:
            with st.spinner("抓取中..."):
                for i, row in df.iterrows():
                    comp = normalize_company_name(str(row[company_col]))
                    the_date = pd.to_datetime(row[date_col]).date()
                    start_iso = f"{(the_date - timedelta(days=window)).strftime('%Y-%m-%d')}T00:00:00Z"
                    end_iso = f"{(the_date + timedelta(days=window)).strftime('%Y-%m-%d')}T23:59:59Z"
                    query = f"from:{comp}"
                    try:
                        has_next = True
                        next_token = None
                        while has_next:
                            try:
                                resp = api.search_tweets(
                                    query=query, 
                                    start_time=start_iso, 
                                    end_time=end_iso, 
                                    expansions=["author_id"], 
                                    max_results=100,
                                    next_token=next_token
                                )
                                data = resp.get("data", [])
                                for t in data:
                                    text = t.get("text","").replace("\n", " ")
                                    all_rows.append({"公司名称": comp, "推文内容": text, "发布时间": t.get("created_at"), "情绪分数": sentiment_score(text)})
                                next_token = resp.get("meta", {}).get("next_token")
                                has_next = bool(next_token)
                            except requests.exceptions.HTTPError as e:
                                if "401" in str(e):
                                    st.error(f"认证失败：请检查Bearer Token是否有效。")
                                    has_next = False
                                    break
                                elif "429" in str(e):
                                    st.warning(f"抓取{comp}的推文时遇到速率限制，将暂停一段时间后继续...")
                                    time.sleep(20)  # 批量内容抓取暂停更久
                                    continue  # 重试当前请求
                                else:
                                    st.warning(f"抓取{comp}的推文时出错：{str(e)}")
                                    has_next = False
                    except Exception as e:
                        error_count += 1
                        st.warning(f"处理{comp}时出错：{str(e)}")
                        continue
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()
        if error_count > 0:
            st.warning(f"完成批量抓取，但有 {error_count} 个公司处理出错。")
        out_df = pd.DataFrame(all_rows)
        out_df.to_csv("contents_结果.csv", index=False, encoding="utf-8")
        st.dataframe(out_df, use_container_width=True)
        st.download_button("下载内容结果 CSV", data=open("contents_结果.csv","rb").read(), file_name="contents_结果.csv")


