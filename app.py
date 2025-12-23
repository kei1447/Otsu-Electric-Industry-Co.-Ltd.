import streamlit as st
from supabase import create_client, Client
import time

# --- ページ設定 ---
st.set_page_config(
    page_title="大津電機工業 社内ポータル",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Supabase設定の読み込み ---
# .streamlit/secrets.toml から情報を取得
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
except Exception:
    st.error("Secretsの設定が読み込めません。project_url と key を確認してください。")
    st.stop()

# --- Supabaseクライアントの初期化 ---
@st.cache_resource
def init_supabase():
    """Supabase Auth用クライアントを作成"""
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ログイン処理関数 ---
def login_with_auth(email, password):
    """
    1. Supabase Authでパスワード認証
    2. 成功したら M_Users テーブルから氏名・役職を取得
    """
    client = init_supabase()
    
    try:
        # Step 1: Authentication (入館証チェック)
        # ここでパスワードが間違っていれば例外が発生します
        auth_response = client.auth.sign_in_with_password({"email": email, "password": password})
        
        # Step 2: M_Users lookup (名簿チェック)
        # DB接続機能を使ってユーザー情報を検索
        conn = st.connection("supabase", type="sql")
        
        # 安全のためパラメータ化は推奨されますが、まずはシンプルに検索
        # user_id(メールアドレス)で検索します
        df = conn.query(f"SELECT * FROM M_Users WHERE user_id = '{email}'", ttl=0)
        
        if df.empty:
            # Authには通ったが、M_Usersに登録がない場合
            return False, "システム利用権限がありません（ユーザーマスタ未登録）。", None
        
        # ユーザー情報を取得
        user_data = df.iloc[0]
        return True, "ログイン成功", user_data
        
    except Exception as e:
        # パスワード違いなどのエラー
        # セキュリティのため詳細は出さず、汎用的なエラーにするのが一般的ですが
        # デバッグ中は e を表示してもOKです
        return False, "メールアドレスまたはパスワードが間違っています。", None

# --- 画面1: ログインページ ---
def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center;'>🏢 大津電機工業</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>社内ポータルシステム</h3>", unsafe_allow_html=True)
        st.markdown("---")
        
        with st.form("login_form"):
            st.write("ログイン情報を入力してください")
            email = st.text_input("メールアドレス", placeholder="yourname@otsudenki.co.jp")
            password = st.text_input("パスワード", type="password")
            
            submitted = st.form_submit_button("ログイン", use_container_width=True)
            
            if submitted:
                if not email or not password:
                    st.warning("メールアドレスとパスワードを入力してください。")
                else:
                    with st.spinner("認証中..."):
                        is_success, msg, user_data = login_with_auth(email, password)
                    
                    if is_success:
                        st.success("認証成功！ポータルへ移動します...")
                        # セッション情報の保存
                        st.session_state["is_logged_in"] = True
                        st.session_state["user_name"] = user_data["display_name"]
                        st.session_state["role"] = user_data["role"]
                        st.session_state["user_email"] = email
                        st.session_state["stamp_text"] = user_data.get("stamp_text", "")
                        
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

# --- 画面2: メインポータル ---
def main_app():
    # サイドバー（ユーザー情報）
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['user_name']} 様")
        st.caption(f"権限: {st.session_state['role']}")
        st.divider()
        
        st.markdown("### 📌 Menu")
        # ページリンク（pagesフォルダ内のファイルを自動検知してリンク化も可能ですが、ここでは手動ガイド）
        st.page_link("app.py", label="🏠 ホーム", icon="🏠")
        st.page_link("pages/sekisui_ocr_tool.py", label="⚙️ OCRツール", icon="📄")
        st.page_link("pages/06_ringi_workflow.py", label="🈸 稟議・申請ワークフロー", icon="✅")
        # st.page_link("pages/99_db_test.py", label="🛠 DBテスト", icon="🔧")
        
        st.divider()
        if st.button("ログアウト", type="secondary", use_container_width=True):
            # セッションをクリアしてリロード
            st.session_state.clear()
            st.rerun()

    # メインコンテンツ
    st.title("🏠 Dashboard")
    
    # 役割に応じたメッセージ
    if "課長" in st.session_state['role'] or "部長" in st.session_state['role']:
        st.info(f"お疲れ様です。現在、承認待ちの案件があるか「稟議・申請ワークフロー」から確認をお願いします。")
    else:
        st.success(f"お疲れ様です。本日の業務を開始しましょう。")

    # ダッシュボード風の配置
    col1, col2 = st.columns(2)
    
    with col1:
        with st.container(border=True):
            st.subheader("📢 社内お知らせ")
            st.markdown("""
            - **2025/12/23**: 電脳工場保守契約の更新時期が近づいています。
            - **2025/12/20**: 年末年始の休業期間について（12/29〜1/4）
            - **2025/12/01**: 新しい社内ポータル(本サイト)の運用を開始しました。
            """)
            
    with col2:
        with st.container(border=True):
            st.subheader("🚀 クイックアクション")
            st.write("よく使うツールへのショートカット")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("📄 稟議書を作成", use_container_width=True):
                    st.switch_page("pages/06_ringi_workflow.py")
            with col_b:
                if st.button("⚙️ 図面OCR処理", use_container_width=True):
                    st.switch_page("pages/sekisui_ocr_tool.py")

# --- セッション状態の初期化 ---
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False

# --- ルーティング ---
if not st.session_state["is_logged_in"]:
    login_page()
else:
    main_app()