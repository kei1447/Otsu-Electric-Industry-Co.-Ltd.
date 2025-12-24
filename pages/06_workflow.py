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

# --- Supabase初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets設定エラー")
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
    st.title("🈸 業務ワークフロー (申請・報告)")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.error("ログインしてください。")
        st.stop()
    
    my_name = st.session_state["user_name"]
    my_role = st.session_state["role"]
    my_email = st.session_state["user_email"]

    conn = st.connection("supabase", type="sql")

    if st.button("＋ 新規起案", type="primary", use_container_width=True):
        st.session_state["editing_ringi_id"] = None
        st.session_state["page_mode"] = "edit"
        # ルートビルダー用の初期化
        st.session_state["draft_route"] = [] 
        st.rerun()

    st.markdown("---")

    if "page_mode" not in st.session_state:
        st.session_state["page_mode"] = "list"

    # ==================================================
    # モードA: 一覧画面 (前回と同じ)
    # ==================================================
    if st.session_state["page_mode"] == "list":
        sql_my_app = f"SELECT ringi_id, created_at, subject, amount, status, applicant_name, '起案分' as type FROM T_Ringi_Header WHERE applicant_email = '{my_email}'"
        sql_to_approve = f"""
            UNION ALL
            SELECT h.ringi_id, h.created_at, h.subject, h.amount, '確認・承認待ち' as status, h.applicant_name, '受信トレイ' as type
            FROM T_Ringi_Header h
            JOIN T_Ringi_Approvals a ON h.ringi_id = a.ringi_id
            WHERE a.approver_id = '{my_email}' AND a.status = '未承認' AND h.status != '却下'
        """
        final_sql = f"SELECT * FROM ({sql_my_app} {sql_to_approve}) AS merged ORDER BY ringi_id DESC"
        df_list = conn.query(final_sql, ttl=0)

        tab1, tab2 = st.tabs(["📋 全案件ステータス", "✅ 受信トレイ (確認・承認)"])
        
        with tab1:
            df_view = df_list[df_list['type'] == '起案分']
            if df_view.empty: st.info("データなし")
            else:
                st.dataframe(df_view[["ringi_id", "created_at", "subject", "amount", "status"]], use_container_width=True, hide_index=True)
                selected_id = st.selectbox("案件詳細を確認", df_view["ringi_id"], index=None)
                if selected_id:
                    row = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {selected_id}", ttl=0).iloc[0]
                    with st.container(border=True):
                        st.subheader(f"{row['subject']}")
                        if row["status"] == "下書き":
                            if st.button("✏️ 編集・回付する"):
                                st.session_state["editing_ringi_id"] = selected_id
                                st.session_state["page_mode"] = "edit"
                                # 既存ルートの復元ロジックが必要だが、今回は簡易的に空リセットまたはDBから再取得
                                # DBからルートを読み込んで draft_route に入れる
                                existing_route = conn.query(f"SELECT approver_id, approver_name, approver_role FROM T_Ringi_Approvals WHERE ringi_id={selected_id} ORDER BY step_order", ttl=0)
                                restored_route = []
                                for _, r_row in existing_route.iterrows():
                                    restored_route.append({
                                        "id": r_row['approver_id'], 
                                        "name": r_row['approver_name'], 
                                        "role": r_row['approver_role']
                                    })
                                st.session_state["draft_route"] = restored_route
                                st.rerun()
                        else:
                            st.write(f"**ステータス:** {row['status']}")
                            if row.get('phase') and row.get('phase') != 'None':
                                st.caption(f"💰 {row.get('fiscal_year', '-')}年度 | {row.get('budget_category', '-')} | {row.get('phase', '-')}")
                            if row['custom_data']:
                                st.markdown("---")
                                c_data = row['custom_data']
                                if isinstance(c_data, str): c_data = json.loads(c_data)
                                for k, v in c_data.items(): st.write(f"**{k}:** {v}")
                            else:
                                st.write(f"**内容:** {row['content']}")
                            st.markdown("---")
                            steps = conn.query(f"SELECT step_order, approver_role, approver_name, status, comment FROM T_Ringi_Approvals WHERE ringi_id = {selected_id} ORDER BY step_order", ttl=0)
                            for idx, s_row in steps.iterrows():
                                icon = "✅" if s_row['status'] == '承認' else ("❌" if s_row['status'] == '却下' else "⏳")
                                st.write(f"{icon} {s_row['approver_name']} ({s_row['status']})")
                                if s_row['comment']: st.info(f"💬 {s_row['comment']}")

        with tab2:
            df_app = df_list[df_list['type'] == '受信トレイ']
            if df_app.empty: st.info("現在、あなたへの回付案件はありません")
            else:
                for i, row in df_app.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**No.{row['ringi_id']} {row['subject']}**")
                        st.caption(f"起案者: {row['applicant_name']}")
                        detail_row = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id={row['ringi_id']}", ttl=0).iloc[0]
                        with st.expander("詳細を見る"):
                            if detail_row.get('phase') and detail_row.get('phase') != 'None':
                                st.caption(f"💰 {detail_row.get('fiscal_year', '-')}年度 | {detail_row.get('budget_category', '-')} | {detail_row.get('phase', '-')}")
                            if detail_row['custom_data']:
                                c_data = detail_row['custom_data']
                                if isinstance(c_data, str): c_data = json.loads(c_data)
                                for k, v in c_data.items(): st.write(f"**{k}:** {v}")
                            else:
                                st.text(detail_row['content'])
                            files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                            for _, f in files.iterrows(): st.markdown(f"📎 [{f['file_name']}]({f['file_url']})")
                        
                        comment = st.text_input("💬 コメント", key=f"cmt_{row['ringi_id']}")
                        c_a, c_b = st.columns(2)
                        with c_a:
                            if st.button("承認 / 確認済", key=f"app_{row['ringi_id']}", type="primary", use_container_width=True):
                                with conn.session as s:
                                    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                                    s.execute(text("UPDATE T_Ringi_Approvals SET status='承認', approved_at=:at, comment=:cm WHERE ringi_id=:rid AND approver_id=:uid"), {"at": now, "cm": comment, "rid": row['ringi_id'], "uid": my_email})
                                    pending = s.execute(text(f"SELECT count(*) FROM T_Ringi_Approvals WHERE ringi_id={row['ringi_id']} AND status='未承認'")).fetchone()[0]
                                    if pending == 0: s.execute(text("UPDATE T_Ringi_Header SET status='決裁完了' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                    s.commit()
                                send_email_notification("applicant@example.com", f"【完了】{row['subject']}", f"{my_name}が確認しました。")
                                st.success("処理しました")
                                st.rerun()
                        with c_b:
                            if st.button("差戻し / 却下", key=f"rej_{row['ringi_id']}", use_container_width=True):
                                 with conn.session as s:
                                    s.execute(text("UPDATE T_Ringi_Approvals SET status='却下', approved_at=:at, comment=:cm WHERE ringi_id=:rid AND approver_id=:uid"), {"at": datetime.datetime.now(), "cm": comment, "rid": row['ringi_id'], "uid": my_email})
                                    s.execute(text("UPDATE T_Ringi_Header SET status='却下' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                    s.commit()
                                 send_email_notification("applicant@example.com", f"【差戻】{row['subject']}", f"理由: {comment}")
                                 st.error("差し戻しました")
                                 st.rerun()

    # ==================================================
    # モードB: 編集・起案画面
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        edit_id = st.session_state.get("editing_ringi_id")
        is_new = edit_id is None
        st.subheader("📝 新規起案" if is_new else "✏️ 案件編集")
        
        templates_df = conn.query("SELECT * FROM M_Templates ORDER BY template_id", ttl=60)
        template_options = {row['template_name']: row for i, row in templates_df.iterrows()}
        
        # 初期値
        default_subject = ""
        default_amount = 0
        default_content = ""
        default_fy = None
        default_cat = None
        default_phase = None
        selected_template_name = None
        loaded_custom_data = {}

        if not is_new:
            existing = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {edit_id}", ttl=0).iloc[0]
            default_subject = existing["subject"]
            default_amount = existing["amount"]
            default_content = existing["content"]
            default_fy = existing.get("fiscal_year")
            default_cat = existing.get("budget_category")
            default_phase = existing.get("phase")
            if existing['template_id']:
                temp_row = templates_df[templates_df['template_id'] == existing['template_id']]
                if not temp_row.empty: selected_template_name = temp_row.iloc[0]['template_name']
            if existing['custom_data']:
                loaded_custom_data = existing['custom_data']
                if isinstance(loaded_custom_data, str): loaded_custom_data = json.loads(loaded_custom_data)

        # テンプレート選択
        template_name = st.selectbox(
            "案件の種類", 
            options=["標準フォーマット"] + list(template_options.keys()),
            index=0 if not selected_template_name else (["標準フォーマット"] + list(template_options.keys())).index(selected_template_name)
        )
        is_standard = (template_name == "標準フォーマット")

        with st.form("ringi_form"):
            st.markdown("##### 1. 基本情報")
            subject = st.text_input("件名", value=default_subject, placeholder="例: ○○に関する報告、××購入の件")
            
            fiscal_year = None
            budget_cat = None
            phase = None
            amount = 0

            # ★標準フォーマット以外の場合のみ、予算情報を入力させる★
            if not is_standard:
                st.caption("※ 金額が発生する場合のみ入力してください")
                c_y, c_c, c_p = st.columns(3)
                with c_y: fiscal_year = st.number_input("対象年度", value=default_fy if default_fy else 2025, step=1)
                with c_c: budget_cat = st.selectbox("予算区分", ["予算内", "突発(予算外)", "その他"], index=["予算内", "突発(予算外)", "その他"].index(default_cat) if default_cat in ["予算内", "突発(予算外)", "その他"] else 0)
                with c_p: phase = st.selectbox("フェーズ", ["執行", "計画(来期予算等)", "報告のみ"], index=["執行", "計画(来期予算等)", "報告のみ"].index(default_phase) if default_phase in ["執行", "計画(来期予算等)", "報告のみ"] else 0)
                amount = st.number_input("金額 (円)", value=default_amount, step=1000)
            else:
                # 標準の場合は金額のみ（予算集計はしない）
                amount = st.number_input("金額 (円) ※必要な場合のみ", value=default_amount, step=1000)

            st.markdown("##### 2. 詳細内容")
            custom_values = {}
            selected_template_id = None
            
            if is_standard:
                content = st.text_area("報告事項・内容", value=default_content, height=150)
            else:
                target_temp = template_options[template_name]
                selected_template_id = int(target_temp['template_id'])
                schema = target_temp['schema_json']
                if isinstance(schema, str): schema = json.loads(schema)
                
                content = ""
                # レイアウトレンダリング
                fields = schema
                rows = []
                current_row = []
                current_w = 0
                for f in fields:
                    w = f.get('width', 100)
                    if current_w + w > 100:
                        rows.append(current_row)
                        current_row = []
                        current_w = 0
                    current_row.append(f)
                    current_w += w
                if current_row: rows.append(current_row)

                for row_fields in rows:
                    cols = st.columns([f.get('width', 100) for f in row_fields])
                    for col, field in zip(cols, row_fields):
                        with col:
                            label = field['label']
                            typ = field['type']
                            init_val = loaded_custom_data.get(label, "")
                            
                            if typ == "text": val = st.text_input(label, value=str(init_val))
                            elif typ == "number": val = st.number_input(label, value=int(init_val) if init_val else 0)
                            elif typ == "date":
                                d_val = None
                                if init_val:
                                    try: d_val = pd.to_datetime(init_val).date()
                                    except: pass
                                val = st.date_input(label, value=d_val)
                            elif typ == "textarea": val = st.text_area(label, value=str(init_val))
                            elif typ == "select":
                                opts = field.get('options', [])
                                idx = opts.index(init_val) if init_val in opts else 0
                                val = st.selectbox(label, opts, index=idx)
                            elif typ == "checkbox": val = st.checkbox(label, value=bool(init_val))
                            
                            if isinstance(val, (datetime.date, datetime.datetime)): custom_values[label] = str(val)
                            else: custom_values[label] = val

            st.markdown("##### 3. 添付ファイル")
            uploaded_files = st.file_uploader("資料", accept_multiple_files=True)
            
            # --- フォーム送信ボタン群 ---
            # ここではまだルート確定せず、ボタンでアクションする
            
            c1, c2 = st.columns([1, 1])
            with c1:
                # キャンセルや保存などのアクション
                if st.form_submit_button("キャンセル"):
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c2:
                # フォームの内容を一時保存（ルート設定へ進むため）はStreamlitの仕様上難しいので
                # ここで一気に確定させる必要があるが、ルートビルダーはFormの外に置く必要がある
                # (Formの中に動的なボタンを置くとリセットされるため)
                # 解決策：ルート設定エリアはフォームの外に出すか、
                # フォームのsubmitボタンを「確認画面へ」にするのが定石ですが、
                # 今回はシンプルに「ルート設定」をフォームの下に配置し、
                # 申請ボタンをフォームの外（または別のフォーム）にする構成に変更します。
                pass

        # --- ★ルートビルダー（フォームの外に配置して動的操作を可能に）---
        st.markdown("##### 4. 回付・承認ルート設定")
        with st.container(border=True):
            # ユーザーリスト取得
            users_df = conn.query("SELECT display_name, role, user_id FROM M_Users ORDER BY role DESC", ttl=60)
            user_options = {f"{row['display_name']} ({row['role']})": row for i, row in users_df.iterrows()}
            
            c_add1, c_add2 = st.columns([3, 1])
            with c_add1:
                selected_user_label = st.selectbox("追加する人を選択", list(user_options.keys()), key="route_adder")
            with c_add2:
                if st.button("ルートに追加"):
                    u_row = user_options[selected_user_label]
                    st.session_state["draft_route"].append({
                        "id": u_row['user_id'],
                        "name": u_row['display_name'],
                        "role": u_row['role']
                    })
                    st.rerun()

            # 現在のルート表示（並べ替え・削除）
            if not st.session_state.get("draft_route"):
                st.info("ルートが設定されていません。上から追加してください。")
            else:
                route = st.session_state["draft_route"]
                for i, r in enumerate(route):
                    c_idx, c_nm, c_up, c_down, c_del = st.columns([0.5, 4, 0.5, 0.5, 0.5])
                    with c_idx: st.write(f"{i+1}.")
                    with c_nm: st.write(f"**{r['name']}** ({r['role']})")
                    with c_up:
                        if i > 0 and st.button("↑", key=f"r_up_{i}"):
                            route[i], route[i-1] = route[i-1], route[i]
                            st.rerun()
                    with c_down:
                        if i < len(route) - 1 and st.button("↓", key=f"r_down_{i}"):
                            route[i], route[i+1] = route[i+1], route[i]
                            st.rerun()
                    with c_del:
                        if st.button("🗑", key=f"r_del_{i}"):
                            route.pop(i)
                            st.rerun()

        # --- 最終アクションエリア ---
        st.markdown("---")
        col_final1, col_final2 = st.columns(2)
        
        with col_final1:
            if st.button("下書き保存", use_container_width=True):
                 save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "下書き", uploaded_files, st.session_state["draft_route"], selected_template_id, custom_values, fiscal_year, budget_cat, phase)
                 st.toast("下書き保存しました")
                 st.session_state["page_mode"] = "list"
                 st.rerun()

        with col_final2:
            if st.button("起案・回付する", type="primary", use_container_width=True):
                # バリデーション
                if not subject:
                    st.warning("件名を入力してください")
                elif not st.session_state["draft_route"]:
                    st.warning("回付ルートを1人以上設定してください")
                else:
                    save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, "申請中", uploaded_files, st.session_state["draft_route"], selected_template_id, custom_values, fiscal_year, budget_cat, phase)
                    # メール通知はルートの1人目へ
                    first_approver = st.session_state["draft_route"][0]
                    send_email_notification(first_approver['id'], subject, "業務回付")
                    st.success("回付を開始しました！")
                    st.session_state["page_mode"] = "list"
                    st.rerun()

def save_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files, approver_list, template_id, custom_data, fy, cat, ph):
    with conn.session as s:
        target_id = ringi_id
        json_str = json.dumps(custom_data, ensure_ascii=False) if custom_data else None
        
        if is_new:
            row = s.execute(text("INSERT INTO T_Ringi_Header (applicant_name, applicant_email, subject, amount, content, status, template_id, custom_data, fiscal_year, budget_category, phase) VALUES (:nm, :em, :sub, :amt, :cnt, :st, :tid, :cdata, :fy, :cat, :ph) RETURNING ringi_id"),
                            {"nm": name, "em": email, "sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str, "fy": fy, "cat": cat, "ph": ph}).fetchone()
            target_id = row[0]
        else:
            s.execute(text("UPDATE T_Ringi_Header SET subject=:sub, amount=:amt, content=:cnt, status=:st, template_id=:tid, custom_data=:cdata, fiscal_year=:fy, budget_category=:cat, phase=:ph WHERE ringi_id=:rid"),
                      {"sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str, "rid": ringi_id, "fy": fy, "cat": cat, "ph": ph})
        
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url: s.execute(text("INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url) VALUES (:rid, :fn, :fu)"), {"rid": target_id, "fn": f_name, "fu": f_url})

        # ルート更新
        if approver_list: # 下書きでルート空の場合は更新しない運用も可だが、ここでは上書きする
            s.execute(text(f"DELETE FROM T_Ringi_Approvals WHERE ringi_id={target_id}"))
            for i, user in enumerate(approver_list):
                s.execute(text("INSERT INTO T_Ringi_Approvals (ringi_id, step_order, approver_id, approver_name, approver_role) VALUES (:rid, :ord, :uid, :nm, :role)"),
                          {"rid": target_id, "ord": i+1, "uid": user['id'], "nm": user['name'], "role": user['role']})
        s.commit()

if __name__ == "__main__":
    main()