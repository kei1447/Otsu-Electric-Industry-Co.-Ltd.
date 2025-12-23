import streamlit as st
import os
from PIL import Image, ImageDraw, ImageFont
import datetime

# --- 設定 ---
STAMP_SIZE = 120
STAMP_COLOR = (220, 50, 50) # 朱色

# ★ここにアップロードしたフォントファイル名を正確に入力してください★
# ※もしファイル名が違う場合は書き換えてください
FONT_FILENAME = "ShipporiMincho-Bold.ttf" 

def get_font_path():
    """フォントファイルの場所を賢く探す関数"""
    path1 = os.path.join("fonts", FONT_FILENAME)
    path2 = FONT_FILENAME
    path3 = os.path.join("pages", "fonts", FONT_FILENAME)
    
    if os.path.exists(path1): return path1
    elif os.path.exists(path2): return path2
    elif os.path.exists(path3): return path3
    else: return None

def create_digital_stamp(name_text, date_text):
    """
    電子印鑑生成（デザイン調整版）
    - 上段：承認（大きく）
    - 中段：日付（少し大きく）
    - 下段：名前（3文字対応・自動縮小）
    - 配置：完全中央揃え
    """
    # 1. キャンバス作成
    img = Image.new('RGBA', (STAMP_SIZE, STAMP_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # 2. 外枠の円
    margin = 4
    draw.ellipse(
        (margin, margin, STAMP_SIZE - margin, STAMP_SIZE - margin),
        outline=STAMP_COLOR,
        width=3
    )
    
    # 3. 区切り線の位置定義（全体のバランス調整）
    # 上段(承認)エリア: 0% ～ 36%
    # 中段(日付)エリア: 36% ～ 64%
    # 下段(名前)エリア: 64% ～ 100%
    line_y1 = int(STAMP_SIZE * 0.36)
    line_y2 = int(STAMP_SIZE * 0.64)
    
    # 線を描画
    padding = 12 # 線の左右の余白
    draw.line((padding, line_y1, STAMP_SIZE - padding, line_y1), fill=STAMP_COLOR, width=2)
    draw.line((padding, line_y2, STAMP_SIZE - padding, line_y2), fill=STAMP_COLOR, width=2)

    # 4. フォント読み込みとサイズ設定
    font_path = get_font_path()
    
    if not font_path:
        st.error(f"フォントファイル '{FONT_FILENAME}' が見つかりません。")
        return img

    try:
        # --- 文字サイズの調整 ---
        
        # 上段「承認」: 大きくドシッと
        size_top = 22 
        font_top = ImageFont.truetype(font_path, size_top)

        # 中段「日付」: 少し大きく見やすく
        size_date = 15 
        font_date = ImageFont.truetype(font_path, size_date)

        # 下段「名前」: 文字数によってサイズを自動変更
        if len(name_text) >= 3:
            size_name = 18 # 3文字以上なら少し小さくして収める
        else:
            size_name = 24 # 2文字以下なら大きく
        font_name = ImageFont.truetype(font_path, size_name)

    except Exception as e:
        st.error(f"フォント読み込みエラー: {e}")
        return img

    # 5. 文字の描画（完全中央揃えロジック）
    # anchor="mm" (Middle-Middle) を使うと、指定した座標が文字の中心になります
    
    # --- 上段：「承認」 ---
    # エリアの中心Y座標 = (0 + line_y1) / 2
    center_y_top = line_y1 / 2
    draw.text((STAMP_SIZE / 2, center_y_top), "承認", font=font_top, fill=STAMP_COLOR, anchor="mm")

    # --- 中段：日付 ---
    # エリアの中心Y座標 = (line_y1 + line_y2) / 2
    center_y_date = (line_y1 + line_y2) / 2
    # 少しだけ上に補正（フォントのベースライン調整）
    draw.text((STAMP_SIZE / 2, center_y_date - 1), date_text, font=font_date, fill=STAMP_COLOR, anchor="mm")

    # --- 下段：名前 ---
    # エリアの中心Y座標 = (line_y2 + STAMP_SIZE) / 2
    center_y_name = (line_y2 + STAMP_SIZE) / 2
    # 円の下部にぶつからないよう少し上に補正
    draw.text((STAMP_SIZE / 2, center_y_name - 2), name_text, font=font_name, fill=STAMP_COLOR, anchor="mm")

    return img

# --- UI ---
st.title("🈸 電子稟議・決裁デモ")

col1, col2 = st.columns(2)

with col1:
    st.subheader("承認アクション")
    # デフォルトを3文字ネームにしてテストしやすくしました
    approver_name = st.text_input("承認者名（名字）", "佐々木")
    
    today = datetime.date.today()
    date_str = f"{today.year-2000}.{today.month:02}.{today.day:02}"
    
    if st.button("承認する（ハンコ生成）"):
        stamp_img = create_digital_stamp(approver_name, date_str)
        st.session_state["demo_stamp"] = stamp_img
        
        if get_font_path():
            st.success("電子印影を生成しました！")

with col2:
    st.subheader("プレビュー")
    with st.container(border=True):
        st.markdown(f"**件名:** 電脳工場保守更新の件")
        st.markdown("**承認欄:**")
        
        stamp_cols = st.columns(4)
        with stamp_cols[0]:
            st.caption("課長")
            if "demo_stamp" in st.session_state:
                st.image(st.session_state["demo_stamp"], width=100)
            else:
                st.markdown("<div style='height:100px; border:1px dashed #ccc; text-align:center; line-height:100px;'>印</div>", unsafe_allow_html=True)