import streamlit as st
import pandas as pd
from sqlalchemy import text
import datetime
import uuid
import os
# import smtplib  # メール機能は一旦無効化
# from email.mime.text import MIMEText
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
    """
    メール送信機能（現在はシミュレーションモード）
    Outlookでの本格運用時にコメントアウトを外します。
    """
    # 画面右下に通知を出すだけ（安全策）
    st.toast(f"📩 (Mail Simulation) To: {to_email} | {subject}")
    
    # --- 将来の実装用メモ（Outlook設定） ---
    # email_conf = st.secrets.get("email")
    # if email_conf:
    #     msg = MIMEText(body)
    #     msg['Subject'] = subject
    #     msg['From'] = email_conf["sender_email"]
    #     msg['To'] = to_email
    #     server = smtplib.SMTP(email_conf["smtp_server"], 587)
    #     server.starttls()
    #     server.login(email_conf["sender_email"], email_conf["sender_password"])
    #     server.send_message(msg)
    #     server.quit()

# --- メイン処理 ---
def main():
    st.title("🈸 稟議・申請ステータスボード")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.error("ログインしてください。")
        st.stop()
    
    my_name = st.session_state["user_name"]
    my_role = st.session_state["role"]
    my_email = st.session_state["user_email"]

    manager_roles = ["課長", "部長", "社長", "専務", "常務", "工場長"]
    is_manager = any(role in my_role for role in manager_roles)

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
        
        sql_my_app = f"SELECT ringi_id, created_at, subject, amount, status, applicant_name, '申請分' as type FROM T_Ringi_Header WHERE applicant_email = '{my_email}'"
        sql_to_approve = ""
        if is_manager:
            sql_to_approve = f"""
                UNION ALL
                SELECT h.ringi_id, h.created_at, h.subject, h.amount, '承認待ち' as status, h.applicant_name, '承認待' as type
                FROM T_Ringi_Header h
                JOIN T_Ringi_Approvals a ON h.ringi_id = a.ringi_id
                WHERE a.approver_role = '{my_role}' AND a.status = '未承認' AND h.status != '却下'
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
                
                st.write("▼ 詳細・コメント確認")
                selected_id = st.selectbox("案件を選択", df_view["ringi_id"], index=None)
                
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
                            
                            # ★履歴とコメントの表示エリア★
                            st.markdown("###### 承認・回付履歴")
                            steps = conn.query(f"SELECT approver_role, approver_name, status, comment, approved_at FROM T_Ringi_Approvals WHERE ringi_id = {selected_id} ORDER BY approval_id", ttl=0)
                            
                            for idx, s_row in steps.iterrows():
                                # アイコン決定
                                icon = "⬜"
                                status_text = s_row['status']
                                if status_text == '承認': icon = "✅"
                                elif status_text == '却下': icon = "❌"
                                elif status_text == '未承認': icon = "⏳"
                                
                                # カード風に表示
                                with st.container():
                                    cols = st.columns([1, 4])
                                    with cols[0]:
                                        st.markdown(f"**{icon} {s_row['approver_role']}**")
                                    with cols[1]:
                                        if s_row['status'] == '未承認':
                                            st.caption("審査中...")
                                        else:
                                            st.write(f"**{s_row['status']}** by {s_row['approver_name']}")
                                            st.caption(f"日時: {s_row['approved_at']}")
                                            # コメントがあれば目立つように表示
                                            if s_row['comment']:
                                                st.info(f"💬 **コメント:** {s_row['comment']}")
                                    st.divider()

        with tab2:
            if is_manager:
                df_app = df_list[df_list['type'] == '承認待']
                if df_app.empty:
                    st.info("承認待ち案件はありません")
                else:
                    for i, row in df_app.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**No.{row['ringi_id']} {row['subject']}**")
                            st.write(f"申請者: {row['applicant_name']} | ¥{row['amount']:,}")
                            
                            # 内容・ファイル
                            detail = conn.query(f"SELECT content FROM T_Ringi_Header WHERE ringi_id={row['ringi_id']}", ttl=0).iloc[0]
                            with st.expander("申請内容の詳細を見る"):
                                st.text(detail['content'])
                                files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                                for _, f in files.iterrows():
                                    st.markdown(f"📎 [{f['file_name']}]({f['file_url']})")

                            # ★コメント入力欄★
                            st.markdown("---")
                            comment = st.text_input("💬 コメント / 申し送り事項 (任意)", key=f"cmt_{row['ringi_id']}", placeholder="例: 金額妥当と判断します。")
                            
                            c_a, c_b = st.columns(2)
                            with c_a:
                                if st.button("承認する", key=f"app_{row['ringi_id']}", type="primary", use_container_width=True):
                                    with conn.session as s:
                                        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                                        # コメントも一緒に保存
                                        s.execute(
                                            text("UPDATE T_Ringi_Approvals SET status='承認', approver_name=:nm, approved_at=:at, comment=:cm WHERE ringi_id=:rid AND approver_role=:role"),
                                            {"nm": my_name, "at": now, "cm": comment, "rid": row['ringi_id'], "role": my_role}
                                        )
                                        # 最終決裁判定
                                        is_final = (my_role == "社長")
                                        if is_final:
                                            s.execute(text("UPDATE T_Ringi_Header SET status='決裁完了' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                        
                                        s.commit()
                                    
                                    # メール通知 (シミュレーション)
                                    send_email_notification("applicant@example.com", f"【承認】{row['subject']}", f"{my_name}が承認しました。コメント: {comment}")
                                    st.success("承認しました")
                                    st.rerun()
                            with c_b:
                                if st.button("却下する", key=f"rej_{row['ringi_id']}", use_container_width=True):
                                     with conn.session as s:
                                        # 却下時もコメント保存
                                        s.execute(
                                            text("UPDATE T_Ringi_Approvals SET status='却下', approver_name=:nm, comment=:cm WHERE ringi_id=:rid AND approver_role=:role"),
                                            {"nm": my_name, "cm": comment, "rid": row['ringi_id'], "role": my_role}
                                        )
                                        s.execute(text("UPDATE T_Ringi_Header SET status='却下' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                        s.commit()
                                     
                                     send_email_notification("applicant@example.com", f"【却下】{row['subject']}", f"理由: {comment}")
                                     st.error("却下しました")
                                     st.rerun()

    # ==================================================
    # モードB: 編集画面 (変更なし)
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        # (前回のコードと同じため、中略なしで記述します)
        edit_id = st.session_state.get("editing_ringi_id")
        is_new = edit_id is None
        st.subheader("📝 稟議書作成" if is_new else "✏️ 稟議書編集")
        
        default_subject = ""
        default_amount = 0
        default_content = ""
        if not is_new:
            existing = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {edit_id}", ttl=0).iloc[0]
            default_subject = existing["subject"]
            default_amount = existing["amount"]
            default_content = existing["content"]

        with st.form("ringi_form"):
            subject = st.text_input("件名", value=default_subject)
            amount = st.number_input("金額 (円)", value=default_amount, step=1000)
            content = st.text_area("内容", value=default_content, height=150)
            uploaded_files = st.file_uploader("添付ファイル追加", accept_multiple_files=True)
            
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.form_submit_button("キャンセル"):
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c2:
                if st.form_submit_button("下書き保存"):
                    save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "下書き", uploaded_files)
                    st.toast("下書き保存しました")
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c3:
                if st.form_submit_button("申請する", type="primary"):
                    if not subject: st.warning("件名は必須です")
                    else:
                        save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "申請中", uploaded_files)
                        # 申請メール通知
                        send_email_notification("manager@example.com", f"【新規申請】{subject}", f"{my_name}から申請がありました。")
                        st.success("申請しました！")
                        st.session_state["page_mode"] = "list"
                        st.rerun()

def save_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files):
    with conn.session as s:
        target_id = ringi_id
        if is_new:
            row = s.execute(text("INSERT INTO T_Ringi_Header (applicant_name, applicant_email, subject, amount, content, status) VALUES (:nm, :em, :sub, :amt, :cnt, :st) RETURNING ringi_id"),
                            {"nm": name, "em": email, "sub": subject, "amt": amount, "cnt": content, "st": status}).fetchone()
            target_id = row[0]
        else:
            s.execute(text("UPDATE T_Ringi_Header SET subject=:sub, amount=:amt, content=:cnt, status=:st WHERE ringi_id=:rid"),
                      {"sub": subject, "amt": amount, "cnt": content, "st": status, "rid": ringi_id})
        
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url: s.execute(text("INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url) VALUES (:rid, :fn, :fu)"), {"rid": target_id, "fn": f_name, "fu": f_url})

        if status == "申請中":
            check = s.execute(text(f"SELECT count(*) FROM T_Ringi_Approvals WHERE ringi_id={target_id}")).fetchone()[0]
            if check == 0:
                for r in ["課長", "部長", "社長"]:
                    s.execute(text("INSERT INTO T_Ringi_Approvals (ringi_id, approver_role) VALUES (:rid, :role)"), {"rid": target_id, "role": r})
        s.commit()

if __name__ == "__main__":
    main()