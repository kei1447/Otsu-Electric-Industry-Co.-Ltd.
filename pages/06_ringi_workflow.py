import streamlit as st
import os
from PIL import Image, ImageDraw, ImageFont
import datetime

# --- 設定 ---
STAMP_SIZE = 120
STAMP_COLOR = (220, 50, 50) # 朱色

# ★ここにアップロードしたフォントファイル名を正確に入力してください★
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

def create_digital_stamp(name_text, datetime_obj):
    """
    電子印鑑生成（日時・秒対応版）
    - 上段：承認
    - 中段：YYYY/MM/DD (改行) HH:MM:SS
    - 下段：名前（3文字対応）
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
    
    # 3. 区切り線の位置定義
    # 2行入れるため、中段エリアをわずかに広げます (36-64% -> 34-66%)
    line_y1 = int(STAMP_SIZE * 0.34)
    line_y2 = int(STAMP_SIZE * 0.66)
    
    padding = 12
    draw.line((padding, line_y1, STAMP_SIZE - padding, line_y1), fill=STAMP_COLOR, width=2)
    draw.line((padding, line_y2, STAMP_SIZE - padding, line_y2), fill=STAMP_COLOR, width=2)

    # 4. フォント設定
    font_path = get_font_path()
    if not font_path:
        st.error(f"フォントファイル '{FONT_FILENAME}' が見つかりません。")
        return img

    try:
        # 上段「承認」
        size_top = 22 
        font_top = ImageFont.truetype(font_path, size_top)

        # 中段「日時」: 2行にするため小さく設定 (11pt)
        size_date = 11
        font_date = ImageFont.truetype(font_path, size_date)

        # 下段「名前」
        if len(name_text) >= 3:
            size_name = 18
        else:
            size_name = 24
        font_name = ImageFont.truetype(font_path, size_name)

    except Exception as e:
        st.error(f"フォント読み込みエラー: {e}")
        return img

    # 5. 文字の描画
    
    # --- 上段：「承認」 ---
    center_y_top = line_y1 / 2
    draw.text((STAMP_SIZE / 2, center_y_top), "承認", font=font_top, fill=STAMP_COLOR, anchor="mm")

    # --- 中段：日時 (2行) ---
    # フォーマット: YYYY/MM/DD \n HH:MM:SS
    date_str = datetime_obj.strftime("%Y/%m/%d\n%H:%M:%S")
    
    center_y_date = (line_y1 + line_y2) / 2
    # multiline_textで描画 (align='center' と anchor='mm' を組み合わせる)
    # spacing=1 で行間を詰めます
    draw.multiline_text(
        (STAMP_SIZE / 2, center_y_date), 
        date_str, 
        font=font_date, 
        fill=STAMP_COLOR, 
        anchor="mm", 
        align="center", 
        spacing=1
    )

    # --- 下段：名前 ---
    center_y_name = (line_y2 + STAMP_SIZE) / 2
    draw.text((STAMP_SIZE / 2, center_y_name - 2), name_text, font=font_name, fill=STAMP_COLOR, anchor="mm")

    return img

# --- UI ---
st.title("🈸 電子稟議・決裁デモ")

col1, col2 = st.columns(2)

with col1:
    st.subheader("承認アクション")
    approver_name = st.text_input("承認者名（名字）", "日比野")
    
    # 承認ボタン
if st.button("承認する（現在時刻で捺印）"):
        # 日本時間 (UTC+9) のタイムゾーンを定義
        JST = datetime.timezone(datetime.timedelta(hours=9))
        # 日本時間を指定して現在時刻を取得
        now = datetime.datetime.now(JST)
        
        stamp_img = create_digital_stamp(approver_name, now)
        st.session_state["demo_stamp"] = stamp_img
        
        if get_font_path():
            st.success(f"承認完了: {now.strftime('%H:%M:%S')}")

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