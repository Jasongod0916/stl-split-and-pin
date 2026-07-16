# STL Splitter

STL Splitter 是一個可在瀏覽器中使用的 STL 裁切工具。它可以把超出列印尺寸的模型切成兩個零件，讓使用者手動指定切割位置與定位孔，最後直接下載 ZIP。

## 功能

- 在瀏覽器中開啟本機 binary / ASCII STL。
- 使用 3D Orbit 與正投影視圖檢查模型。
- 手動選擇切割軸與切割位置。
- 提供 1/2、1/3、1/4 等分輔助點。
- 在 Cut Face 上繪製、移動、選取、複製、刪除定位孔。
- 顯示孔位安全提示，協助避開危險位置。
- 在切割面產生對應的母孔。
- 匯出兩個切割 STL、所有定位 pin STL，以及 JSON 報告。
- 所有輸出會打包成 ZIP，直接由瀏覽器下載。

## 線上使用

開啟：

```text
https://jasongod0916.github.io/stl-split-and-pin/
```

也可以直接用瀏覽器開啟本機的 `web_app.html`。

基本流程：

1. 按 `Open STL` 選擇本機 STL 檔。
2. 選擇切割軸與切割位置。
3. 用 `Draw` 在 Cut Face 上放置定位孔。
4. 調整孔半徑、孔深度與公差。
5. 按 `Split and download ZIP`。
6. 將輸出的 STL 放進切片軟體檢查後再列印。

## ZIP 內容

下載的 ZIP 會包含：

- `*_part_A.stl`
- `*_part_B.stl`
- `*_alignment_pin_*.stl`
- `*_split_report.json`

## 注意事項

- 母孔功能是針對切割面定位 pin 設計，不是通用 CAD 布林運算。
- 孔位請避開薄壁、外框邊緣與模型功能面。
- STL 單位會以毫米處理。
- 列印前請務必在 Bambu Studio 或其他切片軟體中檢查輸出結果。

## 本機工具

專案也保留本機 Python 工具：

```text
run_interactive.bat
run_gui.bat
```

一般使用建議直接使用瀏覽器版本。
