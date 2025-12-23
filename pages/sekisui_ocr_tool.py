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

# --- ログイン認証チェック ---
if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("⚠️ ログインしていません。左上の「app」に戻ってログインしてください。")
    st.stop()

# --- 設定 ---
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
    model_path = YOLO_MODEL_PATH
    if not os.path.exists(model_path):
        if os.path.exists(f"../{YOLO_MODEL_PATH}"):
            model_path = f"../{YOLO_MODEL_PATH}"
        else:
            st.error(f"モデルファイル({YOLO_MODEL_PATH})が見つかりません。")
            return None, None
    
    try:
        yolo = YOLO(model_path)
    except Exception as e:
        st.error(f"YOLOモデル読み込みエラー: {e}")
        return None, None

    # 2. Google Vision Client
    try:
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

# --- 関数群 ---

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
    
    # 上から順にソート（Y座標）
    name_regions.sort(key=lambda x: x["coords"][1])
    quantity_regions.sort(key=lambda x: x["coords"][1])

    paired = []
    # 少ない方に合わせてペアリング
    for i in range(min(len(name_regions), len(quantity_regions))):
        paired.append({
            "name_coords": name_regions[i]["coords"],
            "quantity_coords": quantity_regions[i]["coords"]
        })
    return paired

def combine_multiple_paired_regions(image, paired_regions, max_pairs=MAX_PAIRS_PER_IMAGE, padding=20):
    if not paired_regions:
        return []

    images_to_return = []
    
    current_batch = []
    current_height = 0
    current_width = 0
    
    for i, pair in enumerate(paired_regions):
        nx1, ny1, nx2, ny2 = pair["name_coords"]
        qx1, qy1, qx2, qy2 = pair["quantity_coords"]
        n_img = image.crop((nx1, ny1, nx2, ny2))
        q_img = image.crop((qx1, qy1, qx2, qy2))
        
        p_w = max(n_img.width, q_img.width)
        p_h = n_img.height + q_img.height + padding
        pair_img = Image.new("RGB", (p_w, p_h), "white")
        pair_img.paste(n_img, (0, 0))
        pair_img.paste(q_img, (0, n_img.height + padding))
        
        boundary_y = n_img.height + (padding / 2)
        
        current_batch.append({"img": pair_img, "boundary": boundary_y})
        current_height += p_h + padding
        current_width = max(current_width, p_w)
        
        if (i + 1) % max_pairs == 0 or (i + 1) == len(paired_regions):
            final_img = Image.new("RGB", (current_width, current_height), "white")
            y_offset = 0
            
            pair_locations = []
            
            for item in current_batch:
                p_img = item["img"]
                final_img.paste(p_img, (0, y_offset))
                
                pair_locations.append({
                    "top": y_offset,
                    "bottom": y_offset + p_img.height,
                    "split_y_absolute": y_offset + item["boundary"]
                })
                
                y_offset += p_img.height + padding
            
            images_to_return.append({
                "image": final_img,
                "metadata": pair_locations
            })
            
            current_batch = []
            current_height = 0
            current_width = 0
            
    return images_to_return

def perform_ocr_and_parse(combined_data):
    image = combined_data["image"]
    metadata = combined_data["metadata"]
    
    if not vision_client:
        return []

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format="PNG")
    content = img_byte_arr.getvalue()
    vision_image = vision.Image(content=content)

    results = []
    try:
        response = vision_client.text_detection(image=vision_image)
        annotations = response.text_annotations
        
        if not annotations:
            return []

        extracted_pairs = [{"name": [], "quantity": []} for _ in metadata]

        for text_info in annotations[1:]:
            text = text_info.description
            vertices = text_info.bounding_poly.vertices
            y_coords = [v.y for v in vertices]
            center_y = sum(y_coords) / len(y_coords)
            
            for i, meta in enumerate(metadata):
                if meta["top"] <= center_y <= meta["bottom"]:
                    if center_y < meta["split_y_absolute"]:
                        extracted_pairs[i]["name"].append(text)
                    else:
                        extracted_pairs[i]["quantity"].append(text)
                    break
        
        for p in extracted_pairs:
            raw_name = "".join(p["name"])
            raw_qty = "".join(p["quantity"])
            
            # O/o -> 0 変換
            cleaned_name = raw_name.replace("O", "0").replace("o", "0")
            cleaned_name = cleaned_name.replace(" ", "")
            
            cleaned_qty = raw_qty.replace(" ", "")
            
            results.append((cleaned_name, cleaned_qty))
            
    except Exception as e:
        st.error(f"OCR解析エラー: {e}")
        return []

    return results

# --- メイン処理 ---
def main():
    st.set_page_config(page_title="OCR Tool", layout="wide")
    
    st.title("📄 AI-OCR 自動集計ツール")
    st.markdown("YOLO検出 → 座標ベースOCR解析 → 編集＆ダウンロード")

    uploaded_file = st.file_uploader("PDF/TIFFアップロード (例: 251223AM.pdf)", type=["pdf", "tif", "tiff"])

    if "ocr_result_df" not in st.session_state:
        st.session_state["ocr_result_df"] = None

    if uploaded_file:
        if "last_uploaded_file" not in st.session_state or st.session_state["last_uploaded_file"] != uploaded_file.name:
            st.session_state["ocr_result_df"] = None
            st.session_state["last_uploaded_file"] = uploaded_file.name

        if st.button("処理開始"):
            if not yolo_model or not vision_client:
                st.error("初期化失敗：モデルか認証情報が不足しています。")
                st.stop()

            with st.spinner("画像を解析中..."):
                file_bytes = uploaded_file.read()
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                
                if ext == ".pdf":
                    images = pdf_to_images(file_bytes)
                else:
                    images = tiff_to_images(file_bytes)
            
            if not images:
                st.error("画像を読み込めませんでした。")
                st.stop()

            all_results = []
            progress_bar = st.progress(0)
            
            for i, image in enumerate(images):
                progress_bar.progress((i + 1) / len(images))
                
                detections = detect_regions_with_yolo(image)
                paired = pair_regions(detections)
                combined_data_list = combine_multiple_paired_regions(image, paired, padding=30)
                
                for data in combined_data_list:
                    page_results = perform_ocr_and_parse(data)
                    for item, qty in page_results:
                        all_results.append({
                            "ページ": f"Page {i+1}",
                            "品名": item,
                            "数量": qty
                        })

            st.success("解析完了！")
            
            if all_results:
                st.session_state["ocr_result_df"] = pd.DataFrame(all_results)
            else:
                st.warning("データが検出されませんでした。")
                st.session_state["ocr_result_df"] = None

    # --- 結果表示と編集エリア ---
    if st.session_state["ocr_result_df"] is not None:
        st.subheader("📝 結果の確認・編集")
        st.info("下の表を編集後、ダウンロードしてください。")
        
        edited_df = st.data_editor(
            st.session_state["ocr_result_df"],
            num_rows="dynamic",
            use_container_width=True,
            height=500
        )
        
        st.subheader("📥 ダウンロード")
        
        # ▼▼▼ ファイル名自動生成ロジック ▼▼▼
        # 元ファイル名を取得 (例: 251223AM.pdf)
        original_name = st.session_state.get("last_uploaded_file", "result.csv")
        # 拡張子を除去 (例: 251223AM)
        base_name = os.path.splitext(original_name)[0]
        # 頭に '20' をつけて .csv にする (例: 20251223AM.csv)
        download_filename = f"20{base_name}.csv"
        # ▲▲▲ ここまで ▲▲▲
        
        csv_buffer = edited_df.to_csv(index=False).encode('utf-8-sig')
        
        col1, col2 = st.columns([1, 4])
        with col1:
            st.download_button(
                label=f"CSVダウンロード ({download_filename})", # ボタンにもファイル名を表示
                data=csv_buffer,
                file_name=download_filename,
                mime="text/csv",
                type="primary"
            )

if __name__ == "__main__":
    main()