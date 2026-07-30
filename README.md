# 工廠不良表單 OCR 自動登打

每天拍照不良記錄表（製令、品號、作業人員、正字畫不良項目），自動辨識並登打到 Excel。

## OCR 能不能辨識？結論

**可以，但不建議「全自動、零人工」一步到位。**

| 內容 | 傳統 OCR（如 Tesseract） | Vision LLM（本專案預設） |
|------|--------------------------|---------------------------|
| 製令 / 品號（印刷或正楷） | 通常可用 | 較穩 |
| 手寫人名、潦草數字 | 不穩 | 明顯較好 |
| **正字畫計數** | 幾乎不可靠（會當文字辨識，不會數筆畫） | **可行**（把格子當圖理解並計數） |
| 歪斜、反光、陰影照片 | 差 | 中等到良好 |

實務建議：**AI 先讀 → 人眼 10~30 秒審核低信心欄位 → 一鍵寫入 Excel**。通常仍可比下班逐張手打快很多。

### 為什麼正字畫特別難？

正字畫不是「讀出正這個字」，而是要數：

- `正` = 5
- 未完成的一／二／三／四筆 = 1~4
- `正正一` = 11

傳統 OCR 常把潦草筆畫認成雜訊或其他字。本專案用 **多模態 Vision 模型**直接看格子並換算數量，再用 `zheng_count` 規則做二次校正。

### 如何提高成功率

1. **表單版面固定**（可用本專案產生的空白表）
2. 正字畫寫在框內，不要壓線、不要連筆跨格
3. 製令／品號盡量正楷、蓋章或印出條碼
4. 拍照整張入鏡、光線均勻、避免反光
5. 保留「審核頁」：信心分數低的欄位用黃色提醒

可在 `config/defect_schema.json` 依你們工廠實際不良項目修改。

## 快速開始

```bash
pip install -r requirements.txt

# 建立空白表單與統計 Excel
python main.py init

# 啟動網頁（手機也可上傳拍照）
python main.py serve
# 開啟 http://127.0.0.1:8000
```

啟用真實影像辨識（建議）：

```bash
export OPENAI_API_KEY=sk-...
# 可選：export OCR_VISION_MODEL=gpt-4o-mini
# 可選相容其他 OpenAI 介面：export OPENAI_BASE_URL=https://api.openai.com/v1
python main.py serve
```

未設定 API Key 時為**示範模式**（可跑通上傳→審核→Excel 流程；檔名若為 `日期_製令_品號_人員.jpg` 會帶入表頭）。

### 命令列單張處理

```bash
python main.py recognize photo.jpg --write-excel --json-out out.json
```

## 專案結構

```
app/
  ocr_engine.py    # Vision / 示範辨識
  zheng_count.py   # 正字畫換算
  excel_writer.py  # 寫入 defect_stats.xlsx
  preprocess.py    # 矯正、強化
  form_template.py # 產生空白表
  web.py           # 上傳與審核 UI
config/defect_schema.json
templates/
```

## 下一步可加強

- 依你們真實表單框線做「欄位裁切」再辨識，準度會再升
- 製令／品號改條碼或 QR，表頭幾乎 100% 準
- 對接既有 Excel 範本欄位對應（改 schema 即可）
- 累積人工修正資料後可微調／做專用正字畫模型
