import streamlit as st
import pandas as pd
from sqlalchemy import text
import datetime
import uuid
import os
from supabase import create_client

# --- 設定 ---
BUCKET_NAME = "workflow_files"

# --- Supabaseクライアント初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secretsの設定が不足しています。")
    st.stop()

# --- 関数群 ---
def upload_file_to_storage(uploaded_file):
    if uploaded_file is None: return None, None
    try:
        file_ext = os.path.splitext(uploaded_file.name)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        bucket = supabase.storage.from_(BUCKET_NAME)
        bucket.upload(unique_filename, uploaded_file.getvalue(), {"content-type": uploaded_file.type})
        return bucket.get_public_url(unique_filename), uploaded_file.name
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None, None

def send_email_notification(to_email, subject, body):
    # シミュレーション通知
    st.toast(f"📩 (Mail Simulation) To: {to_email} | {subject}")

# --- メイン処理 ---
def main():
    st.title("🈸 稟議・申請ステータスボード")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.error("ログインしてください。")
        st.stop()
    
    my_name = st.session_state["user_name"]
    my_role = st.session_state["role"]
    my_email = st.session_state["user_email"]

    conn = st.connection("supabase", type="sql")

    # --- アクションメニュー ---
    if st.button("＋ 新規作成", type="primary", use_container_width=True):
        st.session_state["editing_ringi_id"] = None
        st.session_state["page_mode"] = "edit"
        st.rerun()

    st.markdown("---")

    if "page_mode" not in st.session_state:
        st.session_state["page_mode"] = "list"

    # ==================================================
    # モードA: ステータス一覧ボード
    # ==================================================
    if st.session_state["page_mode"] == "list":
        
        # 自分の申請分
        sql_my_app = f"SELECT ringi_id, created_at, subject, amount, status, applicant_name, '申請分' as type FROM T_Ringi_Header WHERE applicant_email = '{my_email}'"
        
        # 自分への承認待ち (IDで個人指定されたもの)
        sql_to_approve = f"""
            UNION ALL
            SELECT h.ringi_id, h.created_at, h.subject, h.amount, '承認待ち' as status, h.applicant_name, '承認待' as type
            FROM T_Ringi_Header h
            JOIN T_Ringi_Approvals a ON h.ringi_id = a.ringi_id
            WHERE a.approver_id = '{my_email}' AND a.status = '未承認' AND h.status != '却下'
        """
        
        final_sql = f"SELECT * FROM ({sql_my_app} {sql_to_approve}) AS merged ORDER BY ringi_id DESC"
        df_list = conn.query(final_sql, ttl=0)

        tab1, tab2 = st.tabs(["📋 全案件ステータス", "✅ 承認作業トレイ"])
        
        with tab1:
            st.caption("あなたが関わった案件一覧")
            df_view = df_list[df_list['type'] == '申請分']
            if df_view.empty:
                st.info("データなし")
            else:
                st.dataframe(df_view[["ringi_id", "created_at", "subject", "amount", "status"]], use_container_width=True, hide_index=True)
                
                selected_id = st.selectbox("案件詳細を確認", df_view["ringi_id"], index=None)
                if selected_id:
                    row = df_view[df_view["ringi_id"] == selected_id].iloc[0]
                    with st.container(border=True):
                        st.subheader(f"{row['subject']}")
                        if row["status"] == "下書き":
                            if st.button("✏️ 編集・申請する"):
                                st.session_state["editing_ringi_id"] = selected_id
                                st.session_state["page_mode"] = "edit"
                                st.rerun()
                        else:
                            st.write(f"**現在のステータス:** {row['status']}")
                            
                            # フロー状況表示
                            st.markdown("###### 承認・回付履歴")
                            steps = conn.query(f"SELECT step_order, approver_role, approver_name, status, comment, approved_at FROM T_Ringi_Approvals WHERE ringi_id = {selected_id} ORDER BY step_order", ttl=0)
                            
                            for idx, s_row in steps.iterrows():
                                icon = "⬜"
                                if s_row['status'] == '承認': icon = "✅"
                                elif s_row['status'] == '却下': icon = "❌"
                                elif s_row['status'] == '未承認': icon = "⏳"
                                
                                st.markdown(f"**{s_row['step_order']}. {icon} {s_row['approver_name']} ({s_row['approver_role']})** : {s_row['status']}")
                                if s_row['comment']:
                                    st.info(f"💬 {s_row['comment']}")

        with tab2:
            df_app = df_list[df_list['type'] == '承認待']
            if df_app.empty:
                st.info("あなた宛ての承認依頼はありません")
            else:
                for i, row in df_app.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**No.{row['ringi_id']} {row['subject']}**")
                        st.write(f"申請者: {row['applicant_name']} | ¥{row['amount']:,}")
                        
                        detail = conn.query(f"SELECT content FROM T_Ringi_Header WHERE ringi_id={row['ringi_id']}", ttl=0).iloc[0]
                        with st.expander("詳細を見る"):
                            st.text(detail['content'])
                            files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                            for _, f in files.iterrows():
                                st.markdown(f"📎 [{f['file_name']}]({f['file_url']})")

                        comment = st.text_input("💬 コメント", key=f"cmt_{row['ringi_id']}")
                        
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button("承認する", key=f"app_{row['ringi_id']}", type="primary", use_container_width=True):
                                with conn.session as s:
                                    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                                    s.execute(
                                        text("UPDATE T_Ringi_Approvals SET status='承認', approved_at=:at, comment=:cm WHERE ringi_id=:rid AND approver_id=:uid"),
                                        {"at": now, "cm": comment, "rid": row['ringi_id'], "uid": my_email}
                                    )
                                    # 全員の承認が終わったかチェック
                                    # (簡易判定: 未承認が0件になれば完了)
                                    pending_count = s.execute(text(f"SELECT count(*) FROM T_Ringi_Approvals WHERE ringi_id={row['ringi_id']} AND status='未承認'")).fetchone()[0]
                                    if pending_count == 0:
                                        s.execute(text("UPDATE T_Ringi_Header SET status='決裁完了' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                    
                                    s.commit()
                                
                                send_email_notification("applicant@example.com", f"【承認】{row['subject']}", f"{my_name}が承認しました。")
                                st.success("承認しました")
                                st.rerun()
                        with c_b:
                            if st.button("却下する", key=f"rej_{row['ringi_id']}", use_container_width=True):
                                 with conn.session as s:
                                    s.execute(
                                        text("UPDATE T_Ringi_Approvals SET status='却下', approved_at=:at, comment=:cm WHERE ringi_id=:rid AND approver_id=:uid"),
                                        {"at": datetime.datetime.now(), "cm": comment, "rid": row['ringi_id'], "uid": my_email}
                                    )
                                    s.execute(text("UPDATE T_Ringi_Header SET status='却下' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                    s.commit()
                                 send_email_notification("applicant@example.com", f"【却下】{row['subject']}", f"理由: {comment}")
                                 st.error("却下しました")
                                 st.rerun()

    # ==================================================
    # モードB: 編集画面
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        edit_id = st.session_state.get("editing_ringi_id")
        is_new = edit_id is None
        st.subheader("📝 稟議書作成" if is_new else "✏️ 稟議書編集")
        
        default_subject = ""
        default_amount = 0
        default_content = ""
        default_approvers_indices = [] # 編集時の承認者再現は少し複雑なため今回は初期値のみ対応
        
        # ユーザーマスタから承認者リストを取得
        users_df = conn.query("SELECT display_name, role, user_id FROM M_Users ORDER BY role DESC", ttl=60)
        # 表示用リスト: "山田 太郎 (課長)"
        user_options = [f"{row['display_name']} ({row['role']})" for i, row in users_df.iterrows()]
        # 保存用リスト: メールアドレス
        user_ids = users_df['user_id'].tolist()
        
        if not is_new:
            existing = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {edit_id}", ttl=0).iloc[0]
            default_subject = existing["subject"]
            default_amount = existing["amount"]
            default_content = existing["content"]
            # 既に設定されたルートがあれば読み込む処理が必要だが、今回はシンプル化のためスキップ

        with st.form("ringi_form"):
            subject = st.text_input("件名", value=default_subject)
            amount = st.number_input("金額 (円)", value=default_amount, step=1000)
            content = st.text_area("内容", value=default_content, height=150)
            uploaded_files = st.file_uploader("添付ファイル追加", accept_multiple_files=True)
            
            st.markdown("---")
            st.write("▼ 承認ルート設定")
            st.caption("承認してほしい順番に選択してください。上から順に承認フローが回ります。")
            
            # ★ルート選択機能★
            selected_approvers = st.multiselect(
                "承認者を選択",
                options=user_options,
                default=[] # デフォルトは空、必要に応じて["日比野 (課長)", ...]のようにセット可
            )
            
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.form_submit_button("キャンセル"):
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c2:
                if st.form_submit_button("下書き保存"):
                    # 下書き時はルート保存しなくてもOK
                    save_header_only(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "下書き", uploaded_files)
                    st.toast("下書き保存しました")
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c3:
                if st.form_submit_button("申請する", type="primary"):
                    if not subject:
                        st.warning("件名は必須です")
                    elif not selected_approvers:
                        st.warning("承認ルートを設定してください")
                    else:
                        # 選択された表示名から、ユーザー情報を復元して保存
                        approver_data_list = []
                        for sel in selected_approvers:
                            idx = user_options.index(sel)
                            approver_data_list.append({
                                "id": user_ids[idx],
                                "name": users_df.iloc[idx]['display_name'],
                                "role": users_df.iloc[idx]['role']
                            })
                        
                        save_full_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "申請中", uploaded_files, approver_data_list)
                        send_email_notification(approver_data_list[0]['id'], f"【承認依頼】{subject}", f"{my_name}から申請がありました。")
                        st.success("申請しました！")
                        st.session_state["page_mode"] = "list"
                        st.rerun()

def save_header_only(conn, is_new, ringi_id, name, email, subject, amount, content, status, files):
    """下書き用: ルート未定でも保存可能"""
    save_full_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files, [])

def save_full_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files, approver_list):
    """申請用: ルート情報込みで保存"""
    with conn.session as s:
        target_id = ringi_id
        # 1. Header保存
        if is_new:
            row = s.execute(text("INSERT INTO T_Ringi_Header (applicant_name, applicant_email, subject, amount, content, status) VALUES (:nm, :em, :sub, :amt, :cnt, :st) RETURNING ringi_id"),
                            {"nm": name, "em": email, "sub": subject, "amt": amount, "cnt": content, "st": status}).fetchone()
            target_id = row[0]
        else:
            s.execute(text("UPDATE T_Ringi_Header SET subject=:sub, amount=:amt, content=:cnt, status=:st WHERE ringi_id=:rid"),
                      {"sub": subject, "amt": amount, "cnt": content, "st": status, "rid": ringi_id})
        
        # 2. ファイル保存
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url: s.execute(text("INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url) VALUES (:rid, :fn, :fu)"), {"rid": target_id, "fn": f_name, "fu": f_url})

        # 3. ルート保存 (申請時のみ)
        if status == "申請中" and approver_list:
            # 既存ルート削除（上書き）
            s.execute(text(f"DELETE FROM T_Ringi_Approvals WHERE ringi_id={target_id}"))
            # 新規ルート登録
            for i, user in enumerate(approver_list):
                s.execute(
                    text("""
                    INSERT INTO T_Ringi_Approvals (ringi_id, step_order, approver_id, approver_name, approver_role) 
                    VALUES (:rid, :ord, :uid, :nm, :role)
                    """),
                    {"rid": target_id, "ord": i+1, "uid": user['id'], "nm": user['name'], "role": user['role']}
                )
        s.commit()

if __name__ == "__main__":
    main()