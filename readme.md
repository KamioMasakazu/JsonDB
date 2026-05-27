# jdb（簡易JSONデータベース、エディタ）
JSONファイルを簡易的なデータベースとして扱える、シェルスクリプトなどから非対話的にJSONファイルを編集するためのツール群。

## jqに対する利点
- 検索や更新の記述が圧倒的に平易
- サーバ・クライアント方式なので一度ロードしたJSONはインメモリで何度でも処理できる。jqで何度もファイルを開き直す必要があるなら負荷が小さい。
- jdb_loadでロードしてからjdb_saveで保存するまでファイルは更新されないのでトランザクションを保てる。
- 使い捨ての（簡易的な）key=valueストアとして使える。入れ子の要素を持つ連想配列を使いたい時はbashの連想配列より楽。

（例：jqの場合）
```shell
# jqの場合のイメージ（一時ファイルや再書き込みが必要）
DATA=$(jq '.users | select(.name=="kamio")' data.json)
# 何か処理をする...
NEW_DATA=$(echo $DATA | jq '.status = "active"')
# 最終的にファイル全体を読み直して特定箇所を置換し、一時ファイルを経由して書き戻す
jq --argjson nd "$NEW_DATA" '(.users[] | select(.name=="kamio")) = $nd' data.json > tmp.json && mv tmp.json data.json
```

（例：jdbの場合）
```shell
# JDBの場合のイメージ
# 1. サーバ起動
./jdb_server -f ./databases/mydb.json
# 2. 検索（jdb_query）
RESULT=$(./jdb_query.py "mydb.users.kamio")

# 3. シェル側で何か処理をして新しい値（NEW_VAL）を決める

# 4. 直接更新（jdb_update）して必要に応じてセーブ
./jdb_update.py "mydb.users.kamio" "$NEW_VAL"
./jdb_save.py "mydb"
# 5. 終了
./jdb_server stop
```

## 構成
- jdb_utils.py：
  各コマンドが使うライブラリ。
- jdb_server.py：
  サーバプロセス。
- jdb_client：
  汎用（テスト用）クライアントであり、各種クライアントコマンドの処理実体であるライブラリ。
- jdb_load.py：
  JSONをjdb_serverにロードルするコマンド。
- jdb_save.py：
  jdb_serverにロードしたJSONデータをファイルに保存するコマンド。
- jdb_listdb.py：
  jdb_serverにロードされているデータベース（JSON）名を確認するコマンド。
- jdb_query.py：
  jdb_serverにロードされたデータベース（JSON）を検索するコマンド。
- jdb_add.py：
  jdb_serverにロードされたデータベース（JSON）にキーと値を追加するコマンド。
- jdb_delete.py：
  jdb_serverにロードされたデータベース（JSON）からキーと値、配列の値を削除するコマンド。
- jdb_update.py：
  jdb_serverにロードされたデータベース（JSON）の値を書き換えるコマンド。

## 各コマンド共通のオプション
- -d 標準エラーにデバッグ出力あり。
- -l <path/to/log> ログファイルの出力先。-dを組み合わせるとログが詳細になる。
- -s <name> サーバの場合は複数起動用。クライアントは接続先の選択。
- -h ヘルプ
- --version バージョン情報

## jdb_server.py
jdbサーバをプロセス。

### 
jdb_server.py [start|stop|list] [-c db_name] [-f files ...] [-F]

#### 位置引数
start サーバを起動する。省略時のデフォルト。  
stop サーバを停止する。-c, -f, -Fは無視する。  
list サーバの名前リスト。-d以外のオプションを無視する。  

#### オプション
-c db_name 起動した後空のデータベースをdb_nameで作成する。  
-f files... 指定したファイルを起動時にデータベースとしてロードする。DB名はファイル名のパスと拡張子を除いたもの。  
-F フォアグラウンドで実行する。Ctrl+Cで停止できる。  
-s ソケットファイルを指定する。複数起動時用。stop時は停止するサーバの指定になる。

### 使用例
```shell
# 単に実行
$ ./jdb_server.py
# フォアグラウンドで実行し標準エラー出力あり（デバッグに便利）
$ ./jdb_server -F -d
# 起動時にdefaultという空のDBを作成
$ ./jdb_server -c default
# 起動時にデータベースをロード（sampleとtestというDBができる）
$ ./jdb_server.py -f ./databases/sample.json ./databases/test.json
# ログ出力あり
$ ./jdb_server -l log/jdb.log
# 詳細なログ出力と標準エラー出力あり
$ ./jdb_server -d -l log/jdb.log
# 名前指定
$ ./jdb_server -s hoge
# 起動しているサーバのリスト
# ./jdb_server list
default
hoge
# hogeを停止
./jdb_server.py stop -s hoge
# defaultを停止
./jdb_server stop
```

### 備考
$TMPDIRにjdb_server.???.pidとjdb_server.???.socketを作る。  
???はサーバ名。  
pidファイルは起動中のサーバのPIDを記録する。  
socketファイルはUnix Domainのソケット。  
SIGTERMとSIGINTはこれらを削除して終了する。  
⚠️SIGKILLなどで殺したときはゴミが残るので手動で消すこと。  


## jdb_load.py
jdb_serverにJSONをロードする。  
繰り返し実行することで複数ファイルをロードできる。  
再ロードすることでリセットできる。

### コマンドライン
jdb_load.py [path] [-a|--alias alias]  
pathか-a aliasの少なくとも一方は必要。  
aliasだけを指定したら空のデータベースを作成する。

#### 位置引数
path: jsonファイルへのパス  

### オプション
-a|--alias jdb_serverでのデータベース名。指定しなければjsonファイルの拡張子を除いた名前になる。  

### 使用例
```shell
# JSONをロード
$ ./jdb_load.py ./databases/sample.json
# my_testというDB名でロード
$ ./jdb_load.py ./databases/test.json -a my_test
# new_dbという空のデータベースを作成
$ ./jdb_load.py -a new_db
```

1つ目だとデータベース名sampleでロードされる。  
2つ目だとデータベース名my_testでロードされる。

## jdb_save.py
指定したjdb_serverのデータベースをjsonファイルに書き出す。

### コマンドライン
jdb_save.py \<db_name> [path]  

#### 位置引数
dn_name: jdb_serverでのデータベース名。  

#### オプション
path: jsonファイルへのパス。指定しなければ上書きする。

### 使用例
```shell
# sampleデータベースを元のファイルに上書き
$ ./jdb_save.py sample
# sampleデータベースを./databases/test2.jsonに書き出し
$ ./jdb_save.py my_test ./databases/test2.json 
```

## jdb_listdb.py
ロードされているデータベース名をリストする。または、データベースがロードされているかを確認する。

### コマンドライン
jdb_listdb.py [db_mane ...]  

#### 位置引数
db_name: 存在確認するデータベース名。  
引数無しならロードされているデータベースのリスト取得。

### 使用例
```shell
# ロードされている全DB名
$ ./jdb_listdb.py 
['sample', 'test']
# testというDBがあるか
$ ./jdb_listdb.py test
['test']
# noneというDBがあるか
$ ./jdb_listdb.py none
[]
```

## jdb_query.py
データベース（JSON）を検索して結果を返す。

### コマンドライン
jdb_query.py [--print key|count] \<query_string> [-c additional_query ...]  

# 位置引数
query_string：クエリ文字列。後述のクエリパスとフィルタを参照。  
⚠️ クエリ文字列はシェルの展開を抑制するため'シングルクォート'で囲んだほうが良い。

#### オプション
--print key|count  
key：結果がオブジェクトならオブジェクトのキーの配列を表示する。結果がオブジェクトで無いなら空文字列を表示する。  
count：結果がオブジェクトか配列なら要素数を表示する。結果がオブジェクトか配列で無いなら空文字列を表示する。  

-c|--choices
検索結果に対する絞り込み条件を設定する。クエリの書式はtargetと同じ。  
ただし、検索結果に対してのパスを記述する必要がある。  
詳細は後述。  

### クエリパス
db.path.to.target  
db名から始まり、目的のキーまでを.（ドット）で繋いだもの。  
シェル形式のワイルドカード（*、?）を使用できる。
返却値は値かJSON文字列である。

#### 単純なパス指定の例
指定したパスの値を返す。値がオブジェクトならJSON形式で返る。なければ空文字列が返る。
```shell
# 値が返る
$ ./jdb_query.py 'test.int_val'
1
# JSONが返る
$ ./jdb_query.py 'test.object2.aaa'
{"xxx": 1, "yyy": "aaa"}
# 配列（JSON)が返る
$ ./jdb_query.py 'test.array'
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# 見つからなかった
$ ./jdb_query.py 'test.bad_target'

# ワイルドカード（*）
$ ./jdb_query.py 'test.object.*'
["hoge", "fuga", ["ika", "namako"]]
# ワイルドカード（?）
$ ./jdb_query.py 'test.object.t???'
[["ika", "namako"]]
```

#### 配列の要素指定
要素番号（0オリジン）かpythonのスライスと同じ書き方。コンマくぎりで複数指定可能。
返却値は必ず配列形式で返る。

```shell
# 3番目の要素
$ ./jdb_query.py 'test.array.3'
[4]
# 3番目と5番目の要素
$ ./jdb_query.py 'test.array.3,5'
[4, 6]
# 3番未満と7番目の要素
$ ./jdb_query.py 'test.array.:3,7'
[1, 2, 3, 8]
# 6番目以降
./jdb_query.py 'test.array.6:'
[9, 10, 7, 8]
# 全部
$ ./jdb_query.py 'test.array.:'
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# 配列要素がオブジェクトの0〜1番目を取得して、さらにそのオブジェクトのfld1
$ ./jdb_query.py 'test.object_array.:2.fld1'
["aaa", "bbb"]
```

#### キーの複数指定
同じ階層のキーは|（バーティカルバー）で複数指定できる。
返却値は必ず配列形式で返る。

```shell
# int_valかstring_val
$ ./jdb_query.py 'test.int_val|string_val'
[1, "hoge"]
# object_arrayの全要素からfld1とflg3を取り出す
$ ./jdb_query.py 'test.object_array.:2.fld1|flg3'
[["aaa", "AAA"], ["bbb", "BBB"]]
```

### フィルタ
検索の絞り込み条件を@...で付加できる。

#### 数値、文字列フィルタ
完全一致のフィルタをかける。
これは末尾要素（それ以上子要素がない要素=クエリパスの末尾）にしか使用できない。

- @null（nullと一致）、@!null（nullでないものと一致）
- @true、@false
- @数値
- @"文字列"（ダブルクォートで括らないとダメ）
- @[配列]

⚠️配列のフィルタは配列同士の比較である。'test.array@[1, 2, 3]'はarrayの値（=配列）と配列との比較なので成立する。'test.array.:@[1, 2, 3]'はarrayから取り出した個々の値（1と2と3）ぞれぞれと配列との比較なので成立しない。


```shell
# 数値
$ ./jdb_query.py 'test.object_array.:.fld2@222'
[222]
# 数値（一致するものがない）
$ ./jdb_query.py 'test.object_array.:.fld2@200'
[]
# 文字列
$ ./jdb_query.py 'test.object.hoge@"hoge"'
hoge
# 文字列（一致するものがない）
$ ./jdb_query.py 'test.object.hoge@"xxx"'

# nullか
$ ./jdb_query.py 'test.name@null'

# nullでないか
./jdb_query.py 'test.name@!null'
test db
# 配列
$ ./jdb_query.py 'test.array@[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]'
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# これはヒットしない
$ ./jdb_query.py 'test.array.:@[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]'
[]
```

#### IS_NULL、RANGE、REGEXフィルタ
- @{"IS_NULL": true|false}  
  nullと同値かnullと同値でないかの比較フィルタ

- @{"RANGE": ["配列要素指定書式", ...]}か@{"RANGE": "配列要素指定書式をコンマ区切り"}  
  配列要素の値の範囲を指定する。  
  ⚠️ RANGEフィルタのスライス表記は配列要素指定と意味が異なる。  
　配列要素指定'target.array.2:5'はarrayの**要素番号が**2以上5未満のもの。  
　RANGEフィルタの'target.array.:@{"RANGE": "2:5"}'はarrayの要素で**値が**2以上5未満のもの

- @{"REGEX": "正規表現"}  
  Pythonの正規表現でフィルタ

これらも末尾要素にしか指定できない。  

```shell
# 範囲指定
$ ./jdb_query.py 'test.array.:@{"RANGE": ["2:5"]}'
[2, 3, 4]
# 範囲指定（文字列指定でも良い）
$ ./jdb_query.py 'test.array.:@{"RANGE": "2:5"}'
[2, 3, 4]
# 複数範囲指定（2<=n<5と8<=n<9）
$ ./jdb_query.py 'test.array.:@{"RANGE": ["2:5", "8:9"]}'
[2, 3, 4, 8]
# コンマ区切りの文字列でも良い
$ ./jdb_query.py 'test.array.:@{"RANGE": "2:5,8:9"}'
[2, 3, 4, 8]
# 範囲指定2
$ ./jdb_query.py 'test.object_array.:.fld2@{"RANGE": [":200"]}'
[111]
# 正規表現
$ ./jdb_query.py 'test.object_array.:.fld1@{"REGEX": "b.*"}'
["bbb"]
# null値で無いか
$ ./jdb_query.py 'test.object_array.:.fld2@{"IS_NULL":false}'
[111, 222, 333]
```

#### 途中要素に指定する
JSON形式でキーとフィルタを記述すると途中要素もフィルタできる。  
複数キーを指定することもでき、その場合は両方の条件を満たしたものがヒットする（AND条件）。
- @{"キー": null}  ※!nullは指定できない  
- @{"キー": true|false}  
- @{"キー": 数値}  
- @{"キー": "文字列"}  
- @{"キー": [配列]}  
- @{"キー": {"IS_NULL": true|false}}  
- @{"キー": {"RANGE": [範囲指定]}}  
- @{"キー": {"REGEX": "正規表現"}}

```shell
# 前述の末尾要素へのREGEXフィルタとは異なり、
# 配列要素のオブジェクト自体がフィルタ対象。
# なのでオブジェクトが返ってくる。
$ ./jdb_query.py 'test.object_array.:@{"fld1": {"REGEX": "b.*"}}'
[{"fld1": "bbb", "fld2": 222, "flg3": "BBB"}]
# 複数項目の指定もOK
$ ./jdb_query.py 'test.object_array.:@{"fld1": {"REGEX": "a+"}, "fld2": {"RANGE": "0:300"}}'
[{"fld1": "aaa", "fld2": 111, "flg3": "AAA"}]
# フィルタの後にパス
$ ./jdb_query.py 'test.object_array.:@{"fld2": {"RANGE": "0:300"}}.flg3'
["AAA", "BBB"]
# パスの複数箇所にフィルタをつけてもOK
$ ./jdb_query.py 'test.object_array.:@{"fld2": {"RANGE": "0:300"}}.flg3@"AAA"'
["AAA"]
```

⚠️ 配列への範囲フィルタ  
フィルタは値を比較するものである。配列やオブジェクトと値を比較しても決して一致しない。
```shell
# これは正しい
# array.:はarrayの全要素。その個別の値に対して@{"RANGE": ":"}フィルタがかかる。
$ ./jdb_query.py 'test.array.:@{"RANGE": ":"}'
[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
# これはヒットしない。
# arrayは配列そのもので、配列と値の範囲は比較できない
$ ./jdb_query.py 'test.array@{"RANGE": ":"}'

```

### -c（--choices）による絞り込み
検索結果に対して絞り込みを行うときに使用する。  
targetのパスを増やすのとは結果が異なるので具体例をもって説明する。  

-cで絞り込みをしないとき次の結果になるとする。
```shell
$ ./jdb_query.py 'test.object_array'
[{"fld1": "aaa", "fld2": 111, "flg3": "AAA"}, {"fld1": "bbb", "fld2": 222, "flg3": "BBB"}, {"fld1": "ccc", "fld2": 333, "flg3": "CCC"}]
```

targetのパスを伸ばした場合は次の様になる。  
指定したパスの値だけが結果として得られる。
```shell
$ ./jdb_query.py 'test.object_array.:.fld1@{"REGEX": "aaa|bbb"}'
["aaa", "bbb"]
```

絞り込みを行うとこの様になる。  
指定したパスまでの結果の内、fld1が"aaa"か"bbb"のものだけになる。
```shell
$ ./jdb_query.py 'test.object_array' -c 'fld1@{"REGEX": "aaa|bbb"}'
[{"fld1": "aaa", "fld2": 111, "flg3": "AAA"}, {"fld1": "bbb", "fld2": 222, "flg3": "BBB"}]
```
絞り込み対象がオブジェクトのとき、最初のキーは無視されることに注意すること。  
これは絞り込み前の結果の全項目を対象にするためである。  
絞り込みを行わないときは次の結果。
```shell
$ ./jdb_query.py 'test.object2'
{"aaa": {"xxx": 1, "yyy": "aaa", "zzz": {"key1": "key11", "key2": "key12"}}, "bbb": {"xxx": 2, "yyy": "bbb", "zzz": {"key1": "key21", "key2": "key22"}}, "ccc": {"xxx": 3, "yyy": "ccc", "zzz": {"key1": "key31", "key2": "key32"}}}
```

絞り込みはこの様に指定する（"aaa"、"bbb"、"ccc"といった最初のキーは無視される）。
```shell
$ ./jdb_query.py 'test.object2' -c 'zzz.key1@"key21"'
{"bbb": {"xxx": 2, "yyy": "bbb", "zzz": {"key1": "key21", "key2": "key22"}}}
```

絞り込みを使わない、ワイルドカードと再起的なフィルタを使った場合結果は次の様にパス「./jdb_query.py 'test.object2.*」の値の配列になる。
```shell
$ ./jdb_query.py 'test.object2.*@{"zzz": {"key1": "key21"}}'
[{"xxx": 2, "yyy": "bbb", "zzz": {"key1": "key21", "key2": "key22"}}]
```


## jdb_add.py
データベースに新規要素を追加する。

### コマンドライン
jdb_add.py \<target> \<key> \<value>  

#### 位置引数
target：クエリ文字列。jdb_queryと同じ。オブジェクトか配列のキーを指定しなければならない。
key: 新規に追加するキー。  
　targetが配列要素のキーのときはappendかextendを指定すること。  
　appendは配列に値を追加する。  
　extendは配列型の値を連結する。  
value：更新後の値。文字列、数値、JSONで指定。

### 使用例
```shell
$ ./jdb_add.py test new_int_val 1234
SUCCESS
$ ./jdb_add.py 'test.array' extend '[200, 300]'
SUCCESS
./jdb_add.py 'test.array' append 200
SUCCESS
$ ./jdb_add.py 'test.object2' xxx '{"XXX": 100, "yyy": "abc"}'
SUCCESS
```

## jdb_delete.py
データベースから要素を削除する。

### コマンドライン
jdb_delete.py \<target>  

#### 位置引数
target：クエリ文字列。jdb_queryと同じ。

### 使用例
```shell
# キーを指定して削除
$ ./jdb_delete.py 'test.object.fuga'
SUCCESS(1)
# 指定した要素を削除
$ ./jdb_delete.py 'test.array.2:5'
SUCCESS(3)
# フィルタにかかったものを削除
$ ./jdb_delete.py 'test.object_array.:@{"fld1": {"REGEX": "aaa|bbb"}}'
SUCCESS(2)
```

## jdb_update.py
データベース（JSON）を検索し、一致した要素の値を更新する。  
成功したら更新件数が応答される。

### コマンドライン
jdb_query.py \<query_string> \<value>  

#### 位置引数
query_string：クエリ文字列。jdb_queryと同じ。  
value：更新後の値。文字列、数値、JSONで指定。

### 使用例
```shell
# キーを指定して更新
$ ./jdb_update.py 'test.int_val' 1234
SUCCESS(1)
# 配列要素を指定して更新
./jdb_update.py 'test.array.2' 1000
SUCCESS(1)
# フィルタにかかったものを更新
$ ./jdb_update.py 'test.object_array.:@{"fld1": {"REGEX": "aaa|bbb"}}.fld2' 999
SUCCESS(2)
# nullに設定
$ ./jdb_update.py 'test.int_val' null
SUCCESS(1)
# true（真偽値）に設定
$ ./jdb_update.py 'test.int_val' true
SUCCESS(1)
```