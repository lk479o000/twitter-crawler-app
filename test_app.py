import streamlit as st

st.title("🐦 测试页面")
st.write("如果看到这个，说明 Streamlit 工作正常！")

if st.button("点击测试"):
    st.success("按钮工作正常！")