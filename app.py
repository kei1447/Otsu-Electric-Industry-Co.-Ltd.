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
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
except Exception:
    st.error("Secretsの設定が読み込めません。project_url と key を確認してください。")
    st.stop()

# --- Supabaseクライアントの初期化 ---
@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# --- ログイン処理関数 ---
def login_with_auth(email, password):
    client = init_supabase()
    try:
        # 1. Authチェック
        auth_response = client.auth.sign_in_with_password({"email": email, "password": password})
        
        # 2. 名簿(M_Users)チェック
        conn = st.connection("supabase", type="sql")
        df = conn.query(f"SELECT * FROM M_Users WHERE user_id = '{email}'", ttl=0)
        
        if df.empty:
            return False, "システム利用権限がありません（ユーザーマスタ未登録）。", None
        
        user_data = df.iloc[0]
        return True, "ログイン成功", user_data
        
    except Exception as e:
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
            email = st.text_input("メールアドレス", placeholder="yourname@otsu-elec.co.jp")
            password = st.text_input("パスワード", type="password")
            submitted = st.form_submit_button("ログイン", use_container_width=True)
            
            if submitted:
                if not email or not password:
                    st.warning("メールアドレスとパスワードを入力してください。")
                else:
                    with st.spinner("認証中..."):
                        is_success, msg, user_data = login_with_auth(email, password)
                    
                    if is_success:
                        st.success("認証成功！")
                        st.session_state["is_logged_in"] = True
                        st.session_state["user_name"] = user_data["display_name"]
                        st.session_state["role"] = user_data["role"]
                        st.session_state["user_email"] = email
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)

# --- 画面2: メインポータル ---
def main_app():
    # サイドバー（メニュー）
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state['user_name']} 様")
        st.caption(f"権限: {st.session_state['role']}")
        st.divider()
        
        st.markdown("### 📌 Menu")
        st.page_link("app.py", label="🏠 ホーム", icon="🏠")
        
        # ★ここを修正しました (06_workflow.py)
        st.page_link("pages/06_workflow.py", label="✅ 業務ワークフロー", icon="✅")
        
        # 新機能へのリンクも追加
        st.page_link("pages/07_search_database.py", label="🔎 案件データベース", icon="🔎")
        st.page_link("pages/08_dashboard.py", label="📊 経営ダッシュボード", icon="📊")
        st.page_link("pages/sekisui_ocr_tool.py", label="⚙️ OCRツール", icon="📄")
        
        # 管理者向けメニュー（区分け）
        st.divider()
        st.caption("管理者メニュー")
        st.page_link("pages/90_template_builder.py", label="🛠 帳票テンプレート作成", icon="🛠")
        
        st.divider()
        if st.button("ログアウト", type="secondary", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # メインコンテンツ
    st.title("🏠 Dashboard")
    
    # 役割別メッセージ
    if "課長" in st.session_state['role'] or "部長" in st.session_state['role'] or "社長" in st.session_state['role']:
        st.info(f"お疲れ様です。承認待ち案件や経営状況は、左のメニューから確認できます。")
    else:
        st.success(f"お疲れ様です。本日の業務を開始しましょう。")

    col1, col2 = st.columns(2)
    
    with col1:
        with st.container(border=True):
            st.subheader("📢 社内お知らせ")
            st.markdown("""
            - **2025/12/24**: 年末調整の提出期限は明日までです。
            - **2025/12/23**: 電脳工場保守契約の更新時期が近づいています。
            - **2025/12/01**: 新しい社内ポータル(本サイト)の運用を開始しました。
            """)
            
    with col2:
        with st.container(border=True):
            st.subheader("🚀 クイックアクション")
            st.write("よく使うツールへのショートカット")
            col_a, col_b = st.columns(2)
            with col_a:
                # ★ここも修正しました
                if st.button("📄 申請書を作成", use_container_width=True):
                    st.switch_page("pages/06_workflow.py")
            with col_b:
                if st.button("⚙️ 図面OCR処理", use_container_width=True):
                    st.switch_page("pages/sekisui_ocr_tool.py")

# --- ルーティング ---
if "is_logged_in" not in st.session_state:
    st.session_state["is_logged_in"] = False

if not st.session_state["is_logged_in"]:
    login_page()
else:
    main_app()