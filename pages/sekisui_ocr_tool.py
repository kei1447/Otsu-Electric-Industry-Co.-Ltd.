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
    # ルートにあるか確認
    model_path = YOLO_MODEL_PATH
    if not os.path.exists(model_path):
        # pagesフォルダから実行されている場合、親ディレクトリを見る必要があるかも
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
    """
    切り出した画像を結合する。
    ここでは「品名」の下に「数量」を配置し、さらに次のペアを下に繋げていく（あるいは横）。
    OCRの精度向上のため、1ペアごとに明確な余白(padding)を入れる。
    """
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

        # 1ペアの結合画像を作成（上が品名、下が数量）
        pair_h = name_crop.height + quantity_crop.height + padding
        pair_w = max(name_crop.width, quantity_crop.width)
        
        combined_pair = Image.new("RGB", (pair_w, pair_h), "white")
        combined_pair.paste(name_crop, (0, 0))
        # 数量は品名の下、padding分空けて貼る
        combined_pair.paste(quantity_crop, (0, name_crop.height + padding))

        # この1ペア画像と、「品名と数量の境界線（Y座標）」を記録しておく
        # 品名の終わり = name_crop.height
        split_y = name_crop.height + (padding / 2) 

        temp_combined.append({
            "image": combined_pair,
            "split_y": split_y # この画像のどこが境界線か
        })
        
        total_height += pair_h + padding
        max_width = max(max_width, pair_w)

        # 規定数でバッチ化
        if (index + 1) % max_pairs == 0 or (index + 1) == len(paired_regions):
            # APIリクエスト用の一枚絵を作成（縦に並べる）
            # ※OCR解析時に個別のペア画像を認識できるよう、ここではリストのまま返すか、
            # 結合しつつ座標管理をする必要がある。
            # シンプルにするため、「APIリクエスト回数削減」の優先度がそこまで高くなければ
            # 1ペアごとにOCRしたほうが座標判定は圧倒的に正確で簡単。
            # 今回は「精度」重視のリクエストなので、**結合せず1ペアずつ処理する** 方針に切り替えますか？
            # いや、リクエスト数は増やしたくないとのことなので、結合して送ります。
            pass

    # --- 修正方針 ---
    # 結合して送ると「どこからどこまでが1つ目のペアか」の判定が複雑になりズレの原因になります。
    # しかし「結合画像」メソッドは維持したい。
    # ここではシンプルに「1ペアごとにOCRにかける」のが最もズレません。
    # リクエスト数は増えますが、無料枠(月1000回)内なら許容範囲かもしれません。
    # ★今回は「リクエスト数は増やさずに」という要望があるので、結合ロジックを維持しつつ、
    # 結合画像を「ペアごと」にリストで返して、ループ処理側で対応します。
    # （※Google Vision APIは画像をバッチで送る機能もありますが、実装が複雑になるため）
    
    # 妥協案として、ここでは「結合画像」ではなく「切り出し画像のリスト（ペア済み）」を返します。
    # これにより perform_ocr は回数増えますが、精度は最強になります。
    # もし大量に処理して課金が怖い場合は「結合」ロジックに戻しますが、
    # 「ズレ」と「精度」を最優先するなら、個別に投げるのがベストです。
    
    # ユーザー要望の「リクエスト数は増やさずに」を守るため、
    # やはり結合しますが、解析ロジックを強化します。
    
    # 結合画像のリストを生成（以前と同じロジック）
    final_images_for_api = []
    
    # temp_combined に溜まったペア画像を縦に結合していく
    if temp_combined:
        # 今回はシンプル化のため、max_pairs などを考慮せず、ペア画像をそのままリストで返す形に変更してもよいでしょうか？
        # いえ、結合します。
        
        # 1つの結合画像にまとめる（バッチ単位）
        # ただし、座標解析を容易にするため、ここでは「1ペア = 1画像」として扱います。
        # APIリクエスト節約ロジックを入れると解析コードが肥大化しすぎるため、
        # 今回は「ズレ解消」を優先し、1ペア=1リクエストの構成に変更させてください。
        # （どうしても節約したい場合は、結合ロジック+高度な座標計算が必要になりますが、保守性が下がります）
        
        # ...と考えましたが、要望は「リクエスト数は増やさずに」ですね。
        # 承知しました。では結合します。
        pass

    # 再構築: 以前のロジックで結合画像を生成
    images_to_return = []
    
    current_batch = []
    current_height = 0
    current_width = 0
    
    for i, pair in enumerate(paired_regions):
        # 切り出し
        nx1, ny1, nx2, ny2 = pair["name_coords"]
        qx1, qy1, qx2, qy2 = pair["quantity_coords"]
        n_img = image.crop((nx1, ny1, nx2, ny2))
        q_img = image.crop((qx1, qy1, qx2, qy2))
        
        # 1つのペア画像を作る
        p_w = max(n_img.width, q_img.width)
        p_h = n_img.height + q_img.height + padding
        pair_img = Image.new("RGB", (p_w, p_h), "white")
        pair_img.paste(n_img, (0, 0))
        pair_img.paste(q_img, (0, n_img.height + padding))
        
        # 境界線（ここより上が品名）
        boundary_y = n_img.height + (padding / 2)
        
        current_batch.append({"img": pair_img, "boundary": boundary_y})
        current_height += p_h + padding # ペア同士の間隔
        current_width = max(current_width, p_w)
        
        # バッチ区切り
        if (i + 1) % max_pairs == 0 or (i + 1) == len(paired_regions):
            # 結合画像作成
            final_img = Image.new("RGB", (current_width, current_height), "white")
            y_offset = 0
            
            # 各ペアの座標情報を保持しておくためのリスト
            pair_locations = [] # {"top": y, "bottom": y+h, "boundary_relative": boundary}
            
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
    """
    結合画像をOCRにかけ、座標情報(metadata)を使って
    品名と数量を確実に分離・抽出する
    """
    image = combined_data["image"]
    metadata = combined_data["metadata"] # 各ペアの位置情報
    
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

        # annotations[0]は全文。annotations[1:]が個別の単語/行。
        # これらを使って、どのペアの、上(品名)か下(数量)かを判定する。
        
        # 各ペアごとにバケツを用意
        extracted_pairs = [{"name": [], "quantity": []} for _ in metadata]

        for text_info in annotations[1:]:
            text = text_info.description
            # バウンディングボックスの中心Y座標を計算
            vertices = text_info.bounding_poly.vertices
            y_coords = [v.y for v in vertices]
            center_y = sum(y_coords) / len(y_coords)
            
            # どのペア領域に属しているか判定
            for i, meta in enumerate(metadata):
                if meta["top"] <= center_y <= meta["bottom"]:
                    # このペアの中にいる。では品名(上)か数量(下)か？
                    if center_y < meta["split_y_absolute"]:
                        extracted_pairs[i]["name"].append(text)
                    else:
                        extracted_pairs[i]["quantity"].append(text)
                    break
        
        # 文字列結合と整形
        for p in extracted_pairs:
            # 配列で結合（英語スペース等考慮が必要だが、日本語や型番なら直結でよい場合も。今回はスペース結合して後で除去）
            raw_name = "".join(p["name"])
            raw_qty = "".join(p["quantity"])
            
            # --- ルール適用: O/o を 0 に変換 (品名のみ) ---
            cleaned_name = raw_name.replace("O", "0").replace("o", "0")
            cleaned_name = cleaned_name.replace(" ", "") # スペース除去
            
            cleaned_qty = raw_qty.replace(" ", "")
            
            results.append((cleaned_name, cleaned_qty))
            
    except Exception as e:
        st.error(f"OCR解析エラー: {e}")
        return []

    return results

# --- メイン処理 ---
def main():
    st.set_page_config(page_title="OCR Tool", layout="wide")
    
    st.title("📄 AI-OCR 自動集計ツール (高精度版)")
    st.markdown("YOLO検出 → 座標ベースOCR解析 → 編集＆ダウンロード")
    st.markdown("※品名内の 'O/o' は自動的に '0' に変換されます。")

    uploaded_file = st.file_uploader("PDF/TIFFアップロード", type=["pdf", "tif", "tiff"])

    # Session Stateでデータを保持（編集機能のため）
    if "ocr_result_df" not in st.session_state:
        st.session_state["ocr_result_df"] = None

    if uploaded_file:
        # ファイルが変わったらリセット
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
                
                # 1. YOLO検出
                detections = detect_regions_with_yolo(image)
                # 2. ペアリング
                paired = pair_regions(detections)
                # 3. 画像結合とメタデータ作成
                combined_data_list = combine_multiple_paired_regions(image, paired, padding=30)
                
                # 4. OCRと座標解析
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
        st.info("下の表のセルをダブルクリックすると修正できます。修正後にCSVをダウンロードしてください。")
        
        # Data Editorで編集可能にする
        edited_df = st.data_editor(
            st.session_state["ocr_result_df"],
            num_rows="dynamic", # 行の追加削除も許可したい場合は "dynamic"
            use_container_width=True,
            height=500
        )
        
        st.subheader("📥 ダウンロード")
        csv_buffer = edited_df.to_csv(index=False).encode('utf-8-sig')
        
        col1, col2 = st.columns([1, 4])
        with col1:
            st.download_button(
                label="CSVダウンロード",
                data=csv_buffer,
                file_name="ocr_result_edited.csv",
                mime="text/csv",
                type="primary"
            )

if __name__ == "__main__":
    main()