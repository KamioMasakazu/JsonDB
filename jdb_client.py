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

import sys
import socket
import argparse
import json
import logging
import traceback

import jdb_utils as utls

class Client:
	""" JDBクライアント
	基本的にライブラリとして使用する。
	mainはテスト用の実装。
	"""

	# コンストラクタ
	def __init__(self, config: dict, logger_name: str = None):
		""" コンストラクタ

		Args:
			config: 設定情報
			logger_name: loggerの名前。未指定ならデフォルトロガーを使う。
		"""
		self.socket_path = utls.socket_path(config["socket"])

		if logger_name:
			self.logger = logging.getLogger(logger_name)
			utls.init_logger(self.logger, logger_name, config)
		else:
			self.logger = logging.getLogger(__name__)
			self.logger.addHandler(logging.NullHandler())


	# 送信処理
	def send(self, command: str) -> str:
		""" commandのJSON文字列を送信する

		Args:
			command: Clientの利用先プログラムで作成したコマンドのJSON文字列。
				次のような形式。
				{
					"mode": "mode固有の文字列",
					...
				}
				mode以外は実装するクライアントごとによる。
		Return:
			結果文字列
		"""
		try:
			self.logger.info("Client::send()")
			self.logger.debug(f"command: {command}")

			with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
				s.connect(self.socket_path)

				# ファイルオブジェクトに変換（テキストモード、改行文字を自動処理）
				with s.makefile("rw", encoding="utf-8") as f:
					f.write(f"{command}\n")
					f.flush()

					response = f.readline()
					return response.strip()
		except FileNotFoundError as fnfe:
			return "ERROR: maybe server is not started."
		except Exception as e:
			self.logger.error("UNKNOWN ERROR\n" + traceback.format_exc())
			sys.exit(1)


###############################################################################
# 実行用関数
# クライアントの実装はこれらを経由して呼ぶと楽
###############################################################################
# クライアント実行
def run(name: str, arg_parse: function):
	""" クライアントを実行して結果を標準出力に出す。
	Args:
		name:
			クライアントコマンド名
		
		arg_parser:
			コマンドライン解析機の関数。(config: dict, command: dict)を返す必要がある。
			send関数を参照。
	"""
	(config, command) = arg_parse()
	ret = send(name, config, command)
	print(ret)

# クライアント実行2
def send(name: str, config: dict, command: dict) -> str:
	""" クライアントを実行して結果文字列を返す。
	Args:
		name:
			クライアントコマンド名

		config:
			クライアント設定データ
			{
				"socket": "path.to.unuxdomain.socket", #Unix Domainソケットファイルのパス
				"debug": True | False,	# デバッグモード
				"log": "path.to.log_file", #ログファイルのパス
			}

		command
			クライアント送信コマンドデータ
			{
				"mode": "...", # サーバに要求する実行モード名
				"...": "...", # その他モードごとのパラメータ
			}
		Returns:
			結果文字列
	"""
	client = Client(config, name)
	cmd_str = json.dumps(command, ensure_ascii=False)
	ret = client.send(cmd_str)
	return ret

###############################################################################
# テスト用
###############################################################################
# 引数解析
def arg_parse():
	""" 引数を解析してClientのコンストラクタに渡す設定とsendするコマンドを返す。
	"""
	parser = argparse.ArgumentParser(description="JSON DB Client.")
	parser.add_argument("command", type=str, help="コマンドのJSON文字列")
	utls.default_args(parser)

	args = parser.parse_args()

	command = args.command
	config = {
		"socket": args.socket,
		"debug": args.debug,
		"log": args.log,
	}

	return (config, command)

# 汎用クライアント用main
# commandはJSON文字列を直接指定なので注意！
def main():
	(config, command) = arg_parse()
	client = Client(config, "default_client")
	ret = client.send(command)
	print(ret)

# main
if __name__ == '__main__':
	main()