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

# フォーム初期値の設定関数
def init_form_state(data=None):
    if data:
        st.session_state["form_subject"] = data["subject"]
        st.session_state["form_amount"] = data["amount"]
        st.session_state["form_content"] = data["content"]
        st.session_state["form_fy"] = data.get("fiscal_year")
        st.session_state["form_cat"] = data.get("budget_category")
        st.session_state["form_phase"] = data.get("phase")
        # カスタムデータは動的なので別途読み込みが必要だが、簡易的にここで保持
        if data.get('custom_data'):
            c_data = data['custom_data']
            if isinstance(c_data, str): c_data = json.loads(c_data)
            for k, v in c_data.items():
                st.session_state[f"custom_{k}"] = v
    else:
        # 新規時の初期値
        st.session_state["form_subject"] = ""
        st.session_state["form_amount"] = 0
        st.session_state["form_content"] = ""
        st.session_state["form_fy"] = 2025
        st.session_state["form_cat"] = "予算内"
        st.session_state["form_phase"] = "執行"
        # カスタムフィールドのキーもクリアしたいが、動的なため上書きされるのを期待

# --- メイン処理 ---
def main():
    st.title("🈸 業務ワークフロー (申請・報告)")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.error("ログインしてください。")
        st.stop()
    
    my_email = st.session_state["user_email"]
    conn = st.connection("supabase", type="sql")

    # ユーザー情報の取得
    try:
        user_sql = f"SELECT id, display_name, role, department_id FROM public.profiles WHERE email = '{my_email}'"
        user_df = conn.query(user_sql, ttl=60)
        if user_df.empty:
            st.error("ユーザー情報が見つかりません。管理者にお問い合わせください。")
            st.stop()
        my_user = user_df.iloc[0]
        my_uuid = my_user['id']
        my_name = my_user['display_name']
        my_role = my_user['role']
    except Exception as e:
        st.error(f"DB接続エラー: {e}")
        st.stop()

    if st.button("＋ 新規起案", type="primary", use_container_width=True):
        st.session_state["editing_workflow_id"] = None
        st.session_state["page_mode"] = "edit"
        st.session_state["draft_route"] = [] 
        # フォーム初期化
        init_form_state(None)
        st.rerun()

    st.markdown("---")

    if "page_mode" not in st.session_state:
        st.session_state["page_mode"] = "list"

    # ==================================================
    # モードA: 一覧画面
    # ==================================================
    if st.session_state["page_mode"] == "list":
        sql_my_app = f"""
            SELECT h.workflow_id, h.created_at, h.subject, h.amount, h.status, p.display_name as applicant_name, '起案分' as type 
            FROM T_Workflow_Header h
            JOIN public.profiles p ON h.applicant_id = p.id
            WHERE h.applicant_id = '{my_uuid}'
        """
        sql_to_approve = f"""
            UNION ALL
            SELECT h.workflow_id, h.created_at, h.subject, h.amount, '確認・承認待ち' as status, p.display_name as applicant_name, '受信トレイ' as type
            FROM T_Workflow_Header h
            JOIN T_Workflow_Approvals a ON h.workflow_id = a.workflow_id
            JOIN public.profiles p ON h.applicant_id = p.id
            WHERE a.approver_id = '{my_uuid}' AND a.status = '未承認' AND h.status != '却下'
        """
        final_sql = f"SELECT * FROM ({sql_my_app} {sql_to_approve}) AS merged ORDER BY workflow_id DESC"
        df_list = conn.query(final_sql, ttl=0)

        tab1, tab2 = st.tabs(["📋 全案件ステータス", "✅ 受信トレイ (確認・承認)"])
        
        with tab1:
            df_view = df_list[df_list['type'] == '起案分']
            if df_view.empty: st.info("データなし")
            else:
                st.dataframe(df_view[["workflow_id", "created_at", "subject", "amount", "status"]], use_container_width=True, hide_index=True)
                selected_id = st.selectbox("案件詳細を確認", df_view["workflow_id"], index=None)
                if selected_id:
                    row = conn.query(f"SELECT * FROM T_Workflow_Header WHERE workflow_id = {selected_id}", ttl=0).iloc[0]
                    with st.container(border=True):
                        st.subheader(f"{row['subject']}")
                        
                        if row["status"] in ["下書き", "差戻し"]:
                            msg = "下書き編集中" if row["status"] == "下書き" else "⚠️ 差戻し案件です。内容を修正して再提出してください。"
                            st.warning(msg)
                            if st.button("✏️ 編集・再提出する"):
                                st.session_state["editing_workflow_id"] = selected_id
                                st.session_state["page_mode"] = "edit"
                                # 既存データの読み込みとStateへのセット
                                init_form_state(row)
                                # ルート復元
                                existing_route = conn.query(f"SELECT approver_id, approver_name, approver_role FROM T_Workflow_Approvals WHERE workflow_id={selected_id} ORDER BY step_order", ttl=0)
                                restored_route = []
                                for _, r_row in existing_route.iterrows():
                                    restored_route.append({"id": r_row['approver_id'], "name": r_row['approver_name'], "role": r_row['approver_role']})
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
                            steps = conn.query(f"SELECT step_order, approver_role, approver_name, status, comment FROM T_Workflow_Approvals WHERE workflow_id = {selected_id} ORDER BY step_order", ttl=0)
                            for idx, s_row in steps.iterrows():
                                icon = "✅" if s_row['status'] == '承認' else ("↩️" if s_row['status'] == '差戻し' else ("❌" if s_row['status'] == '却下' else "⏳"))
                                st.write(f"{icon} {s_row['approver_name']} ({s_row['status']})")
                                if s_row['comment']: st.info(f"💬 {s_row['comment']}")

        with tab2:
            df_app = df_list[df_list['type'] == '受信トレイ']
            if df_app.empty: st.info("承認待ち案件はありません")
            else:
                for i, row in df_app.iterrows():
                    with st.container(border=True):
                        st.markdown(f"**No.{row['workflow_id']} {row['subject']}**")
                        st.caption(f"起案者: {row['applicant_name']}")
                        
                        detail_row = conn.query(f"SELECT * FROM T_Workflow_Header WHERE workflow_id={row['workflow_id']}", ttl=0).iloc[0]
                        with st.expander("詳細を見る"):
                            if detail_row.get('phase') and detail_row.get('phase') != 'None':
                                st.caption(f"💰 {detail_row.get('fiscal_year', '-')}年度 | {detail_row.get('budget_category', '-')} | {detail_row.get('phase', '-')}")
                            if detail_row['custom_data']:
                                c_data = detail_row['custom_data']
                                if isinstance(c_data, str): c_data = json.loads(c_data)
                                for k, v in c_data.items(): st.write(f"**{k}:** {v}")
                            else:
                                st.text(detail_row['content'])
                            files = conn.query(f"SELECT file_name, file_path FROM T_Workflow_Attachments WHERE workflow_id = {row['workflow_id']}", ttl=0)
                            for _, f in files.iterrows(): 
                                st.markdown(f"📎 {f['file_name']}") 
                        
                        # --- ルート変更機能 ---
                        with st.expander("⚙️ 承認ルートの確認・変更"):
                            current_step_df = conn.query(f"SELECT step_order FROM T_Workflow_Approvals WHERE workflow_id={row['workflow_id']} AND approver_id='{my_uuid}'", ttl=0)
                            if not current_step_df.empty:
                                current_step_order = current_step_df.iloc[0]['step_order']
                                future_steps = conn.query(f"SELECT approval_id, approver_name, approver_role, approver_id FROM T_Workflow_Approvals WHERE workflow_id={row['workflow_id']} AND step_order > {current_step_order} ORDER BY step_order", ttl=0)
                                
                                future_route_key = f"future_route_{row['workflow_id']}"
                                if future_route_key not in st.session_state:
                                    st.session_state[future_route_key] = []
                                    for _, fs in future_steps.iterrows():
                                        st.session_state[future_route_key].append({
                                            "id": fs['approver_id'], "name": fs['approver_name'], "role": fs['approver_role']
                                        })

                                st.caption("▼ 現在予定されている後続のルート")
                                current_future = st.session_state[future_route_key]
                                
                                users_df = conn.query("SELECT display_name, role, id FROM public.profiles ORDER BY role DESC", ttl=60)
                                u_opts = {f"{r['display_name']} ({r['role']})": r for _, r in users_df.iterrows()}
                                add_u = st.selectbox("承認者を追加", list(u_opts.keys()), key=f"add_sel_{row['workflow_id']}")
                                if st.button("最後尾に追加", key=f"add_btn_{row['workflow_id']}"):
                                    u_data = u_opts[add_u]
                                    st.session_state[future_route_key].append({"id": u_data['id'], "name": u_data['display_name'], "role": u_data['role']})
                                    st.rerun()

                                if not current_future:
                                    st.info("後続の承認者はいません。")
                                else:
                                    for idx, fr in enumerate(current_future):
                                        fc1, fc2, fc3 = st.columns([0.5, 4, 1])
                                        with fc1: st.write(f"次+{idx+1}")
                                        with fc2: st.write(f"**{fr['name']}** ({fr['role']})")
                                        with fc3: 
                                            if st.button("削除", key=f"del_f_{row['workflow_id']}_{idx}"):
                                                st.session_state[future_route_key].pop(idx)
                                                st.rerun()

                        comment = st.text_input("💬 コメント / 申し送り事項", key=f"cmt_{row['workflow_id']}")
                        c_a, c_b = st.columns(2)
                        
                        with c_a:
                            if st.button("承認 / 回付", key=f"app_{row['workflow_id']}", type="primary", use_container_width=True):
                                with conn.session as s:
                                    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                                    s.execute(text("UPDATE T_Workflow_Approvals SET status='承認', approved_at=:at, comment=:cm WHERE workflow_id=:rid AND approver_id=:uid"), 
                                                {"at": now, "cm": comment, "rid": row['workflow_id'], "uid": my_uuid})
                                    
                                    current_step_df = conn.query(f"SELECT step_order FROM T_Workflow_Approvals WHERE workflow_id={row['workflow_id']} AND approver_id='{my_uuid}'", ttl=0)
                                    cur_step = current_step_df.iloc[0]['step_order']
                                    
                                    s.execute(text(f"DELETE FROM T_Workflow_Approvals WHERE workflow_id={row['workflow_id']} AND step_order > {cur_step}"))
                                    
                                    future_route_key = f"future_route_{row['workflow_id']}"
                                    if future_route_key in st.session_state:
                                        new_route = st.session_state[future_route_key]
                                        for i, usr in enumerate(new_route):
                                            s.execute(text("""
                                                INSERT INTO T_Workflow_Approvals (workflow_id, step_order, approver_id, approver_name, approver_role)
                                                VALUES (:rid, :ord, :uid, :nm, :role)
                                            """), {"rid": row['workflow_id'], "ord": cur_step + 1 + i, "uid": usr['id'], "nm": usr['name'], "role": usr['role']})
                                        del st.session_state[future_route_key]

                                    pending = s.execute(text(f"SELECT count(*) FROM T_Workflow_Approvals WHERE workflow_id={row['workflow_id']} AND status='未承認'")).fetchone()[0]
                                    if pending == 0:
                                        s.execute(text("UPDATE T_Workflow_Header SET status='決裁完了' WHERE workflow_id=:rid"), {"rid": row['workflow_id']})
                                    s.commit()
                                
                                send_email_notification("next@example.com", f"【承認・回付】{row['subject']}", f"{my_name}が承認しました。")
                                st.success("承認し、次のステップへ回しました")
                                st.rerun()

                        with c_b:
                            if st.button("差戻し", key=f"remand_{row['workflow_id']}", use_container_width=True):
                                 with conn.session as s:
                                    s.execute(text("UPDATE T_Workflow_Approvals SET status='差戻し', approved_at=:at, comment=:cm WHERE workflow_id=:rid AND approver_id=:uid"), 
                                                {"at": datetime.datetime.now(), "cm": comment, "rid": row['workflow_id'], "uid": my_uuid})
                                    s.execute(text("UPDATE T_Workflow_Header SET status='差戻し' WHERE workflow_id=:rid"), {"rid": row['workflow_id']})
                                    s.commit()
                                 send_email_notification("applicant@example.com", f"【差戻】{row['subject']}", f"修正依頼: {comment}")
                                 st.warning("差し戻しました")
                                 st.rerun()

    # ==================================================
    # モードB: 編集・起案画面
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        edit_id = st.session_state.get("editing_workflow_id")
        is_new = edit_id is None
        
        # セッションステート初期化チェック (ページリロード対策)
        if "form_subject" not in st.session_state:
            init_form_state(None)

        page_title = "📝 新規起案" if is_new else "✏️ 案件編集・再提出"
        st.subheader(page_title)
        
        templates_df = conn.query("SELECT * FROM M_Templates ORDER BY template_id", ttl=60)
        template_options = {row['template_name']: row for i, row in templates_df.iterrows()}
        
        # 既存データのテンプレート名を特定 (編集時)
        selected_template_name = None
        if not is_new and edit_id:
            existing = conn.query(f"SELECT template_id FROM T_Workflow_Header WHERE workflow_id = {edit_id}", ttl=0).iloc[0]
            if existing['template_id']:
                temp_row = templates_df[templates_df['template_id'] == existing['template_id']]
                if not temp_row.empty: selected_template_name = temp_row.iloc[0]['template_name']

        template_name = st.selectbox("案件の種類", options=["標準フォーマット"] + list(template_options.keys()), index=0 if not selected_template_name else (["標準フォーマット"] + list(template_options.keys())).index(selected_template_name))
        is_standard = (template_name == "標準フォーマット")

        # --- フォーム入力部 (st.form廃止, keyでState管理) ---
        st.markdown("##### 1. 基本情報")
        # keyを指定することで、Stateに直接値を書き込む
        st.text_input("件名", key="form_subject")
        
        fiscal_year = None
        budget_cat = None
        phase = None
        amount = 0

        if not is_standard:
            st.caption("※ 金額が発生する場合のみ入力してください")
            c_y, c_c, c_p = st.columns(3)
            with c_y: st.number_input("対象年度", step=1, key="form_fy")
            with c_c: st.selectbox("予算区分", ["予算内", "突発(予算外)", "その他"], key="form_cat")
            with c_p: st.selectbox("フェーズ", ["執行", "計画(来期予算等)", "報告のみ"], key="form_phase")
            st.number_input("金額 (円)", step=1000, key="form_amount")
        else:
            st.number_input("金額 (円) ※必要な場合のみ", step=1000, key="form_amount")

        st.markdown("##### 2. 詳細内容")
        custom_values = {}
        selected_template_id = None
        
        if is_standard:
            st.text_area("報告事項・内容", height=150, key="form_content")
        else:
            target_temp = template_options[template_name]
            selected_template_id = int(target_temp['template_id'])
            schema = target_temp['schema_json']
            if isinstance(schema, str): schema = json.loads(schema)
            
            # ダイナミックフォーム生成
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
                        # 動的フィールドもkeyで管理
                        field_key = f"custom_{label}"
                        
                        if typ == "text": st.text_input(label, key=field_key)
                        elif typ == "number": st.number_input(label, step=1, key=field_key)
                        elif typ == "date": st.date_input(label, key=field_key)
                        elif typ == "textarea": st.text_area(label, key=field_key)
                        elif typ == "select":
                            opts = field.get('options', [])
                            st.selectbox(label, opts, key=field_key)
                        elif typ == "checkbox": st.checkbox(label, key=field_key)
                        
                        # 保存用に値を収集
                        if field_key in st.session_state:
                            val = st.session_state[field_key]
                            if isinstance(val, (datetime.date, datetime.datetime)): custom_values[label] = str(val)
                            else: custom_values[label] = val

        st.markdown("##### 3. 添付ファイル")
        uploaded_files = st.file_uploader("資料", accept_multiple_files=True)
        
        if st.button("キャンセル"):
            st.session_state["page_mode"] = "list"
            st.rerun()

        # ルートビルダー
        st.markdown("##### 4. 回付・承認ルート設定")
        with st.container(border=True):
            users_df = conn.query("SELECT display_name, role, id FROM public.profiles ORDER BY role DESC", ttl=60)
            user_options = {f"{row['display_name']} ({row['role']})": row for i, row in users_df.iterrows()}
            
            c_add1, c_add2 = st.columns([3, 1])
            with c_add1:
                selected_user_label = st.selectbox("追加する人を選択", list(user_options.keys()), key="route_adder")
            with c_add2:
                # フォームがないので、ここでボタンを押しても入力値（State）は保持されたままリランされる
                if st.button("ルートに追加"):
                    u_row = user_options[selected_user_label]
                    if "draft_route" not in st.session_state: st.session_state["draft_route"] = []
                    st.session_state["draft_route"].append({"id": u_row['id'], "name": u_row['display_name'], "role": u_row['role']})
                    st.rerun()

            if not st.session_state.get("draft_route"):
                st.info("ルートが設定されていません")
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

        st.markdown("---")
        col_final1, col_final2 = st.columns(2)
        with col_final1:
            if st.button("下書き保存", use_container_width=True):
                 # Stateから値を取得
                 sub = st.session_state.get("form_subject")
                 amt = st.session_state.get("form_amount")
                 cnt = st.session_state.get("form_content")
                 fy = st.session_state.get("form_fy")
                 cat = st.session_state.get("form_cat")
                 ph = st.session_state.get("form_phase")
                 
                 save_data(conn, is_new, edit_id, my_uuid, sub, amt, cnt, "下書き", uploaded_files, st.session_state.get("draft_route", []), selected_template_id, custom_values, fy, cat, ph)
                 st.toast("下書き保存しました")
                 st.session_state["page_mode"] = "list"
                 st.rerun()
        with col_final2:
            btn_label = "起案・回付する" if is_new else "修正して再提出する"
            if st.button(btn_label, type="primary", use_container_width=True):
                sub = st.session_state.get("form_subject")
                
                if not sub: st.warning("件名を入力してください")
                elif not st.session_state.get("draft_route"): st.warning("回付ルートを設定してください")
                else:
                    amt = st.session_state.get("form_amount")
                    cnt = st.session_state.get("form_content")
                    fy = st.session_state.get("form_fy")
                    cat = st.session_state.get("form_cat")
                    ph = st.session_state.get("form_phase")
                    
                    save_data(conn, is_new, edit_id, my_uuid, sub, amt, cnt, "申請中", uploaded_files, st.session_state["draft_route"], selected_template_id, custom_values, fy, cat, ph)
                    st.success("回付を開始しました！")
                    st.session_state["page_mode"] = "list"
                    st.rerun()

def save_data(conn, is_new, workflow_id, uid, subject, amount, content, status, files, approver_list, template_id, custom_data, fy, cat, ph):
    with conn.session as s:
        target_id = workflow_id
        json_str = json.dumps(custom_data, ensure_ascii=False) if custom_data else None
        
        if is_new:
            row = s.execute(text("INSERT INTO T_Workflow_Header (applicant_id, subject, amount, content, status, template_id, custom_data, fiscal_year, budget_category, phase) VALUES (:uid, :sub, :amt, :cnt, :st, :tid, :cdata, :fy, :cat, :ph) RETURNING workflow_id"),
                            {"uid": uid, "sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str, "fy": fy, "cat": cat, "ph": ph}).fetchone()
            target_id = row[0]
        else:
            s.execute(text("UPDATE T_Workflow_Header SET subject=:sub, amount=:amt, content=:cnt, status=:st, template_id=:tid, custom_data=:cdata, fiscal_year=:fy, budget_category=:cat, phase=:ph WHERE workflow_id=:rid"),
                      {"sub": subject, "amt": amount, "cnt": content, "st": status, "tid": template_id, "cdata": json_str, "rid": workflow_id, "fy": fy, "cat": cat, "ph": ph})
        
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url: s.execute(text("INSERT INTO T_Workflow_Attachments (workflow_id, file_name, file_path) VALUES (:rid, :fn, :fp)"), {"rid": target_id, "fn": f_name, "fp": f_url})

        if status == "申請中" and approver_list:
            s.execute(text(f"DELETE FROM T_Workflow_Approvals WHERE workflow_id={target_id}"))
            for i, user in enumerate(approver_list):
                s.execute(text("INSERT INTO T_Workflow_Approvals (workflow_id, step_order, approver_id, approver_name, approver_role) VALUES (:rid, :ord, :uid, :nm, :role)"),
                          {"rid": target_id, "ord": i+1, "uid": user['id'], "nm": user['name'], "role": user['role']})
        s.commit()

if __name__ == "__main__":
    main()