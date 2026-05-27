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

import os
import sys
import socket
import signal
import argparse
import json
from pathlib import Path
from pprint import pprint, pformat
import copy
import glob
import logging
import traceback

import jdb_utils as utls

# ロガー
LOGGER_NAME = "jdb_server"
logger = logging.getLogger(LOGGER_NAME)
logger.addHandler(logging.NullHandler())

###############################################################################
# jdbサーバ
###############################################################################
class Server:
	""" JsonDBサーバ
	unix domainソケットでリクエストを受けて結果を返す。
	"""

	# コンストラクタ
	def __init__(self, config: dict):
		""" コンストラクタ

		Args:
			config: 設定データ
		"""
		self.socket_path = utls.socket_path(config["socket"])
		self.pid_file = utls.pid_path(config["socket"])
		self.create_db_name = config["create"]	# -cが指定された時
		self.initial_files = config["files"]	# -fが指定された時
		self.databases = {}
		self.json_paths = {}

	# 終了シグナルハンドラ
	def term_handler(self, signum, frame):
		""" 終了シグナルハンドラ
		"""
		sys.exit(0)

	# pidファイル作成
	def create_pid_file(self):
		with open(self.pid_file, "w") as f:
			f.write(str(os.getpid()) + "\n")
		logger.debug(f"{self.pid_file} cleated")

	# pidファイル削除
	def delete_pid_file(self):
		if os.path.exists(self.pid_file): os.remove(self.pid_file)
		logger.debug(f"{self.pid_file} deleted.")

	# 未実装機能用のエコー関数
	def echo(self, command: dict) -> str:
		""" 未実装機能用のエコー関数

		Args:
			command: 要求コマンド
		"""
		logger.info("Server::echo()")
		logger.info(pformat(command))
		return "UNKNOWN_COMMAND: " + json.dumps(command, ensure_ascii=False)

	# jsonファイルを読み込んでデコードしたデータを返す。
	def init_database(self, path: str, alias: str):
		""" pathのjsonファイルを読み込んでデコードし、aliasの名前でデータベースを登録する。
		fnameが指定されていないなら空のデータベースを作成する。
		"""
		logger.info("Server::init_database()")
		data = None
		if path:
			with open(path, "r") as f:
				data = json.load(f)
		else:
			data = {}

		self.databases[alias] = data
		self.json_paths[alias] = path

	# JSONファイルをdatabasesにロードする
	def load_database(self, command: dict) -> str:
		"""JSONファイルをdatabasesにロードする
		json_pathが空なら空のデータベースを作成する。
		Args:
			command: jdb_load.pyが送信するコマンド。

		Returns:
			メッセージ文字列。
		"""
		logger.info("Server::load_database()")

		try:
			if not command["json_path"] and not command["alias"]:
				logger.info("empty parameter.")
				return "ERROR: empty parameter."
			self.init_database(command["json_path"], command["alias"])

		except Exception as e:
			logger.error(repr(e))
			return "ERROR: read file."

		logger.info(f"loaded {command["alias"]}: {command["json_path"]}")
		utls.dump(logger, "json_paths", self.json_paths)
		utls.dump(logger, "databases", self.databases)

		return f"LOAD: {command["alias"]}"

	# 指定されたデータベースをファイルに保存する
	def save_database(self, command: dict) -> str:
		"""指定されたデータベースをファイルに保存する

		Args:
			command: jdb_load.pyが送信するコマンド。

		Returns:
			メッセージ文字列。
		"""
		logger.info("Server::save_database()")

		db_name = command["db_name"]
		path = command["json_path"]

		try:
			if not db_name in self.databases:
				logger.info("no such database.")
				return "ERROR: no such database."

			if len(path) == 0:
				if len(self.json_paths[db_name]) == 0:
					logger.info("file is not specified.")
					return "ERROR: file is not specified."
				path = self.json_paths[db_name]

			with open(path, "w") as f:
				json.dump(self.databases[db_name], f, indent=4)

		except Exception as e:
			logger.info(repr(e))
			return "ERROR: save failed."

		return "SAVE: OK"

	# データベースのリストを返す
	def list_databases(self, command: dict) -> str:
		"""Jdatabasesに存在するデータベースを照会する。
		command["databases"]が空なら全データベースを返す。
		command["databases"]が空でないならデータベース名が一致したもののリストを返す。

		Args:
			command: jdb_load.pyが送信するコマンド。

		Returns:
			メッセージ文字列。
		"""
		logger.info("Server::list_database()")

		ret = []
		if len(command["databases"]) == 0:
			ret = list(self.databases)
		else:
			for k in self.databases:
				if k in command["databases"]:
					ret.append(k)

		logger.info("listed")
		utls.dump(logger, "ret", ret)
		return f"{ret}"

	# DBの存在確認
	def _check_common_command(self, command: dict) -> tuple[str, str]:
		""" 共通の入力チェック
		Args:
			command: jdb_query.pyが送信するコマンド。
		Returns:
			(データベース名, エラー時のメッセージ)
			データベース名: 失敗時はNone
			エラー時のメッセージ： 成功時はNone
		"""
		logger.info("Server::_check_common_command()")

		if len(command["target"]) == 0:
			logger.info("QUERY: target is not specified.")
			return (None, "ERROR: target is not specified.")

		root = command["target"][0]

		if root["node_type"] != "KEY":
			logger.info(f"QUERY: bad database type ({root}).")
			return (None, "ERROR: bad database was specified.")

		db_name = root["target"]
		if not db_name in self.databases:
			logger.info(f"QUERY: database is not found ({db_name}).")
			return (None, f"ERROR: database is not found ({db_name}).")
		
		return (db_name, None)

	def _choice_query_result(self, result: dict | list, path: list) -> dict| list:
		""" クエリ結果の絞り込み
		"""
		logger.info("Server::_choice_query_result()")
		new_result = result

		# 絞り込みがなかったら何もせず返る
		if not path:
			return new_result

		if isinstance(result, list):
			new_result = []
			for obj in result:
				ret = utls.search_db(obj, path[:])
				if ret != utls.FoundValue.NotFound:
					new_result.append(obj)
		if isinstance(result, dict):
			new_result = {}
			for name, obj in result.items():
				utls._dbg("name:", name)
				utls._dbg("obj:", obj)
				ret = utls.search_db(obj, path[:])
				if ret != utls.FoundValue.NotFound:
					new_result[name] = obj

		logger.info("choice query finished")
		utls.dump(logger, "query result", new_result)

		return new_result


	# DBを検索して結果を返す
	def query_db(self, command: dict) -> str:
		""" DBを検索して結果を返す。
		結果は基本的にJSON文字列だが、結果がプリミティブ（数値や文字列）になる時はJSON形式ではない文字列を返す。

		Args:
			command: jdb_query.pyが送信するコマンド。

		Returns:
			結果の文字列かJSON文字列
		"""
		logger.info("Server::query_db()")
		(db_name, msg) = self._check_common_command(command)
		if not db_name: return ""	# エラーの時に空文字列を返す

		# targetを検索
		ret = utls.search_db(self.databases, command["target"][:])
		logger.info("query finished")
		utls.dump(logger, "query result", ret)

		# 結果を絞り込み
		for choice in command["choices"]:
			ret = self._choice_query_result(ret, choice)

		if ret == utls.FoundValue.NotFound:
			return ""
		elif isinstance(ret, (list, dict)):
			return json.dumps(ret, ensure_ascii=False)
		elif ret == None:
			return "null"
		else:
			return f"{ret}"

	# DBに値を追加する
	def add_db(self, command: dict):
		""" DBに新しい値を追加する。
		Args:
			command: jdb_query.pyが送信するコマンド。
		Returns:
			結果の文字列かJSON文字列
		"""
		logger.info("Server::add_db()")
		(db_name, msg) = self._check_common_command(command)
		if not db_name: return msg

		last = command["target"][-1]
		if last["node_type"] != "KEY":
			logger.info("node_type must be KEY.")
			return "ERROR: node_type must be KEY."

		ret = utls.search_db(self.databases, command["target"])
		utls.dump(logger, "query finished", ret)

		new_key = command["key"]
		new_value = command["value"]
#		utls._dbg("key", new_key)
#		utls._dbg("value", new_value)
#		utls._dbg("to update", ret)

		if isinstance(ret, list):
			# node_typeがKEYでない時はすでにreturnしているのでここにきた時は配列要素のキーが指定された時
			if new_key == "extend":
				if isinstance(new_value["value"], list): ret.extend(new_value["value"])
				else:
					logger.info("value must be array to extend.")
					return "ERROR: value must be array to extend."
			elif new_key == "append":
				ret.append(new_value["value"])
			else:
				logger.info("key of array node must be append or extend.")
				return "ERROR: key of array node must be append or extend."
		elif isinstance(ret, dict):
			if not new_key in ret:
				ret[new_key] = new_value["value"]
		elif ret == utls.FoundValue.NotFound:
			logger.info("tareget is not found.")
			return "ERROR: tareget is not found."
		else:
			logger.info("target is not array or object.")
			return "ERROR: target is not array or object."

		logger.info("added")
		utls.dump(logger, "added db", self.databases[db_name])

		return "SUCCESS"

	# DBを更新する
	def update_db(self, command: dict) -> str:
		""" DBを検索して更新する。
		Args:
			command: jdb_query.pyが送信するコマンド。
		Returns:
			成否を示す文字列
		"""
		logger.info("Server::update_db()")
		(db_name, msg) = self._check_common_command(command)
		if not db_name: return msg

		last = command["target"][-1]
		ret = utls.search_db(self.databases, command["target"][:-1])
		utls.dump(logger, "query finished", ret)

#		utls._dbg("last", last)
#		utls._dbg("update", command["update"])
#		utls._dbg("to update", ret)

		updated = 0
		if isinstance(ret, list):
			if last["node_type"] == "ARRAY":
				items = utls._get_array_nums(last["target"], len(ret))
				for i in items:
					if "filter_type" in last:
						if not utls._check_filter(ret[i], last["filter_type"], last["filter"]):
							continue
					ret[i] = copy.deepcopy(command["update"]["value"])
					updated += 1
			else:
				for r in ret:
					if not last["target"] in r:
						logger.info(f'key not found: {last["target"]}')
						continue
					if "filter_type" in last:
						if not utls._check_filter(r[last["target"]] , last["filter_type"], last["filter"]):
							continue
					r[last["target"]] = copy.deepcopy(command["update"]["value"])
					updated += 1
		elif isinstance(ret, dict):
			if last["node_type"] == "MULTI_KEY":
				targets = utls.list_targets(last["target"], ret)

				for t in targets:
					if not t in ret:
						logger.info(f'key not found: {targets}')
					else:
						filter_ok = True
						if "filter_type" in last:
							filter_ok = utls._check_filter(ret[t], last["filter_type"], last["filter"])
						if filter_ok:
							ret[t] = copy.deepcopy(command["update"]["value"])
							updated += 1
			else:	# KEY
				if not last["target"] in ret:
					logger.info(f'key not found: {last["target"]}')
				else:
					filter_ok = True
					if "filter_type" in last:
						filter_ok = utls._check_filter(ret[last["target"]], last["filter_type"], last["filter"])
					if filter_ok:
						ret[last["target"]] = command["update"]["value"]
						updated += 1
		else:
			logger.error("target cannot update.")
			return "ERROR: target cannot update."

		logger.info("updated")
		utls.dump(logger, "updated db", self.databases[db_name])

		return f"SUCCESS({updated})"

	# DBを削除する
	def delete_db(self, command: dict) -> str:
		""" DBを検索して削除する。
		Args:
			command: jdb_query.pyが送信するコマンド。
		Returns:
			成否を示す文字列
		"""
		logger.info("Server::delete_db()")
		(db_name, msg) = self._check_common_command(command)
		if not db_name: return msg

		last = command["target"][-1]
		ret = utls.search_db(self.databases, command["target"][:-1])
		utls.dump(logger, "query finished", ret)

#		utls._dbg("last", last)
#		utls._dbg("to delete", ret)

		count = 0
		if last["node_type"] == "ARRAY":
			before_del = len(ret)	# 削除前の件数
			if "filter_type" in last:
				lst = [v for v in ret if not utls._check_filter(v, last["filter_type"], last["filter"])]
			else:
				if isinstance(ret, list):
					ids = set(utls._get_array_nums(last["target"], len(ret)))
					lst = [v for i, v in enumerate(ret) if not i in ids]
			
			ret[:] = lst
			count = before_del - len(ret)
		elif last["node_type"] == "MULTI_KEY":
			for t in last["target"]:
				if not t in ret:
					logger.info(f'key not found: {t}')
				else:
					filter_ok = True
					if "filter_type" in last:
						filter_ok = utls._check_filter(ret[t], last["filter_type"], last["filter"])
					if filter_ok:
						ret.pop(t)
						count += 1
		else:
			if not last["target"] in ret:
				logger.info(f'key not found: {last["target"]}')
			else:
				filter_ok = True
				if "filter_type" in last:
					filter_ok = utls._check_filter(ret[last["target"]], last["filter_type"], last["filter"])
				if filter_ok:
					ret.pop(last["target"])
					count += 1

		logger.info("deleted")
		utls.dump(logger, "deleted db", self.databases[db_name])

		return f"SUCCESS({count})"

	# accept後の処理
	def accepted(self, connection, address):
		"""処理の本体
		リクエストコマンドに応じて処理を行い結果を応答する。

		Args:
			connestion: acceptが返したソケット
			address: acceptが返したアドレス
		"""
		logger.info(f"Server::accepted(): {address}")
		HANDLER = {
			"LOAD": self.load_database,
			"SAVE": self.save_database,
			"LIST_DB": self.list_databases,
			"QUERY": self.query_db,
			"ADD": self.add_db,
			"DELETE": self.delete_db,
			"UPDATE": self.update_db,
		}
		with connection.makefile("rw", encoding="utf-8") as f:
			req = f.readline().strip()
			logger.debug(f"req: {req}")

			resp = "ERROR: Bad Request"
			try:
				command = json.loads(req)
				if command["mode"] in HANDLER:
					handle = HANDLER[command["mode"]]
					logger.info(f"exec {command["mode"]}")
					utls.dump(logger, "command", command)
					resp = handle(command)
				else:
					logger.info("unknown mode recieved.")
					resp = self.echo(command)
			except json.JSONDecodeError:
				logger.info("bad request recieved.")
			except KeyError:
				logger.info("mode is not specified.")

			f.write(f"{resp}\n")
			f.flush()

	# サーバ開始
	def start(self):
		""" サーバ開始
		"""
		logger.info(f"Server::start()")
		signal.signal(signal.SIGTERM, self.term_handler)
		signal.signal(signal.SIGINT, self.term_handler)

		self.create_pid_file()

		try:
			# DBロードが指定されていたら
			if self.create_db_name:
				self.init_database(None, self.create_db_name)
			elif self.create_db_name == "":
				logger.info("cannot create unnamed database.")
				sys.exit(1)
			
			if self.initial_files:
				for f in self.initial_files:
					self.init_database(f, Path(f).stem)

			# ここからソケット待ち
			with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
				s.bind(self.socket_path)
				s.listen(1)
				while True:
					connection, address = s.accept()
					logger.debug(f"connected {address}")
					self.accepted(connection, address)
					logger.debug(f"disconnect {address}")
		except Exception as e:
			logger.error("UNKNOWN ERROR\n" + traceback.format_exc())
			sys.exit(1)
		finally:
			if os.path.exists(self.socket_path): os.remove(self.socket_path)
			self.delete_pid_file()
			logger.info("exit server.")

###############################################################################
# 関数群
###############################################################################
# 二重起動チェック
def is_dup_process(sock_name: str) -> bool:
	""" プロセスの重複チェック
	二重起動している可能性があればTrue、無ければFalse
	ソケットがある時は二重起動。
	pidファイルがある時はプロセスがいるか見て判断する。
	"""
	logger.info("is_dup_process()")
	try:
		# ソケットがあったらダメ
		sock_path = utls.socket_path(sock_name)
		if os.path.exists(sock_path):
			logger.warning(f"{sock_path} already exists.")
			return True

		# pidファイルがなかったらOK
		pid_path = utls.pid_path(sock_name)
		if not os.path.exists(pid_path):
			return False

		with open(pid_path, "r") as f:
			pid = int(f.read().strip())

			if utls.is_process_running(pid):
				logger.warning(f"pid {pid} already is running.")
				return True

		# 一応消す
		os.remove(pid_path)

		return False
	except Exception as e:
		logger.error(f"{e}")
		return True

# デーモン化
def demonize():
	""" 子プロセスを産んで親プロセスは終了する。
	demoniez()を呼んだ後の処理はデーモンプロセスとして動く。
	"""
	logger.info("demonize()")
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0)
	except OSError as e:
		logger.error(f"fork failed: {e}")
		sys.exit(1)

	# ターミナルを切り離す
	os.setsid()

# サーバを起動する
def start_server(config: dict, daemon_mode: bool):
	logger.info("start_server()")
	# 二重起動チェック
	if is_dup_process(config["socket"]):
		sys.exit(1)

	# デーモン動作がデフォルト（foreground オプションがない場合）
	if daemon_mode:
		demonize()

	# デーモン化が完了した「後」に Server インスタンスを作成・起動する
	server = Server(config)
	server.start()

# サーバのソケット名一覧を表示する
def list_server():
	logger.info("list_server()")

	tmp_dir = utls.tmp_path()
	files = glob.glob(f"{tmp_dir}/jdb_server.*.pid")
	for f in files:
		fname = os.path.splitext(os.path.basename(f))[0]
		print(fname.replace("jdb_server.", ""))

# SIGTERMを送ってサーバを停止する
def stop_server(config: dict):
	logger.info("stop_server()")

	pid_f = utls.pid_path(config["socket"])
	try:
		if not os.path.exists(pid_f):
			logger.warning(f"Server is not running (PID file not found).")
			sys.exit(1)

		pid = -1	# pidにはない値
		with open(pid_f, "r") as f:
			pid = int(f.read().strip())

		if pid > 0: os.kill(pid, signal.SIGTERM)
		logger.info(f"SIGTERM send to {pid}.")
		sys.exit(0)
	except Exception as e:
		logger.error(f"stop server.\n{e}")
		sys.exit(1)


# 引数解析
def arg_parse():
	""" コマンドライン引数を解析してServerのコンストラクタに渡す設定を返す。
	"""
	parser = argparse.ArgumentParser(description="JSON DB Server.", formatter_class=argparse.RawTextHelpFormatter)
	parser.add_argument("mode", type=str, nargs="?", choices=["start", "stop", "list"], default="start",
	help="""このコマンドの動作モード
  start: サーバを起動する。全てのオプションが有効。
  stop: サーバを停止する。-c, -f, -Fは無視する。
  list: 起動しているサーバのソケット名一覧を表示する。-d以外のオプションを無視する。
	"""
	)
	parser.add_argument("-c", "--create", type=str, help="create empty database.")
	parser.add_argument("-f", "--files", type=str, nargs="*", help="json files.")
	parser.add_argument("-F", "--foreground", action="store_true", help="run foreground process.")
	utls.default_args(parser)

	args = parser.parse_args()

	config = {
		"create": args.create,
		"files": args.files,
		"socket": args.socket,
	}

	option = {
		"mode": args.mode,
		"daemon": not args.foreground,
		"debug": args.debug,
		"log": args.log,
	}

	return (config, option)

###############################################################################
# Main
###############################################################################
def main():
	(config, option) = arg_parse()

	utls.init_logger(logger, LOGGER_NAME, option)
	utls.logger = logger	# jdb_utils.pyの関数でもログ出力できるように

	match option["mode"]:
		case "start":
			start_server(config, option["daemon"])
		case "stop":
			stop_server(config)
		case "list":
			list_server()
		case _:
			print(f"ERROR: invalid mode {option["mode"]}", file=sys.stderr)
			sys.exit(1)

if __name__ == '__main__':
	main()

