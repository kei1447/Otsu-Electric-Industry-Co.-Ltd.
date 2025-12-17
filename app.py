import streamlit as st

# ページ設定
st.set_page_config(
    page_title="社内ポータル",
    page_icon="🏢",
)

# --- 認証機能 ---
def check_password():
    """パスワード認証を行う関数"""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        st.title("🔒 社内ポータル ログイン")
        password = st.text_input("パスワードを入力してください", type="password")
        
        if st.button("ログイン"):
            if password == st.secrets["PASSWORD"]:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

# --- メイン処理 ---
if check_password():
    st.title("🏢 社内用ツールポータル")
    st.markdown("業務効率化ツールへようこそ。以下のメニューからツールを選択してください。")
    
    st.divider()

    st.subheader("🛠 利用可能なツール一覧")
    
    # 2列レイアウト
    col1, col2 = st.columns(2)
    
    with col1:
        # カード1: OCRツール
        with st.container(border=True):
            # タイトルをファイル名に変更
            st.markdown("### 📄 sekisui_ocr_tool.py")
            st.markdown("図面データ(PDF/TIFF)から、品名と数量をAIが読み取り一覧化します。")
            st.markdown("---")
            # ラベルもファイル名ベースに変更
            st.page_link("pages/sekisui_ocr_tool.py", label="sekisui_ocr_tool を起動", icon="🚀")

    with col2:
        # カード2: 電脳工場ツール
        with st.container(border=True):
            # タイトルをファイル名に変更
            st.markdown("### 🏭 price_list_convert.py")
            st.markdown("電脳工場から出力した製品リスト(.xls)を、見やすいテーブル形式に変換します。")
            st.markdown("---")
            # ラベルもファイル名ベースに変更
            st.page_link("pages/denno_tool.py", label="denno_tool を起動", icon="✨")

    # 今後の拡張用スペース
    st.divider()
    st.info("💡 **お知らせ**: 新しいツールへの要望や不具合報告は、開発担当までご連絡ください。")