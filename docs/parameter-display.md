# 競走馬パラメータ表示パッチ

`patch_ds97_parameter_display.py`は、フリーズ回避パッチ適用済みの
『ダービースタリオン97』後期版v1.1に追加適用するno-ROMパッチ作成ツールです。

本来の競走成績を維持したまま、競走馬画面の「右芝・右ダ・左芝・左ダ」4行を、
競走馬レコード内部の16個の数値へ置き換えます。

ゲーム本体、BIN、CUE、ROM、セーブデータ、差分パッチファイルは含みません。

## 実機確認状況

確認済みの出力BINは、no$psX 2.3で次の範囲をruntime-confirmedとしています。

- `record+0x18..+0x27`のパラメータ表示
- 本来の競走成績の維持
- 勝利後に停止せず牧場へ戻り、正常に進行すること
- ゲーム内セーブ
- cold boot後の再ロード
- 前段の協調型フリーズ回避機能が維持されること

この追加パッチについて、DuckStation、長期運用、すべての周辺画面は未確認です。
前段のフリーズ回避パッチ単独については、no$psX 2.3とDuckStationの双方で
勝利後の正常進行を確認しています。

## 適用順

```text
ダビスタ97 後期版 v1.1
  ↓ patch_ds97_win_freeze.py
DerbyStallion97_v11_fix.bin
  ↓ patch_ds97_parameter_display.py
DerbyStallion97_v11_fix_display.bin
```

元の後期版BINや、開発途中の旧表示版へ直接適用することはできません。

## 対応入力

| 項目 | 値 |
|---|---|
| 推奨ファイル名 | `DerbyStallion97_v11_fix.bin` |
| サイズ | `405,917,568` bytes |
| SHA-256 | `f3b56a1d00f95695bdad992128985e5e9135c9c681b716c8e0188916f2471f84` |

入力は、確認済みのオリジナルBINへこのリポジトリの
`patch_ds97_win_freeze.py`を適用した直後の出力です。
サイズまたはSHA-256が一致しない場合、ツールは入力を変更せず停止します。

## 1. 入力BINを確認する

PowerShellでリポジトリのフォルダへ移動します。

```powershell
Set-Location "C:\Users\ユーザー名\Desktop\DS97-fix"
```

入力BINが`patched`フォルダにあるか確認します。

```powershell
Test-Path ".\patched\DerbyStallion97_v11_fix.bin"
```

`False`の場合は、リポジトリ内を検索します。

```powershell
Get-ChildItem . -Recurse -File -Filter "DerbyStallion97_v11_fix.bin" |
  Select-Object FullName, Length
```

例えば、次の場所にある場合があります。

```text
.\original\DerbyStallion97_v11_fix.bin
```

## 2. 入力SHA-256を確認する

入力が`patched`フォルダにある場合の例です。

```powershell
Get-FileHash `
  ".\patched\DerbyStallion97_v11_fix.bin" `
  -Algorithm SHA256
```

次の値と完全に一致することを確認してください。

```text
F3B56A1D00F95695BDAD992128985E5E9135C9C681B716C8E0188916F2471F84
```

## 3. パラメータ表示パッチを実行する

入力が`patched`フォルダにある場合:

```powershell
py -3 .\patch_ds97_parameter_display.py `
  --input-bin ".\patched\DerbyStallion97_v11_fix.bin" `
  --output-bin ".\patched\DerbyStallion97_v11_fix_display.bin"
```

入力が`original`フォルダにある場合:

```powershell
New-Item -ItemType Directory -Force ".\patched" | Out-Null

py -3 .\patch_ds97_parameter_display.py `
  --input-bin ".\original\DerbyStallion97_v11_fix.bin" `
  --output-bin ".\patched\DerbyStallion97_v11_fix_display.bin"
```

`py`が認識されない場合は、先頭の`py -3`を`python`へ変更してください。
`--output-bin`を省略すると、入力名の末尾へ`_display`を加えた名前を使います。

## 4. 出力

正常に終了すると、次の3ファイルが生成されます。

```text
DerbyStallion97_v11_fix_display.bin
DerbyStallion97_v11_fix_display.cue
DerbyStallion97_v11_fix_display.audit.json
```

確認済み出力BINのSHA-256:

```text
fc66ceed0d09abbf73725321500eefc6486404d2bd01f90f5838bff9d5df484b
```

入力BINは変更されません。既存の出力ファイルはデフォルトでは上書きしません。
明示的に置き換える場合だけ、出力先を確認して`--force`を追加してください。

## 5. 起動

エミュレーターでは、BINではなく生成されたCUEを選びます。

```text
DerbyStallion97_v11_fix_display.cue
```

- savestateから再開せずcold bootする
- 古いsavestateを使用しない
- no$psXのRAM code `800F8D3C 0018`を併用しない
- no$psXで既存牧場を使う場合は、新しいbasenameに対応するMCDを確認する

## 表示内容

表示範囲は`record+0x18..+0x27`です。

| 表示行 | 1番目 | 2番目 | 3番目 | 4番目 |
|---|---|---|---|---|
| 右芝 | `+0x18` 用途未確認 | ベスト馬体重内部値 | 最大SP | 現在SP |
| 右ダ | 最大ST | 現在ST | 最大根性 | 現在根性 |
| 左芝 | 最大気性 | 現在気性 | 人気 | 成長型・衰え時期合成値 |
| 左ダ | ダート | 丈夫さ | 回復 | `+0x27` 用途未確認 |

表示形式はゲーム本来の10進数2桁です。100以上は百の位が表示されません。

```text
98  → 98
120 → 20
133 → 33
```

## ベスト馬体重

表示されるのは馬体重の内部値です。

```text
ベスト馬体重kg = 256 + 内部値 × 2
```

| ベスト馬体重 | 内部値 | 画面表示 |
|---:|---:|---:|
| 400kg | 72 | `72` |
| 428kg | 86 | `86` |
| 504kg | 124 | `24` |
| 508kg | 126 | `26` |

仔馬のベスト馬体重内部値は牡馬で62～141、牝馬で62～131です。
画面表示が`00～41`なら100を加えて復元します。

## 成長型・衰え時期

`record+0x23`の表示値を`B`とすると、次のように分解できます。

```text
成長型コード   = B // 8
衰え時期コード = B % 8
```

| 成長型コード | 成長型 |
|---:|---|
| 0 | 超早熟 |
| 1 | 早熟 |
| 2 | 普通 |
| 3 | 普通遅 |
| 4 | 晩成 |
| 5 | 超晩成 |

| 衰え時期コード | 衰え時期 |
|---:|---|
| 0 | 4歳3月 |
| 1 | 4歳7月 |
| 2 | 5歳5月 |
| 3 | 6歳3月 |
| 4 | 7歳1月 |
| 5 | 7歳7月 |

例えば表示値`44`は、`44 // 8 = 5`、`44 % 8 = 4`なので、
超晩成・7歳1月です。

## 繁殖牝馬

このパッチに内蔵しているのは競走馬画面の表示です。
牧場繁殖牝馬の表示は、従来のno$psX RAM codeを使用します。

```text
800F98D0 0008
800F98FC 0009
```

技術的な変更箇所、静的監査、実機確認境界は
[parameter-display-technical-details.md](parameter-display-technical-details.md)を参照してください。
