# STL Splitter

把超過 Bambu Lab A1 Mini 約 180 x 180 x 180 mm 列印範圍的 STL，沿指定軸切成兩個 STL。

這是第一版 MVP，重點是：

- 支援 binary STL 與常見 ASCII STL 讀取。
- 可用 `run_gui.bat` 開啟視窗，自行選擇本機 STL 檔案。
- 目前 GUI 固定為「一刀切割，輸出兩個部分」。
- 可先將模型繞 Z 軸旋轉，再沿指定軸切一刀。
- 將切面補成平面，輸出兩個可切片的 STL。
- 產生一份 JSON 報告，列出每個零件尺寸是否符合 180 mm 列印體積。
- 可另外輸出定位圓榫 pin STL，方便列印後黏合定位。

目前限制：

- 這版不做 mesh boolean，所以不會自動在零件上挖母榫孔。
- 對非常複雜、有多重交叉輪廓或非封閉 STL 的補面可能需要檢查。
- 若原模型單位不是 mm，請先在切片軟體或建模軟體確認尺度。

## 使用方式

### 互動式人工判斷介面

直接雙擊：

```text
run_interactive.bat
```

這個介面可以：

- 從上、前、後、左、右五個視角檢查模型。
- 用滑桿指定切割位置，也可以用 1/2、1/3、2/3、1/4、2/4、3/4 快捷按鈕吸附到常用等分點。
- 在切面地圖上用滑鼠點選圓榫孔位置。
- 旁邊只需要調兩個孔位參數：孔半徑、孔深度。
- 按 `Process STL` 後自動切割、挖孔、輸出 Part A / Part B / pins。

### 圖形介面

直接雙擊：

```text
run_gui.bat
```

視窗裡可以：

- 預設會帶入 `C:\A1Mini_STL_Splitter\test.stl`，如果檔案存在即可直接切割。
- 按 `Browse...` 選擇本機 STL 檔案。
- 選擇輸出資料夾。
- 選擇切割軸。`test.stl` 預設使用 `y`。
- `Rotate Z before split` 可以先把模型水平旋轉再切。`test.stl` 預設使用 `0` 度。
- 預設不產生定位 pin，也不自動挖孔；先輸出乾淨的 Part A / Part B 最安全。
- 需要定位 pin 時，再把 Pins 改成 2 並勾選 `Cut socket holes`。注意：複雜模型可能挖到功能面或薄壁，列印前一定要在切片軟體檢查孔位。
- 按 `Split STL` 輸出 Part A、Part B、定位 pin 和報告。

### 命令列

```powershell
& "C:\Users\jason\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  C:\A1Mini_STL_Splitter\split_stl.py `
  input.stl `
  --out-dir C:\A1Mini_STL_Splitter\my_split `
  --build-volume 180 180 180 `
  --rotate-z 120 `
  --axis x `
  --pins 0
```

常用參數：

- `--axis x|y|z|auto`：切割軸，預設 `auto`，會選模型最長軸。
- `--position 90`：指定切割平面位置。未指定時使用該軸中心。
- `--build-volume 180 180 180`：列印尺寸限制。
- `--pins 0..N`：輸出 N 個獨立定位圓榫 STL，預設 0。複雜模型建議先用 0。
- `--pin-radius 3`：圓榫半徑，單位 mm。
- `--pin-length 12`：圓榫長度，單位 mm。
- `--pin-clearance 0.2`：給未來母榫孔使用的建議間隙，會寫入報告。
- `--socket-holes`：在兩個零件切面挖圓榫孔，需要 `vendor` 內的 `trimesh` 和 `manifold3d`。複雜模型請謹慎使用。

## 建議工作流

1. 先用本工具切成兩件。
2. 把兩個 STL 放入 Bambu Studio，確認各自尺寸是否小於 180 mm。
3. 若使用定位 pin，另印 pins，黏合時以 pin 作為對位輔助。
4. 真正需要「公榫/母榫自動挖孔」時，下一版可接 `trimesh + manifold3d` 做布林。
