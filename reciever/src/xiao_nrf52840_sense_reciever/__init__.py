from __future__ import annotations

import argparse
import logging
import sys

from .ble_receiver import run


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="xiao-nrf52840-sense-reciever",
        description="XIAO nRF52840 Sense から BLE (NUS) 経由で CSV テレメトリを受信して標準出力へ流します。",
    )
    parser.add_argument(
        "--address", help="接続するデバイスの BLE アドレス (未指定で自動検出)"
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="先頭にヘッダ行を出力しない",
    )
    parser.add_argument(
        "--drop-missing-audio",
        action="store_true",
        help="audioRMS=-1.0 の行を除外",
    )
    parser.add_argument(
        "--device-name",
        default="XIAO Sense IMU",
        help="スキャンで優先的に探すデバイス名",
    )
    parser.add_argument(
        "--scan-timeout",
        type=float,
        default=10.0,
        help="スキャンのタイムアウト秒数",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help="受信が一定秒数途絶えたらエラー終了（未指定で無制限）",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=[
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
            "NOTSET",
        ],
        help="ログレベル（既定: WARNING）",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="ログをファイルにも出力（既定: 標準エラーのみ）",
    )

    args = parser.parse_args()

    # ロギング初期化（CSVはstdout、ログはstderr/ファイルへ）
    level = getattr(logging, str(args.log_level).upper(), logging.WARNING)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, encoding="utf-8")
            handlers.append(file_handler)
        except Exception:
            # ファイルハンドラに失敗しても実行は継続（stderrにだけ出す）
            pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,  # 他のbasicConfigに影響されないよう強制
    )

    code = run(
        address=args.address,
        show_header=not args.no_header,
        drop_missing_audio=args.drop_missing_audio,
        device_name=args.device_name,
        scan_timeout=args.scan_timeout,
        idle_timeout=args.idle_timeout,
    )
    raise SystemExit(code)
