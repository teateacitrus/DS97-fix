# Troubleshooting

## SHA-256が一致しない

対象はSLPS-00777 v1.1の確認済みraw BINです。別バージョン、変換済みイメージ、吸い出し不良の可能性があります。デフォルトでは未確認SHA-256を拒否します。

## パラメータ表示パッチで入力パスだけがERRORになる

例えば次のように、`ERROR:`の後へ入力パスだけが表示される場合は、指定位置にBINが存在するか確認してください。

```powershell
Test-Path ".\patched\DerbyStallion97_v11_fix.bin"
```

`False`なら、実際の保存場所を検索します。

```powershell
Get-ChildItem . -Recurse -File -Filter "DerbyStallion97_v11_fix.bin" |
  Select-Object FullName, Length
```

見つかった`FullName`を`--input-bin`へ指定してください。例えば入力が`original`フォルダにある場合は次のようにします。

```powershell
py -3 .\patch_ds97_parameter_display.py `
  --input-bin ".\original\DerbyStallion97_v11_fix.bin" `
  --output-bin ".\patched\DerbyStallion97_v11_fix_display.bin"
```

## パラメータ表示パッチで入力SHA-256が一致しない

二段階目の入力は、確認済みオリジナルBINへ`patch_ds97_win_freeze.py`を適用した直後のBINです。

```text
size:    405,917,568 bytes
SHA-256: f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84
```

元の後期版BIN、初期版BIN、開発途中の表示版、別パッチ適用済みBINは受け付けません。二段階目には未確認SHA-256を許可するオプションはありません。

## BINサイズが一致しない

対応サイズは `405,917,568` bytes です。raw 2352-byte-sector BIN以外は対象外です。

## CHDしか持っていない

このツールはCHDへ直接適用しません。自分で所有するディスクからraw BIN/CUEを用意してください。

## ISOに適用しようとした

ISOは2352-byte-sector raw BINではありません。EDC/ECC領域も前提が異なるため拒否されます。

## CUEがBINを見つけられない

出力CUEは出力BINのファイル名を参照します。CUEとBINを同じディレクトリに置き、出力CUEから起動してください。

## 旧牧場を読み込めるが保存できない

症状:

- 既存牧場はロードできる
- 保存時にロードしたデータがない旨のメッセージが出る

確認事項:

- パッチ後にCUE/BINのbasenameを変更していないか
- no$psXが別名MCDを使用していないか
- パッチ済みイメージ用MCDが空または別内容でないか
- 正常な旧MCDをバックアップしたか
- no$psXを完全終了してからコピーしたか

対処:

1. 正常な旧MCDをバックアップする
2. 正常な旧MCDをパッチ済みイメージ名のMCDへコピーする
3. コピー元とコピー先のサイズ・SHA-256を比較する
4. パッチ済みCUEを電源投入状態から起動する
5. ゲーム内からロードする
6. まずロード直後にセーブする
7. 次に勝利後の牧場復帰後にセーブする

保存できない場合でも、MCDを削除・初期化・上書きする前に必ずバックアップしてください。

## Pythonコマンドが見つからない

PowerShellで `py -3 --version` を確認してください。見つからない場合はPython 3をインストールし、Python Launcherを有効にしてください。

## パッチ後も勝利後に止まる

古いsavestateからではなく、電源投入状態から出力CUEで起動してください。変更LBA、EDC/ECC検証、入力SHA-256が成功しているか確認してください。未確認の回避策は断定できません。

## 古いステートセーブから起動した

古いsavestateにはパッチ前のRAM状態が残る可能性があります。電源投入状態から起動してください。

## パラメータ表示が出ない、または表示が想定と違う

- `DerbyStallion97_v11_fix_display.cue`から起動したか確認する
- savestateではなくcold bootする
- no$psX RAM code `800F8D3C 0018`を併用しない
- 出力BIN SHA-256が`fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b`か確認する
- 100以上の値はゲーム本来の2桁表示で百の位が省略されることに注意する

## 出力ファイルがすでに存在する

デフォルトでは上書きを拒否します。必要な場合だけ、出力先を確認して `--force` を使ってください。

## 別バージョンへ適用しようとした

SLPS-00777 v1.1以外は未対応です。アドレス、命令列、LBA、SHA-256が一致しないため拒否されます。
