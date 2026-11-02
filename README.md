# Choreia Learn（リポ名 N4）

英語話者向けの日本語N4コースと、日本語話者向けの英語コースを持つ練習サイト。4択で出題し、1問ごとの回答と回答秒数を自社のGoogleスプレッドシートに記録する。

- 公開: https://choreia.github.io/N4/
- 構成: 単一HTML SPA + Google OAuth + Sheets API（サーバー無し）。Choreia モジュール共通のクライアントID・認証方式を踏襲。
- データ: 共有ドライブ内のスプレッドシート（初回セットアップで作成）
  - `問題` … ID／分野／問題／選択肢A〜D／正解(A-D)／解説／有効。行を足せば再デプロイ不要で出題が増える。分野ID = vocab / kanji / grammar / reading
  - `回答ログ` … 日時／メール／氏名／セッション／問題ID／分野／問題／回答／正誤／回答秒数（1回答=1行、回答直後に追記）
  - `設定` … 予備
- コース: jp=日本語N4(語彙/漢字/文法/読解・UI英語・93問)／en=英語(単語600=1日20語×30日+文法/表現/読解48・UI日本語・648問)。`問題`・`回答ログ`の末尾「コース」列で区別、空欄はjp
- 役割: 学習者（ログインして学習。スプレッドシートへの編集権限が必要）／管理者（全学習者の進捗閲覧、管理者追加）
- 今日のセット: 1回20問(設定シート set_size で変更可)を9時・13時・17時。2回連続で正解した問題は習得済みとして二度と出ない。優先=今日間違えた > 未出題 > 過去に間違えた。自分のレベルの在庫が尽きたら上のレベルの問題を出す(セッションIDは T始まり)。レベルは1セット90%以上で上がり、2セット連続50%未満で下がる(2026-11-02 変更: 解けた問題を繰り返さない・どんどん難しく)
- 自由練習: 分野を選んで出題。未出題 > 前回不正解 > 前回正解 の重みで選ぶ。選択肢は画面でシャッフル。
- 初期問題: セットアップ時に741問(両コース)を `問題` シートへ書き込む（index.html 内 SEED）。

## 学習者を増やすとき
1. 管理画面のリンクからスプレッドシートを開き、学習者のGoogleアカウント（@m2-labo.jp）に「編集者」で共有する
2. 学習者が https://choreia.github.io/N4/ にログインする

## ライセンス
MIT

## 英語600語の生成元
`words/all.tsv` 形式(単語・品詞・意味・例文)から、同じ品詞の別の語の意味を誤答にして4択を生成(意味の文字が重なる語は除外)。既にセットアップ済みのシートへ入れるときは `seed_en_rows.csv` を「問題」シートの末尾に貼り付ける(ID EN-1001〜)。

## 音声(Speaking / Listening)
「🎙 音声」タブ。今日のセットの単語を材料に、OpenAI Realtime API(gpt-realtime-2.1-mini)の講師と話す。
- スピーキング: 単語を使わせる短い質問の会話／リスニング: 単語ごとに1文読み上げ→質問→正誤。
- 双方の発話はテキストで「会話ログ」シートに保存(初回に自動作成)。終了ボタンで講評→切断。1セッション10分上限。
- 鍵: ブラウザはOpenAIの鍵を持たない。`worker/`(Cloudflare Worker)がGoogleトークンを検証して短命トークンを発行する。`worker/README.md`参照。

## Hanasu の問題取り込み
Kartik Dhar さん作 [Hanasu](https://github.com/KartikDhar09/hanasu) の語彙・漢字・文法データ(N5/N4)を4択に変換した `hanasu_jp.json`(約2,300問)を同梱。
管理タブ「Hanasuの問題を取り込む」で未取込分だけ「問題」シートに追加される(コース=jp・レベル=N5/N4)。
再生成: `python3 tools/import_hanasu.py <hanasuリポジトリ>`。Book(教科書)関連は著作物のため対象外。利用は Kartik さんの許可(2026-11-02 メール)に基づく。

## 問題パック(packs/)
公開データから生成した4択問題。`packs/index.json` に並ぶパックを、管理者がログインしたときに自動で「問題」シートへ追加する(シートに無い問題文だけ・管理タブ「今すぐ取り込む」でも可)。
- `hanasu_jp.json` … Hanasu N5/N4 2,275問(上記)
- `packs/jp_vocab_n3n2n1.json` … JLPT語彙 N3 2,101 / N2 1,897 / N1 2,684問。元データ [open-anki-jlpt-decks](https://github.com/jamsinclair/open-anki-jlpt-decks) (MIT)
- `packs/jp_kanji_n3n2n1.json` … 漢字の意味・音読み N3 367 / N2 367 / N1 1,232問。元データ [kanji-data](https://github.com/davidluzgouveia/kanji-data) (MIT)
- `packs/en_cefr_b2c1.json` … 英単語 B2 2,360 / C1 803問。見出し語 [CEFR-J Vocabulary Profile / Octanove Vocabulary Profile](https://github.com/openlanguageprofiles/olp-en-cefrj) (CC BY-SA 4.0)、訳語 [EJDict-hand](https://github.com/kujirahand/EJDict) (パブリックドメイン)
再生成: 元データを1つのフォルダに置いて `python3 tools/build_packs.py <フォルダ>`(取得URLはスクリプト冒頭)。誤答は同レベル・同品詞の別の語の意味から、意味の語が重ならないものを選ぶ。
