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
- 今日のセット: 1回=語彙クイズ20問(設定シート set_size で変更可)→同じ単語でスピーキング(AI会話)→リスニング(音声4択・2026-11-03)の3部構成。回の完了=3つ揃ったとき(バッジは 1/3・2/3 で途中表示、継続スコアも3部で数える)。9時・13時・17時。2回連続で正解した問題は習得済みとして二度と出ない。優先=今日間違えた > 未出題 > 過去に間違えた。自分のレベルの在庫が尽きたら上のレベルの問題を出す(セッションIDは T始まり)。レベルは1セット90%以上で上がり、2セット連続50%未満で下がる(2026-11-02 変更: 解けた問題を繰り返さない・どんどん難しく)
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
- 双方の発話はテキストで「会話ログ」シートに保存(初回に自動作成)。時間が来ると自動で講評→採点→切断。1セッションの長さは設定シート voice_minutes(既定5分・管理タブで変更)。残り1分で講師に締めを指示し、画面は残り時間のカウントダウン。1回につきスピーキング1回・リスニング1回(2026-11-02 安河内: 何分やるか決めてだらだらしない)。
- 鍵: ブラウザはOpenAIの鍵を持たない。`worker/`(Cloudflare Worker)がGoogleトークンを検証して短命トークンを発行する。`worker/README.md`参照。

- 講師の話す速さ: 音声タブの「講師の話す速さ」で 0.7x〜1.1x。初期値はレベル連動(N5 0.75 / N4 0.85 / N3 0.95 / A2 0.8 / B1 0.9 / B2以上 1.0)。設定シート `speed:<email>:<course>` に保存。Realtime API の `audio.output.speed` に渡す(2026-11-02 Snehaさん要望)

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
- `packs/en_ipa.json` … 英単語クイズの読み(発音記号) 8,444語。元データ [ipa-dict](https://github.com/open-dict-data/ipa-dict) en_US (MIT)。問題には取り込まず、単語クイズの画面で語の下に表示(🔊=Worker `/tts`、失敗時はブラウザの読み上げ)。再生成=`python3 tools/build_ipa.py en_US.txt cefrj.csv cefr_c.csv`
再生成: 元データを1つのフォルダに置いて `python3 tools/build_packs.py <フォルダ>`(取得URLはスクリプト冒頭)。誤答は同レベル・同品詞の別の語の意味から、意味の語が重ならないものを選ぶ。

## リスニング(音声4択)
- 今日の単語ごとに「文(聞くだけ・画面には出ない)+質問+4択」を1問。問題シートに cat=listening・exp=読み上げ文・M列ref=元の語彙問題IDで保存。IDは `EN-L0001` 形式。
- 不足分は Worker `/generate` (kind=listening) が gpt-5.4-mini で生成。読み上げは Worker `/tts` (gpt-4o-mini-tts, 速度=講師の話す速さ, エッジでキャッシュ)。
- 記録は回答ログ(session=L始まり・cat=listening)。習得ルールは語彙と同じ(2回連続正解)。スキルメーターのリスニング軸=直近7日の正答率。
- 音声タブのリスニング(AI会話型)はボタンを外した(旧データは記録に残る)。

## 週末テスト（毎週金曜・最後の2時間）
- テストタブ。JLPT（N5→N4→N3…）と英語（TOEIC形式）。本番と同じ区分・時間（N5=20/40/30分、TOEIC=L45/R75分、Part 1 写真問題は無し）、聴解は1回だけ、終えた区分には戻れない。
- 問題と正解は公開リポジトリに置かない：`worker/tests_src/`（git管理外）→ `python3 tools/build_tests.py` → `worker/tests_built/`（git管理外）→ Worker デプロイ。Worker は `TEST_WINDOW`（既定 金 15:00–19:00 JST）の間だけ問題を配信し、採点する。
- 結果＝「テスト結果」シート。同じレベルで `test_promote_after`（既定2）回続けて合格すると次のレベル（設定 `testlevel:メール:コース`、en は TOEIC 目標点 600/730/860/945）。
- 新しい回を足すとき：`tests_src/tests.json` に1件追加し、問題ファイル（SPEC.md の書式・options[0]=正解）を置いて、ビルドしてデプロイする。
