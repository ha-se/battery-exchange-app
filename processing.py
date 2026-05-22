"""
データ処理モジュール
重複検出・バッテリー基準判定・集計処理
"""
import numpy as np
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
    バッテリー残量が基準外かどうかを判定（行単位・後方互換用）

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


def check_battery_standard_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    バッテリー残量が基準外かどうかをベクトル演算で一括判定
    apply(axis=1) の数十倍高速
    """
    maker = df['自転車メーカー名']
    battery = df['battery_remaining']

    result = pd.Series(None, index=df.index, dtype=object)

    m = (maker == 'Panasonic') & battery.notna()
    result[m] = np.where(battery[m] >= 25, '基準外', '基準内')

    m = (maker == 'YAMAHA') & battery.notna()
    result[m] = np.where(battery[m] >= 70, '基準外', '基準内')

    m = (maker == 'DBS') & battery.notna()
    result[m] = np.where(
        battery[m] == 100, '基準内',
        np.where(battery[m] >= 50, '基準外', '基準内')
    )

    m = (maker == 'glafit') & battery.notna()
    result[m] = np.where(battery[m] >= 50, '基準外', '基準内')

    m = (maker == 'シナネンサイクル') & battery.notna()
    result[m] = np.where(battery[m] >= 40, '基準外', '基準内')

    return result


def _aggregate_core(df_for_aggregation: pd.DataFrame, group_col: str) -> Dict[str, pd.DataFrame]:
    """
    指定列でグループ化して集計を行うコア処理

    最適化: 事前にgroupbyで全集計し、辞書引きで各セルを埋める
    （元の三重ループでの都度DataFrameフィルタリングを廃止）
    """
    maker_col = '自転車メーカー名'
    user_col = 'user_name'
    normalized_col = '_group_normalized'

    df_temp = df_for_aggregation.copy()
    df_temp[normalized_col] = df_temp[group_col].astype(str).str.lower().str.strip()

    name_mapping = {}
    for orig_name in df_temp[group_col].dropna().unique():
        normalized = str(orig_name).lower().strip()
        if normalized not in name_mapping:
            name_mapping[normalized] = orig_name

    valid_groups = [g for g in df_temp[normalized_col].dropna().unique() if g != 'nan']
    if not valid_groups:
        return {}

    # MAKERSのみに絞り込み
    df_makers = df_temp[df_temp[maker_col].isin(MAKERS)].copy()
    # NaN・空文字の基準判定を '_なし' に正規化
    df_makers['_kijun'] = df_makers['基準判定'].fillna('_なし').replace('', '_なし')

    df_no_dup = df_makers[~df_makers['is_duplicate']]
    df_dup = df_makers[df_makers['is_duplicate']]

    # 全データを一括groupby（ループ内でのフィルタリングを廃止）
    no_dup_agg = (
        df_no_dup.groupby([normalized_col, user_col, maker_col, '_kijun'])
        .size()
        .reset_index(name='cnt')
    )
    dup_agg = (
        df_dup.groupby([normalized_col, user_col, maker_col])
        .size()
        .reset_index(name='dup_cnt')
    )

    # O(1) 辞書引き用に変換
    no_dup_lookup: dict = no_dup_agg.set_index(
        [normalized_col, user_col, maker_col, '_kijun']
    )['cnt'].to_dict()
    dup_lookup: dict = dup_agg.set_index(
        [normalized_col, user_col, maker_col]
    )['dup_cnt'].to_dict()

    # グループごとのユーザー一覧を事前取得
    users_per_group: dict = (
        df_temp[df_temp[normalized_col].isin(valid_groups)]
        .groupby(normalized_col)[user_col]
        .unique()
        .to_dict()
    )

    aggregated_data = {}

    for group_norm in valid_groups:
        display_name = name_mapping.get(group_norm, group_norm)
        group_users = [u for u in users_per_group.get(group_norm, []) if pd.notna(u)]

        result_data = []
        for user in group_users:
            row_data = {'user_name': user}
            total = total_dup = total_kijun_nai = total_kijun_gai = total_kijun_nashi = 0

            for maker in MAKERS:
                key = (group_norm, user, maker)
                kijun_nai   = no_dup_lookup.get((*key, '基準内'), 0)
                kijun_gai   = no_dup_lookup.get((*key, '基準外'), 0)
                kijun_nashi = no_dup_lookup.get((*key, '_なし'),  0)
                maker_total = kijun_nai + kijun_gai + kijun_nashi
                maker_dup   = dup_lookup.get(key, 0)

                row_data[f'{maker}_基準内']    = kijun_nai
                row_data[f'{maker}_基準外']    = kijun_gai
                row_data[f'{maker}_合計']      = maker_total
                row_data[f'{maker}_重複除外数'] = maker_dup

                total            += maker_total
                total_dup        += maker_dup
                total_kijun_nai  += kijun_nai
                total_kijun_gai  += kijun_gai
                total_kijun_nashi += kijun_nashi

            row_data['総合計']            = total
            row_data['総重複除外数']       = total_dup
            row_data['全メーカー_基準内']   = total_kijun_nai
            row_data['全メーカー_基準外']   = total_kijun_gai
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

    # apply(axis=1) → ベクトル演算に変更（大幅高速化）
    df_with_standard['基準判定'] = check_battery_standard_vectorized(df_with_standard)

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
