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

""" JSON DB サーバから要素を削除する。
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
		description="JSON DB delete CLient.",
		formatter_class=argparse.RawTextHelpFormatter,
		epilog="""
  配列はPythonのスライス表記で指定できる。コンマ区切りで複数も可能。
  フィールドは|で複数指定可能。

  Examples:
  ./jdb_query.py 'db.users.:.name'
  ./jdb_query.py 'db.users.:.age@{"RANGE": ["20:30"]}'
  ./jdb_query.py 'db.users.:.tags|"name"'
"""
		)
	parser.add_argument("target", type=str, help="検索パス。 ex: db_name.key1.key2...")
	utls.default_args(parser)

	args = parser.parse_args()

	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	command = {
		"mode": "DELETE",
		"target": utls.parse_query_string(args.target),
	}

	return (config, command)

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
	jdb.run("jdb_delete", arg_parse)