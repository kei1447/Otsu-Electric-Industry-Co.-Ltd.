import streamlit as st
import os
import io
import logging
import pandas as pd
from pdf2image import convert_from_bytes
from PIL import Image
from ultralytics import YOLO
from google.cloud import vision
from google.oauth2 import service_account

# --- 設定 ---
# 実行時の基準ディレクトリはルートフォルダになるため、パスはそのまま指定可能です
YOLO_MODEL_PATH = "best.pt" 
MAX_PAIRS_PER_IMAGE = 12
NAME_LABEL = 0
QUANTITY_LABEL = 1

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# --- 認証と初期化 ---
@st.cache_resource
def load_models():
    """モデルとAPIクライアントをロード"""
    # 1. YOLOモデル
    if not os.path.exists(YOLO_MODEL_PATH):
        st.error(f"モデルファイル({YOLO_MODEL_PATH})がルートフォルダに見つかりません。")
        return None, None
    
    try:
        yolo = YOLO(YOLO_MODEL_PATH)
    except Exception as e:
        st.error(f"YOLOモデル読み込みエラー: {e}")
        return None, None

    # 2. Google Vision Client (Streamlit Secretsから読み込み)
    try:
        # secrets.toml の [gcp_service_account] セクションを読み込む
        if "gcp_service_account" not in st.secrets:
            st.error("SecretsにGCP認証情報が設定されていません。")
            return yolo, None
            
        key_dict = dict(st.secrets["gcp_service_account"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        client = vision.ImageAnnotatorClient(credentials=creds)
    except Exception as e:
        st.error(f"Google Cloud認証設定エラー: {e}")
        return yolo, None
        
    return yolo, client

yolo_model, vision_client = load_models()

# --- 関数群 (YOLO, 画像処理, OCR) ---

def pdf_to_images(file_bytes):
    try:
        return convert_from_bytes(file_bytes, dpi=300)
    except Exception as e:
        st.error(f"PDF変換エラー: {e}")
        return []

def tiff_to_images(file_bytes):
    images = []
    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            for i in range(getattr(img, "n_frames", 1)):
                img.seek(i)
                images.append(img.copy())
    except Exception as e:
        st.error(f"TIFF変換エラー: {e}")
    return images

def detect_regions_with_yolo(image):
    results = yolo_model(image)
    if not results or not results[0].boxes:
        return []
    boxes = results[0].boxes.xyxy.cpu().numpy()
    labels = results[0].boxes.cls.cpu().numpy()
    return [{"coords": box, "label": label} for box, label in zip(boxes, labels)]

def pair_regions(regions):
    name_regions = [r for r in regions if r["label"] == NAME_LABEL]
    quantity_regions = [r for r in regions if r["label"] == QUANTITY_LABEL]
    name_regions.sort(key=lambda x: x["coords"][1])
    quantity_regions.sort(key=lambda x: x["coords"][1])

    paired = []
    for i in range(min(len(name_regions), len(quantity_regions))):
        paired.append({
            "name_coords": name_regions[i]["coords"],
            "quantity_coords": quantity_regions[i]["coords"]
        })
    return paired

def combine_multiple_paired_regions(image, paired_regions, max_pairs=MAX_PAIRS_PER_IMAGE, padding=20):
    if not paired_regions:
        return []

    combined_images = []
    temp_combined = []
    total_height = 0
    max_width = 0

    for index, pair in enumerate(paired_regions):
        nx1, ny1, nx2, ny2 = pair["name_coords"]
        qx1, qy1, qx2, qy2 = pair["quantity_coords"]
        
        name_crop = image.crop((nx1, ny1, nx2, ny2))
        quantity_crop = image.crop((qx1, qy1, qx2, qy2))

        pair_h = name_crop.height + quantity_crop.height + padding
        pair_w = max(name_crop.width, quantity_crop.width)
        
        combined_pair = Image.new("RGB", (pair_w, pair_h), "white")
        combined_pair.paste(name_crop, (0, 0))
        combined_pair.paste(quantity_crop, (0, name_crop.height + padding))

        temp_combined.append(combined_pair)
        total_height += pair_h + padding
        max_width = max(max_width, pair_w)

        if (index + 1) % max_pairs == 0 or (index + 1) == len(paired_regions):
            final_combined = Image.new("RGB", (max_width, total_height), "white")
            current_y = 0
            for pair_image in temp_combined:
                final_combined.paste(pair_image, (0, current_y))
                current_y += pair_image.height + padding
            combined_images.append(final_combined)
            temp_combined = []
            total_height = 0

    return combined_images

def perform_ocr(image):
    if not vision_client:
        return ""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="PNG")
    content = img_byte_arr.getvalue()
    vision_image = vision.Image(content=content)
    try:
        response = vision_client.text_detection(image=vision_image)
        if response.text_annotations:
            return response.text_annotations[0].description.strip()
    except Exception as e:
        st.error(f"OCR APIエラー: {e}")
    return ""

def parse_ocr_result(ocr_text):
    lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
    parsed = []
    for i in range(0, len(lines), 2):
        item_name = lines[i] if i < len(lines) else ""
        quantity = lines[i+1] if i+1 < len(lines) else ""
        item_name = item_name.replace(" ", "")
        parsed.append((item_name, quantity))
    return parsed

# --- メイン処理 ---
def main():
    # 認証チェック（必要なら有効化）
    # if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    #     st.warning("左上の Home からログインしてください")
    #     st.stop()
    
    st.title("📄 AI-OCR 自動集計ツール")
    st.markdown("YOLO検出 → 結合 → Google Vision OCR")

    uploaded_file = st.file_uploader("PDF/TIFFアップロード", type=["pdf", "tif", "tiff"])

    if uploaded_file and st.button("処理開始"):
        if not yolo_model or not vision_client:
            st.error("初期化失敗：モデルか認証情報が不足しています。")
            st.stop()

        with st.spinner("処理中..."):
            file_bytes = uploaded_file.read()
            ext = os.path.splitext(uploaded_file.name)[1].lower()
            
            if ext == ".pdf":
                images = pdf_to_images(file_bytes)
            else:
                images = tiff_to_images(file_bytes)
        
        if not images:
            st.error("画像を読み込めませんでした。")
            st.stop()

        results_data = []
        progress_bar = st.progress(0)
        
        for i, image in enumerate(images):
            progress_bar.progress((i + 1) / len(images))
            detections = detect_regions_with_yolo(image)
            paired = pair_regions(detections)
            combined_imgs = combine_multiple_paired_regions(image, paired, padding=20)
            
            for c_img in combined_imgs:
                ocr_text = perform_ocr(c_img)
                parsed = parse_ocr_result(ocr_text)
                for item, qty in parsed:
                    results_data.append([f"Page {i+1}", item, qty])

        st.success("完了しました！")
        if results_data:
            df = pd.DataFrame(results_data, columns=["ページ", "品名", "数量"])
            st.dataframe(df)
            csv_buffer = df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("CSVダウンロード", csv_buffer, f"ocr_result.csv", "text/csv")
        else:
            st.warning("データが検出されませんでした。")

if __name__ == "__main__":
    main()