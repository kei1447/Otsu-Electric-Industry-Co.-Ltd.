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
    """ファイルをStorageにアップロードし、URLを返す"""
    if uploaded_file is None:
        return None, None
    try:
        file_ext = os.path.splitext(uploaded_file.name)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        
        file_bytes = uploaded_file.getvalue()
        supabase.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type}
        )
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
        return public_url, uploaded_file.name
    except Exception as e:
        st.error(f"Upload Error ({uploaded_file.name}): {e}")
        return None, None

def get_status_badge_color(status):
    """ステータスに応じた色コードを返す（UI用）"""
    if status == "下書き": return "gray"
    if status == "申請中": return "blue" # 正確には「回付中」
    if status == "承認": return "green"  # 完了
    if status == "決裁完了": return "green"
    if status == "却下": return "red"
    return "gray"

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

    # --- 上部：アクションメニュー ---
    col_act1, col_act2 = st.columns([1, 5])
    with col_act1:
        # 新規作成モードへの切り替えフラグ
        if st.button("＋ 新規作成", type="primary", use_container_width=True):
            st.session_state["editing_ringi_id"] = None # 新規
            st.session_state["page_mode"] = "edit"
            st.rerun()

    st.markdown("---")

    # --- 画面切り替えロジック ---
    # mode: "list" (一覧) / "edit" (作成・編集)
    if "page_mode" not in st.session_state:
        st.session_state["page_mode"] = "list"

    # ==================================================
    # モードA: ステータス一覧ボード (メイン画面)
    # ==================================================
    if st.session_state["page_mode"] == "list":
        
        # 1. データ取得（自分の申請 + 自分への承認待ち + 過去の承認履歴）
        # ※複雑になるので、まずは「自分が関わったもの全て」を表示します
        
        # 自分の申請
        sql_my_app = f"""
            SELECT ringi_id, created_at, subject, amount, status, applicant_name, '申請分' as type
            FROM T_Ringi_Header 
            WHERE applicant_email = '{my_email}'
        """
        
        # 自分への承認待ち（管理職のみ）
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

        # 2. タブ分け表示
        tab1, tab2 = st.tabs(["📋 全案件ステータス", "✅ 承認作業トレイ"])
        
        with tab1:
            st.caption("あなたが申請した案件、または下書き保存中の案件一覧です。")
            if df_list[df_list['type'] == '申請分'].empty:
                st.info("申請データはありません。")
            else:
                # 申請分のみ抽出
                df_view = df_list[df_list['type'] == '申請分'].copy()
                
                # 表示用データフレーム作成
                st.dataframe(
                    df_view[["ringi_id", "created_at", "subject", "amount", "status"]],
                    column_config={
                        "ringi_id": "No.",
                        "created_at": st.column_config.DatetimeColumn("日付", format="Y/M/D"),
                        "subject": "件名",
                        "amount": st.column_config.NumberColumn("金額", format="¥%d"),
                        "status": st.column_config.TextColumn("状態") # シンプルなテキストで
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                # 詳細確認・編集エリア
                st.write("▼ 詳細を確認・編集するにはIDを選択してください")
                selected_id = st.selectbox("案件を選択", df_view["ringi_id"], index=None, placeholder="詳細を見る...")
                
                if selected_id:
                    # 案件詳細の取得
                    row = df_view[df_view["ringi_id"] == selected_id].iloc[0]
                    
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.subheader(f"{row['subject']}")
                            # 下書きなら「編集」ボタン
                            if row["status"] == "下書き":
                                st.info("これは「下書き」です。編集して申請できます。")
                                if st.button("✏️ 編集・申請する"):
                                    st.session_state["editing_ringi_id"] = selected_id
                                    st.session_state["page_mode"] = "edit"
                                    st.rerun()
                            else:
                                # 進行状況の可視化
                                st.write(f"**現在のステータス:** {row['status']}")
                                # 誰のところで止まっているか？
                                pending_df = conn.query(f"SELECT approver_role, approver_name, status FROM T_Ringi_Approvals WHERE ringi_id = {selected_id} ORDER BY approval_id", ttl=0)
                                
                                # 簡易プログレスバー表示
                                steps = []
                                current_step = 0
                                for idx, p_row in pending_df.iterrows():
                                    step_name = f"{p_row['approver_role']}"
                                    if p_row['status'] == '承認':
                                        step_name += " (済)"
                                        current_step += 1
                                    steps.append(step_name)
                                
                                # 進捗表示
                                st.progress(current_step / len(steps) if steps else 0)
                                st.text(" → ".join(steps))

        with tab2:
            if not is_manager:
                st.write("承認権限がありません。")
            else:
                st.caption("あなたの承認を待っている案件です。")
                df_app = df_list[df_list['type'] == '承認待']
                
                if df_app.empty:
                    st.info("現在、承認待ち案件はありません。")
                else:
                    for i, row in df_app.iterrows():
                        with st.container(border=True):
                            st.markdown(f"**No.{row['ringi_id']} {row['subject']}**")
                            st.write(f"申請者: {row['applicant_name']} | 金額: ¥{row['amount']:,}")
                            
                            # 内容と添付ファイルを取得
                            detail_df = conn.query(f"SELECT content FROM T_Ringi_Header WHERE ringi_id={row['ringi_id']}", ttl=0)
                            content_text = detail_df.iloc[0]['content'] if not detail_df.empty else ""
                            st.text(content_text)

                            files_df = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                            if not files_df.empty:
                                for _, f_row in files_df.iterrows():
                                    st.markdown(f"📎 [{f_row['file_name']}]({f_row['file_url']})")

                            # 承認アクション
                            c_a, c_b = st.columns(2)
                            with c_a:
                                if st.button("承認する", key=f"app_{row['ringi_id']}", type="primary", use_container_width=True):
                                    # 脱ハンコ：データ更新のみ
                                    with conn.session as s:
                                        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
                                        # 自分のApprovalレコードを更新
                                        s.execute(
                                            text("""
                                            UPDATE T_Ringi_Approvals 
                                            SET status='承認', approver_name=:name, approved_at=:at 
                                            WHERE ringi_id=:rid AND approver_role=:role
                                            """),
                                            {"name": my_name, "at": now, "rid": row['ringi_id'], "role": my_role}
                                        )
                                        # 全員承認完了したかチェック？（今回は簡易的に、最終承認者が社長なら完了とする等のロジックが必要だが、まずは承認のみ実行）
                                        # もし自分が「社長」ならヘッダーも「決裁完了」にする例
                                        if my_role == "社長":
                                             s.execute(text("UPDATE T_Ringi_Header SET status='決裁完了' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                        
                                        s.commit()
                                    st.success("承認しました")
                                    st.rerun()
                            with c_b:
                                if st.button("却下", key=f"rej_{row['ringi_id']}", use_container_width=True):
                                     with conn.session as s:
                                        s.execute(text("UPDATE T_Ringi_Approvals SET status='却下', approver_name=:name WHERE ringi_id=:rid AND approver_role=:role"),
                                                  {"name": my_name, "rid": row['ringi_id'], "role": my_role})
                                        s.execute(text("UPDATE T_Ringi_Header SET status='却下' WHERE ringi_id=:rid"), {"rid": row['ringi_id']})
                                        s.commit()
                                     st.error("却下しました")
                                     st.rerun()

    # ==================================================
    # モードB: 新規作成・編集画面
    # ==================================================
    elif st.session_state["page_mode"] == "edit":
        edit_id = st.session_state.get("editing_ringi_id")
        is_new = edit_id is None
        
        st.subheader("📝 稟議書作成" if is_new else "✏️ 稟議書編集")
        
        # 初期値の準備
        default_subject = ""
        default_amount = 0
        default_content = ""
        
        if not is_new:
            # DBから既存データをロード
            existing = conn.query(f"SELECT * FROM T_Ringi_Header WHERE ringi_id = {edit_id}", ttl=0).iloc[0]
            default_subject = existing["subject"]
            default_amount = existing["amount"]
            default_content = existing["content"]

        with st.form("ringi_form"):
            subject = st.text_input("件名", value=default_subject)
            amount = st.number_input("金額 (円)", value=default_amount, step=1000)
            content = st.text_area("内容", value=default_content, height=150)
            
            # ファイル添付（編集時は「追加」扱いになります）
            uploaded_files = st.file_uploader("添付ファイル追加", accept_multiple_files=True)
            
            c1, c2, c3 = st.columns(3)
            with c1:
                # 戻るボタン
                if st.form_submit_button("キャンセル"):
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c2:
                # 下書き保存ボタン
                if st.form_submit_button("下書き保存"):
                    status = "下書き"
                    save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, status, uploaded_files)
                    st.toast("下書き保存しました")
                    st.session_state["page_mode"] = "list"
                    st.rerun()
            with c3:
                # 申請ボタン
                if st.form_submit_button("申請する", type="primary"):
                    if not subject:
                        st.warning("件名は必須です")
                    else:
                        status = "申請中"
                        save_data(conn, is_new, edit_id, my_name, my_email, subject, amount, content, status, uploaded_files)
                        st.success("申請しました！")
                        st.session_state["page_mode"] = "list"
                        st.rerun()

def save_data(conn, is_new, ringi_id, name, email, subject, amount, content, status, files):
    """DB保存処理（新規・更新共通）"""
    with conn.session as s:
        target_id = ringi_id
        
        if is_new:
            # INSERT
            row = s.execute(
                text("""
                INSERT INTO T_Ringi_Header (applicant_name, applicant_email, subject, amount, content, status)
                VALUES (:nm, :em, :sub, :amt, :cnt, :st)
                RETURNING ringi_id
                """),
                {"nm": name, "em": email, "sub": subject, "amt": amount, "cnt": content, "st": status}
            ).fetchone()
            target_id = row[0]
        else:
            # UPDATE
            s.execute(
                text("""
                UPDATE T_Ringi_Header 
                SET subject=:sub, amount=:amt, content=:cnt, status=:st
                WHERE ringi_id=:rid
                """),
                {"sub": subject, "amt": amount, "cnt": content, "st": status, "rid": ringi_id}
            )
        
        # ファイル保存
        if files:
            for f in files:
                f_url, f_name = upload_file_to_storage(f)
                if f_url:
                    s.execute(
                        text("INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url) VALUES (:rid, :fn, :fu)"),
                        {"rid": target_id, "fn": f_name, "fu": f_url}
                    )

        # ステータスが「申請中」になったタイミングで、承認ルートを作る
        # （既にルートがある場合は重複しないように削除してから作る等の制御が必要だが、今回は簡易的に「申請時」に作成）
        if status == "申請中":
            # 既存ルート確認
            check = s.execute(text(f"SELECT count(*) FROM T_Ringi_Approvals WHERE ringi_id={target_id}")).fetchone()[0]
            if check == 0:
                route = ["課長", "部長", "社長"]
                for r in route:
                    s.execute(
                        text("INSERT INTO T_Ringi_Approvals (ringi_id, approver_role) VALUES (:rid, :role)"),
                        {"rid": target_id, "role": r}
                    )
        
        s.commit()

if __name__ == "__main__":
    main()