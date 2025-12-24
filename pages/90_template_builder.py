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

    # --- State管理 ---
    if "builder_fields" not in st.session_state:
        st.session_state["builder_fields"] = []
    if "editing_field_index" not in st.session_state:
        st.session_state["editing_field_index"] = None # 今どのフィールドを編集しているか
    if "target_template_id" not in st.session_state:
        st.session_state["target_template_id"] = None # 既存修正時のID

    # --- ヘルパー関数 ---
    def move_item(index, direction):
        fields = st.session_state["builder_fields"]
        if direction == "up" and index > 0:
            fields[index], fields[index-1] = fields[index-1], fields[index]
        elif direction == "down" and index < len(fields) - 1:
            fields[index], fields[index+1] = fields[index+1], fields[index]
        # 編集状態をリセット
        st.session_state["editing_field_index"] = None

    def delete_item(index):
        st.session_state["builder_fields"].pop(index)
        st.session_state["editing_field_index"] = None

    def load_field_to_editor(index):
        st.session_state["editing_field_index"] = index

    # --- 1. モード選択 (新規 or 編集) ---
    with st.container(border=True):
        mode = st.radio("作業モード", ["新規作成", "既存テンプレートの編集"], horizontal=True)
        
        if mode == "既存テンプレートの編集":
            # テンプレート一覧取得
            templates_df = conn.query("SELECT template_id, template_name, schema_json FROM M_Templates ORDER BY template_id DESC", ttl=0)
            if templates_df.empty:
                st.info("編集できるテンプレートがありません。")
            else:
                options = {row['template_name']: row for i, row in templates_df.iterrows()}
                selected_name = st.selectbox("編集するテンプレートを選択", list(options.keys()))
                
                # ロードボタン
                if st.button("このテンプレートを読み込む"):
                    row = options[selected_name]
                    st.session_state["target_template_id"] = row['template_id']
                    st.session_state["builder_template_name"] = row['template_name']
                    # JSON読み込み
                    schema = row['schema_json']
                    if isinstance(schema, str): schema = json.loads(schema)
                    st.session_state["builder_fields"] = schema
                    st.session_state["editing_field_index"] = None
                    st.rerun()
        else:
            # 新規モード切替時にIDをクリア（一度だけ）
            if st.session_state["target_template_id"] is not None:
                st.session_state["target_template_id"] = None
                st.session_state["builder_fields"] = []
                st.session_state["builder_template_name"] = ""
                st.rerun()

    # --- 画面構成 ---
    col_editor, col_preview = st.columns([1, 1])

    # === 左側: フィールドエディタ ===
    with col_editor:
        st.subheader("1. 項目定義")
        
        # 編集中のフィールドがあるか？
        edit_idx = st.session_state["editing_field_index"]
        is_edit_mode = (edit_idx is not None)
        
        # フォーム初期値の設定
        default_label = ""
        default_type = "text"
        default_width_label = "全幅 (100%)"
        default_options = ""
        width_map = {"全幅 (100%)": 100, "1/2 (50%)": 50, "1/3 (33%)": 33, "1/4 (25%)": 25}
        inv_width_map = {v: k for k, v in width_map.items()}

        if is_edit_mode:
            target_field = st.session_state["builder_fields"][edit_idx]
            default_label = target_field['label']
            default_type = target_field['type']
            w_val = target_field.get('width', 100)
            default_width_label = inv_width_map.get(w_val, "全幅 (100%)")
            if target_field.get('options'):
                default_options = ",".join(target_field['options'])
            st.info(f"📝 項目「{default_label}」を編集中...")

        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                input_label = st.text_input("項目名", value=default_label, key="in_lbl")
            with c2:
                input_type = st.selectbox("タイプ", ["text", "number", "date", "textarea", "select", "checkbox"], index=["text", "number", "date", "textarea", "select", "checkbox"].index(default_type), key="in_typ")
            with c3:
                input_width_lbl = st.selectbox("横幅", list(width_map.keys()), index=list(width_map.keys()).index(default_width_label), key="in_wid")
                input_width = width_map[input_width_lbl]
            
            input_options_str = ""
            if input_type == "select":
                input_options_str = st.text_input("選択肢 (カンマ区切り)", value=default_options, placeholder="A, B, C", key="in_opt")

            # 追加/更新ボタン
            btn_text = "変更を保存" if is_edit_mode else "フィールドを追加"
            if st.button(btn_text, type="primary" if is_edit_mode else "secondary", use_container_width=True):
                if not input_label:
                    st.warning("項目名は必須です")
                else:
                    field_def = {
                        "label": input_label,
                        "type": input_type,
                        "width": input_width,
                        "options": input_options_str.split(",") if input_type == "select" and input_options_str else []
                    }
                    
                    if is_edit_mode:
                        # 上書き更新
                        st.session_state["builder_fields"][edit_idx] = field_def
                        st.session_state["editing_field_index"] = None # 編集終了
                        st.success("更新しました")
                    else:
                        # 新規追加
                        st.session_state["builder_fields"].append(field_def)
                    
                    st.rerun()
            
            if is_edit_mode:
                if st.button("編集をキャンセル"):
                    st.session_state["editing_field_index"] = None
                    st.rerun()

        st.markdown("---")
        st.subheader("フィールド一覧 (並べ替え・編集)")
        
        if not st.session_state["builder_fields"]:
            st.caption("項目がありません")
        else:
            for i, field in enumerate(st.session_state["builder_fields"]):
                # 編集中の行はハイライト
                bg_color = "rgba(255, 255, 0, 0.1)" if i == edit_idx else "transparent"
                with st.container():
                    c_up, c_down, c_info, c_edit, c_del = st.columns([1, 1, 6, 1.5, 1])
                    
                    with c_up:
                        if i > 0 and st.button("↑", key=f"up_{i}"):
                            move_item(i, "up")
                            st.rerun()
                    with c_down:
                        if i < len(st.session_state["builder_fields"]) - 1 and st.button("↓", key=f"down_{i}"):
                            move_item(i, "down")
                            st.rerun()
                    
                    with c_info:
                        w_lbl = "全幅" if field['width'] == 100 else f"{field['width']}%"
                        st.markdown(f"**{field['label']}** <small>({field['type']} / {w_lbl})</small>", unsafe_allow_html=True)
                    
                    with c_edit:
                        if st.button("✎", key=f"edit_{i}"):
                            load_field_to_editor(i)
                            st.rerun()
                    
                    with c_del:
                        if st.button("🗑", key=f"del_{i}"):
                            delete_item(i)
                            st.rerun()
                    st.divider()

    # === 右側: プレビュー & 保存 ===
    with col_preview:
        st.subheader("2. プレビュー & 保存")
        
        # テンプレート名の入力（既存編集時は初期値を入れる）
        current_name = st.session_state.get("builder_template_name", "")
        template_name = st.text_input("テンプレート名", value=current_name, placeholder="例: 支払依頼書")
        
        with st.container(border=True):
            st.markdown(f"### 📄 {template_name if template_name else '(名称未定)'}")
            st.markdown("---")
            
            # レンダリング
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

        # 保存ボタン
        is_update = (st.session_state["target_template_id"] is not None)
        save_label = "テンプレートを更新" if is_update else "新規登録"
        
        if st.button(save_label, type="primary", use_container_width=True):
            if not template_name or not fields:
                st.error("テンプレート名と項目を設定してください")
            else:
                schema_json = json.dumps(fields, ensure_ascii=False)
                try:
                    with conn.session as s:
                        if is_update:
                            # UPDATE
                            s.execute(
                                text("UPDATE M_Templates SET template_name=:name, schema_json=:json WHERE template_id=:tid"),
                                {"name": template_name, "json": schema_json, "tid": st.session_state["target_template_id"]}
                            )
                            st.success(f"テンプレート「{template_name}」を更新しました！")
                        else:
                            # INSERT
                            s.execute(
                                text("INSERT INTO M_Templates (template_name, schema_json) VALUES (:name, :json)"),
                                {"name": template_name, "json": schema_json}
                            )
                            st.success(f"テンプレート「{template_name}」を新規登録しました！")
                            st.session_state["builder_fields"] = []
                            st.session_state["builder_template_name"] = ""
                        
                        s.commit()
                except Exception as e:
                    st.error(f"保存エラー: {e}")

if __name__ == "__main__":
    main()