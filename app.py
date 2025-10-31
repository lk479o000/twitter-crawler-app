# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time

st.set_page_config(
    page_title="公司Twitter数据抓取",
    page_icon="🐦",
    layout="wide"
)


def main():
    st.title("🐦 美国上市公司Twitter数据抓取工具")
    st.markdown("---")

    # 侧边栏配置
    with st.sidebar:
        st.header("⚙️ 配置参数")

        # 公司选择
        st.subheader("选择公司")
        company_options = {
            'AAPL': 'Apple Inc.',
            'TSLA': 'Tesla Inc.',
            'MSFT': 'Microsoft Corporation',
            'GOOGL': 'Alphabet Inc.',
            'AMZN': 'Amazon.com Inc.',
            'META': 'Meta Platforms Inc.',
            'NFLX': 'Netflix Inc.',
            'NVDA': 'NVIDIA Corporation'
        }

        selected_companies = st.multiselect(
            "选择要抓取的公司:",
            options=list(company_options.keys()),
            format_func=lambda x: f"{x} - {company_options[x]}",
            default=['AAPL', 'TSLA']
        )

        # 时间范围选择
        st.markdown("---")
        st.subheader("时间范围")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "开始日期:",
                value=datetime.now() - timedelta(days=30),
                max_value=datetime.now()
            )
        with col2:
            end_date = st.date_input(
                "结束日期:",
                value=datetime.now(),
                max_value=datetime.now()
            )

        # 其他参数
        st.markdown("---")
        st.subheader("其他设置")
        max_tweets = st.slider(
            "每家公司最大推文数量:",
            min_value=10,
            max_value=100,
            value=30,
            step=10
        )

    # 主内容区
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("📊 抓取控制")

        # 显示配置摘要
        st.subheader("当前配置")
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            st.metric("选择公司", len(selected_companies))
        with summary_col2:
            st.metric("时间范围", f"{(end_date - start_date).days}天")
        with summary_col3:
            st.metric("最大推文", max_tweets)

        # 开始抓取按钮
        st.markdown("---")
        if st.button("🚀 开始抓取数据", type="primary", use_container_width=True):
            if not selected_companies:
                st.error("❌ 请至少选择一个公司！")
                return

            with st.spinner("正在抓取数据，请稍候..."):
                # 模拟抓取过程
                progress_bar = st.progress(0)
                status_text = st.empty()

                for i in range(100):
                    # 更新进度
                    progress = i + 1
                    progress_bar.progress(progress)
                    status_text.text(f"抓取进度: {progress}%")
                    time.sleep(0.02)  # 模拟处理时间

                # 模拟结果
                mock_data = []
                for company in selected_companies:
                    for j in range(5):  # 每个公司5条模拟数据
                        mock_data.append({
                            'company_ticker': company,
                            'company_name': company_options.get(company, company),
                            'twitter_username': company_options.get(company, company).split()[0],
                            'tweet_text': f'这是 {company} 的模拟推文内容 #{j + 1}',
                            'tweet_date': (datetime.now() - timedelta(days=j)).strftime('%Y-%m-%d %H:%M:%S'),
                            'like_count': j * 10 + 5,
                            'retweet_count': j * 2 + 1
                        })

                results_df = pd.DataFrame(mock_data)

                # 显示结果
                st.success(f"✅ 抓取完成！共获取 {len(results_df)} 条推文")

                # 显示数据
                st.subheader("📋 抓取结果")
                st.dataframe(results_df, use_container_width=True)

                # 导出选项
                st.subheader("💾 导出数据")
                export_col1, export_col2, export_col3 = st.columns(3)

                with export_col1:
                    csv = results_df.to_csv(index=False)
                    st.download_button(
                        label="📥 下载CSV",
                        data=csv,
                        file_name=f"twitter_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with export_col2:
                    # 注意：实际部署时需要安装 openpyxl
                    excel_buffer = pd.ExcelWriter('temp.xlsx', engine='openpyxl')
                    results_df.to_excel(excel_buffer, index=False)
                    excel_buffer.close()

                    with open('temp.xlsx', 'rb') as f:
                        excel_data = f.read()

                    st.download_button(
                        label="📥 下载Excel",
                        data=excel_data,
                        file_name=f"twitter_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.ms-excel",
                        use_container_width=True
                    )

    with col2:
        st.header("📈 状态面板")
        st.info("""
        **当前状态：** 就绪
        **部署环境：** Streamlit Cloud
        **数据源：** Twitter
        """)


if __name__ == "__main__":
    main()