#!/usr/bin/env python3
# MIT License
#
# Copyright (c) 2026-05-24 神尾政和
#
# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
# copies of the Software, and to permit persons to whom the Software is 
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, 
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE 
# SOFTWARE.

""" JSON DB サーバにクエリを行う。
クエリを要求し、結果を標準出力に印字する。
あらかじめjdb_load.pyでサーバにデータベースをロードしておく必要がある。
"""
import sys
import re
import argparse
import json
from pprint import pprint

import jdb_utils as utls
import jdb_client as jdb


# 引数解析
def arg_parse():
	parser = argparse.ArgumentParser(
		description="JSON DB qery CLient.",
		formatter_class=argparse.RawTextHelpFormatter,
		epilog="""
Examples:
  ./jdb_query.py 'db.users.:.name'
  ./jdb_query.py 'db.users.:.age@{"RANGE": ["20:30"]}'
  ./jdb_query.py 'db.users.:.tags|"name"'

パスの記述ルール:
  ドット区切りで記述する。先頭はデータベース名(jdb_load.pyのalias)。
    ex: db_name.key1.key2...
  特殊文字を含むキーは\"\"で囲む。
    ex: db_name.\"special.chars|key\"
  配列要素番号(0始まり）かはPythonのスライス表記で指定できる。コンマ区切りで複数も可能。配列名（下例のarray_key）と指定する要素番号は.（ドット）で区切る。
    ex: db_name.key1.array_key.1,5:.key2
  複数キーを|で指定可能。
    ex: db_name.object_key.aaa|bbb|zzz.fld1

フィルタの指定：
  フィルタを指定することで絞り込みを行える。フィルタは「キー@フィルタ」と記述する。

・値比較フィルタ
  末尾要素（値が数値、文字列、真偽値、nullの要素）は次のいずれかを指定できる。中間要素（値が配列かオブジェクトの要素）は値を比較でき無いので指定でき無い。
    @null、@!null: @nullはnullであること、@!nullはnullで無いことを比較する。大小文字無視。
    @true、@false: bool値を指定する。大小文字無視。
    @数値: 整数か小数を指定する。
    @"文字列": 文字列を指定する。""で囲むこと。
    @{"IS_NULL": true|false}: trueはnullであること、falseはnullでないことを比較する。末尾要素指定では@null、@!nullと同じ。
    @{"REGEX": "Pythonの正規表現"}: 正規表現フィルタの指定。
    @{"RANGE": [...]}: 数値が指定の範囲内にあるかをチェックする。["2", "3:5", "10:"]のようにコンマ区切りで複数指定可能。
       "n": 同値か
       ":n": n未満か
       "n:": n以上か
       "n:m": n以上m未満か
       ":": 全て

・JSONフィルタ
  JSONフィルタは中間要素にも指定できる。
  JSONフィルタはキーの値がJSONで指定したフィールドと値（数値、文字列、真偽値、null）を持つかを見る。
    @{"fld1": "aaa", "fld2": 100}
  値部分にIS_NULL、REGEX、RANGEを指定することも可能。末尾要素に指定可能な!nullは指定できないのでIS_NULLを使うこと。
    @{"fld1": {"REGEX": "aaa|zzz"}, "fld2": {"RANGE": ["10:20","50:"]}}

  （注意）JSONフィルタは1階層の要素しか見ない。次のようなフィルタはfld3の比較が常に失敗するので無意味である。
   @{"fld1": "aaa", "fld2": 100, "fld3": {"sub1": "xx"}}
"""
		)
	parser.add_argument("target", type=str, help="検索パスを指定する\n")
	parser.add_argument("--print", type=str, choices=["key", "count"], default=None, help="""
  key: 結果がオブジェクトならキーの配列を表示。オブジェクトで無いなら空文字列。
  count: 結果がオブジェクトか配列なら要素数を表示。そうで無ければ空文字列。
""")
	utls.default_args(parser)

	args = parser.parse_args()

	# Clientの設定
	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	# このコマンドのオプション
	options = {
		"print": args.print,
	}

	# サーバに送るコマンド
	command = {
		"mode": "QUERY",
		"target": utls.parse_query_string(args.target),
	}

	return (config, options, command)

def print_keys(result: str) -> str:
	""" 結果文字列をデコードした結果のキーの配列を返す。
	resultがdictにパースできる時だけ。
	"""
	try:
		decoded = json.loads(result)
		if isinstance(decoded, dict):
			keys = list(decoded.keys())
			return json.dumps(keys, ensure_ascii=False)
		else:	# None & list
			return ""
	except json.JSONDecodeError:
		return ""

def print_counts(result: str) -> str:
	""" 結果文字列をデコードした結果の要素数を返す。
	resultがlistかdictにパースできる時だけ。
	"""
	try:
		decoded = json.loads(result)
		if isinstance(decoded, (list, dict)):
			return str(len(decoded))
		else:	# None
			return ""
	except json.JSONDecodeError:
		return ""

def print_result(result: str, options: dict):
	""" オプションに応じて結果を表示する
	"""
	match options["print"]:
		case "key":
			print(print_keys(result))
		case "count":
			print(print_counts(result))
		case _:
			print(result)

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
	(config, options, command) = arg_parse()
	ret = jdb.send("jdb_query", config, command)
	print_result(ret, options)
