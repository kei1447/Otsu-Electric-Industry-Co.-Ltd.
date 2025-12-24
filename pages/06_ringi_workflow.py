import streamlit as st
import pandas as pd
from sqlalchemy import text
import datetime
import uuid
import os
import json
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
        
        # 自分への承認待ち
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
                    # 詳細データ取得（custom_data含む）
                    row = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {selected_id}", ttl=0).iloc[0]
                    
                    with st.container(border=True):
                        st.subheader(f"{row['subject']}")
                        if row["status"] == "下書き":
                            if st.button("✏️ 編集・申請する"):
                                st.session_state["editing_ringi_id"] = selected_id
                                st.session_state["page_mode"] = "edit"
                                st.rerun()
                        else:
                            st.write(f"**ステータス:** {row['status']}")
                            
                            # ★カスタムデータの表示★
                            if row['custom_data']:
                                st.markdown("---")
                                st.caption("申請詳細:")
                                c_data = row['custom_data']
                                # JSONが文字列で入っている場合の対策
                                if isinstance(c_data, str):
                                    c_data = json.loads(c_data)
                                
                                # 辞書の中身をきれいに表示
                                for k, v in c_data.items():
                                    st.write(f"**{k}:** {v}")
                            else:
                                # 従来の内容表示
                                st.write(f"**内容:** {row['content']}")

                            st.markdown("---")
                            # フロー状況表示
                            steps = conn.query(f"SELECT step_order, approver_role, approver_name, status, comment FROM T_Ringi_Approvals WHERE ringi_id = {selected_id} ORDER BY step_order", ttl=0)
                            for idx, s_row in steps.iterrows():
                                icon = "✅" if s_row['status'] == '承認' else ("❌" if s_row['status'] == '却下' else "⏳")
                                st.write(f"{icon} {s_row['approver_name']} ({s_row['status']})")
                                if s_row['comment']: st.info(f"💬 {s_row['comment']}")

        with tab2:
            df_app = df_list[df_list['type'] == '承認待']
            if df_app.empty:
                st.info("承認依頼はありません")
            else:
                for i, row in df_app.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**No.{row['ringi_id']} {row['subject']}**")
                        st.write(f"申請者: {row['applicant_name']} | ¥{row['amount']:,}")
                        
                        # 詳細取得
                        detail_row = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id={row['ringi_id']}", ttl=0).iloc[0]
                        
                        with st.expander("申請内容の詳細を見る"):
                            # ★カスタムデータがあればそれを表示★
                            if detail_row['custom_data']:
                                c_data = detail_row['custom_data']
                                if isinstance(c_data, str): c_data = json.loads(c_data)
                                for k, v in c_data.items():
                                    st.write(f"**{k}:** {v}")
                            else:
                                st.text(detail_row['content'])
                                
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
                                    pending = s.execute(text(f"SELECT count(*) FROM T_Ringi_Approvals WHERE ringi_id={row['ringi_id']} AND status='未承認'")).fetchone()[0]
                                    if pending == 0:
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
    # モードB: 編集画面 (テンプレート対応版)
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        edit_id = st.session_state.get("editing_ringi_id")
        is_new = edit_id is None
        st.subheader("📝 稟議・申請作成")
        
        # --- 1. テンプレート選択 ---
        # 登録済みのテンプレートを取得
        templates_df = conn.query("SELECT * FROM M_Templates ORDER BY template_id", ttl=60)
        template_options = {row['template_name']: row for i, row in templates_df.iterrows()}
        
        # 初期値ロード
        default_subject = ""
        default_amount = 0
        default_content = ""
        selected_template_name = None
        loaded_custom_data = {}

        if not is_new:
            # 既存データ読み込み
            existing = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {edit_id}", ttl=0).iloc[0]
            default_subject = existing["subject"]
            default_amount = existing["amount"]
            default_content = existing["content"]
            
            # テンプレート情報の復元
            if existing['template_id']:
                temp_row = templates_df[templates_df['template_id'] == existing['template_id']]
                if not temp_row.empty:
                    selected_template_name = temp_row.iloc[0]['template_name']
            
            # カスタムデータの復元
            if existing['custom_data']:
                loaded_custom_data = existing['custom_data']
                if isinstance(loaded_custom_data, str):
                    loaded_custom_data = json.loads(loaded_custom_data)

        # テンプレート選択UI
        # (新規作成時、または既存データにテンプレートがある場合)
        template_name = st.selectbox(
            "申請書の種類 (テンプレート)", 
            options=["標準稟議書"] + list(template_options.keys()),
            index=0 if not selected_template_name else (["標準稟議書"] + list(template_options.keys())).index(selected_template_name)
        )

        with st.form("ringi_form"):
            # 共通ヘッダー項目
            subject = st.text_input("件名", value=default_subject)
            amount = st.number_input("金額 (円) ※予算管理用", value=default_amount, step=1000)
            
            # --- 2. 可変フォーム生成 ---
            custom_values = {} # ここに入力データを詰める
            selected_template_id = None
            
            if template_name == "標準稟議書":
                # 従来通りのテキストエリア
                content = st.text_area("内容・理由", value=default_content, height=150)
            else:
                # ★テンプレート展開ロジック★
                st.info(f"📋 {template_name} の入力フォーム")
                content = "" # 標準内容は使わないので空に
                
                # 選択されたテンプレの設計図(JSON)を取得
                target_temp = template_options[template_name]
                selected_template_id = int(target_temp['template_id'])
                schema = target_temp['schema_json']
                if isinstance(schema, str): schema = json.loads(schema)
                
                # 設計図に基づいてウィジェットをループ生成
                for field in schema:
                    label = field['label']
                    typ = field['type']
                    # 編集時は既存の値を初期値にする
                    init_val = loaded_custom_data.get(label, "")
                    
                    if typ == "text":
                        val = st.text_input(label, value=str(init_val))
                    elif typ == "number":
                        val = st.number_input(label, value=int(init_val) if init_val else 0)
                    elif typ == "date":
                        # 日付変換処理
                        d_val = None
                        if init_val:
                            try: d_val = pd.to_datetime(init_val).date()
                            except: pass
                        val = st.date_input(label, value=d_val)
                    elif typ == "textarea":
                        val = st.text_area(label, value=str(init_val))
                    elif typ == "select":
                        opts = field.get('options', [])
                        idx = opts.index(init_val) if init_val in opts else 0
                        val = st.selectbox(label, opts, index=idx)
                    elif typ == "checkbox":
                        val = st.checkbox(label, value=bool(init_val))
                    
                    # 辞書に格納 (日付などは文字列化しておくとJSON保存が楽)
                    if isinstance(val, (datetime.date, datetime.datetime)):
                        custom_values[label] = str(val)
                    else:
                        custom_values[label] = val

            st.markdown("---")
            uploaded_files = st.file_uploader("添付ファイル", accept_multiple_files=True)
            
            st.write("▼ 承認ルート設定")
            users_df = conn.query("SELECT display_name, role, user_id FROM M_Users ORDER BY role DESC", ttl=60)
            user_options = [f"{row['display_name']} ({row['role']})" for i, row in users_df.iterrows()]
            user_ids = users_df['user_id'].tolist()
            
            selected_approvers = st.multiselect("承認者を選択", options=user_options)

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.form_submit_button("キャンセル"):
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c2:
                if st.form_submit_button("下書き保存"):
                    save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "下書き", uploaded_files, [], selected_template_id, custom_values)
                    st.toast("保存しました")
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c3:
                if st.form_submit_button("申請する", type="primary"):
                    if not subject: st.warning("件名は必須です")
                    elif not selected_approvers: st.warning("承認ルートを設定してください")
                    else:
                        approver_data = []
                        for sel in selected_approvers:
                            idx = user_options.index(sel)
                            approver_data.append({"id": user_ids[idx], "name": users_df.iloc[idx]['display_name'], "role": users_df.iloc[idx]['role']})
                        
                        save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "申請中", uploaded_files, approver_data, selected_template_id, custom_values)
                        send_email_notification(approver_data[0]['id'], subject, "承認依頼")
                        st.success("申請しました！")
                        st.session_state["page_mode"] = "list"
                        st.rerun()

def save_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files, approver_list, template_id, custom_data):
    """保存処理（カスタムデータ対応版）"""
    with conn.session as s:
        target_id = ringi_id
        # custom_data (dict) をJSON文字列に変換
        json_str = json.dumps(custom_data, ensure_ascii=False) if custom_data else None
        
        if is_new:
            row = s.execute(
                text("""
                INSERT INTO T_Ringi_Header 
                (applicant_name, applicant_email, subject, amount, content, status, template_id, custom_data) 
                VALUES (:nm, :em, :sub, :amt, :cnt, :st, :tid, :cdata) 
                RETURNING ringi_id
                """),
                {"nm": name, "em": email, "sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str}
            ).fetchone()
            target_id = row[0]
        else:
            s.execute(
                text("""
                UPDATE T_Ringi_Header 
                SET subject=:sub, amount=:amt, content=:cnt, status=:st, template_id=:tid, custom_data=:cdata
                WHERE ringi_id=:rid
                """),
                {"sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str, "rid": ringi_id}
            )
        
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url: s.execute(text("INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url) VALUES (:rid, :fn, :fu)"), {"rid": target_id, "fn": f_name, "fu": f_url})

        if status == "申請中" and approver_list:
            s.execute(text(f"DELETE FROM T_Ringi_Approvals WHERE ringi_id={target_id}"))
            for i, user in enumerate(approver_list):
                s.execute(text("INSERT INTO T_Ringi_Approvals (ringi_id, step_order, approver_id, approver_name, approver_role) VALUES (:rid, :ord, :uid, :nm, :role)"),
                          {"rid": target_id, "ord": i+1, "uid": user['id'], "nm": user['name'], "role": user['role']})
        s.commit()

if __name__ == "__main__":
    main()