# re-search

東京23区の賃貸マンション/アパートを、家賃・周辺施設・**沿革（旧町名・旧地形）・風水ルール・建替/再開発計画**まで含めて検索・比較するための、個人用 CLI ツール。

## 設計の特徴

- **4つの軸で物件を見る**
  - `livability`（居住快適性、0–100）: 家賃コスパ・徒歩・面積・築年・耐震・周辺施設
  - `locality`（街の将来性、0–100、補助）: 地価・地価トレンド・人口・治安・再開発フラグ
  - `heritage`（沿革・地相、スコア化しない）: 旧町名・旧用途・旧地形（台地/低地/旧河道/崖下/埋立）を中立に表示
  - `fengshui`（風水、0–100、ルール辞書）: 四神相応・路冲・天斬殺・鬼門 等を機械判定
- **建替・再開発を独立エンティティ化**: `redevelopment_project` で公表案件を管理し、賃貸視点（立ち退きリスク）と売買視点（権利変換チャンス）を **両面併記**。機械的減点はしない
- **Copilot CLI 連携は MCP サーバ経由**: 本 CLI は決定論的スコアを返し、Copilot CLI 側からオーケストレーションする

## インストール（開発用）

```bash
cd ~/realestate-search
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
re --help
```

## 初期化

```bash
re init
```

`~/Library/Application Support/re-search/re.db`（macOS）に SQLite DB を作成し、`~/Library/Application Support/re-search/`（または XDG `~/.config/re-search/`）に設定ファイルを置く。

## 利用上の注意（規約・倫理）

- HTML 本文・画像・詳細説明文は保存しない（最小メタデータのみ）
- ログイン必須コンテンツは対象外
- スクレイピングは `experimental/` モジュールに隔離。明示的な `--i-accept-risks` フラグなしには動作しない
- `robots.txt` 遵守、UA 明示、低頻度（1 リクエスト/秒以下）
- 旧地名・同和地区関連情報は **機械的減点に使わない**。事実の中立表示のみ
- 建替・再開発情報は公表ソースに限定。未公表の噂・憶測は登録しない
- 風水評価は「自分の好みの定量化」。占術的厳密性は主張しない
- 個人利用限定、第三者への配布・公開はしない

## 状況

Phase 0（プロジェクト雛形 + SQLite 基盤）実装中。
詳細な実装プランは `~/.copilot/session-state/<session>/plan.md` を参照。
