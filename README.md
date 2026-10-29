# 多平台电商账单自动对账 (Ecommerce Reconcile)

上传多个平台/店铺导出的 Excel 或 CSV，自动标准化并生成差异报告。

## 功能 v1.0

- 自动识别平台（淘宝/天猫、京东、拼多多、抖店等）
- 标准化：订单号、日期、金额、手续费、状态、商品、店铺
- **优先按订单号**跨文件匹配；无订单号时用 **日期+金额**
- 输出：匹配成功、金额不一致、仅在文件 A/B/C…、全部标准化流水、汇总
- 隐私优先：处理完即删，无账号

## 适用场景

- 平台账单 vs 自家记账表
- 淘宝账单 vs 拼多多账单（找重复/遗漏）
- 多店铺导出对账

## 本地运行

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 http://127.0.0.1:8000 ，上传 `samples/` 下两个示例文件测试。

## License

MIT
