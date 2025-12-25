import streamlit as st
import pandas as pd
from sqlalchemy import text
from supabase import create_client

# --- Supabase初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets設定エラー")
    st.stop()

def main():
    st.set_page_config(page_title="社員マスタ管理", layout="wide")
    st.title("👥 社員マスタ管理")
    
    # 認証 & 権限チェック
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()
    
    # 本来はここで「管理者権限」をチェックすべきですが、今回は全員アクセス可としておきます
    # if "管理者" not in st.session_state["role"]: ...
    
    conn = st.connection("supabase", type="sql")

    # --- 画面構成 ---
    col_list, col_edit = st.columns([2, 1])

    # === 左側: 社員リスト ===
    with col_list:
        st.subheader("社員一覧")
        
        # データ取得
        df_users = conn.query("SELECT user_id, display_name, role, password, is_active FROM M_Users ORDER BY user_id", ttl=0)
        
        # 表示用にパスワードは伏せ字にする
        display_df = df_users.copy()
        display_df['password'] = "********"
        
        st.dataframe(
            display_df,
            column_config={
                "user_id": "ログインID (Email)",
                "display_name": "氏名",
                "role": "役職/権限",
                "password": "PW",
                "is_active": "有効"
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.caption("※ 編集するには、右側のフォームを使用してください。")

    # === 右側: 追加・編集フォーム ===
    with col_edit:
        st.subheader("編集 / 追加")
        
        mode = st.radio("操作", ["新規追加", "既存編集"], horizontal=True)
        
        # フォーム用変数の初期化
        f_user_id = ""
        f_name = ""
        f_role = "社員"
        f_pass = "1234"
        f_active = True
        
        if mode == "既存編集":
            user_options = df_users['user_id'].tolist()
            selected_user_id = st.selectbox("編集する社員を選択", user_options)
            
            if selected_user_id:
                target_row = df_users[df_users['user_id'] == selected_user_id].iloc[0]
                f_user_id = target_row['user_id']
                f_name = target_row['display_name']
                f_role = target_row['role']
                f_pass = target_row['password']
                f_active = bool(target_row['is_active'])
        
        with st.form("user_form"):
            # IDは新規時のみ入力可、編集時は表示のみ
            if mode == "新規追加":
                val_id = st.text_input("ログインID (メールアドレス)", value=f_user_id)
            else:
                st.text_input("ログインID", value=f_user_id, disabled=True)
                val_id = f_user_id # 変更不可
            
            val_name = st.text_input("氏名", value=f_name)
            val_role = st.selectbox("役職", ["社長", "専務", "常務", "部長", "課長", "係長", "主任", "社員"], index=["社長", "専務", "常務", "部長", "課長", "係長", "主任", "社員"].index(f_role) if f_role in ["社長", "専務", "常務", "部長", "課長", "係長", "主任", "社員"] else 7)
            val_pass = st.text_input("パスワード", value=f_pass, type="password")
            val_active = st.checkbox("アカウント有効", value=f_active)
            
            # 送信ボタン
            btn_txt = "登録する" if mode == "新規追加" else "更新する"
            if st.form_submit_button(btn_txt, type="primary"):
                if not val_id or not val_name:
                    st.error("IDと氏名は必須です。")
                else:
                    try:
                        with conn.session as s:
                            if mode == "新規追加":
                                # 重複チェック
                                check = s.execute(text(f"SELECT count(*) FROM M_Users WHERE user_id='{val_id}'")).fetchone()[0]
                                if check > 0:
                                    st.error("そのIDは既に登録されています。")
                                else:
                                    s.execute(
                                        text("INSERT INTO M_Users (user_id, display_name, role, password, is_active) VALUES (:id, :nm, :rl, :pw, :act)"),
                                        {"id": val_id, "nm": val_name, "rl": val_role, "pw": val_pass, "act": val_active}
                                    )
                                    s.commit()
                                    st.success(f"社員「{val_name}」を追加しました！")
                                    st.rerun()
                            else:
                                # 更新
                                s.execute(
                                    text("UPDATE M_Users SET display_name=:nm, role=:rl, password=:pw, is_active=:act WHERE user_id=:id"),
                                    {"id": val_id, "nm": val_name, "rl": val_role, "pw": val_pass, "act": val_active}
                                )
                                s.commit()
                                st.success(f"社員「{val_name}」の情報を更新しました！")
                                st.rerun()
                    except Exception as e:
                        st.error(f"DBエラー: {e}")

if __name__ == "__main__":
    main()