import streamlit as st
import pandas as pd
from sqlalchemy import text
from supabase import create_client

# --- 設定 ---
LIMIT = 50

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

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()
    
    conn = st.connection("supabase", type="sql")

    # --- 検索フィルターエリア ---
    with st.container(border=True):
        st.subheader("検索条件")
        c1, c2, c3 = st.columns([2, 2, 2])
        
        with c1:
            keyword = st.text_input("キーワード (件名・内容)", placeholder="PC購入, 保守契約 etc...")
        
        with c2:
            # DBから申請者リスト(重複なし)を取得してプルダウンにする
            applicants_df = conn.query("SELECT DISTINCT applicant_name FROM T_Ringi_Header ORDER BY applicant_name", ttl=60)
            applicant_list = applicants_df["applicant_name"].tolist()
            selected_applicant = st.selectbox("申請者", options=applicant_list, index=None, placeholder="指定なし")
            
        with c3:
            status_filter = st.multiselect("ステータス", ["申請中", "決裁完了", "却下"], default=["申請中", "決裁完了"])

        # 検索ボタン (これを押さないと動かないようにする)
        run_search = st.button("この条件で検索する", type="primary", use_container_width=True)

    # --- 検索実行ロジック ---
    if run_search:
        # 条件組み立て
        conditions = []
        
        # 1. キーワード
        if keyword:
            conditions.append(f"(subject ILIKE '%{keyword}%' OR content ILIKE '%{keyword}%')")
        
        # 2. 申請者
        if selected_applicant:
            conditions.append(f"applicant_name = '{selected_applicant}'")
        
        # 3. ステータス
        if status_filter:
            status_str = ",".join([f"'{s}'" for s in status_filter])
            conditions.append(f"status IN ({status_str})")
        else:
            conditions.append("1=1") # 選択なしなら全ステータス

        # WHERE句の結合
        where_clause = " AND ".join(conditions)
        
        sql = f"""
            SELECT ringi_id, created_at, subject, applicant_name, amount, status, content 
            FROM T_Ringi_Header 
            WHERE {where_clause}
            ORDER BY ringi_id DESC
            LIMIT {LIMIT}
        """
        
        df = conn.query(sql, ttl=0)

        st.markdown(f"### 検索結果: {len(df)}件")

        if df.empty:
            st.warning("条件に一致する案件は見つかりませんでした。")
        else:
            st.dataframe(
                df,
                column_config={
                    "ringi_id": st.column_config.NumberColumn("ID", width="small"),
                    "created_at": st.column_config.DatetimeColumn("申請日", format="YYYY/MM/DD"),
                    "subject": "件名",
                    "applicant_name": "申請者",
                    "amount": st.column_config.NumberColumn("金額", format="¥%d"),
                    "status": "状態",
                    "content": "概要"
                },
                use_container_width=True,
                hide_index=True
            )

            # 詳細表示エリア (検索結果がある時だけ表示)
            st.divider()
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
                        st.info(row['content'])
                    
                    # 添付・履歴の表示（前回と同じ）
                    files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {detail_id}", ttl=0)
                    if not files.empty:
                        st.markdown("**📎 添付資料:**")
                        for _, f in files.iterrows():
                            st.markdown(f"- [{f['file_name']}]({f['file_url']})")
                    
                    st.write("**📋 履歴:**")
                    approvals = conn.query(f"SELECT approver_role, approver_name, status, comment FROM T_Ringi_Approvals WHERE ringi_id = {detail_id}", ttl=0)
                    st.dataframe(approvals, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()