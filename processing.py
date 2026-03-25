"""
データ処理モジュール
重複検出・バッテリー基準判定・集計処理
"""
import pandas as pd
from typing import Dict, Optional, Tuple

from constants import MAKERS, SELF_EXCHANGE_MAPPING, TARGET_PT_COMPANIES


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    前後1時間で同じ車両番号（code）のレコードを重複として検出

    Args:
        df: 元データ（do_date列とcode列が必要）

    Returns:
        重複フラグ列（is_duplicate）を追加したDataFrame
    """
    df = df.copy()

    df['is_duplicate'] = False

    if 'do_date' not in df.columns or 'code' not in df.columns:
        return df

    df['do_date'] = pd.to_datetime(df['do_date'], errors='coerce')

    valid_mask = df['code'].notna() & df['do_date'].notna()
    if not valid_mask.any():
        return df

    df_sorted = df.sort_values(['code', 'do_date'])

    df_sorted['prev_code'] = df_sorted['code'].shift(1)
    df_sorted['prev_date'] = df_sorted['do_date'].shift(1)
    df_sorted['time_diff'] = df_sorted['do_date'] - df_sorted['prev_date']
    df_sorted['is_duplicate'] = (
        (df_sorted['code'] == df_sorted['prev_code']) &
        (df_sorted['time_diff'] <= pd.Timedelta(hours=1))
    )

    df.loc[df_sorted.index, 'is_duplicate'] = df_sorted['is_duplicate']

    return df


def check_battery_standard(row) -> Optional[str]:
    """
    バッテリー残量が基準外かどうかを判定

    基準:
    - Panasonic: 25%以上が基準外
    - YAMAHA: 70%以上が基準外
    - DBS: 50%以上が基準外（ただし100%は基準内）
    - glafit: 50%以上が基準外
    - シナネンサイクル: 40%以上が基準外
    - KUROAD: 基準判定なし

    Returns:
        '基準内', '基準外', または None
    """
    maker = row['自転車メーカー名']
    battery = row['battery_remaining']

    if pd.isna(battery):
        return None

    if maker == 'Panasonic':
        return '基準外' if battery >= 25 else '基準内'
    elif maker == 'YAMAHA':
        return '基準外' if battery >= 70 else '基準内'
    elif maker == 'DBS':
        if battery == 100:
            return '基準内'
        return '基準外' if battery >= 50 else '基準内'
    elif maker == 'glafit':
        return '基準外' if battery >= 50 else '基準内'
    elif maker == 'シナネンサイクル':
        return '基準外' if battery >= 40 else '基準内'
    else:
        return None


def _aggregate_core(df_for_aggregation: pd.DataFrame, group_col: str) -> Dict[str, pd.DataFrame]:
    """
    指定列でグループ化して集計を行うコア処理

    Args:
        df_for_aggregation: 集計対象DataFrame（is_duplicate・基準判定列が必要）
        group_col: グループ化する列名

    Returns:
        グループ名をキー、集計結果DataFrameを値とする辞書
    """
    aggregated_data = {}
    normalized_col = '_group_normalized'

    df_temp = df_for_aggregation.copy()
    df_temp[normalized_col] = df_temp[group_col].astype(str).str.lower().str.strip()

    name_mapping = {}
    for orig_name in df_temp[group_col].dropna().unique():
        normalized = str(orig_name).lower().strip()
        if normalized not in name_mapping:
            name_mapping[normalized] = orig_name

    groups_normalized = df_temp[normalized_col].dropna().unique()
    groups_normalized = [c for c in groups_normalized if c != 'nan']

    user_col = 'user_name'
    maker_col = '自転車メーカー名'

    for group_normalized in groups_normalized:
        display_name = name_mapping.get(group_normalized, group_normalized)
        group_df = df_temp[df_temp[normalized_col] == group_normalized]

        result_data = []
        for user in group_df[user_col].dropna().unique():
            user_df = group_df[group_df[user_col] == user]
            row_data = {'user_name': user}

            user_df_no_dup = user_df[user_df['is_duplicate'] == False]
            user_df_dup = user_df[user_df['is_duplicate'] == True]

            total = 0
            total_duplicates = 0
            total_kijun_nai = 0
            total_kijun_gai = 0
            total_kijun_nashi = 0

            for maker in MAKERS:
                maker_df = user_df_no_dup[user_df_no_dup[maker_col] == maker]
                maker_dup_count = len(user_df_dup[user_df_dup[maker_col] == maker])

                kijun_nai = len(maker_df[maker_df['基準判定'] == '基準内'])
                kijun_gai = len(maker_df[maker_df['基準判定'] == '基準外'])
                kijun_nashi = len(maker_df[maker_df['基準判定'].isna() | (maker_df['基準判定'] == '')])
                maker_total = len(maker_df)

                row_data[f'{maker}_基準内'] = kijun_nai
                row_data[f'{maker}_基準外'] = kijun_gai
                row_data[f'{maker}_合計'] = maker_total
                row_data[f'{maker}_重複除外数'] = maker_dup_count

                total += maker_total
                total_duplicates += maker_dup_count
                total_kijun_nai += kijun_nai
                total_kijun_gai += kijun_gai
                total_kijun_nashi += kijun_nashi

            row_data['総合計'] = total
            row_data['総重複除外数'] = total_duplicates
            row_data['全メーカー_基準内'] = total_kijun_nai
            row_data['全メーカー_基準外'] = total_kijun_gai
            row_data['全メーカー_判定なし'] = total_kijun_nashi
            row_data['検証_基準内+判定なし'] = total_kijun_nai + total_kijun_nashi
            result_data.append(row_data)

        result_df = pd.DataFrame(result_data)

        total_row = {'user_name': '合計'}
        for col in result_df.columns:
            if col != 'user_name':
                total_row[col] = result_df[col].sum()

        result_df = pd.concat([result_df, pd.DataFrame([total_row])], ignore_index=True)

        ordered_columns = ['user_name']
        for maker in MAKERS:
            if f'{maker}_基準内' in result_df.columns:
                ordered_columns.extend([
                    f'{maker}_基準内',
                    f'{maker}_基準外',
                    f'{maker}_合計',
                    f'{maker}_重複除外数'
                ])
        ordered_columns.extend([
            '総合計', '総重複除外数',
            '全メーカー_基準内', '全メーカー_基準外', '全メーカー_判定なし', '検証_基準内+判定なし'
        ])

        existing_columns = [col for col in ordered_columns if col in result_df.columns]
        result_df = result_df[existing_columns]

        aggregated_data[display_name] = result_df

    return aggregated_data


def aggregate_by_company_and_maker(df: pd.DataFrame) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    PT企業毎に、user_nameと自転車メーカー別の集計を行う
    基準内/基準外、重複除外も含めて集計
    自社交換分（E列とV列の特定組み合わせ）は除外し、別途返す
    また、E列(bike_company等)毎の集計も行う

    Returns:
        tuple: (集計結果Dict, E列集計結果Dict, 自社交換分DataFrame)
    """
    company_col = 'user_company(所属)'

    df_with_standard = detect_duplicates(df)

    if hasattr(df, 'attrs'):
        df_with_standard.attrs.update(df.attrs)

    df_with_standard['基準判定'] = df_with_standard.apply(check_battery_standard, axis=1)

    df_with_standard['is_self_exchange'] = False

    e_col_name = df_with_standard.attrs.get('e_column_name', None)
    v_col_name = df_with_standard.attrs.get('v_column_name', 'user_company(所属)')

    if e_col_name and e_col_name in df_with_standard.columns:
        e_values = df_with_standard[e_col_name].astype(str).str.strip()
        v_values = df_with_standard[v_col_name].astype(str).str.strip()

        mask = v_values.isin(TARGET_PT_COMPANIES) & e_values.isin(SELF_EXCHANGE_MAPPING.keys())
        for e_str, v_expected in SELF_EXCHANGE_MAPPING.items():
            df_with_standard.loc[mask & (e_values == e_str) & (v_values == v_expected), 'is_self_exchange'] = True

    self_exchange_df = df_with_standard[df_with_standard['is_self_exchange'] == True].copy()
    df_for_aggregation = df_with_standard[df_with_standard['is_self_exchange'] == False].copy()

    aggregated_data = _aggregate_core(df_for_aggregation, company_col)

    aggregated_by_bike = {}
    if e_col_name and e_col_name in df_for_aggregation.columns:
        aggregated_by_bike = _aggregate_core(df_for_aggregation, e_col_name)

    return aggregated_data, aggregated_by_bike, self_exchange_df
