import streamlit as st
import pandas as pd
from sqlalchemy import text
import json
from supabase import create_client

# --- 設定 ---
LIMIT = 100

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
    st.title("🔎 案件・業務データベース")

    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()
    
    conn = st.connection("supabase", type="sql")

    # --- 検索フィルターエリア ---
    with st.container(border=True):
        st.subheader("検索条件")
        
        # 1. テンプレート種類の取得
        templates_df = conn.query("SELECT * FROM M_Templates ORDER BY template_id", ttl=60)
        template_map = {row['template_name']: row['template_id'] for i, row in templates_df.iterrows()}
        template_options = ["すべて"] + list(template_map.keys())

        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            keyword = st.text_input("キーワード", placeholder="件名、申請者、内容...")
        with c2:
            # テンプレート選択
            selected_template = st.selectbox("帳票タイプ", template_options)
        with c3:
            # 年度
            years_df = conn.query("SELECT DISTINCT fiscal_year FROM T_Ringi_Header ORDER BY fiscal_year DESC", ttl=60)
            years = years_df['fiscal_year'].dropna().tolist()
            if not years: years = [2025]
            selected_year = st.selectbox("年度", ["指定なし"] + years)
        with c4:
            status_filter = st.multiselect("ステータス", ["申請中", "決裁完了", "却下"], default=["申請中", "決裁完了"])

        run_search = st.button("検索実行", type="primary", use_container_width=True)

    # --- 検索実行 ---
    if run_search:
        # WHERE句の構築
        conditions = ["1=1"]
        
        if keyword:
            conditions.append(f"(subject ILIKE '%{keyword}%' OR applicant_name ILIKE '%{keyword}%' OR content ILIKE '%{keyword}%')")
        
        if selected_template != "すべて":
            tid = template_map[selected_template]
            conditions.append(f"template_id = {tid}")
        
        if selected_year != "指定なし":
            conditions.append(f"fiscal_year = {selected_year}")
            
        if status_filter:
            status_str = ",".join([f"'{s}'" for s in status_filter])
            conditions.append(f"status IN ({status_str})")

        where_clause = " AND ".join(conditions)
        
        # データ取得
        sql = f"""
            SELECT ringi_id, created_at, fiscal_year, subject, applicant_name, amount, status, content, custom_data, template_id
            FROM T_Ringi_Header 
            WHERE {where_clause}
            ORDER BY ringi_id DESC
            LIMIT {LIMIT}
        """
        df = conn.query(sql, ttl=0)

        st.markdown(f"### 検索結果: {len(df)}件")

        if df.empty:
            st.warning("条件に一致するデータはありません。")
        else:
            # ★ここがポイント: JSONデータの列展開★
            display_df = df.copy()
            
            # custom_data列を解析して、個別の列に展開する
            custom_columns = []
            
            # JSON展開処理
            expanded_data = []
            for i, row in display_df.iterrows():
                base_info = {
                    "ID": row['ringi_id'],
                    "日付": pd.to_datetime(row['created_at']).strftime('%Y-%m-%d'),
                    "年度": row['fiscal_year'],
                    "件名": row['subject'],
                    "申請者": row['applicant_name'],
                    "金額": f"¥{row['amount']:,}",
                    "状態": row['status']
                }
                
                # JSONデータがあれば展開してマージ
                if row['custom_data']:
                    c_data = row['custom_data']
                    if isinstance(c_data, str): c_data = json.loads(c_data)
                    # 辞書のキーを列名として追加
                    base_info.update(c_data)
                
                expanded_data.append(base_info)
            
            # 新しいDataFrameを作成
            result_df = pd.DataFrame(expanded_data)
            
            # 表示
            st.dataframe(result_df, use_container_width=True, hide_index=True)

            # --- 詳細表示エリア ---
            st.divider()
            st.caption("▼ 詳細を確認・履歴を見るにはIDを選択してください")
            
            # IDリスト作成（セレクトボックス用）
            id_list = result_df["ID"].tolist()
            detail_id = st.selectbox("詳細表示", id_list, index=None, label_visibility="collapsed")
            
            if detail_id:
                # 元データから再取得（添付ファイル等が欲しいため）
                row = df[df["ringi_id"] == detail_id].iloc[0]
                
                with st.container(border=True):
                    color = get_status_color(row['status'])
                    st.subheader(f"{color} {row['subject']}")
                    
                    c_a, c_b = st.columns([1, 2])
                    with c_a:
                        st.write(f"**申請者:** {row['applicant_name']}")
                        st.write(f"**申請日:** {row['created_at']}")
                        st.metric("金額", f"¥{row['amount']:,}")
                    with c_b:
                        # 独自項目の表示
                        if row['custom_data']:
                            c_data = row['custom_data']
                            if isinstance(c_data, str): c_data = json.loads(c_data)
                            st.write("**詳細内容:**")
                            # 見やすく表形式などで
                            st.json(c_data, expanded=False)
                        else:
                            st.write(f"**内容:** {row['content']}")
                    
                    # 添付ファイル
                    files = conn.query(f"SELECT file_name, file_url FROM T_Ringi_Attachments WHERE ringi_id = {detail_id}", ttl=0)
                    if not files.empty:
                        st.markdown("**📎 添付資料:**")
                        for _, f in files.iterrows():
                            st.markdown(f"- [{f['file_name']}]({f['file_url']})")
                    
                    # 履歴
                    st.markdown("---")
                    st.write("**📋 プロセス履歴:**")
                    approvals = conn.query(f"SELECT step_order, approver_role, approver_name, status, comment, approved_at FROM T_Ringi_Approvals WHERE ringi_id = {detail_id} ORDER BY step_order", ttl=0)
                    st.dataframe(approvals, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()