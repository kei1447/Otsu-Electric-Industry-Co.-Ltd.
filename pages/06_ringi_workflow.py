import streamlit as st
import pandas as pd
from sqlalchemy import text
from PIL import Image, ImageDraw, ImageFont
import datetime
import io
import base64
import os
import uuid
from supabase import create_client

# --- 設定 ---
STAMP_SIZE = 120
STAMP_COLOR = (220, 50, 50)
FONT_FILENAME = "ShipporiMincho-Bold.ttf" 
BUCKET_NAME = "workflow_files" # ★変更しました

# --- Supabaseクライアント初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secretsの設定が不足しています。")
    st.stop()

# --- 関数群 ---
def get_font_path():
    path1 = os.path.join("fonts", FONT_FILENAME)
    path2 = FONT_FILENAME
    path3 = os.path.join("pages", "fonts", FONT_FILENAME)
    if os.path.exists(path1): return path1
    elif os.path.exists(path2): return path2
    elif os.path.exists(path3): return path3
    else: return None

def create_digital_stamp(name_text, datetime_obj):
    """電子印鑑生成"""
    img = Image.new('RGBA', (STAMP_SIZE, STAMP_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse((margin, margin, STAMP_SIZE - margin, STAMP_SIZE - margin), outline=STAMP_COLOR, width=3)
    
    line_y1 = int(STAMP_SIZE * 0.34)
    line_y2 = int(STAMP_SIZE * 0.66)
    padding = 12
    draw.line((padding, line_y1, STAMP_SIZE - padding, line_y1), fill=STAMP_COLOR, width=2)
    draw.line((padding, line_y2, STAMP_SIZE - padding, line_y2), fill=STAMP_COLOR, width=2)

    font_path = get_font_path()
    if font_path:
        try:
            font_top = ImageFont.truetype(font_path, 22)
            font_date = ImageFont.truetype(font_path, 11)
            size_name = 18 if len(name_text) >= 3 else 24
            font_name = ImageFont.truetype(font_path, size_name)
            
            draw.text((STAMP_SIZE/2, line_y1/2), "承認", font=font_top, fill=STAMP_COLOR, anchor="mm")
            date_str = datetime_obj.strftime("%Y/%m/%d\n%H:%M:%S")
            center_y_date = (line_y1 + line_y2) / 2
            draw.multiline_text((STAMP_SIZE/2, center_y_date), date_str, font=font_date, fill=STAMP_COLOR, anchor="mm", align="center", spacing=1)
            center_y_name = (line_y2 + STAMP_SIZE) / 2
            draw.text((STAMP_SIZE/2, center_y_name - 2), name_text, font=font_name, fill=STAMP_COLOR, anchor="mm")
        except:
            pass
    return img

def image_to_base64(img):
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def upload_file_to_storage(uploaded_file):
    """ファイルをStorageにアップロードし、URLを返す"""
    if uploaded_file is None:
        return None, None
    try:
        # 日本語ファイル名などのトラブルを防ぐため、UUIDを使用
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

# --- メイン処理 ---
def main():
    st.title("🈸 稟議・申請ワークフロー")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.error("ログインしてください。")
        st.stop()
    
    my_name = st.session_state["user_name"]
    my_role = st.session_state["role"]
    my_email = st.session_state["user_email"]
    stamp_name = my_name.split(" ")[0] if " " in my_name else my_name[0:2]

    manager_roles = ["課長", "部長", "社長", "専務", "常務", "工場長"]
    is_manager = any(role in my_role for role in manager_roles)

    tab_titles = ["📄 新規申請", "🗂 申請履歴"]
    if is_manager:
        tab_titles.append("✅ 承認待ち案件")
    
    tabs = st.tabs(tab_titles)
    conn = st.connection("supabase", type="sql")

    # --- TAB 1: 新規申請 ---
    with tabs[0]:
        st.caption("新しい稟議書を作成・申請します。")
        with st.form("new_ringi", clear_on_submit=True): # 送信後フォームをクリア
            subject = st.text_input("件名", placeholder="例: 電脳工場保守契約更新の件")
            amount = st.number_input("金額 (円)", step=1000)
            content = st.text_area("申請理由・詳細", height=150)
            
            # ★複数ファイル＆全種類対応★
            # type=Noneで全許可、accept_multiple_files=Trueで複数許可
            uploaded_files = st.file_uploader(
                "添付資料 (複数選択可)", 
                type=None, 
                accept_multiple_files=True
            )
            
            submitted = st.form_submit_button("申請する", type="primary")
            
            if submitted:
                if not subject:
                    st.warning("件名は必須です。")
                else:
                    try:
                        with conn.session as s:
                            # 1. 稟議ヘッダー保存
                            # file_url等は使わず、ここでは案件情報のみ保存
                            row = s.execute(
                                text("""
                                INSERT INTO T_Ringi_Header 
                                (applicant_name, applicant_email, subject, amount, content)
                                VALUES (:nm, :em, :sub, :amt, :cnt)
                                RETURNING ringi_id
                                """),
                                {
                                    "nm": my_name, "em": my_email, 
                                    "sub": subject, "amt": amount, "cnt": content
                                }
                            ).fetchone()
                            new_id = row[0]
                            
                            # 2. 添付ファイルの保存 (ループ処理)
                            if uploaded_files:
                                with st.spinner(f"{len(uploaded_files)}件のファイルをアップロード中..."):
                                    for f in uploaded_files:
                                        f_url, f_name = upload_file_to_storage(f)
                                        if f_url:
                                            s.execute(
                                                text("""
                                                INSERT INTO T_Ringi_Attachments (ringi_id, file_name, file_url)
                                                VALUES (:rid, :fn, :fu)
                                                """),
                                                {"rid": new_id, "fn": f_name, "fu": f_url}
                                            )
                            
                            # 3. 承認ルート生成
                            route = ["課長", "部長", "社長"]
                            for r in route:
                                s.execute(
                                    text("INSERT INTO T_Ringi_Approvals (ringi_id, approver_role) VALUES (:rid, :role)"),
                                    {"rid": new_id, "role": r}
                                )
                            s.commit()
                        st.success(f"申請完了！ (管理No: {new_id})")
                        
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")

    # --- TAB 2: 申請履歴 ---
    with tabs[1]:
        # 履歴表示
        df_my = conn.query(f"SELECT ringi_id, created_at, subject, amount, status FROM T_Ringi_Header WHERE applicant_email = '{my_email}' ORDER BY ringi_id DESC", ttl=0)
        
        if df_my.empty:
            st.info("申請履歴はありません。")
        else:
            # 各案件ごとに詳細を表示
            for i, row in df_my.iterrows():
                with st.expander(f"No.{row['ringi_id']} {row['subject']} ({row['status']})"):
                    st.write(f"申請日: {row['created_at']} / 金額: ¥{row['amount']:,}")
                    
                    # 添付ファイルを取得して表示
                    files_df = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                    if not files_df.empty:
                        st.markdown("**📎 添付ファイル:**")
                        for _, f_row in files_df.iterrows():
                            st.markdown(f"- [{f_row['file_name']}]({f_row['file_url']})")

    # --- TAB 3: 承認作業 ---
    if is_manager and len(tabs) > 2:
        with tabs[2]:
            st.subheader(f"承認トレイ ({my_role})")
            
            sql = f"""
                SELECT h.ringi_id, h.subject, h.applicant_name, h.amount, h.content, 
                       h.created_at, a.approval_id
                FROM T_Ringi_Header h
                JOIN T_Ringi_Approvals a ON h.ringi_id = a.ringi_id
                WHERE a.approver_role = '{my_role}' 
                  AND a.status = '未承認'
                  AND h.status != '却下'
                ORDER BY h.ringi_id ASC
            """
            df_pending = conn.query(sql, ttl=0)
            
            if df_pending.empty:
                st.info("承認待ち案件はありません。")
            else:
                for i, row in df_pending.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        with c1:
                            st.markdown(f"#### {row['subject']}")
                            st.caption(f"申請者: {row['applicant_name']} | 金額: ¥{row['amount']:,} | {row['created_at']}")
                            st.write(row['content'])
                            
                            # ★添付ファイルをリスト表示★
                            files_df = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {row['ringi_id']}", ttl=0)
                            if not files_df.empty:
                                st.markdown("---")
                                st.caption("📎 添付資料:")
                                for _, f_row in files_df.iterrows():
                                    # 拡張子などでアイコンを変えても面白いですが、まずはシンプルに
                                    st.markdown(f"- 📄 [{f_row['file_name']}]({f_row['file_url']})")
                            else:
                                st.caption("（添付資料なし）")
                        
                        with c2:
                            if st.button("承認する", key=f"btn_app_{row['approval_id']}", type="primary"):
                                JST = datetime.timezone(datetime.timedelta(hours=9))
                                now = datetime.datetime.now(JST)
                                stamp = create_digital_stamp(stamp_name, now)
                                stamp_b64 = image_to_base64(stamp)
                                
                                with conn.session as s:
                                    s.execute(
                                        text("""
                                        UPDATE T_Ringi_Approvals
                                        SET status='承認', approver_name=:name, approved_at=:at, stamp_data=:st
                                        WHERE approval_id=:aid
                                        """),
                                        {"name": my_name, "at": now, "st": stamp_b64, "aid": row['approval_id']}
                                    )
                                    s.commit()
                                st.success("承認しました！")
                                st.rerun()

if __name__ == "__main__":
    main()