import streamlit as st
import pandas as pd
from sqlalchemy import text
from supabase import create_client

# --- 設定 ---
# 1ページあたりの表示件数
LIMIT = 20

# --- 関数群 ---
def get_status_color(status):
    if status == '決裁完了': return '🟢'
    if status == '承認': return '🔵'
    if status == '却下': return '🔴'
    if status == '申請中': return '🟡'
    return '⚪'

# --- メイン処理 ---
def main():
    st.set_page_config(page_title="案件データベース", layout="wide")
    st.title("🔎 案件・稟議データベース")

    # 1. 認証チェック
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()
    
    conn = st.connection("supabase", type="sql")

    # 2. 検索フィルターエリア
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        with c1:
            search_query = st.text_input("キーワード検索", placeholder="件名、申請者、内容から検索...")
        with c2:
            status_filter = st.multiselect("ステータス", ["申請中", "決裁完了", "却下"], default=["申請中", "決裁完了"])
        with c3:
            st.write("") # スペース調整
            st.write("")
            search_btn = st.button("検索する", type="primary", use_container_width=True)

    # 3. データ取得・表示
    # ステータスフィルターの処理
    if not status_filter:
        status_condition = "1=1" # 全検索
    else:
        # SQL用にリストを文字列化 ('A', 'B')
        status_str = ",".join([f"'{s}'" for s in status_filter])
        status_condition = f"status IN ({status_str})"

    # キーワード検索の処理 (PostgreSQLの ILIKE は大文字小文字無視)
    if search_query:
        keyword_condition = f"""
            (subject ILIKE '%{search_query}%' OR 
             applicant_name ILIKE '%{search_query}%' OR 
             content ILIKE '%{search_query}%')
        """
    else:
        keyword_condition = "1=1"

    # SQL組み立て
    sql = f"""
        SELECT ringi_id, created_at, subject, applicant_name, amount, status, content 
        FROM T_Ringi_Header 
        WHERE {status_condition} AND {keyword_condition}
        ORDER BY ringi_id DESC
        LIMIT {LIMIT}
    """
    
    df = conn.query(sql, ttl=0)

    st.markdown(f"### 検索結果: {len(df)}件")

    if df.empty:
        st.info("該当する案件は見つかりませんでした。")
    else:
        # テーブル表示 (st.dataframeのcolumn_configでリッチに)
        st.dataframe(
            df,
            column_config={
                "ringi_id": st.column_config.NumberColumn("ID", width="small"),
                "created_at": st.column_config.DatetimeColumn("申請日", format="YYYY/MM/DD"),
                "subject": st.column_config.TextColumn("件名", width="medium"),
                "applicant_name": "申請者",
                "amount": st.column_config.NumberColumn("金額", format="¥%d"),
                "status": "状態",
                "content": st.column_config.TextColumn("内容概要", width="large"),
            },
            use_container_width=True,
            hide_index=True
        )

        # 詳細確認用エクスパンダー
        st.caption("▼ 詳細を確認したいIDを選択してください")
        detail_id = st.selectbox("詳細表示", df["ringi_id"], index=None, label_visibility="collapsed")
        
        if detail_id:
            row = df[df["ringi_id"] == detail_id].iloc[0]
            with st.container(border=True):
                color = get_status_color(row['status'])
                st.subheader(f"{color} {row['subject']}")
                
                c_a, c_b = st.columns(2)
                with c_a:
                    st.write(f"**申請者:** {row['applicant_name']}")
                    st.write(f"**申請日:** {row['created_at']}")
                    st.metric("金額", f"¥{row['amount']:,}")
                with c_b:
                    st.write("**内容:**")
                    st.info(row['content'])
                
                # 添付ファイル
                files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {detail_id}", ttl=0)
                if not files.empty:
                    st.markdown("---")
                    st.write("**📎 添付資料:**")
                    for _, f in files.iterrows():
                        st.markdown(f"- [{f['file_name']}]({f['file_url']})")
                
                # 承認履歴
                st.markdown("---")
                st.write("**📋 承認プロセス履歴:**")
                approvals = conn.query(f"SELECT approver_role, approver_name, status, comment, approved_at FROM T_Ringi_Approvals WHERE ringi_id = {detail_id} ORDER BY approval_id", ttl=0)
                st.dataframe(approvals, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()