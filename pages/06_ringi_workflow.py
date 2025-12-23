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

# --- Supabaseクライアント初期化 (Storage操作用) ---
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
    """ファイルをSupabase Storageにアップロードし、公開URLを返す"""
    if uploaded_file is None:
        return None, None
    
    try:
        # ファイル名が重複しないようにUUIDを付与
        file_ext = os.path.splitext(uploaded_file.name)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        bucket_name ="workflow_files" # Step1で作ったバケツ名
        
        # アップロード実行
        file_bytes = uploaded_file.getvalue()
        supabase.storage.from_(bucket_name).upload(
            path=unique_filename,
            file=file_bytes,
            file_options={"content-type": uploaded_file.type}
        )
        
        # 公開URLを取得
        public_url = supabase.storage.from_(bucket_name).get_public_url(unique_filename)
        return public_url, uploaded_file.name
        
    except Exception as e:
        st.error(f"ファイルアップロードエラー: {e}")
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
        with st.form("new_ringi"):
            subject = st.text_input("件名", placeholder="例: 電脳工場保守契約更新の件")
            amount = st.number_input("金額 (円)", step=1000)
            content = st.text_area("申請理由・詳細", height=150)
            
            # ★ファイルアップロード機能★
            uploaded_file = st.file_uploader("添付資料 (見積書PDFなど)", type=["pdf", "jpg", "png", "xlsx"])
            
            submitted = st.form_submit_button("申請する", type="primary")
            
            if submitted:
                if not subject:
                    st.warning("件名は必須です。")
                else:
                    try:
                        file_url = None
                        file_name = None
                        
                        # ファイルがあればアップロード処理
                        if uploaded_file:
                            with st.spinner("ファイルをアップロード中..."):
                                file_url, file_name = upload_file_to_storage(uploaded_file)
                        
                        with conn.session as s:
                            # DB保存 (file_url, file_nameを追加)
                            row = s.execute(
                                text("""
                                INSERT INTO T_Ringi_Header 
                                (applicant_name, applicant_email, subject, amount, content, file_url, file_name)
                                VALUES (:nm, :em, :sub, :amt, :cnt, :furl, :fname)
                                RETURNING ringi_id
                                """),
                                {
                                    "nm": my_name, "em": my_email, "sub": subject, 
                                    "amt": amount, "cnt": content,
                                    "furl": file_url, "fname": file_name
                                }
                            ).fetchone()
                            new_id = row[0]
                            
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
        # file_name列も取得するように変更
        df_my = conn.query(f"SELECT ringi_id, created_at, subject, amount, status, file_name, file_url FROM T_Ringi_Header WHERE applicant_email = '{my_email}' ORDER BY ringi_id DESC", ttl=0)
        
        # データフレームだとURLがクリックしにくいので、簡単なリスト表示にする
        if df_my.empty:
            st.info("申請履歴はありません。")
        else:
            st.dataframe(df_my, column_config={
                "file_url": st.column_config.LinkColumn("添付ファイル")
            }, use_container_width=True)

    # --- TAB 3: 承認作業 ---
    if is_manager and len(tabs) > 2:
        with tabs[2]:
            st.subheader(f"承認トレイ ({my_role})")
            # file_url, file_nameを取得に追加
            sql = f"""
                SELECT h.ringi_id, h.subject, h.applicant_name, h.amount, h.content, 
                       h.created_at, h.file_url, h.file_name, a.approval_id
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
                            
                            # ★添付ファイルリンク表示★
                            if row['file_url']:
                                st.markdown(f"📎 **添付資料:** [{row['file_name']}]({row['file_url']})")
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