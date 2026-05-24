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

""" JSON DB サーバにJSONファイルをデータベースとしてロードする。
コマンドライン引数のaliasが異なれば複数のファイルをロードできる。
"""
import sys
import argparse
from pathlib import Path
import json
from pprint import pprint

import jdb_utils as utls
import jdb_client as jdb

# 引数チェック
def check_args(args) -> dict:
	""" pathとaliasの両方がない場合はエラー（None）
	pathは空文字列で無ければ絶対パスにする。
	aliasが空文字列でpathがある時はpathからディレクトリと拡張子を取ったもの。空文字列でないなら指定された値。
	"""
	if not args.json_path and not args.alias:
		return None
	
	path = str(Path(args.json_path).resolve()) if args.json_path else ""
	alias = args.alias if args.alias else Path(args.json_path).stem

	return {
		"path": path,
		"alias": alias,
	}


# 引数解析
def arg_parse():
	parser = argparse.ArgumentParser(description="JSON DB flie loader.")
	parser.add_argument("json_path", type=str, nargs="?", default="", help="JSONファイルのパス")
	parser.add_argument("-a", "--alias", type=str, default="", help="DB用の別名。未指定ならJSONファイルのパスと拡張子を除いたもの。")
	utls.default_args(parser)

	args = parser.parse_args()

	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	checked = check_args(args)
	if not checked:
		print("Error: must set json_path or alias.")
		sys.exit(1)

	command = {
		"mode": "LOAD",
		"json_path": checked["path"],
		"alias": checked["alias"],
	}

	return (config, command)

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
	jdb.run("jdb_load", arg_parse)