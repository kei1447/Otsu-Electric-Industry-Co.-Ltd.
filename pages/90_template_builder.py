import streamlit as st
import pandas as pd
from sqlalchemy import text
import json
from supabase import create_client

# --- Supabase初期化 ---
try:
    SUPABASE_URL = st.secrets["connections"]["supabase"]["project_url"]
    SUPABASE_KEY = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except:
    st.error("Secrets設定エラー")
    st.stop()

def main():
    st.set_page_config(page_title="帳票テンプレート作成", layout="wide")
    st.title("🛠 ノーコード帳票ビルダー")
    
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()

    conn = st.connection("supabase", type="sql")

    if "builder_fields" not in st.session_state:
        st.session_state["builder_fields"] = []

    # --- ヘルパー関数: リストの並べ替え ---
    def move_item(index, direction):
        fields = st.session_state["builder_fields"]
        if direction == "up" and index > 0:
            fields[index], fields[index-1] = fields[index-1], fields[index]
        elif direction == "down" and index < len(fields) - 1:
            fields[index], fields[index+1] = fields[index+1], fields[index]

    # --- 画面構成 ---
    col_editor, col_preview = st.columns([1, 1])

    # === 左側: エディタ ===
    with col_editor:
        st.subheader("1. 項目を定義")
        
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                new_label = st.text_input("項目名 (ラベル)", placeholder="例: 金額、支払先")
            with c2:
                new_type = st.selectbox("入力タイプ", ["text", "number", "date", "textarea", "select", "checkbox"])
            with c3:
                # 横幅設定
                width_map = {"全幅 (100%)": 100, "1/2 (50%)": 50, "1/3 (33%)": 33, "1/4 (25%)": 25}
                new_width_label = st.selectbox("横幅サイズ", list(width_map.keys()))
                new_width = width_map[new_width_label]
            
            new_options = ""
            if new_type == "select":
                new_options = st.text_input("選択肢 (カンマ区切り)", placeholder="A, B, C")

            if st.button("フィールドを追加", use_container_width=True):
                if not new_label:
                    st.warning("項目名は必須です")
                else:
                    field_def = {
                        "label": new_label,
                        "type": new_type,
                        "width": new_width, # 幅情報を保存
                        "options": new_options.split(",") if new_type == "select" and new_options else []
                    }
                    st.session_state["builder_fields"].append(field_def)
                    st.rerun()

        st.markdown("---")
        st.subheader("フィールド構成 (並べ替え可)")
        
        if not st.session_state["builder_fields"]:
            st.info("項目を追加してください")
        else:
            for i, field in enumerate(st.session_state["builder_fields"]):
                with st.container(border=True):
                    # レイアウト: [↑][↓] [内容] [削除]
                    c_up, c_down, c_info, c_del = st.columns([1, 1, 8, 1])
                    
                    with c_up:
                        if i > 0:
                            if st.button("↑", key=f"up_{i}"):
                                move_item(i, "up")
                                st.rerun()
                    with c_down:
                        if i < len(st.session_state["builder_fields"]) - 1:
                            if st.button("↓", key=f"down_{i}"):
                                move_item(i, "down")
                                st.rerun()
                    
                    with c_info:
                        w_lbl = "全幅" if field['width'] == 100 else f"幅{field['width']}%"
                        st.markdown(f"**{field['label']}** ({field['type']}) - {w_lbl}")
                        if field['options']:
                            st.caption(f"選択肢: {', '.join(field['options'])}")
                            
                    with c_del:
                        if st.button("🗑", key=f"del_{i}"):
                            st.session_state["builder_fields"].pop(i)
                            st.rerun()

            if st.button("全クリア", type="secondary"):
                st.session_state["builder_fields"] = []
                st.rerun()

    # === 右側: プレビュー & 保存 ===
    with col_preview:
        st.subheader("2. プレビュー & 保存")
        template_name = st.text_input("テンプレート名", placeholder="例: 支払依頼書 v2")
        
        with st.container(border=True):
            st.markdown(f"### 📄 {template_name if template_name else '(名称未定)'}")
            st.markdown("---")
            
            # --- レンダリングロジック (行の折り返し計算) ---
            fields = st.session_state["builder_fields"]
            if fields:
                rows = []
                current_row = []
                current_width_sum = 0
                
                for f in fields:
                    w = f.get('width', 100)
                    if current_width_sum + w > 100:
                        rows.append(current_row)
                        current_row = []
                        current_width_sum = 0
                    current_row.append(f)
                    current_width_sum += w
                if current_row: rows.append(current_row)
                
                # 描画
                for row_fields in rows:
                    cols = st.columns([f.get('width', 100) for f in row_fields])
                    for col, field in zip(cols, row_fields):
                        with col:
                            lbl = field['label']
                            typ = field['type']
                            if typ == "text": st.text_input(lbl, key=f"p_{lbl}")
                            elif typ == "number": st.number_input(lbl, step=1, key=f"p_{lbl}")
                            elif typ == "date": st.date_input(lbl, key=f"p_{lbl}")
                            elif typ == "textarea": st.text_area(lbl, key=f"p_{lbl}")
                            elif typ == "select": st.selectbox(lbl, field['options'], key=f"p_{lbl}")
                            elif typ == "checkbox": st.checkbox(lbl, key=f"p_{lbl}")
            
            st.markdown("---")
            st.caption("※ 共通項目（件名・金額・添付・ルート）は自動付与されます")

        if st.button("テンプレートを登録", type="primary", use_container_width=True):
            if not template_name or not fields:
                st.error("テンプレート名と項目を設定してください")
            else:
                schema_json = json.dumps(fields, ensure_ascii=False)
                try:
                    with conn.session as s:
                        s.execute(
                            text("INSERT INTO M_Templates (template_name, schema_json) VALUES (:name, :json)"),
                            {"name": template_name, "json": schema_json}
                        )
                        s.commit()
                    st.success(f"保存しました: {template_name}")
                    st.session_state["builder_fields"] = []
                except Exception as e:
                    st.error(f"保存エラー: {e}")

    # --- 一覧 ---
    st.markdown("---")
    st.subheader("登録済みテンプレート")
    df_temp = conn.query("SELECT * FROM M_Templates ORDER BY template_id DESC", ttl=0)
    st.dataframe(df_temp, use_container_width=True)

if __name__ == "__main__":
    main()