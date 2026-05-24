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

""" JSON DB サーバに値を追加する。
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
		description="JSON DB add CLient.",
		formatter_class=argparse.RawTextHelpFormatter,
		epilog="""Examples:
  ./jdb_add.py test new_int_val 1234
  ./jdb_add.py 'test.array' extend '[200, 300]'
  ./jdb_add.py 'test.array' append 200
  ./jdb_add.py 'test.object2' xxx '{"XXX": 100, "yyy": "abc"}'
"""
	)
	parser.add_argument("target", type=str, help="""追加対象ノードのパス。jdb_query.pyと同じ表記。
配列かオブジェクト要素でなければならない（値であってはならない）。""")
	parser.add_argument("key", type=str, help="""追加するキー文字列。必ず文字列となる。
  targetが配列の時はappendかextendを指定すること。
  - append: 配列の値として追加する。
  - extend: 配列を結合する。""")
	parser.add_argument("value", type=str, help="""追加する値
null、true、false（いずれも大文字、小文字を無視）はnull値、bool値として扱う。
数値（整数、少数）は数値として扱う。
"文字列"は文字列として扱う。
JSON文字列はJSONのオブジェクトとして扱う。配列もJSONの一種として扱う。
数値、null、true、false、JSON文字列を文字列の値にしたいときは'\"null\"'の様に二重にクォートすること。
""")
	utls.default_args(parser)

	args = parser.parse_args()

	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	command = {
		"mode": "ADD",
		"target": utls.parse_query_string(args.target),
		"key": str(args.key),
		"value": utls.parse_value_string(args.value),
	}

	return (config, command)

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
	jdb.run("jdb_add", arg_parse)