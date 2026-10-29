import os
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_default_upload = Path(tempfile.gettempdir()) / "ecom_reconcile_uploads"
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(_default_upload)))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "25"))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_FILES = int(os.getenv("MAX_FILES", "6"))

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# 平台识别关键词
PLATFORM_KEYWORDS = {
    "淘宝/天猫": ["淘宝", "天猫", "taobao", "tmall", "支付宝", "alipay"],
    "京东": ["京东", "jd.com", "京东商城", "京东钱包"],
    "拼多多": ["拼多多", "pdd", "pinduoduo", "多多钱包"],
    "抖音/抖店": ["抖音", "抖店", "tiktok", "巨量"],
    "快手": ["快手", "kwaishop"],
    "亚马逊": ["amazon", "亚马逊", "amz"],
    "虾皮": ["shopee", "虾皮"],
    "微信小店": ["微信小店", "视频号小店", "微信"],
    "通用": [],
}

# 列名别名
COLUMN_ALIASES = {
    "order_id": [
        "订单号", "订单编号", "主订单号", "子订单号", "交易号", "商户订单号",
        "order_id", "order_no", "order id", "订单ID", "支付订单号", "平台订单号",
    ],
    "date": [
        "日期", "订单日期", "成交时间", "支付时间", "入账时间", "结算时间",
        "下单时间", "创建时间", "date", "order_date", "支付日期", "到账时间",
    ],
    "amount": [
        "金额", "订单金额", "实付金额", "支付金额", "结算金额", "入账金额",
        "商家实收", "实收金额", "成交金额", "amount", "settlement", "收款金额",
        "买家实付", "应付金额", "总金额",
    ],
    "fee": [
        "手续费", "服务费", "佣金", "扣点", "平台费", "技术服务费",
        "fee", "commission", "佣金金额", "扣费",
    ],
    "status": [
        "状态", "订单状态", "结算状态", "交易状态", "status", "资金状态",
    ],
    "product": [
        "商品", "商品名称", "品名", "标题", "product", "sku名称", "货品",
    ],
    "shop": [
        "店铺", "店铺名称", "卖家", "shop", "store", "网点",
    ],
    "buyer": [
        "买家", "买家昵称", "客户", "buyer", "收货人",
    ],
}