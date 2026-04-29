"""東京23区の JIS X 0402 市区町村コード辞書。

国土地理院ジオコーダのレスポンスから区名を抽出して町丁目コードを当てる。
将来は国土数値情報の町丁目シェイプデータでより細粒度（町丁目連番）を解決する。
"""

from __future__ import annotations

# 東京23区の市区町村コード（JIS X 0402、上2桁=都道府県=13、下3桁=市区町村）
TOKYO_23_WARDS: dict[str, str] = {
    "千代田区": "13101",
    "中央区": "13102",
    "港区": "13103",
    "新宿区": "13104",
    "文京区": "13105",
    "台東区": "13106",
    "墨田区": "13107",
    "江東区": "13108",
    "品川区": "13109",
    "目黒区": "13110",
    "大田区": "13111",
    "世田谷区": "13112",
    "渋谷区": "13113",
    "中野区": "13114",
    "杉並区": "13115",
    "豊島区": "13116",
    "北区": "13117",
    "荒川区": "13118",
    "板橋区": "13119",
    "練馬区": "13120",
    "足立区": "13121",
    "葛飾区": "13122",
    "江戸川区": "13123",
}

WARD_NAMES = list(TOKYO_23_WARDS.keys())


def ward_from_address(address: str) -> str | None:
    """住所文字列から東京23区のうち含まれる区名を抽出。

    複数該当はあり得ないので最初にヒットしたものを返す。
    """
    if not address:
        return None
    for ward in WARD_NAMES:
        if ward in address:
            return ward
    return None


def city_code_for_ward(ward: str) -> str | None:
    """区名 → 5桁市区町村コード。"""
    return TOKYO_23_WARDS.get(ward)


def city_code_from_address(address: str) -> str | None:
    ward = ward_from_address(address)
    if ward is None:
        return None
    return city_code_for_ward(ward)
