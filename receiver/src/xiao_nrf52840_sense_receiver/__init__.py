from __future__ import annotations

import argparse
import logging
import sys

from .ble_receiver import run

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="xiao-nrf52840-sense-receiver",
        description="XIAO nRF52840 Sense から BLE (NUS) 経由で CSV テレメトリを受信してオシロスコープ表示、またはCSVを標準出力へ流します。",
    )
    parser.add_argument(
        "--address", help="接続するデバイスの BLE アドレス （未指定で自動検出)"
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
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="オシロスコープサーバーポート（既定: 8050）",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="テスト用のMockデータを使用（BLEデバイス不要）",
    )

    # CSV出力モードのオプション（デフォルトはオシロスコープ）
    parser.add_argument(
        "--csv",
        action="store_true",
        help="CSV出力モード（標準出力へCSVを流す）",
    )
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="先頭にヘッダ行を出力しない（CSV出力モード時のみ有効）",
    )
    parser.add_argument(
        "--drop-missing-audio",
        action="store_true",
        help="audioRMS=-1.0 の行を除外（CSV出力モード時のみ有効）",
    )

    args = parser.parse_args()

    # ロギング初期化（CSV出力時はstdout、ログはstderr/ファイルへ）
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

    if args.csv:
        # CSV出力モード
        code = run(
            address=args.address,
            show_header=not args.no_header,
            drop_missing_audio=args.drop_missing_audio,
            device_name=args.device_name,
            scan_timeout=args.scan_timeout,
            idle_timeout=args.idle_timeout,
        )
        raise SystemExit(code)
    else:
        # デフォルト: オシロスコープモード
        from .oscilloscope import create_app
        from .ble_receiver import BleDataSource, MockDataSource

        logger.info("🔧 XIAO nRF52840 Sense - Oscilloscope")
        logger.info("=" * 50)
        logger.info("🌐 Starting web interface...")
        logger.info("📊 BLE connection will take 10-15 seconds to establish")
        logger.info("⏱️ Please be patient while connecting to device...")
        logger.info(f"🔍 Open http://localhost:{args.port} in your browser")
        logger.info("=" * 50)

        # データソースの選択
        from .ble_receiver import DataSource

        data_source: DataSource
        if args.mock:
            logger.info("🔧 Using mock data for testing (no BLE device required)")
            data_source = MockDataSource()
        else:
            # BLE接続を試行、失敗時は明確にエラー終了
            if args.address:
                logger.info(f"🔍 Connecting to specific BLE address: {args.address}")
            else:
                logger.info("🔍 Attempting to connect to BLE device...")
                logger.info("💡 Make sure XIAO Sense IMU is powered on and advertising")

            try:
                data_source = BleDataSource(
                    scan_timeout=args.scan_timeout, idle_timeout=args.idle_timeout
                )
            except Exception as e:
                logger.error(f"❌ Failed to connect to BLE device: {e}")
                logger.info("💡 Troubleshooting tips:")
                logger.info("   - Check if XIAO device is powered on")
                logger.info("   - Verify device is advertising as 'XIAO Sense IMU'")
                logger.info("   - Move device closer to reduce interference")
                logger.info("   - Check Bluetooth is enabled on this computer")
                logger.info("   - Try restarting the device and try again")
                logger.info("   - Use --mock option for testing without device")
                raise SystemExit(1)

        # アプリを作成して起動
        try:
            app = create_app(data_source=data_source)
            app.start_data_collection()

            try:
                app.app.run(debug=False, host="0.0.0.0", port=args.port)
            except KeyboardInterrupt:
                logger.info("\n🛑 Shutting down oscilloscope...")
            finally:
                logger.info("🛑 Stopping data collection...")
                app.stop_data_collection()
                logger.info("🏁 Oscilloscope stopped")

        except Exception as e:
            logger.error(f"❌ Failed to start oscilloscope: {e}")
            raise SystemExit(1)
