import streamlit as st
import pandas as pd
from sqlalchemy import text
from supabase import create_client
import time

# --- Supabase初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets設定エラー")
    st.stop()

def main():
    st.set_page_config(page_title="ユーザー設定", layout="wide")
    st.title("👤 ユーザー設定")
    
    # 認証チェック
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()
    
    my_id = st.session_state["user_email"]
    my_name = st.session_state["user_name"]
    
    conn = st.connection("supabase", type="sql")

    # --- ユーザー情報表示 ---
    with st.container(border=True):
        st.subheader("登録情報")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("氏名", value=my_name, disabled=True)
            st.text_input("権限 (Role)", value=st.session_state["role"], disabled=True)
        with c2:
            st.text_input("ログインID (Email)", value=my_id, disabled=True)
            st.caption("※ 氏名や権限の変更は管理者に依頼してください。")

    # --- パスワード変更フォーム ---
    with st.container(border=True):
        st.subheader("🔐 パスワード変更")
        
        with st.form("pw_change_form"):
            current_pw = st.text_input("現在のパスワード", type="password")
            new_pw = st.text_input("新しいパスワード", type="password", help="4文字以上推奨")
            new_pw_confirm = st.text_input("新しいパスワード (確認)", type="password")
            
            if st.form_submit_button("変更する", type="primary"):
                # バリデーション
                if not current_pw or not new_pw:
                    st.error("パスワードを入力してください。")
                elif new_pw != new_pw_confirm:
                    st.error("新しいパスワードが一致しません。")
                else:
                    # 現在のパスワード確認
                    user_row = conn.query(f"SELECT password FROM M_Users WHERE user_id = '{my_id}'", ttl=0).iloc[0]
                    db_pass = user_row['password']
                    
                    if str(current_pw) != str(db_pass):
                        st.error("現在のパスワードが間違っています。")
                    else:
                        # 更新実行
                        try:
                            with conn.session as s:
                                s.execute(
                                    text("UPDATE M_Users SET password = :pw WHERE user_id = :uid"),
                                    {"pw": new_pw, "uid": my_id}
                                )
                                s.commit()
                            
                            st.success("パスワードを変更しました！")
                            st.info("セキュリティのため、再度ログインしてください。")
                            time.sleep(2)
                            
                            # ログアウト処理
                            st.session_state.clear()
                            st.rerun()
                            
                        except Exception as e:
                            st.error(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()