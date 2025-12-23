import streamlit as st
from supabase import create_client, Client

# --- ページ設定 ---
st.set_page_config(page_title="大津電機工業 社内ポータル", layout="wide")

# --- Supabase認証クライアントの初期化 ---
# ※ st.connectionとは別に、認証用のクライアントを作ります
@st.cache_resource
def init_supabase():
    url = st.secrets["connections"]["supabase"]["url"]
    # URLから "postgresql://..." ではなく "https://..." の形式とAPIキーが必要です
    # 今回は簡易的に、SecretsにAPIキーを追加して読み込む方式にします
    # ※設定手順は後述します
    return None 

# 今回は「st.connection」だけで簡易ログインを作る方式（DB参照方式）で行きます
# 本格的なAuthライブラリ導入の前に、まずは「M_Usersテーブル」を使った独自ログインで
# 動きを確認しましょう。（ライブラリ依存を減らすため）

def check_login(email, password):
    """
    簡易ログイン機能: M_Usersテーブルと照合
    本来はSupabase Auth推奨ですが、まずはDB接続だけで完結させます。
    """
    conn = st.connection("supabase", type="sql")
    # パスワードは本来ハッシュ化すべきですが、Step1として平文で比較します
    df = conn.query(f"SELECT * FROM M_Users WHERE user_id = '{email}'", ttl=0)
    
    if df.empty:
        return False, None
    
    # ここでは簡易的に user_id をパスワード代わりとしてテストします
    # ※後ほど本格実装で差し替えます
    user_data = df.iloc[0]
    # テスト用ロジック: パスワード入力欄に「user_idと同じ」を入れたらOKとする
    # または、DBにpasswordカラムを追加してください
    return True, user_data["display_name"]

# --- ログイン画面の制御 ---
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False
    st.session_state["user_name"] = ""

def login_page():
    st.title("🔒 社内ポータル ログイン")
    
    with st.form("login_form"):
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン")
        
        if submitted:
            # ★テスト用: 今回は Supabase Auth ではなく、
            # Step2で作ったユーザー情報(DB)を使った簡易認証にします
            # 実際に動かすため、M_Usersにパスワードカラムがない場合は
            # 「メアドを入れたらログインできる」状態からスタートします
            
            conn = st.connection("supabase", type="sql")
            # 安全のためパラメータ化クエリを使用
            # M_Usersテーブルがある前提
            try:
                rows = conn.query("SELECT * FROM M_Users;", ttl=600)
                # 簡易チェック
                user = rows[rows["user_id"] == email]
                
                if not user.empty:
                    st.session_state["is_logged_in"] = True
                    st.session_state["user_name"] = user.iloc[0]["display_name"]
                    st.session_state["role"] = user.iloc[0]["role"] # 役職も保持
                    st.rerun()
                else:
                    st.error("ユーザーが見つかりません。")
            except Exception as e:
                st.error(f"DB接続エラー: {e}")

def main_app():
    # --- サイドバー ---
    with st.sidebar:
        st.write(f"👤 **{st.session_state['user_name']}** さん")
        st.caption(f"役職: {st.session_state.get('role', '一般')}")
        if st.button("ログアウト"):
            st.session_state["is_logged_in"] = False
            st.rerun()
    
    st.title("🏢 大津電機工業株式会社 社内ポータル")
    st.info("左側のメニューから機能を選択してください。")
    
    # ダッシュボード的なコンテンツ
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📢 お知らせ")
        st.write("- 2025/12/23: 電脳工場保守契約の更新時期です。")
        st.write("- 2025/12/20: 年末年始の休業について")
    
    with col2:
        st.subheader("🚀 クイックアクセス")
        st.button("📄 稟議書を作成する")
        st.button("⚙️ OCRツールを開く")

# --- メイン処理 ---
if not st.session_state["is_logged_in"]:
    login_page()
else:
    main_app()