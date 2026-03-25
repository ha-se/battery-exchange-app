"""
定数定義モジュール
"""

# 対応メーカーリスト
MAKERS = ['Panasonic', 'YAMAHA', 'DBS', 'glafit', 'シナネンサイクル', 'KUROAD']

# 自社交換分の組み合わせ定義（E列の会社名 → V列のPT企業名）
SELF_EXCHANGE_MAPPING = {
    'トヨタモビリティ東京株式会社': 'TMT',
    '江ノ島電鉄株式会社': '江ノ電',
    'モビリティプラットフォーム株式会社': 'MPF',
    '東急バス株式会社': '東急バス'
}

# 自社交換対象PT企業リスト
TARGET_PT_COMPANIES = list(SELF_EXCHANGE_MAPPING.values())

# 出力時に削除する一時列
TEMP_COLS = [
    'is_duplicate', '基準判定', 'prev_code', 'prev_date', 'time_diff',
    'is_self_exchange', '_group_normalized'
]
