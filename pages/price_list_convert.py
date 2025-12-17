import streamlit as st
import pandas as pd
import io
import os
import openpyxl
from openpyxl.styles import Font
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
    st.warning("⚠️ ログインしていません。左上の「app」に戻ってログインしてください。")
    st.stop()

# --- 設定 ---
NEW_COLUMNS = [
    "品目コード", "機種", "品名", "背番号", "単位", 
    "生産原価", "販売単価", "処理平米", "単位重量", "科目名"
]
TARGET_FONT = "游ゴシック"
FONT_SIZE = 11
ROW_HEIGHT = 18.75
COL_WIDTH = 8.38

def process_excel(uploaded_file):
    """
    Excelデータを読み込み、VBAと同様の整形処理を行ってバイナリデータを返す
    """
    # 拡張子を確認
    filename = uploaded_file.name
    ext = os.path.splitext(filename)[1].lower()
    
    # .xls の場合はエンジンを 'xlrd' に指定、それ以外(.xlsx)は 'openpyxl' (またはdefault)
    engine = 'xlrd' if ext == '.xls' else None

    # 1. データ読み込み
    # header=None, skiprows=3 で、4行目以降のデータを取得
    df = pd.read_excel(uploaded_file, header=None, skiprows=3, engine=engine)

    # 列数を10列に絞る
    df = df.iloc[:, :10]

    # ヘッダーを設定
    df.columns = NEW_COLUMNS

    # --- Excelファイルとしての書き出し処理 ---
    # ※出力は常に最新の .xlsx 形式になります（これが最も安全で互換性が高いため）
    output = io.BytesIO()
    
    sheet_name = '単価マスタ'
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # 2. 書式設定
        standard_font = Font(name=TARGET_FONT, size=FONT_SIZE)
        
        for row in worksheet.iter_rows():
            for cell in row:
                cell.font = standard_font
            worksheet.row_dimensions[row[0].row].height = ROW_HEIGHT

        # 3. 列幅の設定
        for i in range(1, len(NEW_COLUMNS) + 1):
            col_letter = get_column_letter(i)
            worksheet.column_dimensions[col_letter].width = COL_WIDTH

        # 4. テーブルへの変換
        min_col = 1
        max_col = len(NEW_COLUMNS)
        min_row = 1
        max_row = len(df) + 1 

        ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{max_row}"
        tab = Table(displayName="Table1", ref=ref)
        style = TableStyleInfo(
            name="TableStyleMedium2", 
            showFirstColumn=False,
            showLastColumn=False, 
            showRowStripes=True, 
            showColumnStripes=False
        )
        tab.tableStyleInfo = style
        worksheet.add_table(tab)

    return output.getvalue()

# --- メイン画面 ---
def main():
    st.set_page_config(page_title="Data Converter", layout="wide")
    
    st.title("🏭 電脳工場データ整形ツール")
    st.markdown("電脳工場v1.0 (.xls形式) から出力された製品リストに対応しています。")

    uploaded_file = st.file_uploader("Excelファイルをアップロード", type=["xlsx", "xls", "xlsm"])

    if uploaded_file:
        if st.button("変換実行"):
            try:
                # ファイルオブジェクトごと渡すように変更
                processed_data = process_excel(uploaded_file)
                
                st.success("変換が完了しました！")
                
                # ダウンロード時は常に .xlsx に変換して返します
                new_filename = os.path.splitext(uploaded_file.name)[0] + "_formatted.xlsx"
                
                st.download_button(
                    label="整形済みExcelをダウンロード",
                    data=processed_data,
                    file_name=new_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                st.divider()
                st.caption("▼ 変換後のデータプレビュー")
                preview_df = pd.read_excel(io.BytesIO(processed_data))
                st.dataframe(preview_df)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
                if ".xls" in uploaded_file.name:
                    st.info("ヒント: requirements.txt に xlrd が含まれているか確認してください。")

if __name__ == "__main__":
    main()