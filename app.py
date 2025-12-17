import streamlit as st

# --- 認証機能の定義 ---
def check_password():
    """パスワード認証を行う関数"""
    # ユーザーがパスワード未入力、または間違っている場合
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if not st.session_state["password_correct"]:
        # パスワード入力フォームを表示
        password = st.text_input("パスワードを入力してください", type="password")
        
        # パスワード判定（st.secretsから正解を取得して比較）
        if st.button("ログイン"):
            if password == st.secrets["PASSWORD"]:  # 正解なら
                st.session_state["password_correct"] = True
                st.rerun() # 画面を再読み込み
            else:
                st.error("パスワードが違います")
        return False
    return True

# --- メイン処理 ---
if check_password():
    # ここから下に、ログイン後のコンテンツを書く
    st.title("社内用ツールポータル")
    st.write("ようこそ！ここは限られたメンバー専用のページです。")
    
    # 例：機能の選択
    st.subheader("利用可能なツール")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("データ集計ツール起動"):
            st.info("集計スクリプトを実行中...（ダミー）")
    with col2:
        if st.button("在庫確認"):
            st.success("在庫データに接続しました（ダミー）")