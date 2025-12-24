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
    
    # 認証チェック
    if "is_logged_in" not in st.session_state or not st.session_state["is_logged_in"]:
        st.warning("ログインしてください。")
        st.stop()

    conn = st.connection("supabase", type="sql")

    # --- セッション状態で「作成中のフィールド」を管理 ---
    if "builder_fields" not in st.session_state:
        st.session_state["builder_fields"] = []

    # --- 画面構成 ---
    col_editor, col_preview = st.columns([1, 1])

    # === 左側: エディタ ===
    with col_editor:
        st.subheader("1. 項目を定義")
        
        with st.container(border=True):
            # 新しいフィールドの追加フォーム
            c1, c2 = st.columns(2)
            with c1:
                new_label = st.text_input("項目名 (ラベル)", placeholder="例: 出張先、利用交通機関")
            with c2:
                new_type = st.selectbox("入力タイプ", ["text", "number", "date", "textarea", "select", "checkbox"])
            
            # selectの場合の選択肢入力
            new_options = ""
            if new_type == "select":
                new_options = st.text_input("選択肢 (カンマ区切り)", placeholder="新幹線, 飛行機, 電車")

            if st.button("フィールドを追加"):
                if not new_label:
                    st.warning("項目名は必須です")
                else:
                    field_def = {
                        "label": new_label,
                        "type": new_type,
                        "options": new_options.split(",") if new_type == "select" and new_options else []
                    }
                    st.session_state["builder_fields"].append(field_def)
                    st.rerun()

        st.markdown("---")
        st.subheader("現在のフィールド構成")
        
        # 追加されたフィールドのリスト表示（削除機能付き）
        if not st.session_state["builder_fields"]:
            st.info("まだ項目がありません。上から追加してください。")
        else:
            for i, field in enumerate(st.session_state["builder_fields"]):
                with st.container(border=True):
                    c_info, c_del = st.columns([4, 1])
                    with c_info:
                        st.markdown(f"**{i+1}. {field['label']}** ({field['type']})")
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
        
        template_name = st.text_input("テンプレート名", placeholder="例: 出張申請書 v1")
        
        with st.container(border=True):
            st.markdown(f"### 📄 {template_name if template_name else '(名称未定)'}")
            st.markdown("---")
            
            # --- プレビューレンダリング ---
            # ここではinputの戻り値を受け取る必要はないので表示だけ
            for field in st.session_state["builder_fields"]:
                lbl = field['label']
                typ = field['type']
                
                if typ == "text":
                    st.text_input(lbl, key=f"prev_{lbl}")
                elif typ == "number":
                    st.number_input(lbl, step=1, key=f"prev_{lbl}")
                elif typ == "date":
                    st.date_input(lbl, key=f"prev_{lbl}")
                elif typ == "textarea":
                    st.text_area(lbl, key=f"prev_{lbl}")
                elif typ == "select":
                    st.selectbox(lbl, field['options'], key=f"prev_{lbl}")
                elif typ == "checkbox":
                    st.checkbox(lbl, key=f"prev_{lbl}")
            
            st.markdown("---")
            # 共通項目（固定）のイメージ
            st.caption("※ 件名・金額・添付ファイル・承認ルート設定は、全テンプレート共通で自動付与されます。")

        # 保存ボタン
        if st.button("この内容でテンプレートを登録", type="primary", use_container_width=True):
            if not template_name:
                st.error("テンプレート名を入力してください")
            elif not st.session_state["builder_fields"]:
                st.error("フィールドが1つもありません")
            else:
                # JSONに変換して保存
                schema_json = json.dumps(st.session_state["builder_fields"], ensure_ascii=False)
                
                try:
                    with conn.session as s:
                        s.execute(
                            text("INSERT INTO M_Templates (template_name, schema_json) VALUES (:name, :json)"),
                            {"name": template_name, "json": schema_json}
                        )
                        s.commit()
                    st.success(f"テンプレート「{template_name}」を保存しました！")
                    st.session_state["builder_fields"] = [] # クリア
                except Exception as e:
                    st.error(f"保存エラー: {e}")

    # --- 既存テンプレート一覧 ---
    st.markdown("---")
    st.subheader("登録済みテンプレート一覧")
    df_temp = conn.query("SELECT * FROM M_Templates ORDER BY template_id DESC", ttl=0)
    st.dataframe(df_temp, use_container_width=True)

if __name__ == "__main__":
    main()