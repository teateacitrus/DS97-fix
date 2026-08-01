# DS97-fix

『ダービースタリオン97』v1.1（SLPS-00777）で、一部のエミュレーター使用時にレース勝利後の処理が停止する現象を回避するための、検証版パッチ作成ツールです。

このリポジトリは **alpha / experimental** です。ゲーム本体、BIOS、BIN、CUE、ROM、セーブデータ、差分パッチファイルは含みません。自分で所有するディスクから吸い出した raw 2352-byte-sector BIN/CUE が必要です。

## 対象

- 対象ゲーム: Derby Stallion 97 v1.1
- ディスクID: `SLPS-00777`
- 入力BINサイズ: `405,917,568` bytes
- 入力BIN SHA-256: `92fc3d8bae259f4167a5b72ff9e6d849b3c3790dc50140557ca965c8270b080a`
- 検証済みエミュレーター: no$psX 2.3

## raw BIN/CUEについて

- raw BINはCDの各セクターを2352バイト単位で保存した形式です。
- 対応するCUEとセットで使用します。
- CUEのトラック記述では通常 `MODE2/2352` と表示されます。
- ISOやCHDには直接適用できません。CHDしかない場合は、自分で吸い出した元のBIN/CUEを使用してください。
- ファイルサイズが2352で割り切れるだけでは対応イメージとは断定できません。
- スクリプトはサイズ、SHA-256、元命令列も検査します。

## 方式

このツールは、古い `F0 -> CC` の1バイトしきい値変更ではありません。

採用しているのは `DATA/WINNING/GWIN.SOL` 限定の協調型方式です。元の `0xF0` 完了値を保持し、待機中に `801C7678` のpending flagを確認して、必要な場合だけ既存処理 `800F7024` を実行します。runtime確認では `801C4BF0` が本来の完了値 `0xF0` まで進行し、勝利画面から牧場へ正常に復帰しました。

## 重要な注意

- 入力BIN/CUEを直接変更しません。別の出力BIN/CUEを作成します。
- 出力されたCUEから起動してください。
- オリジナルBIN/CUEとメモリーカードを必ずバックアップしてください。
- 古いsavestateから起動せず、電源投入状態から起動してください。
- 旧メモリーカード由来の牧場で、進行後に保存できない未解決事象があります。
- 長期運用、正常なsave/reload、繰り返し勝利、別エミュレーター動作は未確認です。
- 能力表示パッチは含みません。

## 使い方

Python 3を確認します。

```powershell
py -3 --version
```

実行例:

```powershell
py -3 .\patch_ds97_win_freeze.py `
  --input-bin ".\original\DerbyStallion97_v11.bin" `
  --input-cue ".\original\DerbyStallion97_v11.cue" `
  --output-bin ".\patched\DerbyStallion97_v11_fix.bin" `
  --output-cue ".\patched\DerbyStallion97_v11_fix.cue"
```

出力先に既存ファイルがある場合、デフォルトでは拒否します。上書きが必要な場合だけ、内容を確認してから `--force` を使ってください。

## 実行後の確認

- スクリプトが正常終了したこと
- 変更LBAが `151663, 151664` と表示されること
- EDC/ECC検証が成功すること
- 出力CUEから起動すること
- ゲームが起動し、レースを開始できること
- 勝利後に停止せず、牧場へ戻れること
- 確認済みオリジナルBINから生成した場合の出力BIN SHA-256:
  `f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84`

このSHA-256は、確認済み入力BIN `92fc3d8bae259f4167a5b72ff9e6d849b3c3790dc50140557ca965c8270b080a` から生成した場合の値です。`--allow-unverified-sha256` を使った別イメージでは同じ出力SHA-256を保証しません。一般利用では `--allow-unverified-sha256` は推奨しません。

詳細な確認欄は [validation-checklist.md](docs/validation-checklist.md) を使ってください。

## 既知の未解決事項

以前から使用していたメモリーカードの牧場を読み込んで進行後、保存しようとすると、ロード済みセーブデータがない旨の表示となり保存できない事象が確認されています。原因は未確定です。パッチ、no$psXのメモリーカード管理、起動方法、古いsavestateとの関係は未解決です。

トラブルシューティングは [troubleshooting.md](docs/troubleshooting.md) を参照してください。技術詳細は [technical-details.md](docs/technical-details.md) にまとめています。

## ライセンスと非公式性

MIT Licenseです。このプロジェクトは非公式であり、ゲームの開発元・販売元とは無関係です。
