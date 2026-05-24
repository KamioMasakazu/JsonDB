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

""" JSON DB サーバにロードされているデータベースを照会する。
"""
import sys
import argparse
import json
from pprint import pprint

import jdb_utils as utls
import jdb_client as jdb

# 引数解析
def arg_parse():
	parser = argparse.ArgumentParser(description="JSON DB list.")
	parser.add_argument('databases', type=str, nargs="*", help='data base names. all data bases if empty.') 
	utls.default_args(parser)

	args = parser.parse_args()

	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	command = {
		"mode": "LIST_DB",
		"databases": args.databases,
	}

	return (config, command)

###############################################################################
# Main
###############################################################################
if __name__ == "__main__":
	jdb.run("jdb_listdb", arg_parse)