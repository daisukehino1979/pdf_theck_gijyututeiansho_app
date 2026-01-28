import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import io

# ---------------------------------------------------------
# 1. 設定 (必ず一番最初に書く必要があります)
# ---------------------------------------------------------
st.set_page_config(page_title="PDFコメント抽出ツール", layout="wide")

# ---------------------------------------------------------
# 2. 関数定義
# ---------------------------------------------------------

def rgb_to_hex(color_tuple):
    """
    PDFの色情報(0.0-1.0のタプル)を16進数カラーコード(#RRGGBB)に変換する関数
    """
    if not color_tuple:
        return "指定なし"
    
    rgb = [int(c * 255) for c in color_tuple]
    
    if len(rgb) == 3:
        return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])
    elif len(rgb) == 1: # グレースケール
        val = rgb[0]
        return '#{:02x}{:02x}{:02x}'.format(val, val, val)
    else:
        return str(color_tuple)

def get_drawing_number(page, width, height):
    """
    ページ右下の領域から、最も「右下」にあるテキストブロックを特定して取得する関数
    """
    # 検索範囲を「右半分」かつ「下半分」と広めにとる
    clip_rect = fitz.Rect(width * 0.5, height * 0.5, width, height)
    
    # テキストブロックを取得 (位置情報付き)
    blocks = page.get_text("blocks", clip=clip_rect)
    
    if not blocks:
        return "(読取不可)"

    candidates = []
    for b in blocks:
        # b[4]がテキスト内容
        text = b[4].strip()
        if not text:
            continue
        
        # 明らかに図面番号ではないゴミ（Scaleなど）を除外したい場合はここでフィルタ可能
        # 今回は位置判定で解決するため、あえてフィルタせず残します

        candidates.append({
            "text": text,
            "y1": b[3], # 下端の座標（大きいほど下）
            "x1": b[2]  # 左端の座標（大きいほど右）※右寄せならx1(右端)を使う手もありますがx0でも十分です
        })
    
    if not candidates:
        return "(読取不可)"

    # ソートの優先順位：
    # 1. ページの下の方にあるもの (y1が大きい順)
    # 2. 同じ高さなら、右にあるもの (x1が大きい順)
    candidates.sort(key=lambda x: (x["y1"], x["x1"]), reverse=True)
    
    # 一番「右下」にある要素を返す
    best_candidate = candidates[0]["text"]
    
    # 改行を削除して返す
    return best_candidate.replace('\n', '')

# ---------------------------------------------------------
# 3. メイン処理
# ---------------------------------------------------------
def main():
    st.title("🏗️ 建築図面 PDFコメント抽出ツール (高精度版)")
    st.markdown("PDFをアップロードすると、**図面番号（右下）**と**コメント**を自動抽出し、Excel一覧を作成します。")

    # サイドバー（念のための微調整用ですが、基本はいじらなくてOKです）
    st.sidebar.header("⚙️ 設定")
    st.sidebar.info("右下の読み取りロジックは自動化されています。")

    uploaded_file = st.file_uploader("PDFファイルをドラッグ＆ドロップしてください", type=["pdf"])

    if uploaded_file is not None:
        st.success("ファイルを読み込みました。解析を開始します...")

        # PDFを開く
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        
        extracted_data = []
        progress_bar = st.progress(0)
        total_pages = len(doc)

        for i, page in enumerate(doc):
            progress_bar.progress((i + 1) / total_pages)

            # ① 図面番号の読み取り（高精度版関数を使用）
            width = page.rect.width
            height = page.rect.height
            
            drawing_no = get_drawing_number(page, width, height)

            # ② コメント抽出
            annots = page.annots()
            if annots:
                for annot in annots:
                    content = annot.info.get("content")
                    if not content:
                        continue

                    # 色情報の取得
                    stroke_color = annot.colors.get("stroke")
                    color_hex = rgb_to_hex(stroke_color)
                    
                    # 簡易色名判定
                    color_name = "その他"
                    if color_hex.upper() == "#FF0000": color_name = "赤"
                    elif color_hex.upper() == "#0000FF": color_name = "青"
                    elif color_hex.upper() == "#000000": color_name = "黒"

                    extracted_data.append({
                        "ページ": i + 1,
                        "図面番号": drawing_no,
                        "コメント内容": content,
                        "作成者": annot.info.get("title", ""),
                        "更新日時": annot.info.get("modDate", ""),
                        "色名": color_name,
                        "色コード": color_hex
                    })

        # 解析完了後の表示
        if extracted_data:
            df = pd.DataFrame(extracted_data)
            
            st.subheader("📊 抽出結果プレビュー")
            st.dataframe(df)

            # Excel作成
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='コメント一覧')
            
            output_data = output.getvalue()

            st.download_button(
                label="📥 Excelファイルとしてダウンロード",
                data=output_data,
                file_name=f"comment_list_{uploaded_file.name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("コメントが見つかりませんでした。PDFに注釈が含まれているか確認してください。")

if __name__ == "__main__":
    main()