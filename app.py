import io
import time
import logging
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st
import openpyxl

# 配置日志系统
log_file = f"twitter_crawler_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"日志系统初始化成功，日志文件: {log_file}")

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

    # 实时更新设置，无需应用按钮
    st.session_state.api_settings = Settings(
        twitter_bearer_token=token or default_settings.twitter_bearer_token,
        use_search_all=use_all,
        rate_limit_max_retries=int(max_retries),
        rate_limit_base_delay_seconds=float(base_delay),
        rate_limit_max_delay_seconds=float(max_delay),
        requests_per_minute=int(rpm),
    )

# 构造 API 客户端（使用当前设置）
api = TwitterAPI(
    bearer_token=st.session_state.api_settings.twitter_bearer_token,
    settings=st.session_state.api_settings
)

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "1：数据准备与清洗",
    "2：推特账号查找与管理",
    "3：推文抓取与情绪分析",
    "4：推文数量查询",
    "5：批量账号查找与管理",
    "6：批量推文数量查询",
    "7：批量推文内容查询",
    "8：批量查询推文"
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
        st.download_button("下载 标准化公司列表 CSV", data=open("normalized_companies.csv", "rb").read(), file_name="normalized_companies.csv")
        st.download_button("下载 名称映射 CSV", data=open("name_mapping.csv", "rb").read(), file_name="name_mapping.csv")

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
            st.download_button("下载账号映射 CSV", data=open("company_account_map.csv", "rb").read(), file_name="company_account_map.csv")
        else:
            st.info("未找到任何账号，请尝试不同名称。")
    if uploaded_map is not None:
        df_map = pd.read_csv(uploaded_map)
        st.dataframe(df_map, use_container_width=True)

with tab3:
    st.subheader("3：推文抓取与情绪分析")
    # 现在设置会实时更新，直接使用session_state中的值
    st.info(f"当前配置：{'Academic 权限（支持全量历史）' if st.session_state.api_settings.use_search_all else 'Basic Plan（仅支持最近7天）'}")

    by = st.selectbox("查询方式", ["按账号", "按推特账号直接查询", "按关键字"])
    value = st.text_input("账号（不含@）或关键字")

    # 根据权限设置日期范围默认值和限制
    if st.session_state.api_settings.use_search_all:
        default_start = datetime(2006, 1, 1).date()
        default_end = datetime(2022, 12, 31).date()
        st.caption("注意：Academic 权限支持 2006-2022 全量历史数据")
    else:
        default_end = datetime.now().date()
        default_start = default_end - timedelta(days=7)
        st.caption("注意：Basic Plan 仅支持最近 7 天的推文数据")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("开始日期", default_start)
    with col2:
        end_date = st.date_input("结束日期", default_end)
    # 移除包含转推功能
    run_fetch = st.button("抓取并分析")

    if run_fetch and value.strip():
        # 检查Basic Plan下的时间范围限制
        if not st.session_state.api_settings.use_search_all:
            # 获取当前时间
            current_datetime = datetime.now()
            current_date = current_datetime.date()

            # 1. 确保end_time不超过当前时间
            if end_date > current_date:
                st.warning(f"结束日期不能超过当前日期，已调整为今天")
                end_date = current_date
                # 如果是今天，end_time应该是当前时间而不是23:59:59
                end_time = current_datetime
            else:
                # 非今天，使用当天的23:59:59
                end_time = datetime.combine(end_date, datetime.max.time())

            # 2. 计算最早允许的开始日期（当前时间-7天）
            min_start_date = current_date - timedelta(days=7)

            # 确保start_time不早于当前时间-7天
            if start_date < min_start_date:
                st.warning(f"开始日期不能早于7天前，已调整为最早允许日期")
                start_date = min_start_date

            # 3. 确保日期跨度不超过7天
            date_diff = (end_date - start_date).days
            if date_diff > 7:
                st.warning(f"Basic Plan 仅支持7天内的数据，已自动调整开始日期")
                start_date = end_date - timedelta(days=7)

        # 在可能调整日期后，重新计算ISO格式日期
        start_iso = f"{start_date.strftime('%Y-%m-%d')}T00:00:00Z"
        # 如果是当天，使用当前时间，否则使用23:59:59
        if 'end_time' in locals() and end_date == current_date:
            end_iso = end_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        else:
            end_iso = f"{end_date.strftime('%Y-%m-%d')}T23:59:59Z"
        all_rows = []

        try:
            with st.spinner("抓取推文..."):
                # 根据权限和查询方式选择不同的API调用方法
                if by == "按账号" and not st.session_state.api_settings.use_search_all:
                    # Basic Plan：使用 get_user_tweets 端点
                    # 先获取用户ID
                    user_info = api.get_user_by_username(value)
                    if not user_info:
                        st.error(f"未找到账号: {value}")
                        st.stop()

                    user_id = user_info.get("id")
                    # 使用 next_token 进行分页
                    has_next = True
                    next_token = None

                    while has_next:
                        try:
                            resp = api.get_user_tweets(
                                user_id=user_id,
                                start_time=start_iso,
                                end_time=end_iso,
                                exclude="replies,retweets",
                                pagination_token=next_token,
                                max_results=100
                            )
                            data = resp.get("data", [])
                            for t in data:
                                text = t.get("text", "").replace("\n", " ")
                                all_rows.append({
                                    "公司名称": value,
                                    "推文内容": text,
                                    "发布时间": t.get("created_at"),
                                    "情绪分数": sentiment_score(text),
                                })

                            # 使用 next_token 进行分页
                            next_token = resp.get("meta", {}).get("next_token")
                            has_next = bool(next_token)
                        except requests.exceptions.HTTPError as e:
                            if "401" in str(e):
                                st.error(f"认证失败：请检查Bearer Token是否有效。")
                                has_next = False
                                break
                            elif "429" in str(e):
                                st.warning("遇到速率限制，将暂停一段时间后继续...")
                                time.sleep(10)
                                continue
                            else:
                                st.error(f"抓取推文时出错：{str(e)}")
                                has_next = False
                elif by == "按推特账号直接查询":
                    # 直接使用search_tweets端点查询账号，不需要获取用户ID
                    query = f"from:{value} -is:retweet"
                    next_token = None

                    while True:
                        try:
                            resp = api.search_tweets(
                                query=query,
                                start_time=start_iso,
                                end_time=end_iso,
                                max_results=100,
                                next_token=next_token
                            )
                            data = resp.get("data", [])
                            for t in data:
                                text = t.get("text", "").replace("\n", " ")
                                all_rows.append({
                                    "公司名称": value,
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
                                time.sleep(10)
                            else:
                                st.error(f"抓取推文时出错：{str(e)}")
                                break
                        except Exception as e:
                            st.error(f"发生错误：{str(e)}")
                            break
                else:
                    # Academic 权限、按关键字查询或按推特账号直接查询：使用 search_tweets 端点
                    query = f"from:{value}" if by in ["按账号", "按推特账号直接查询"] else value
                    # 默认排除转推
                    query += " -is:retweet"

                    next_token = None
                    while True:
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
                                text = t.get("text", "").replace("\n", " ")
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
                                time.sleep(10)
                            else:
                                st.error(f"抓取推文时出错：{str(e)}")
                                break
                        except Exception as e:
                            st.error(f"发生错误：{str(e)}")
                            break
        except Exception as e:
            st.error(f"发生错误：{str(e)}")
            st.stop()

        if all_rows:
            out_df = pd.DataFrame(all_rows)
            st.dataframe(out_df, use_container_width=True)

            # 计算并显示统计信息
            avg_sentiment = out_df["情绪分数"].mean()
            st.metric("平均情绪分数", round(avg_sentiment, 2))

            out_df.to_csv("tweets_with_sentiment.csv", index=False, encoding="utf-8")
            st.download_button("下载结果 CSV", data=open("tweets_with_sentiment.csv", "rb").read(), file_name="tweets_with_sentiment.csv")
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
            # 根据权限选择不同的API调用方法
            if not st.session_state.api_settings.use_search_all:
                # Basic Plan：使用get_user_tweets端点获取用户推文数量
                try:
                    # 先获取用户ID
                    user_info = api.get_user_by_username(company)
                    if not user_info:
                        st.error(f"未找到账号: {company}")
                        st.stop()

                    user_id = user_info.get("id")
                    # 调用get_user_tweets获取推文数量
                    resp = api.get_user_tweets(
                        user_id=user_id,
                        start_time=start,
                        end_time=end,
                        exclude="replies,retweets"
                    )
                    total = len(resp.get("data", []))
                    st.metric("推文数量", total)
                except Exception as e:
                    st.error(f"查询过程中出错: {str(e)}")
            else:
                # Academic权限：使用search_tweets端点
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
            st.download_button("下载账号映射 CSV", data=open("company_account_map.csv", "rb").read(), file_name="company_account_map.csv")
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
                        # 根据权限选择不同的API调用方法
                        if not st.session_state.api_settings.use_search_all:
                            # Basic Plan：使用get_user_tweets端点
                            # 先获取用户ID
                            user_info = api.get_user_by_username(company)
                            if not user_info:
                                st.warning(f"未找到账号: {company}")
                                error_count += 1
                                continue

                            user_id = user_info.get("id")

                            # 当天统计
                            day_start = f"{the_date.strftime('%Y-%m-%d')}T00:00:00Z"
                            day_end = f"{the_date.strftime('%Y-%m-%d')}T23:59:59Z"
                            resp_day = api.get_user_tweets(
                                user_id=user_id,
                                start_time=day_start,
                                end_time=day_end,
                                exclude="replies,retweets"
                            )
                            count_day = len(resp_day.get("data", []))

                            # Basic Plan只支持最近7天，所以±180天统计改为±3天
                            start_iso = f"{(the_date - timedelta(days=3)).strftime('%Y-%m-%d')}T00:00:00Z"
                            end_iso = f"{(the_date + timedelta(days=3)).strftime('%Y-%m-%d')}T23:59:59Z"
                            resp_week = api.get_user_tweets(
                                user_id=user_id,
                                start_time=start_iso,
                                end_time=end_iso,
                                exclude="replies,retweets"
                            )
                            count_week = len(resp_week.get("data", []))
                            rows.append({"公司名称": company, "日期": str(the_date), "当天推文数": count_day, "±3天推文数": count_week})
                        else:
                            # Academic权限：使用search_tweets端点
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
        st.download_button("下载统计结果 CSV", data=open("counts_结果.csv", "rb").read(), file_name="counts_结果.csv")

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
                    try:
                        # 根据权限选择不同的API调用方法
                        if not st.session_state.api_settings.use_search_all:
                            # Basic Plan：使用get_user_tweets端点
                            # 先获取用户ID
                            user_info = api.get_user_by_username(comp)
                            if not user_info:
                                st.warning(f"未找到账号: {comp}")
                                error_count += 1
                                continue

                            user_id = user_info.get("id")

                            # 调整时间范围为Basic Plan支持的最近7天内
                            # 计算实际可查询的时间范围
                            current_date = datetime.now().date()
                            min_date = current_date - timedelta(days=7)

                            # 调整查询的开始时间不早于7天前
                            actual_start_date = max((the_date - timedelta(days=window)), min_date)
                            actual_end_date = min((the_date + timedelta(days=window)), current_date)

                            start_iso = f"{actual_start_date.strftime('%Y-%m-%d')}T00:00:00Z"
                            end_iso = f"{actual_end_date.strftime('%Y-%m-%d')}T23:59:59Z"

                            has_next = True
                            next_token = None
                            while has_next:
                                try:
                                    resp = api.get_user_tweets(
                                        user_id=user_id,
                                        start_time=start_iso,
                                        end_time=end_iso,
                                        exclude="replies,retweets",
                                        pagination_token=next_token,
                                        max_results=100
                                    )
                                    data = resp.get("data", [])
                                    for t in data:
                                        text = t.get("text", "").replace("\n", " ")
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
                                        time.sleep(20)
                                        continue
                                    else:
                                        st.warning(f"抓取{comp}的推文时出错：{str(e)}")
                                        has_next = False
                        else:
                            # Academic权限：使用search_tweets端点
                            query = f"from:{comp}"
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
                                        text = t.get("text", "").replace("\n", " ")
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
        st.download_button("下载内容结果 CSV", data=open("contents_结果.csv", "rb").read(), file_name="contents_结果.csv")

# 全局变量用于跟踪API限制
if 'api_limits' not in st.session_state:
    st.session_state.api_limits = {
        'monthly_tweets_count': 0,  # 每月推文计数器
        'user_requests': {},  # 每用户请求跟踪 {user_handle: [timestamp1, timestamp2, ...]}
        'app_requests': [],  # 应用级请求时间戳列表
        'last_reset_date': datetime.now().date()  # 上次重置日期
    }

with tab8:
    st.subheader("8：批量查询推文")
    st.caption("仅支持当前配置：Basic Plan（仅支持最近7天）")
    st.caption("API限制：每月最多15K条推文，每用户每15分钟5个请求，每应用每15分钟10个请求")

    # 批量导入推特账号功能
    uploaded_file = st.file_uploader("上传账号文件（支持CSV和Excel格式，三列：公司名称,推特账号,推特ID）", type=["csv", "xlsx", "xls"])

    if uploaded_file is not None:
        # 读取上传的文件（支持CSV和Excel）
        try:
            logger.info(f"开始处理上传文件: {uploaded_file.name}")
            # 根据文件扩展名选择不同的读取方法
            file_extension = uploaded_file.name.split('.')[-1].lower()
            logger.info(f"文件类型: {file_extension}")
            if file_extension in ['xlsx', 'xls']:
                accounts_df = pd.read_excel(uploaded_file)
                logger.info("成功读取Excel文件")
            else:  # csv
                accounts_df = pd.read_csv(uploaded_file)
                logger.info("成功读取CSV文件")
            if len(accounts_df.columns) < 3:
                st.error("上传的文件格式不正确，请确保文件包含至少三列：公司名称、推特账号和推特ID")
            else:
                # 显示上传的数据预览
                logger.info(f"共读取 {len(accounts_df)} 个账号")
                st.write("上传的账号列表：")
                st.dataframe(accounts_df, use_container_width=True)

                # 添加文件格式说明
                st.info("文件格式说明：")
                st.info("- 第1列：公司名称（必填）")
                st.info("- 第2列：推特账号（必填，格式：@username）")
                st.info("- 第3列：推特ID（可选）")
                st.info("- 第4列：开始日期（可选，格式：YYYY/MM/DD）")
                st.info("- 第5列：结束日期（可选，格式：YYYY/MM/DD）")

                # 批量查询按钮
                if st.button("开始批量查询推文"):
                    logger.info("开始执行批量查询推文任务")
                    # 检查并重置月度计数（如果是新月份）
                    current_date = datetime.now().date()
                    if current_date.month != st.session_state.api_limits['last_reset_date'].month:
                        logger.info(f"跨月重置，新月份：{current_date.month}，重置月度推文计数")
                        st.session_state.api_limits['monthly_tweets_count'] = 0
                        st.session_state.api_limits['last_reset_date'] = current_date

                    # 结果列表
                    results = []
                    total_accounts = len(accounts_df)
                    progress_bar = st.progress(0)
                    logger.info(f"批量查询任务开始，总账号数: {total_accounts}")

                    with st.spinner("正在批量查询推文中..."):
                        # 创建账号信息列表
                        accounts_info = []
                        for _, row in accounts_df.iterrows():
                            # 解析基本信息
                            company = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
                            handle = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
                            user_id = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''

                            # 解析日期信息（如果有）
                            start_date = str(row.iloc[3]).strip() if len(row) > 3 and pd.notna(row.iloc[3]) else ''
                            end_date = str(row.iloc[4]).strip() if len(row) > 4 and pd.notna(row.iloc[4]) else ''

                            # 清理推特账号（移除@符号）
                            if handle.startswith('@'):
                                handle = handle[1:]

                            # 公司名称和推特账号为必填
                            if company and handle:
                                accounts_info.append({
                                    'company': company,
                                    'handle': handle,
                                    'user_id': user_id,
                                    'start_date': start_date,
                                    'end_date': end_date
                                })
                            else:
                                logger.warning(f"跳过无效账号行：公司名称={company}，推特账号={handle}")

                        logger.info(f"成功解析 {len(accounts_info)} 个有效账号信息")
                        total_accounts = len(accounts_info)

                        # 清理过期的请求记录（超过15分钟）
                        current_time = time.time()
                        fifteen_minutes_ago = current_time - (15 * 60)

                        # 清理应用级请求记录
                        st.session_state.api_limits['app_requests'] = [
                            t for t in st.session_state.api_limits['app_requests'] 
                            if t > fifteen_minutes_ago
                        ]

                        # 清理每用户请求记录
                        for user in list(st.session_state.api_limits['user_requests'].keys()):
                            st.session_state.api_limits['user_requests'][user] = [
                                t for t in st.session_state.api_limits['user_requests'][user] 
                                if t > fifteen_minutes_ago
                            ]

                        # 批量处理账号
                        break_loop = False  # 用于标记是否需要中断循环
                        for index, account_info in enumerate(accounts_info):
                            if break_loop:
                                break
                            try:
                                # 更新进度
                                progress_bar.progress((index + 1) / total_accounts)

                                # 获取账号信息
                                company_name = account_info['company']
                                twitter_handle = account_info['handle']
                                user_id = account_info['user_id']
                                start_date_str = account_info.get('start_date', '')
                                end_date_str = account_info.get('end_date', '')

                                # 组装时间段
                                def assemble_time_period(start_date, end_date):
                                    # 默认时间段
                                    default_start = "2025-11-14T00:00:00Z"
                                    default_end = "2025-11-19T23:59:59Z"

                                    # 处理空值情况
                                    if not start_date and not end_date:
                                        return default_start, default_end

                                    # 处理开始日期
                                    if start_date:
                                        try:
                                            # 支持多种日期格式: YYYY/MM/DD 和 YYYY-MM-DD 00:00:00
                                            if '/' in start_date:
                                                # YYYY/MM/DD格式
                                                year, month, day = map(int, start_date.split('/'))
                                            else:
                                                # YYYY-MM-DD 00:00:00格式
                                                date_part = start_date.split()[0]  # 获取日期部分
                                                year, month, day = map(int, date_part.split('-'))
                                            
                                            # 保留原始年份
                                            start_iso = f"{year}-{month:02d}-{day:02d}T00:00:00Z"
                                        except:
                                            # 格式错误时使用默认值
                                            logger.warning(f"开始日期格式错误: {start_date}，使用默认值")
                                            start_iso = default_start
                                    else:
                                        start_iso = default_start

                                    # 处理结束日期
                                    if end_date:
                                        try:
                                            # 支持多种日期格式: YYYY/MM/DD 和 YYYY-MM-DD 00:00:00
                                            if '/' in end_date:
                                                # YYYY/MM/DD格式
                                                year, month, day = map(int, end_date.split('/'))
                                            else:
                                                # YYYY-MM-DD 00:00:00格式
                                                date_part = end_date.split()[0]  # 获取日期部分
                                                year, month, day = map(int, date_part.split('-'))
                                            
                                            # 根据需求，年份固定为2025或使用原年份
                                            end_iso = f"{year}-{month:02d}-{day:02d}T23:59:59Z"
                                        except:
                                            # 格式错误时使用默认值
                                            logger.warning(f"结束日期格式错误: {end_date}，使用默认值")
                                            end_iso = default_end
                                    else:
                                        # 如果结束日期为空，在开始日期基础上+6天
                                        if start_date:
                                            try:
                                                # 解析开始日期并加上6天，支持多种格式
                                                if '/' in start_date:
                                                    # YYYY/MM/DD格式
                                                    year, month, day = map(int, start_date.split('/'))
                                                else:
                                                    # YYYY-MM-DD 00:00:00格式
                                                    date_part = start_date.split()[0]  # 获取日期部分
                                                    year, month, day = map(int, date_part.split('-'))
                                                
                                                # 保留原始年份
                                                from datetime import datetime, timedelta
                                                date_obj = datetime(year, month, day)
                                                end_date_obj = date_obj + timedelta(days=6)
                                                end_iso = f"{end_date_obj.year}-{end_date_obj.month:02d}-{end_date_obj.day:02d}T23:59:59Z"
                                            except:
                                                end_iso = default_end
                                        else:
                                            end_iso = default_end

                                    # 验证开始时间不晚于结束时间
                                    from datetime import datetime
                                    try:
                                        start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
                                        end_dt = datetime.fromisoformat(end_iso.replace('Z', '+00:00'))
                                        
                                        if start_dt > end_dt:
                                            logger.warning(f"开始时间({start_iso})晚于结束时间({end_iso})，已自动调整顺序")
                                            # 交换开始时间和结束时间
                                            start_iso, end_iso = end_iso, start_iso
                                    except Exception as e:
                                        logger.error(f"时间验证出错: {str(e)}")
                                    
                                    return start_iso, end_iso

                                # 获取时间段
                                start_time, end_time = assemble_time_period(start_date_str, end_date_str)
                                logger.info(f"时间段: {start_time} 至 {end_time}")

                                logger.info(f"处理账号: {index+1}/{total_accounts} - {company_name} (@{twitter_handle}) ID:{user_id}")

                                # 检查月度推文限制
                                if st.session_state.api_limits['monthly_tweets_count'] >= 15000:
                                    logger.warning(f"已达到每月15K条推文的限制，停止查询")
                                    st.warning(f"已达到每月15K条推文的限制，无法继续查询。")
                                    break

                                # 使用user_id或twitter_handle作为请求跟踪标识
                                request_key = user_id if user_id else twitter_handle

                                # 检查每用户请求限制（每15分钟5个请求）
                                if request_key not in st.session_state.api_limits['user_requests']:
                                    st.session_state.api_limits['user_requests'][request_key] = []

                                user_requests_count = len(st.session_state.api_limits['user_requests'][request_key])
                                if user_requests_count >= 5:
                                    logger.warning(f"用户请求限制: {company_name} (@{twitter_handle}) 已达到每15分钟5个请求的限制，跳过")
                                    st.warning(f"{company_name} (@{twitter_handle}) 已达到每15分钟5个请求的限制，跳过该账号。")
                                    continue

                                # 检查应用级请求限制（每15分钟10个请求）
                                app_requests_count = len(st.session_state.api_limits['app_requests'])
                                if app_requests_count >= 10:
                                    st.warning(f"已达到每应用每15分钟10个请求的限制，请稍后再试。")
                                    break

                                st.write(f"正在查询 {company_name} (@{twitter_handle}) 的推文...")

                                # 优先使用已有的user_id，如果没有则通过username获取
                                if not user_id and twitter_handle:
                                    logger.info(f"通过用户名获取用户ID: @{twitter_handle}")
                                    try:
                                        user = api.get_user_by_username(twitter_handle)
                                        if not user:
                                            logger.error(f"用户不存在: @{twitter_handle}")
                                            st.error(f"无法找到用户: @{twitter_handle}")
                                            continue
                                        user_id = user['id']
                                        logger.info(f"获取到用户ID: {user_id} (@{twitter_handle})")
                                    except Exception as e:
                                        logger.error(f"获取用户ID失败: @{twitter_handle} - {str(e)}")
                                        st.error(f"获取用户ID失败: @{twitter_handle} - {str(e)}")
                                        continue
                                elif not user_id and not twitter_handle:
                                    logger.warning(f"缺少必要的账号信息: {company_name}")
                                    st.warning(f"账号 {company_name} 缺少推特账号和推特ID，跳过")
                                    continue

                                # 调用get_user_tweets方法，使用组装的时间段参数
                                logger.info(f"调用API获取推文: @{twitter_handle} (ID: {user_id})，时间段: {start_time} 至 {end_time}")
                                response = api.get_user_tweets(
                                    user_id=user_id,
                                    start_time=start_time,  # 使用组装的开始时间
                                    end_time=end_time,      # 使用组装的结束时间
                                    max_results=100,        # 使用最大限制
                                    exclude="replies,retweets",  # 排除回复和转发
                                    tweet_fields="id,text,created_at,public_metrics,author_id"
                                )
                                logger.info(f"API调用完成: @{twitter_handle}，响应状态: 成功")

                                # 更新请求计数
                                current_time = time.time()
                                st.session_state.api_limits['app_requests'].append(current_time)
                                st.session_state.api_limits['user_requests'][request_key].append(current_time)

                                # 处理返回的推文
                                tweets = response.get("data", [])
                                logger.info(f"@{twitter_handle} 返回推文数量: {len(tweets)}")

                                # 账号拉取为空时的处理
                                if not tweets:
                                    logger.info(f"@{twitter_handle} 在指定时间范围内没有发布任何推文")
                                    st.info(f"@{twitter_handle} 在指定时间范围内没有发布任何推文")
                                else:
                                    # 检查是否会超出月度限制
                                    tweets_to_process = min(len(tweets), 15000 - st.session_state.api_limits['monthly_tweets_count'])
                                    if tweets_to_process < len(tweets):
                                        st.info(f"处理 {tweets_to_process} 条推文（达到月度限制）")
                                    else:
                                        st.write(f"找到 {len(tweets)} 条推文")

                                    # 更新月度推文计数
                                    st.session_state.api_limits['monthly_tweets_count'] += tweets_to_process
                                    logger.info(f"更新月度推文计数: 当前累计 {st.session_state.api_limits['monthly_tweets_count']}/15000")

                                    # 为每条推文计算情绪分数并添加到结果（但不超过月度限制）
                                    for t in tweets[:tweets_to_process]:
                                        # 计算情绪分数
                                        sentiment = sentiment_score(t.get("text", ""))

                                        # 计算情绪状态
                                        if sentiment > 0.05:
                                            sentiment_status = "正面"
                                        elif sentiment < -0.05:
                                            sentiment_status = "负面"
                                        else:
                                            sentiment_status = "中性"

                                        # 添加到结果列表，包含所有需要的字段
                                        public_metrics = t.get("public_metrics", {})
                                        results.append({
                                            "序号": len(results) + 1,
                                            "公司名称": company_name,
                                            "推特账号": f"@{twitter_handle}",
                                            "推特ID": user_id,
                                            "开始日期": start_date_str,
                                            "结束日期": end_date_str,
                                            "推特内容": t.get("text", ""),
                                            "发布时间": t.get("created_at", ""),
                                            "情绪分数": sentiment,
                                            "情绪状态": sentiment_status,
                                            "转推数": public_metrics.get("retweet_count", 0),
                                            "回复数": public_metrics.get("reply_count", 0),
                                            "点赞数": public_metrics.get("like_count", 0),
                                            "引用数": public_metrics.get("quote_count", 0)
                                        })

                            except Exception as e:
                                error_str = str(e)
                                # 处理400错误（错误请求）- 直接退出循环
                                if "400" in error_str:
                                    logger.error(f"严重错误: {company_name} (@{twitter_handle}) ID:{user_id} - 请求错误(400): {error_str}，终止批量查询")
                                    st.error(f"请求错误 (400)：参数无效或请求格式错误。终止批量查询。")
                                    # 将错误标记为需要中断循环
                                    break_loop = True
                                    break
                                # 处理401错误（认证失败）- 直接退出循环
                                elif "401" in error_str:
                                    logger.error(f"严重错误: {company_name} (@{twitter_handle}) ID:{user_id} - 认证失败(401): {error_str}，终止批量查询")
                                    st.error(f"认证失败 (401)：请检查API密钥是否正确。终止批量查询。")
                                    # 将错误标记为需要中断循环
                                    break_loop = True
                                    break
                                # 处理429错误（速率限制）- 直接退出循环
                                elif "429" in error_str:
                                    logger.error(f"严重错误: {company_name} (@{twitter_handle}) ID:{user_id} - 速率限制(429): {error_str}，终止批量查询")
                                    st.error(f"请求过于频繁 (429)：已达到API速率限制。请稍后再试。终止批量查询。")
                                    # 将错误标记为需要中断循环
                                    break_loop = True
                                    break
                                # 其他错误（账号不存在、网络问题等）- 只跳过当前账号，继续处理下一个
                                else:
                                    logger.error(f"错误: {company_name} (@{twitter_handle}) ID:{user_id} - {error_str}，跳过该账号")
                                    st.warning(f"处理 {company_name} (@{twitter_handle}) 时出错：{error_str}")
                                    st.info(f"跳过该账号，继续处理下一个...")
                                    continue

                    # 显示结果
                    logger.info(f"批量查询任务完成，总共处理 {len(results)} 条推文")
                    if results:
                        # 创建包含所有需要字段的DataFrame
                        results_df = pd.DataFrame(results, columns=[
                            "序号", "公司名称", "推特账号", "推特ID", 
                            "开始日期", "结束日期", "推特内容", 
                            "发布时间", "情绪分数", "情绪状态",
                            "转推数", "回复数", "点赞数", "引用数"
                        ])
                        results_df.to_csv("批量查询推文结果.csv", index=False, encoding="utf-8")
                        logger.info("结果已保存到CSV文件")
                        st.success(f"批量查询完成！共获取 {len(results)} 条推文")

                        # 显示当前API使用情况
                        st.info(f"当前API使用情况：本月已处理 {st.session_state.api_limits['monthly_tweets_count']}/15000 条推文")
                        st.dataframe(results_df, use_container_width=True)

                        # 日志配置说明
                        with st.expander("📝 日志配置说明", expanded=False):
                            st.markdown("""
                            **日志文件信息：**
                            - **文件路径：** 与应用程序在同一目录下
                            - **文件命名格式：** `twitter_crawler_YYYYMMDD_HHMMSS.log`
                            - **日志级别：** INFO及以上（包括INFO、WARNING、ERROR）
                            - **日志内容：** 记录API调用、错误信息、文件处理等关键操作
                            - **说明：** 每个新启动的应用实例会创建一个新的日志文件，文件名包含启动时间戳
                            """)

                        # 导出功能 - 同时支持CSV和Excel格式

                        # 导出CSV
                        csv_data = results_df.to_csv(index=False, encoding="utf-8-sig")
                        logger.info("准备CSV格式下载数据")
                        st.download_button(
                            "下载查询结果 (CSV)",
                            data=csv_data,
                            file_name="批量查询推文结果.csv",
                            mime="text/csv"
                        )

                        # 导出Excel
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            results_df.to_excel(writer, index=False, sheet_name='推文查询结果')
                        excel_data = output.getvalue()
                        logger.info("准备Excel格式下载数据")
                        st.download_button(
                            "下载查询结果 (Excel)",
                            data=excel_data,
                            file_name="批量查询推文结果.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.info("未找到任何推文")
        except Exception as e:
            logger.error(f"读取文件时出错：{str(e)}")
            st.error(f"读取文件时出错：{str(e)}")


