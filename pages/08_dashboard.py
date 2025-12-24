import streamlit as st
import pandas as pd
from sqlalchemy import text
import altair as alt

# --- 設定 ---
st.set_page_config(page_title="予実管理ダッシュボード", layout="wide")

def main():
    st.title("📊 経営ダッシュボード (予実管理)")
    
    # 認証チェック
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()

    conn = st.connection("supabase", type="sql")

    # --- 1. フィルターエリア ---
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            # 年度の選択 (DBにある年度を取得)
            years_df = conn.query("SELECT DISTINCT fiscal_year FROM T_Ringi_Header ORDER BY fiscal_year DESC", ttl=60)
            years = years_df['fiscal_year'].tolist() if not years_df.empty else [2025]
            selected_year = st.selectbox("対象年度", years)
        
        with col2:
            # 視点の切り替え
            view_mode = st.radio("集計モード", ["執行状況 (Spending)", "予算策定 (Planning)"], horizontal=True)
            # フェーズによるフィルタリング
            target_phase = "執行" if view_mode == "執行状況 (Spending)" else "計画(来期予算等)"

    # --- 2. データ取得 ---
    # 選択された年度とフェーズのデータを取得（決裁完了 + 申請中も含める？）
    # 今回は「承認済み（決裁完了）」を実績、「申請中」をパイプラインとして扱います
    sql = f"""
        SELECT subject, amount, budget_category, status, applicant_name, created_at 
        FROM T_Ringi_Header 
        WHERE fiscal_year = {selected_year} 
          AND phase = '{target_phase}'
          AND status != '却下'
    """
    df = conn.query(sql, ttl=0)

    st.markdown("---")

    if df.empty:
        st.info(f"{selected_year}年度の{target_phase}データはまだありません。")
        return

    # --- 3. KPI表示 ---
    # 決裁完了 = 確定額 / 申請中 = 見込額
    df_fixed = df[df['status'] == '決裁完了']
    df_pipeline = df[df['status'].isin(['申請中', '承認'])] # 途中

    total_fixed = df_fixed['amount'].sum()
    total_pipeline = df_pipeline['amount'].sum()
    total_all = total_fixed + total_pipeline

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(label="確定金額 (決裁済)", value=f"¥{total_fixed:,}")
    with c2:
        st.metric(label="申請中 (承認待ち)", value=f"¥{total_pipeline:,}")
    with c3:
        st.metric(label="合計見込", value=f"¥{total_all:,}")

    # --- 4. グラフによる可視化 ---
    col_chart1, col_chart2 = st.columns([2, 1])

    with col_chart1:
        st.subheader("💰 予算区分別 内訳")
        # 予算内 vs 突発 の比較
        # Altairで積み上げ棒グラフを作成
        chart_data = df.groupby(['budget_category', 'status'])['amount'].sum().reset_index()
        
        base = alt.Chart(chart_data).encode(
            x=alt.X('budget_category', title='区分'),
            y=alt.Y('amount', title='金額'),
            color=alt.Color('status', scale=alt.Scale(domain=['決裁完了', '申請中', '承認'], range=['#28a745', '#ffc107', '#17a2b8'])),
            tooltip=['budget_category', 'status', alt.Tooltip('amount', format=',')]
        )
        bar = base.mark_bar().properties(height=300)
        st.altair_chart(bar, use_container_width=True)

    with col_chart2:
        st.subheader("👤 申請者ランキング")
        # 誰が多く使っているか
        ranking = df.groupby('applicant_name')['amount'].sum().reset_index().sort_values('amount', ascending=False).head(5)
        st.dataframe(
            ranking, 
            column_config={"applicant_name": "氏名", "amount": st.column_config.NumberColumn("金額", format="¥%d")},
            hide_index=True,
            use_container_width=True
        )

    # --- 5. 明細データ ---
    with st.expander("詳細データ一覧を見る"):
        st.dataframe(
            df[["created_at", "subject", "applicant_name", "amount", "budget_category", "status"]],
            column_config={
                "created_at": st.column_config.DatetimeColumn("日付", format="YYYY/MM/DD"),
                "amount": st.column_config.NumberColumn("金額", format="¥%d")
            },
            use_container_width=True
        )

if __name__ == "__main__":
    main()