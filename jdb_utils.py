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

""" ユーティリティ関数など
"""
import sys
import re
import json
from pathlib import Path
import copy
import os
from enum import Enum
import subprocess
import logging
from pprint import pprint, pformat
import fnmatch

PRIVATE_DEBUG = True	# このファイルのデバッグ用

# ロガー
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

###############################################################################
# 汎用関数
###############################################################################
# このファイルのデバッグ用
def _dbg(message: str, obj:any = None, *, disp_none=False):
	""" デバッグ出力用
	Args:
		message: メッセージ
		obj: ダンプしたいデータ
	"""
	if not PRIVATE_DEBUG: return
	print(f"PRIVATE DEBUG: {message}")
	if obj == None:
		if disp_none: pprint(obj)
	else:
		pprint(obj)
	print("")

# ロギング
def init_logger(logger: logging.Logger, name: str, option: dict):
	""" ロガーのイニシャライザ
	Args:
		logger: ロガーオブジェクト
		name: getlogger()の名前
		option: 起動時オプション（option["log"]とoption["debug"]）
	"""
	FORMATTER = "%(asctime)s %(name)s [%(levelname)s] %(message)s"
	logger = logging.getLogger(name)

	if option["debug"]: logger.setLevel(logging.DEBUG)
	else: logger.setLevel(logging.INFO)

	if option["log"]:
		log_path = Path(option["log"])
		log_dir = log_path.parent
		os.makedirs(log_dir, exist_ok = True)

		handler = logging.FileHandler(f"{option['log']}", mode='a', encoding="utf-8")
		#handler.setLevel(logging.DEBUG)	# これはなくても良い
		handler.setFormatter(logging.Formatter(FORMATTER))
		logger.addHandler(handler)

	# デバッグモードなら標準エラーにも出す
	if option["debug"]:
		DBG_FMT = "%(name)s [%(levelname)s] %(message)s"
		stream_handler = logging.StreamHandler(sys.stderr)
		stream_handler.setFormatter(logging.Formatter(DBG_FMT))
		logger.addHandler(stream_handler)

# データをログにダンプ
def dump(logger: logging.Logger, msg:str, obj:any):
	""" ログにデータをダンプする。ログレベルはDenug。
	"""
	logger.debug(f"DATA DUMPS: {msg}\n" + pformat(obj))


# argparseにデフォルトのオプションを追加する
def default_args(parser):
	""" デフォルトのコマンドライン引数を追加
	-s(--socket)
	-d(--debug)
	-l(--log)
	"""
	parser.add_argument("-s", "--socket", type=str, default="default", help="Unixdomain socket nmae (without path & ext).")
	parser.add_argument("-d", "--debug", action="store_true", help="Debug mode.")
	parser.add_argument("-l", "--log", type=str, default=None, help="log file (ex. ./log/jsb.log).")
	parser.add_argument("--version", action="version", version="%(prog)s 0.1.2")

# テンポラリディレクトリのパスを返す
def tmp_path() -> str:
	tmp = os.environ.get("TMPDIR")
	if not tmp: tmp = "/tmp"
	return tmp

# unix domainソケットのパスを返す
def socket_path(sock_name: str) -> str:
	return f"{tmp_path()}/jdb_server.{sock_name}.socket"

# pidファイルのパスを返す
def pid_path(sock_name: str) -> str:
	return f"{tmp_path()}/jdb_server.{sock_name}.pid"

# pidでプロセス存在確認
def is_process_running(pid: int) -> bool:
	"""プロセスが生存しているか確認（クロスプラットフォーム対応）"""
	if pid <= 0:
		return False

	if sys.platform == "win32":
		# Windows: tasklistコマンドを使用
		try:
			result = subprocess.run(
				["tasklist", "/FI", f"PID eq {pid}", "/NH"],
				capture_output=True,
				text=True,
				timeout=5,
			)
			# /FI でPIDフィルタ済みなので、出力にPIDが含まれていれば存在確認OK
			# プロセスがない場合は "INFO: No tasks are running..." が返る
			return str(pid) in result.stdout
		except subprocess.SubprocessError:
			return False
	else:
		# Unix: signal 0 を使用
		try:
			os.kill(pid, 0)
			return True
		except OSError:
			return False

###############################################################################
# クエリ文字列パーサ
###############################################################################
def _split_by_unescaped_char(text: str, delimiter: str) -> list[str]:
	"""クォート外にある指定文字（. や | や ,）で文字列を分割するヘルパー"""
	results = []
	current = []
	in_quotes = False

	for char in text:
		if char == '"':
			in_quotes = not in_quotes
			current.append(char)
		elif char == delimiter and not in_quotes:
			results.append("".join(current))
			current = []
		else:
			current.append(char)
	results.append("".join(current))
	return results

def _trim_quotes_only(text: str) -> str:
	"""文字列の外側にダブルクォートがある場合のみそれを取り除く"""
	text = text.strip()
	if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
		return text[1:-1]
	return text

def _is_slices(slices: list) -> list:
	"""  {"RANGE": ["n", ...]}のリストがスライス表記かをチェックする
	チェック後のリストを返す。整数項目があったら文字列にする。
	エラー時は例外を投げる。
	"""
	ret = []
	if not isinstance(slices, list):
		raise ValueError(
				f"Query parse error: must be array of alices.\n"
				f"Node context: '{filter}'"
			)

	for s in slices:
		s = str(s)	# 強制的に文字列にする
		if not re.match(r"^(\d+|\:|:\d+|\d+:|\d+:\d+)$", s):
			raise ValueError(
					f"Query parse error: only slice notation is available.\n"
					f"Node context: '{filter}'"
				)
		ret.append(s)
	
	return ret

def _parse_terminal(filter: any) -> bool:
	""" 末尾要素の値でパースが必要ならパースする（破壊的）。
	filterが{"REGEX": ...}, {"RANGE": ...}, {"IS_NULL": true|false}, null, 真偽値, 数値, 文字列ならtrueを返す。
	{"RANGE": "2, 4:"}の様な文字列表記なら{"RANGE": ["2", "4":]}の配列に変換する。
	そうで無ければfalseを返す。
	"""
#	_dbg(f"_parse_terminal()\n{filter}")
	if isinstance(filter, dict):
		# 文字列表記のスライスを配列に変換
		if "RANGE" in filter and isinstance(filter["RANGE"], str):
			filter["RANGE"] = _split_by_unescaped_char(filter["RANGE"], ",")

		# 配列の中身がスライス表記だけでできていることを確認
		if "RANGE" in filter:
			filter["RANGE"] = _is_slices(filter["RANGE"])
		
		# その他JSON形式の末尾フィルタのタイプかをチェック
		if ("REGEX" in filter) or ("RANGE" in filter) or ("IS_NULL" in filter):
			return True
	if filter == None or isinstance(filter, (bool, int, float, str)):
			return True
	
	return False

def _parse_json_more(filter: dict | list):
	""" JSON型のフィルタを更にパースする（破壊的）
	"""
#	_dbg(f"_parse_json_more():\n{pformat(filter)}")
	if not isinstance(filter, (dict, list)):
		return

	if isinstance(filter, list):
		for child in filter:
			is_terminal = _parse_terminal(child)
			if not is_terminal: _parse_json_more(child)
	elif isinstance(filter, dict):
		for key in filter:
			child = filter[key]
			is_terminal = _parse_terminal(child)
			if not is_terminal: _parse_json_more(child)

	return

def _parse_filter(filter_str: str) -> tuple[str, any]:
	"""フィルター文字列を解析して (filter_type, filter_value) を返す。

	数値でない場合はすべてJSONとしてデコードを試み、失敗した場合は例外を投げます。
	"""
	stripped = filter_str.strip()
#	_dbg(stripped)

	# null判定
	if stripped.upper() == "NULL":
		return "NULL", None
	if stripped.upper() == "!NULL":
		return "NULL", "!null"
	# bool判定
	if stripped.upper() == "TRUE":
		return "BOOL", True
	elif stripped.upper() == "FALSE":
		return "BOOL", False
	# 数値判定（整数）
	if re.match(r"^-?\d+$", stripped):
		return "NUMBER", int(stripped)
	# 数値判定（浮動小数点）
	if re.match(r"^-?\d+\.\d+$", stripped):
		return "NUMBER", float(stripped)

	# 3. それ以外はすべてJSON（文字列表記 '"..."', オブジェクト '{}', 配列 '[]'）としてデコード
	try:
		parsed = json.loads(stripped)
		is_json = True
	except json.JSONDecodeError:
		try:
			# キーのクォート漏れ（テスト2番）の救済を試みる
			fixed_str = re.sub(
				r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:", r'\1"\2":', stripped
			)
			parsed = json.loads(fixed_str)
			is_json = True
		except json.JSONDecodeError as e:
			# 救済してもデコードできなければ、仕様通りエラー（例外）にする
			raise ValueError(
				f"Invalid filter format. Must be a valid NUMBER or JSON string/object.\n"
				f"JSON Error: {e.msg} (line {e.lineno} col {e.colno})\n"
				f"Filter text: '{stripped}'"
			) from e

	# デコード成功後のフィルタータイプ判定
	if isinstance(parsed, dict) and "REGEX" in parsed:
		return "REGEX", parsed
	if isinstance(parsed, dict) and "RANGE" in parsed:
		# {"RANGE": "2,4:"}の様な文字列指定にも対応
		if isinstance(parsed["RANGE"], str):
			parsed["RANGE"] = _split_by_unescaped_char(parsed["RANGE"], ",")
		parsed["RANGE"] = _is_slices(parsed["RANGE"])	# パースした結果がスライス表記だけで構成されているか確認
		return "RANGE", parsed
	if isinstance(parsed, dict) and "IS_NULL" in parsed:
		return "IS_NULL", parsed
	if isinstance(parsed, str):
		return "STRING", parsed
	if isinstance(parsed, list):
		return "ARRAY", parsed

	# JSON型フィルタなら更に内部をパース
	_parse_json_more(parsed)
	return "JSON", parsed

# 設定値のパース
def parse_value_string(value: str) -> dict:
	""" 設定値をパースしてコマンドのdictを返す。
	"""
	stripped = value.strip()

	if re.match(r"^-?\d+$", stripped): pass	# 整数
	elif re.match(r"^-?\d+\.\d+$", stripped): pass # 浮動小数点
	elif stripped.upper() == "NULL": pass	# null
	elif stripped.upper() == "TRUE" or stripped.upper() == "FALSE": pass	# bool
	elif stripped[0] == "{" or stripped[0] == "[":	pass	#json
	else:	# 文字列
		if stripped[0] == '"' and stripped[-1] == '"': pass	# すでにクォートで囲まれている
		else: stripped = f'"{stripped}"'	# クォートで囲まれていないなら囲む

	v_type, v_value = _parse_filter(stripped)
	return {
		"value_type": v_type,
		"value": v_value,
	}

# クエリ文字列を解析して結果を返す
# クエリ文字列は次の様にnode文字列を.（ドット）で連結したものである。
# node_1.node_2...node_N
#
# それぞれのnodeは次の書式である。[カッコ]は省略できることを示す。
# node_N_1[|node_N_2|...|node_N_M][@filter]
#
# 返却値は次の形式のdictを要素とするlistである。
# {
# 	"node_type": "KEY" | "MULTI_KEY" | "ARRAY",
# 	"target": 文字列 | 文字列のリスト,
# 	"filter_type": "JSON" | "REGEX" | "RANGE" | "STRING" |"NUMBER",
# 	"filter": JSONオブジェクト（dictかlist）、文字列、数値
# }
#
# node：キー、複数キー、配列指定のいずれかである。
# 	配列指定：「数値」、「:」、「数値:」、「:数値」を1以上,（コンマ）くぎりで列挙したもの（例：:2,4,6:8,10:）。
# 		node_typeはARRAYにする。
# 		targetはコンマで分割した結果のリストである（例：[":2", "4", "6:8", "10:"]）。要素は全て文字列。
# 	複数キー：配列指定でない文字列を|（バーティカルバー）で連結したもの（例：hoge|fuga|tako）。
# 		node_typeはMULTI_KEYにする。
# 		targetは|で分割した文字列のリストである（例：["hoge", "fuga", "tako"]）。
# 	キー：配列指定でも複数キーでもない文字列（例：some_key）。
# 		nodetypeはKEYにする。
# 		targetは文字列である（例："some_key"）。
#
# filter：@に続いて記述されたJSON文字列か値（文字列、整数、浮動小数点の数値）。
# 	@より後ろから次の.（ドット）まではfilterの指定である。
# 	{"REGEX": "..."}ならfilter_typeはREGEXである。
# 	{"RANGE": "..."}ならfilter_typeはRANGEである。値の書式はnodeの配列指定と同じ。
# 	REGEXでもRANGEでもなく「{」で始まって「}」で終わるか「[」で始まって「]」で終わるならfilter_typeはJSONである。
# 	値が数値ならfilter_typeはNUMBERである。
# 	文字列ならfilter_typeはSTRINGである。文字列は"ダブルクォート"で囲まなければならない。
#
# 	filter_typeがREGEX、RANGE、JSONならfilterにはデコードしたJSONオブジェクトを入れる。
# 	数値か文字列ならその値を入れる。
#
# 	filter_typeがJSON以外のfilterは最後のノードにしか設定できない。
# 	最後のノード以外は子ノードを持つので値（等価な値、正規表現や範囲）として比較できないからである。
#
# 	（備考）
# 	パース処理では気にしなくて良いが、JSONの各値はREGEX、RANGEの指定ができる。
# 	{
# 		"name": {"REGEX": "^[a-zA-Z][a-zA-Z0-9\.=]+[a-zA-Z0-9]$"},
# 		"age": {"RANGE": "20:"},
# 		"sex": "male"
# 	}
#
# 特殊文字の扱い。
# .（ドット）、,（コンマ）、\（バックスラッシュ）、|（バーティカルバー）、@（アットマーク）は特殊文字である。
# "から"は一かたまりの文字列とみなし、この中に現れた特殊文字はそのままの文字として扱う。
# バックスラッシュは"と"に囲まれていない箇所の直後の特殊文字をエスケープする。
# 例えば、「db."ho..ge".:3,5.fu\@ga|tako@{"fld1": "a|a"}」は
# 	[
# 		{"node_type": "KEY", "target": "db"},
# 		{"node_type": "KEY", "target": "ho..ge"},
# 		{"node_type": "ARRAY", "target": [":3", "5"]},
# 		{"node_type": "MULTI_KEY", "target": ["fu@ga", "tako"], "filter_type"="JSON", "filter"={"fld1": "a|a"}}
# 	]
# となる。
def parse_query_string(target: str) -> list[dict]:
	""" クエリ文字列を解析して結果を返す。

	Args：
		node_1.node_2...node_N形式
	"""
	if not target:
		return []

	# --- STEP 1: クエリ全体を、JSONフィルターの内部を保護しながらノードごとに分割する ---
	node_strings = []
	current_node = []

	in_quotes = False
	json_depth = 0

	for char in target:
		if char == '"':
			in_quotes = not in_quotes
			current_node.append(char)
		elif not in_quotes:
			# クォート外のときのみ、JSONのネスト深さをカウント
			if char in ("{", "["):
				json_depth += 1
			elif char in ("}", "]"):
				json_depth -= 1
				if json_depth < 0:
					json_depth = 0

			# クォート外、かつJSONフィルターの外側にあるドットのみを区切り文字とする
			if char == "." and json_depth == 0:
				node_strings.append("".join(current_node))
				current_node = []
				continue

			current_node.append(char)
		else:
			current_node.append(char)

	node_strings.append("".join(current_node))

	# --- STEP 2: 分割された各ノード文字列を個別にパースする ---
	result = []
	for i, node_str in enumerate(node_strings):
		node_info = {}
		is_last_node = i == len(node_strings) - 1

		# 各ノード内の「クォート外の最初の @」を探して分離
		node_body = node_str
		filter_str = None

		iq = False
		filter_index = -1
		for idx, char in enumerate(node_str):
			if char == '"':
				iq = not iq
			elif char == "@" and not iq:
				filter_index = idx
				break

		if filter_index != -1:
			node_body = node_str[:filter_index]
			filter_str = node_str[filter_index + 1 :]

		# ノードタイプの判定 (ARRAY / MULTI_KEY / KEY)
		unescaped_node = _trim_quotes_only(node_body)
		parts = unescaped_node.split(",")
		if all(
			re.match(r"^(\d+|\:|:\d+|\d+:|\d+:\d+)$", p.strip())
			for p in parts
			if p.strip()
		):
			# ここに来た時は配列のスライス表記であることは確定
			node_info["node_type"] = "ARRAY"
			node_info["target"] = [
				_trim_quotes_only(p)
				for p in _split_by_unescaped_char(node_body, ",")
			]
		else:
			multi_keys = _split_by_unescaped_char(node_body, "|")
			if len(multi_keys) > 1:
				node_info["node_type"] = "MULTI_KEY"
				node_info["target"] = [
					_trim_quotes_only(k) for k in multi_keys
				]
			else:
				# ワイルドカードを含むか
				if (node_body[0] != '"' and node_body[-1] != '"') and ("*" in node_body or "?" in node_body):
					node_info["node_type"] = "MULTI_KEY"
					node_info["target"] = unescaped_node
				else:
					node_info["node_type"] = "KEY"
					node_info["target"] = unescaped_node

		# フィルターの解析
		if filter_str is not None:
			f_type, f_val = _parse_filter(filter_str)

			# 仕様チェック: 中間ノードなのにJSON以外のフィルターが指定された場合は例外を投げる
			if not is_last_node and f_type in ("STRING", "NUMBER", "BOOL", "NULL"):
				raise ValueError(
					f"Query parse error: Intermediate node cannot have a primitive filter (NULL, BOOL, NUMBER or STRING).\n"
					f"Node context: '{node_str}'"
				)

			node_info["filter_type"] = f_type
			node_info["filter"] = f_val

		result.append(node_info)

	return result

# クエリ文字列パーサテスト
def test_parse_query_string():
	test_pattern = [
		# 正常系テスト
		'db."ho..ge".:3,5."fu@ga"|tako@{"fld1": "a|a"}',
		'db.object_list.2:3@{"name":{"REGEX":"^a.+:"},"contents": {"fld1":"xxx","fld2":{"RANGE":["2","3:4"]}}}',
		'db.object.str_val@"some string"',  # 文字列はダブルクォート必須
		'db.object.str_val@{"REGEX": "^No\\.\\d+"}',
		"db.object.int_val@100",  # 数値はクォートなしでOK
		'db.object.int_val@{"RANGE": ["1", "3:5", "8:"]}',
		# 異常系テスト（例外が発生することを期待するもの）
		'db.object.str_val@some_string',  # クォートのない不正な文字列 (エラーになるべき)
		'db.object_list.2:3@{"name": "missing_bracket"',  # 閉じカッコ忘れの不正なJSON (エラーになるべき)
	]

	for t in test_pattern:
		print(f"\n--- Input: {t} ---")
		try:
			ret = parse_query_string(t)
			pprint(ret)
		except ValueError as e:
			print(f"【パースエラーを検知（正常な挙動）】:\n{e}")

###############################################################################
# データベース検索
###############################################################################
# 検索結果を表す値
class FoundValue(Enum):
	""" キーが見つからなかった時にNoneを返すと値がnullと区別できないので
	"""
	NotFound = 0

# 配列要素指定を整数のリストにする
def _get_array_nums(targets: list, max_no: int) -> list[int]:
	""" 配列要素指定を整数のリストにする。

	Args:
		targets: 要素指定りスト（例:["1", "3:5", "8:"]）
		max_no: 返却値の最大値

	Returns:
		対象の要素番号のリスト（例：[1, 3, 4, 8, 9, 10]）
	"""
	ret = []

	ptn0 = re.compile(r"^:$")
	ptn1 = re.compile(r"^\d+:\d+$")
	ptn2 = re.compile(r"^\d+:$")
	ptn3 = re.compile(r"^:\d+$")
	ptn4 = re.compile(r"^\d+$")
	for t in targets:
		t = str(t.strip())	# 例外にならない様文字列にする
		if ptn0.match(t):
			ret += [i for i in range(0, max_no)]
			break	# 全件なので後は必要ない
		elif ptn1.match(t):
			(st, ed) = list( map(lambda i: int(i), t.split(":")) )
			if st > max_no: st = max_no
			if ed > max_no: ed = max_no
			if st >= ed: continue
			ret += [i for i in range(st, ed)]
		elif ptn2.match(t):
			st = int(t[:-1])
			if st >= max_no: continue
			ret += [i for i in range(st, max_no)]
		elif ptn3.match(t):
			ed = int(t[1:])
			if ed > max_no: ed = max_no
			ret += [i for i in range(0, ed)]
		elif ptn4.match(t):
			i = int(t)
			if i >= max_no: continue
			ret += [i]

	return list(set(ret))

# 範囲チェック
def _check_range(target_val: int | float ,f_val: list[str]) -> bool:
	""" 範囲フィルタ用に範囲チェックを行う。
	"""
#	_dbg("_check_range(): target_val", target_val)
#	_dbg("_check_range(): f_val", f_val)

	if not isinstance(target_val, (int, float)):
		return False

	ptn1 = re.compile(r"^\d+:\d+$")
	ptn2 = re.compile(r"^\d+:$")
	ptn3 = re.compile(r"^:\d+$")
	ptn4 = re.compile(r"^\d+$")

	ret = False
	for s in f_val:
		s = str(s)	# 例外にならないよう文字列にする
		if s == ":":
			ret = True
			break
		elif ptn1.match(s):
			(m, n) = list( map(lambda i: int(i), s.split(":")) )
			if (m <= target_val) and (target_val < n):
				ret = True
				break
		elif ptn2.match(s):
			m = int(s[:-1])
			if m <= target_val:
				ret = True
				break
		elif ptn3.match(s):
			n = int(s[1:])
			if target_val < n:
				ret = True
				break
		elif ptn4.match(s):
			i = int(s)
			if i == target_val:
				ret = True
				break

	return ret

# 値フィルタチェック
def _evaluate_filter(target_val: any, f_type: str, f_val: any) -> bool:
	"""直下の1つの値がフィルター条件を満たしているかを判定する"""
#	_dbg("_evaluate_filter(): target_val", target_val)
#	_dbg("_evaluate_filter(): f_type", f_type)
#	_dbg("_evaluate_filter(): f_val", f_val)

	# null
	if f_type == "NULL":
		if f_val == "!null":
			return target_val != None
		elif f_val == None:
			return target_val == None
		else:
			logger.info("_evaluate_filter(): bad null filter.")
			dump(f_val)

	if f_type == "IS_NULL":
		if f_val["IS_NULL"]: return target_val == None
		else: return target_val != None

	# null以外の値
	if f_type in ["BOOL", "STRING", "NUMBER", "ARRAY"]:
		return target_val == f_val
	
	if f_type == "REGEX":
		# f_val は {"REGEX": "^a.+"} のような辞書
		pattern = f_val["REGEX"]
		return bool(re.search(pattern, str(target_val)))
		
	if f_type == "RANGE":
		# f_val は {"RANGE": ["1", "3:5"]} のようなリスト
		range_list = f_val["RANGE"]
		return _check_range(target_val, range_list)

	return False

# JSONフィルタチェック
def _match_node_filter(cursor: dict, filter_dict: dict) -> bool:
	"""1階層（直下の子属性）だけをループで回して、すべて満たしているか判定(AND条件)"""
	# filter_dict は {"name": {"REGEX": "^a.+"}, "age": 30} のような構造を想定
	for k, v in filter_dict.items():
		if k not in cursor:
			return False
		
		# v（フィルターの条件）のタイプを判別
		# ※ parse_query_string の _parse_filter と同様のロジックで判定
		if isinstance(v, dict) and "REGEX" in v:
			if not _evaluate_filter(cursor[k], "REGEX", v): return False
		elif isinstance(v, dict) and "RANGE" in v:
			if not _evaluate_filter(cursor[k], "RANGE", v): return False
		elif isinstance(v, dict) and "IS_NULL" in v:
			# IS_NULL: true  -> Nullであるべき (None)
			# IS_NULL: false -> Nullであってはならない (!null)
			f_val = None if v["IS_NULL"] else "!null"
			if not _evaluate_filter(cursor[k], "NULL", f_val): return False
		elif isinstance(v, list):
			if not _evaluate_filter(cursor[k], "ARRAY", v): return False
		elif isinstance(v, bool):
			if not _evaluate_filter(cursor[k], "BOOL", v): return False
		elif isinstance(v, (int, float)):
			if not _evaluate_filter(cursor[k], "NUMBER", v): return False
		elif isinstance(v, str):
			if not _evaluate_filter(cursor[k], "STRING", v): return False
		else:
			# _dbg("_match_node_filter(): cursor", cursor)
			# _dbg("_match_node_filter(): filter", v)
			#if cursor[k] != v: return False	# ネストされた dict/list の場合は、これ以上追わずに等価比較にする（割り切り！）
			return _match_node_filter(cursor[k], v)	# 再起的なフィルタに対応
			
	return True

# 値かJSONかを判断してチェック
def _check_filter(next_cursor: any, filter_type: str, filter: any) -> bool: 
	""" フィルタをチェックする
	Args:
		next_cursor: フィルタ対象のオブジェクト（search_dbのcursorの子）
		filter_type: フィルタ種別
		filter: フィルタ
	Returns:
		Trueならフィルタにかかった。Falseならかからなかった。
	"""
#	_dbg("next_cursor", next_cursor)
#	_dbg("filter_type", filter_type)
#	_dbg("filter", filter)
	if filter_type == "JSON":
		return _match_node_filter(next_cursor, filter)
	elif filter_type in ["NUMBER", "STRING", "BOOL", "NULL", "IS_NULL", "RANGE", "REGEX", "ARRAY"]:
		return _evaluate_filter(next_cursor, filter_type, filter)
	
	return False

# キーが正しい値かどうかを調べる
def _is_valid_key(target: str, cursor: dict) -> bool:
	""" targetが文字列でcursorに存在するかを調べる。
	正しければtrue、正しくなければfalseを返す。
	"""
	if not isinstance(target, str):
		logger.info("search_db(): keys is not string.")
		dump(logger, "target", target)
		return False

	if not target in cursor:
		logger.info(f"search_db(): no target {target}.")
		dump(logger, "cursor", cursor)
		return False

	return True

# MULTI_KEYの対象ノード名がシェルのワイルドカードを含む場合を考慮してtargetのリストを整形する
def list_targets(target: str | list, cursor: dict| list) -> list[str]:
	""" MULTI_KEYの対象ノード名がシェルのワイルドカードを含む場合を考慮してtargetのリストを整形する
	
	Args:
		target: 検索対象のキーのリストか文字列
		cursor: 検索対象のノード

	Returns:
		ワイルドカードを持たない検索対象キーのリスト
	"""
	# 配列にする
	if isinstance(target, str):
		targets = [target]
	else:
		targets = target

	ret = []
	for key in cursor:
		for t in targets:
			if fnmatch.fnmatch(key, t):
				if not key in ret:
					ret.append(key)

	return ret

# DBの検索
def search_db(cursor: dict| list, path: list) -> None | bool | int | float | str | list | dict | FoundValue:
	""" pathに従ってdbを再起的に検索する。

	Args:
		cursor: データベースの現在の参照位置
		path: パスのリスト

	Returns:
		見つかったらその値のオブジェクトか値。
		見つからなかったらFoundValue.NotFound。
	"""
#	_dbg("search_db() path", path)
#	_dbg("search_db() cursor", cursor)
	if len(path) == 0:
		return cursor
	else:
		if not isinstance(cursor, (list, dict)):
			logger.info(f"search_db(): no much child node")
			dump(logger, "cursor", cursor)
			return FoundValue.NotFound
	
	nexts = path.pop(0)	# 次の検索バス

	if (nexts["node_type"] == "ARRAY") and isinstance(cursor, list):
		max_no = len(cursor)
		items = _get_array_nums(nexts["target"], max_no)
		ret = []
		for i in items:
			if "filter" in nexts:
				if not _check_filter(cursor[i], nexts["filter_type"], nexts["filter"]):
					continue

			r = search_db(cursor[i], copy.deepcopy(path))
			if r != FoundValue.NotFound: ret.append(r)
		return ret
	elif (nexts["node_type"] == "MULTI_KEY") and isinstance(cursor, dict):
		targets = list_targets(nexts["target"], cursor)	# ワイルドカードを展開
		ret = []
		for n in targets:
			if not _is_valid_key(n, cursor): continue

			if "filter" in nexts:
				if not _check_filter(cursor[n], nexts["filter_type"], nexts["filter"]):
					continue

			r = search_db(cursor[n], copy.deepcopy(path))
			if r != FoundValue.NotFound: ret.append(r)
		return ret
	else:
		target = nexts["target"]
		if not _is_valid_key(target, cursor): return FoundValue.NotFound

		if "filter" in nexts:
			if not _check_filter(cursor[target], nexts["filter_type"], nexts["filter"]):
				return FoundValue.NotFound

		return search_db(cursor[target], path)

# DBの検索のテスト
def test_search_db():
	global PRIVATE_DEBUG
	PRIVATE_DEBUG = True

	db = {
		"name": "sample db",
		"int_val": 1,
		"float_val": 1.1,
		"string_val": "hoge",
		"array": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
		"object": {
			"hoge": "hoge",
			"fuga": "fuga"
		},
		"object2": {
			"aaa": {
				"xxx": 1,
				"yyy": "aaa"
			},
			"bbb": {
				"xxx": 2,
				"yyy": "bbb"
			},
			"ccc": {
				"xxx": 3,
				"yyy": "ccc"
			}
		},
		"object_array": [
			{"fld1": "aaa", "fld2": 111, "flg3": "AAA"},
			{"fld1": "bbb", "fld2": 222, "flg3": "BBB"},
			{"fld1": "ccc", "fld2": 333, "flg3": "CCC"}
		]
	}

	test_pattern = [
		[{"node_type": "KEY", "target": "name"}],
		[{"node_type": "KEY", "target": "array"}],
		[{"node_type": "KEY", "target": "object"}],
		[
			{"node_type": "KEY", "target": "object"},
			{"node_type": "KEY", "target": "fuga"},
		],
		[
			{"node_type": "KEY", "target": "object2"},
			{"node_type": "MULTI_KEY", "target": ["bbb", "ccc"]},
		],
		[
			{"node_type": "KEY", "target": "array"},
			{"node_type": "ARRAY", "target": ["1", "2:4", "7"]},
		],
		[
			{"node_type": "KEY", "target": "object_array"},
			{"node_type": "ARRAY", "target": ["1", "2"]},
		],
		[
			{"node_type": "KEY", "target": "object_array"},
			{"node_type": "ARRAY", "target": [":2"]},
			{"node_type": "KEY", "target": "fld2"},
		],
		[
			{"node_type": "KEY", "target": "object"},
			{"node_type": "KEY", "target": "fuga", "filter": "fuga", "filter_type": "STRING"},
		],
		[
			{"node_type": "KEY", "target": "object"},
			{"node_type": "KEY", "target": "fuga", "filter": {"REGEX": "f..a"}, "filter_type": "REGEX"},
		],
		[
		 	{"node_type": "KEY", "target": "object"},
		 	{"node_type": "KEY", "target": "fuga", "filter": 100, "filter_type": "NUMBER"},
		],
		[
			{"node_type": "KEY", "target": "object_array"},
			{"node_type": "ARRAY", "target": [":"], "filter": {"fld2": {"RANGE": ["100:200"]}}, "filter_type": "JSON" },
		],
		[
			{"node_type": "KEY", "target": "name", "filter": "sample.db", "filter_type": "STRING"},
		],
		[
			{"node_type": "KEY", "target": "object2"},
			{"node_type": "MULTI_KEY", "target": ["bbb", "ccc"], "filter": {"xxx": 3}, "filter_type": "JSON"},
		],
		[
			{"node_type": "KEY", "target": "object2"},
			{"node_type": "MULTI_KEY", "target": "*"},
		],
		[
			{"node_type": "KEY", "target": "object2"},
			{"node_type": "KEY", "target": "*"},
		],
	]

	for t in test_pattern:
		ret = search_db(db, t)
		print(f"{ret}")

###############################################################################
# テスト用main
###############################################################################
if __name__ == "__main__":
#	test_parse_query_string()
#	test_parse_list_items()
	test_search_db()
#	print(tmp_path())
	pass