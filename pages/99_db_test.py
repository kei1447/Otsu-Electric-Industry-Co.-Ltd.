import streamlit as st
import pandas as pd
from sqlalchemy import text

# --- ログイン認証チェック ---
if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("⚠️ ログインしていません。")
    st.stop()

st.title("🗄️ データベース接続テスト")

# 1. 接続を確立
# secretsの [connections.supabase] を自動で読みに行きます
try:
    conn = st.connection("supabase", type="sql")
    st.success("✅ データベースへの接続に成功しました！")
except Exception as e:
    st.error(f"接続エラー: {e}")
    st.stop()

# 2. テスト用テーブルの作成とデータ追加（ボタン式）
st.subheader("データの書き込みテスト")
if st.button("テスト用テーブル作成＆データ追加"):
    with conn.session as s:
        # SQLを実行してテーブルを作る
        s.execute(text("""
            CREATE TABLE IF NOT EXISTS test_table (
                id SERIAL PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """))
        # データを1件入れる
        s.execute(text("INSERT INTO test_table (name) VALUES ('接続テスト成功！');"))
        s.commit()
    st.toast("データを追加しました！")

# 3. データの読み出し表示
st.subheader("データの読み出し")
# キャッシュ有効期間（ttl）を0にすると、ボタンを押すたびに最新を見に行きます
df = conn.query("SELECT * FROM test_table ORDER BY id DESC;", ttl=0)

st.dataframe(df)

# おまけ: テーブル削除（掃除用）
if st.button("テスト用テーブルを削除（リセット）"):
    with conn.session as s:
        s.execute(text("DROP TABLE IF EXISTS test_table;"))
        s.commit()
    st.rerun()