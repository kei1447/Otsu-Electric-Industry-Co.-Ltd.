import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import datetime
import io

# --- 設定 ---
STAMP_SIZE = 120
STAMP_COLOR = (220, 50, 50) # 朱色

def create_digital_stamp(name, date_str):
    """
    名前と日付を受け取り、電子印鑑画像(PNG)を生成して返す関数
    """
    # 1. 空の透明画像を作成
    img = Image.new('RGBA', (STAMP_SIZE, STAMP_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # 2. 外枠の円を描く
    margin = 5
    draw.ellipse(
        (margin, margin, STAMP_SIZE - margin, STAMP_SIZE - margin),
        outline=STAMP_COLOR,
        width=3
    )
    
    # 3. 横線を引く (日付の上下)
    line_y1 = STAMP_SIZE * 0.35
    line_y2 = STAMP_SIZE * 0.65
    padding = 15
    draw.line((padding, line_y1, STAMP_SIZE - padding, line_y1), fill=STAMP_COLOR, width=2)
    draw.line((padding, line_y2, STAMP_SIZE - padding, line_y2), fill=STAMP_COLOR, width=2)

    # 4. 文字を描く
    # フォントが無いとエラーになるのでデフォルトロードを試みる
    # ※本番では日本語フォントファイル(.ttf)をフォルダに置いて指定するのがベスト
    try:
        # Windows等に入っているフォントを指定する場合（環境による）
        # font = ImageFont.truetype("msgothic.ttc", 18) 
        # Streamlit Cloud用にはデフォルトを使用（日本語が出ない可能性あり）
        # そのため、今回は簡易的に描画します
        font_date = ImageFont.load_default()
        font_name = ImageFont.load_default()
    except:
        font_date = None
        font_name = None

    # 本来はここで日本語描画を行いますが、環境依存を避けるため
    # Streamlit Cloud上では「日付」のみを中央に描画する簡易版とします
    # ★本格実装時は、NotoSansJP.ttf などを同梱して読み込ませます
    
    # 日付 (2025.12.23)
    # テキストの位置調整などは微調整が必要
    # ここではシンプル化のため実装ロジックのみ提示
    
    return img

# --- 本番に向けた改良版スタンプ生成（日本語フォントなしでも動く版） ---
def generate_simple_stamp(text_top, text_date, text_bottom):
    """
    上段：役職/名字、中段：日付、下段：名前 などを配置するイメージ
    Streamlit Cloudのデフォルト環境では日本語フォントがないため、
    実運用では 'font' フォルダを作って .ttf ファイルを置く必要があります。
    今回はイメージ確認用です。
    """
    # キャンバス
    W, H = 100, 100
    image = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    
    # 円
    draw.ellipse((2, 2, W-2, H-2), outline="red", width=3)
    # 線
    draw.line((15, 36, 85, 36), fill="red", width=1)
    draw.line((15, 64, 85, 64), fill="red", width=1)
    
    # ※ここで文字を入れる処理が入りますが、
    # フォントファイルがないと□□になってしまうため、
    # 実際の実装時には「IPAフォント」などをアップロードして使います。
    
    return image

# --- UI ---
st.title("🈸 電子稟議・決裁デモ")

st.info("ここに「電子印鑑」の自動生成イメージを表示します。承認ボタンを押すと、このハンコが押される仕組みになります。")

col1, col2 = st.columns(2)

with col1:
    st.subheader("承認アクション")
    approver_name = st.text_input("承認者名（名字）", "大津")
    approval_date = st.date_input("承認日", datetime.date.today())
    
    if st.button("承認する（ハンコ生成）"):
        # ハンコ画像を生成
        stamp_img = generate_simple_stamp(approver_name, str(approval_date), "")
        
        # セッションに保存して右側で表示
        st.session_state["demo_stamp"] = stamp_img
        st.success(f"{approver_name} さんの承認印を生成しました！")

with col2:
    st.subheader("稟議書プレビュー")
    # 稟議書の背景（紙）に見立てた白い箱
    with st.container(border=True):
        st.markdown("### 稟議書")
        st.markdown(f"**件名:** 電脳工場保守更新の件")
        st.markdown("**承認欄:**")
        
        # ハンコ枠を表示
        stamp_cols = st.columns(4)
        with stamp_cols[0]:
            st.caption("課長")
            if "demo_stamp" in st.session_state:
                st.image(st.session_state["demo_stamp"], width=80)
            else:
                st.markdown("<div style='height:80px; border:1px dashed #ccc; text-align:center; line-height:80px; color:#ccc;'>印</div>", unsafe_allow_html=True)
        
        with stamp_cols[1]:
            st.caption("部長")
            st.markdown("<div style='height:80px; border:1px solid #333;'></div>", unsafe_allow_html=True)

st.markdown("---")
st.caption("※本番環境では、明朝体フォントを使用して「大津」「25.12.23」のようなリアルな印影を生成します。")