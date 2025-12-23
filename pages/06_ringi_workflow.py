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
    # 候補1: ルートの fonts フォルダにある場合 (標準)
    path1 = os.path.join("fonts", FONT_FILENAME)
    # 候補2: 同じフォルダにある場合
    path2 = FONT_FILENAME
    # 候補3: pagesフォルダの中に fonts がある場合
    path3 = os.path.join("pages", "fonts", FONT_FILENAME)
    
    if os.path.exists(path1):
        return path1
    elif os.path.exists(path2):
        return path2
    elif os.path.exists(path3):
        return path3
    else:
        return None

def create_digital_stamp(name_text, date_text):
    """
    名前と日付を受け取り、電子印鑑画像(PNG)を生成して返す関数
    """
    # 1. キャンバス作成（背景透明）
    img = Image.new('RGBA', (STAMP_SIZE, STAMP_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # 2. 外枠の円
    margin = 5
    draw.ellipse(
        (margin, margin, STAMP_SIZE - margin, STAMP_SIZE - margin),
        outline=STAMP_COLOR,
        width=3
    )
    
    # 3. 横線（日付の上下）
    line_y1 = STAMP_SIZE * 0.36
    line_y2 = STAMP_SIZE * 0.64
    padding = 15
    draw.line((padding, line_y1, STAMP_SIZE - padding, line_y1), fill=STAMP_COLOR, width=2)
    draw.line((padding, line_y2, STAMP_SIZE - padding, line_y2), fill=STAMP_COLOR, width=2)

    # 4. フォントの読み込み
    font_path = get_font_path()
    
    if font_path:
        try:
            # 正常にフォントが見つかった場合
            # 名前用（大きめ）
            font_name = ImageFont.truetype(font_path, 24)
            # 日付用（小さめ）
            font_date = ImageFont.truetype(font_path, 14)
        except Exception as e:
            st.error(f"フォント読み込みエラー: {e}")
            return img
    else:
        # フォントが見つからない場合のエラー表示
        st.error(f"⚠️ フォントファイル '{FONT_FILENAME}' が見つかりませんでした。")
        st.info("確認: 'fonts' フォルダの中に .ttf ファイルが入っていますか？")
        # デバッグ用: 現在のファイル構成を表示
        st.write("現在の場所:", os.getcwd())
        if os.path.exists("fonts"):
            st.write("fontsフォルダの中身:", os.listdir("fonts"))
        else:
            st.write("fontsフォルダ自体が見つかりません。")
        return img

    # 5. 文字の描画（中央揃え計算）
    # --- 日付 (中段) ---
    bbox = draw.textbbox((0, 0), date_text, font=font_date)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(((STAMP_SIZE - w) / 2, (STAMP_SIZE - h) / 2), date_text, font=font_date, fill=STAMP_COLOR)

    # --- 名前 (下段) ---
    # ※名字が2文字の場合のバランス調整
    bbox = draw.textbbox((0, 0), name_text, font=font_name)
    w = bbox[2] - bbox[0]
    # 下段の中心位置におく
    y_pos = line_y2 + 5 
    draw.text(((STAMP_SIZE - w) / 2, y_pos), name_text, font=font_name, fill=STAMP_COLOR)
    
    # --- 役職/上段 (今回は簡易的に「認」または空欄) ---
    top_text = "認"
    bbox = draw.textbbox((0, 0), top_text, font=font_date)
    w = bbox[2] - bbox[0]
    y_pos_top = line_y1 - 18
    draw.text(((STAMP_SIZE - w) / 2, y_pos_top), top_text, font=font_date, fill=STAMP_COLOR)

    return img

# --- UI ---
st.title("🈸 電子稟議・決裁デモ")

col1, col2 = st.columns(2)

with col1:
    st.subheader("承認アクション")
    approver_name = st.text_input("承認者名（名字）", "大津")
    # 今日の日付を文字列に (例: 25.12.23)
    today = datetime.date.today()
    date_str = f"{today.year-2000}.{today.month:02}.{today.day:02}"
    
    if st.button("承認する（ハンコ生成）"):
        # ハンコ画像を生成
        stamp_img = create_digital_stamp(approver_name, date_str)
        st.session_state["demo_stamp"] = stamp_img
        
        # フォントが見つかっていれば成功メッセージ
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