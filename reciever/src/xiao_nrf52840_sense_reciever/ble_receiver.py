"""
XIAO nRF52840 Sense (NUS 互換) から BLE 経由で CSV テレメトリを受信するユーティリティ。

機能:
- 指定名/UUID でデバイスをスキャン
- Notify (TX) を購読し、断片を改行で組み立て
- 各行を CSV パースして dict に変換
- 任意で CSV のまま標準出力へ書き出し

要件: bleak
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterator, Callable, Iterable, Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError


# NUS UUID 定数
NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_CHAR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify
NUS_RX_CHAR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write (unused)


DEVICE_NAME = "XIAO Sense IMU"


@dataclass(frozen=True)
class ImuRow:
    millis: int
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float
    tempC: float
    audioRMS: float

    @staticmethod
    def parse_csv(line: str) -> "ImuRow":
        # 受信は「, 」が基本だが空白有無に寛容にする
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 9:
            raise ValueError(f"Unexpected CSV fields count: {len(parts)} in '{line}'")

        millis = int(parts[0])
        ax, ay, az = float(parts[1]), float(parts[2]), float(parts[3])
        gx, gy, gz = float(parts[4]), float(parts[5]), float(parts[6])
        tempC = float(parts[7])
        audioRMS = float(parts[8])
        return ImuRow(
            millis=millis,
            ax=ax,
            ay=ay,
            az=az,
            gx=gx,
            gy=gy,
            gz=gz,
            tempC=tempC,
            audioRMS=audioRMS,
        )


@dataclass
class BufferStats:
    """Statistics about the data buffer."""

    fill_level: int = 0
    sample_rate: float = 0.0
    last_update: float = 0.0

    def update(self, row: ImuRow) -> None:
        """Update statistics with new data."""
        current_time = time.time()
        if self.last_update > 0:
            time_diff = current_time - self.last_update
            if time_diff > 0:
                self.sample_rate = 1.0 / time_diff
        self.last_update = current_time


class DataBuffer:
    """Thread-safe circular buffer for IMU data."""

    def __init__(self, max_size: int = 1000):
        self._max_size = max_size
        self._buffer: deque[ImuRow] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._stats = BufferStats()

    def append(self, row: ImuRow) -> None:
        """Add a new data row to the buffer."""
        with self._lock:
            self._buffer.append(row)
            self._stats.fill_level = len(self._buffer)
            self._stats.update(row)

    def get_recent(self, count: int) -> list[ImuRow]:
        """Get the most recent N data points."""
        with self._lock:
            return (
                list(self._buffer)[-count:]
                if count <= len(self._buffer)
                else list(self._buffer)
            )

    def get_all(self) -> list[ImuRow]:
        """Get all data points in the buffer."""
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        """Clear all data from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._stats.fill_level = 0

    @property
    def stats(self) -> BufferStats:
        """Get buffer statistics."""
        with self._lock:
            return self._stats

    @property
    def size(self) -> int:
        """Get current buffer size."""
        with self._lock:
            return len(self._buffer)

    @property
    def max_size(self) -> int:
        """Get maximum buffer size."""
        return self._max_size


class DataSource(ABC):
    """Abstract base class for data sources."""

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if the data source is connected."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start the data source."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the data source."""
        pass

    @abstractmethod
    def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Get an async generator that yields IMU data rows."""
        pass


class BleDataSource(DataSource):
    """BLE data source adapter for existing BLE receiver with enhanced stability."""

    def __init__(self, scan_timeout: float = 15.0, idle_timeout: float = 30.0) -> None:
        self._connected = False
        self._scan_timeout = scan_timeout
        self._idle_timeout = idle_timeout
        self._connection_attempts = 0
        self._last_data_time = 0.0

    async def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._connected = True

    async def stop(self) -> None:
        self._connected = False

    async def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Get BLE data stream with enhanced stability and monitoring."""
        import logging
        import time

        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)

        self._connected = True
        self._connection_attempts += 1

        try:
            logger.info(
                f"🔍 Scanning for XIAO Sense IMU device (attempt {self._connection_attempts})..."
            )
            logger.info(
                f"⚙️ Scan timeout: {self._scan_timeout}s, Idle timeout: {self._idle_timeout}s"
            )

            data_count = 0
            last_log_time = time.time()
            connection_start = time.time()

            async for row in stream_rows(
                scan_timeout=self._scan_timeout, idle_timeout=self._idle_timeout
            ):
                if not self._connected:
                    logger.info("🛑 Connection manually stopped")
                    break

                current_time = time.time()
                self._last_data_time = current_time
                data_count += 1

                # Log connection health every 10 seconds
                if current_time - last_log_time > 10.0:
                    connection_duration = current_time - connection_start
                    avg_rate = (
                        data_count / connection_duration
                        if connection_duration > 0
                        else 0
                    )
                    logger.info(
                        f"📊 Connection healthy: {data_count} samples, {avg_rate:.1f}Hz avg"
                    )
                    last_log_time = current_time

                yield row

        except KeyboardInterrupt:
            logger.info("🛑 BLE stream interrupted by user")
            self._connected = False
            raise
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"❌ BLE stream error: {error_msg}")

            # Classify error types for better debugging
            if "was not found" in str(e) or "No such device" in str(e):
                logger.error(
                    "🔍 Device not found - check if XIAO is powered on and advertising"
                )
            elif "Connection failed" in str(e) or "timeout" in str(e).lower():
                logger.error("⏱️ Connection timeout - device may be out of range")
            elif "was disconnected" in str(e) or "disconnected" in str(e).lower():
                logger.error(
                    "🔌 Device disconnected - connection lost during operation"
                )

            self._connected = False
            raise
        finally:
            connection_duration = (
                time.time() - connection_start if "connection_start" in locals() else 0
            )
            logger.info(
                f"🔌 BLE data stream disconnected after {connection_duration:.1f}s"
            )
            self._connected = False


class MockDataSource(DataSource):
    """Mock data source for testing and development."""

    def __init__(self, update_interval: float = 0.04):  # 25Hz
        self._connected = False
        self._running = False
        self._update_interval = update_interval
        self._start_time = time.time()

    async def is_connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._connected = True
        self._running = True
        self._start_time = time.time()

    async def stop(self) -> None:
        self._connected = False
        self._running = False

    async def get_data_stream(self) -> AsyncGenerator[ImuRow, None]:
        """Generate mock IMU data."""
        self._connected = True
        self._running = True

        try:
            counter = 0
            while self._running:
                current_time = time.time()
                elapsed = current_time - self._start_time

                # Generate sinusoidal data with some noise
                ax = 0.5 * math.sin(2 * math.pi * 0.5 * elapsed) + random.gauss(0, 0.1)
                ay = 0.3 * math.cos(2 * math.pi * 0.3 * elapsed) + random.gauss(0, 0.1)
                az = (
                    1.0
                    + 0.2 * math.sin(2 * math.pi * 0.1 * elapsed)
                    + random.gauss(0, 0.05)
                )

                gx = 10.0 * math.sin(2 * math.pi * 0.8 * elapsed) + random.gauss(0, 2.0)
                gy = 15.0 * math.cos(2 * math.pi * 0.6 * elapsed) + random.gauss(0, 2.0)
                gz = 5.0 * math.sin(2 * math.pi * 0.4 * elapsed) + random.gauss(0, 1.0)

                tempC = (
                    25.0
                    + 3.0 * math.sin(2 * math.pi * 0.01 * elapsed)
                    + random.gauss(0, 0.5)
                )

                # Audio RMS with some random dropouts (-1 indicates missing data)
                if random.random() > 0.1:  # 90% data availability
                    audioRMS = abs(
                        1000.0 * math.sin(2 * math.pi * 2.0 * elapsed)
                    ) + random.gauss(0, 50.0)
                else:
                    audioRMS = -1.0

                millis = int(elapsed * 1000)

                row = ImuRow(
                    millis=millis,
                    ax=ax,
                    ay=ay,
                    az=az,
                    gx=gx,
                    gy=gy,
                    gz=gz,
                    tempC=tempC,
                    audioRMS=audioRMS,
                )

                yield row
                counter += 1

                await asyncio.sleep(self._update_interval)

        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False
            self._running = False


logger = logging.getLogger(__name__)


async def _scan_ble_devices(
    timeout: float,
) -> dict[str, tuple[BLEDevice, AdvertisementData]]:
    """BLEデバイスをスキャンして広告データを取得。"""
    try:
        # bleak 0.22+ では BLEDevice に metadata が無い。
        # 広告データを得るため return_adv=True を指定して取得する。
        devices_adv = await BleakScanner.discover(timeout=timeout, return_adv=True)
        logger.debug("スキャン結果件数: %d", len(devices_adv))
        return devices_adv
    except BleakError as e:
        raise RuntimeError(
            "BLE スキャナの起動に失敗しました。以下を確認してください:\n"
            "- Windows の『Bluetooth』がオン\n"
            "- Windows の『位置情報サービス』がオン（BLE スキャンに必要）\n"
            "- 仮想環境/WSL ではないこと（Windows ネイティブで実行）\n"
            "- リモートデスクトップ接続では一部環境でスキャン不可\n"
            "- Bluetooth アダプタ/ドライバが正しく認識\n"
        ) from e


def _match_device(
    dev: BLEDevice, adv: AdvertisementData, device_name: str, service_uuid: str
) -> bool:
    """デバイスが条件に一致するかチェック。"""
    logger.debug(
        "検出: addr=%s name=%s rssi=%s uuids=%s",
        getattr(dev, "address", "?"),
        getattr(dev, "name", None),
        getattr(adv, "rssi", None),
        getattr(adv, "service_uuids", None),
    )

    # 名称優先
    if dev.name == device_name:
        logger.info("デバイス名一致で選択: %s (%s)", dev.name, dev.address)
        return True

    # Service UUID による一致も許容
    uuids: Iterable[str] = adv.service_uuids or []
    if any(u.lower() == service_uuid.lower() for u in uuids):
        logger.info("Service UUID一致で選択: %s (%s)", dev.name, dev.address)
        return True

    return False


async def find_device(
    *,
    device_name: str = DEVICE_NAME,
    service_uuid: str = NUS_SERVICE,
    timeout: float = 10.0,
) -> Optional[BLEDevice]:
    """指定条件で BLE デバイスをスキャンし、最初に見つかったものを返す。"""
    logger.info(
        "BLE スキャン開始: name='%s' service='%s' timeout=%.1fs",
        device_name,
        service_uuid,
        timeout,
    )

    devices_adv = await _scan_ble_devices(timeout)

    # devices_adv: dict[address, (BLEDevice, AdvertisementData)]
    for dev, adv in devices_adv.values():
        if _match_device(dev, adv, device_name, service_uuid):
            return dev
    return None


def _parse_line_from_buffer(
    buffer: bytearray, debug_hex_dumped: dict[str, bool]
) -> Optional[str]:
    """バッファから1行を抽出する。戻り値がNoneの場合は行が完成していない。"""
    delim_map = [
        (b"\n", "LF"),
        (b"\r", "CR"),
        (b"\x00", "NUL"),
        (b"\x1e", "RS"),
        (b"\x1f", "US"),
        (b"\x1d", "GS"),
        (b"\x03", "ETX"),
        (b"\x04", "EOT"),
    ]
    candidates = []
    for token, name in delim_map:
        idx = buffer.find(token)
        if idx != -1:
            candidates.append((idx, token, name))

    if not candidates:
        # まだ行になっていない
        if len(buffer) > 0:
            logger.debug("バッファ蓄積: %d bytes (行未確定)", len(buffer))
            # 一度だけHEX/ASCIIプレビューを出して、未知の区切りや制御文字の存在を可視化
            if not debug_hex_dumped["dumped"] and len(buffer) >= 256:
                _log_buffer_preview(buffer)
                debug_hex_dumped["dumped"] = True
            # バッファ暴走防止のソフトガード（64KB超で先頭を少し捨てる）
            if len(buffer) > 64 * 1024:
                drop = len(buffer) - 64 * 1024
                logger.warning(
                    "区切り未検出でバッファ肥大のため %d bytes を切り詰め", drop
                )
                del buffer[:drop]
        return None

    # 最も早く現れた区切り
    idx, token, token_name = min(candidates, key=lambda t: t[0])
    # CRLF は 2 文字消費、それ以外は 1 文字
    consume = 1
    delim_name = token_name
    if token == b"\r" and idx + 1 < len(buffer) and buffer[idx + 1 : idx + 2] == b"\n":
        consume = 2
        delim_name = "CRLF"

    # 1 行取り出し（末尾の CR は落とす）
    line = buffer[:idx].rstrip(b"\r")
    del buffer[: idx + consume]

    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        logger.error("UTF-8 デコード失敗: %r", line)
        return None

    # 空白とカンマのみの行や空行はノイズとして破棄
    if text.strip() == "" or text.replace(",", "").strip() == "":
        logger.debug("ノイズ行をスキップ: %r", text)
        return None

    logger.debug("行確定(区切り=%s): %s", delim_name, text)
    return text


def _log_buffer_preview(buffer: bytearray) -> None:
    """バッファの内容をHEX/ASCII形式でプレビューログ出力。"""
    # バッファ内に存在する制御バイト(<0x20)の種類を一覧表示
    ctrl_set = sorted(set(b for b in buffer if b < 0x20))
    if ctrl_set:
        logger.debug(
            "制御バイト存在: %s",
            " ".join(f"{b:02X}" for b in ctrl_set),
        )

    head = bytes(buffer[:32])
    tail = bytes(buffer[-32:]) if len(buffer) > 32 else b""

    def hex_str(bs: bytes) -> str:
        return " ".join(f"{b:02X}" for b in bs)

    def ascii_str(bs: bytes) -> str:
        return "".join(chr(b) if 32 <= b < 127 else "." for b in bs)

    logger.debug("HEXプレビュー(head): %s | ASCII: %s", hex_str(head), ascii_str(head))
    if tail:
        logger.debug(
            "HEXプレビュー(tail): %s | ASCII: %s", hex_str(tail), ascii_str(tail)
        )


def _create_notification_handler(
    queue: asyncio.Queue[Optional[str]],
    buffer: bytearray,
    debug_hex_dumped: dict[str, bool],
    disconnected: asyncio.Event,
) -> Callable[[bytearray], None]:
    """通知データを処理するハンドラーを作成。"""

    def wake_consumer() -> None:
        try:
            queue.put_nowait(None)
        except Exception:
            pass

    def handle(data: bytearray) -> None:
        logger.debug("Notify 受信: %d bytes", len(data))
        buffer.extend(data)

        # 改行区切りで行に切る
        while True:
            text = _parse_line_from_buffer(buffer, debug_hex_dumped)
            if text is None:
                break
            queue.put_nowait(text)

        # 受信が断続的に途絶えた場合に備え、切断時は consumer を起こす
        if disconnected.is_set():
            wake_consumer()

    return handle


async def _get_device_address(
    address: Optional[str], device_name: str, service_uuid: str, scan_timeout: float
) -> str:
    """デバイスアドレスを取得（スキャンまたは直接指定）。"""
    if address is not None:
        return address

    dev = await find_device(
        device_name=device_name, service_uuid=service_uuid, timeout=scan_timeout
    )
    if not dev:
        raise RuntimeError(
            "対象デバイスが見つかりませんでした。スキャン条件や距離を確認してください。"
        )

    logger.info("接続先アドレス: %s (name=%s)", dev.address, getattr(dev, "name", None))
    return dev.address


async def _process_message_queue(
    queue: asyncio.Queue[Optional[str]],
    idle_timeout: Optional[float],
    disconnected: asyncio.Event,
    client: BleakClient,
) -> AsyncIterator[ImuRow]:
    """キューからメッセージを処理してImuRowをyieldする。"""
    while True:
        # アイドルタイムアウトが設定されていれば待機に制限をかける
        if idle_timeout is not None:
            try:
                logger.debug("キュー待ち（timeout=%.1fs）", idle_timeout)
                line = await asyncio.wait_for(queue.get(), timeout=idle_timeout)
                logger.debug("キュー取得: %r", line)
            except asyncio.TimeoutError:
                # タイムアウト。接続が切れていれば終了、そうでなければ継続待機。
                logger.warning("受信タイムアウト (%.1fs)", idle_timeout)
                if disconnected.is_set() or not client.is_connected:
                    raise RuntimeError("BLE が切断されました。")
                else:
                    continue
        else:
            logger.debug("キュー待ち（無期限）")
            line = await queue.get()
            logger.debug("キュー取得: %r", line)

        if line is None:
            # 切断センチネル
            raise RuntimeError("BLE が切断されました。")
        if not line:
            logger.debug("空行をスキップ")
            continue

        try:
            row = ImuRow.parse_csv(line)
            yield row
        except Exception as ex:
            # 変換失敗はスキップ（ログで記録）
            logger.warning("CSV 解析失敗: %s (err=%s)", line, ex)
            continue


async def stream_rows(
    address: Optional[str] = None,
    *,
    device_name: str = DEVICE_NAME,
    service_uuid: str = NUS_SERVICE,
    tx_char_uuid: str = NUS_TX_CHAR,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> AsyncIterator[ImuRow]:
    """XIAO の Notify を購読し、組み立てた CSV 行を ImuRow でストリームする。"""

    address = await _get_device_address(
        address, device_name, service_uuid, scan_timeout
    )

    buffer = bytearray()
    # デバッグ用: 区切り未検出でバッファが肥大したとき、一度だけHEXプレビューを出す
    debug_hex_dumped = {"dumped": False}

    # 切断通知コールバック
    disconnected = asyncio.Event()

    def on_disconnect(_client: BleakClient) -> None:
        logger.warning("BLE が切断されました（コールバック）")
        disconnected.set()

    logger.info("BLE 接続開始: %s", address)
    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        if not client.is_connected:
            raise RuntimeError("BLE 接続に失敗しました。")
        logger.info("BLE 接続完了: %s", address)

        # データ行を受け取るキュー。切断時は None を流して終了を知らせる。
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

        handle = _create_notification_handler(
            queue, buffer, debug_hex_dumped, disconnected
        )

        logger.info("Notify 購読開始: char=%s", tx_char_uuid)
        await client.start_notify(tx_char_uuid, lambda _, data: handle(data))

        try:
            async for row in _process_message_queue(
                queue, idle_timeout, disconnected, client
            ):
                yield row
        finally:
            logger.info("Notify 購読停止")
            await client.stop_notify(tx_char_uuid)


async def print_stream(
    address: Optional[str] = None,
    *,
    show_header: bool = True,
    drop_missing_audio: bool = False,
    device_name: str = DEVICE_NAME,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> None:
    """受信行を CSV として標準出力へ流すヘルパー。"""
    if show_header:
        logger.info("CSV header: millis,ax,ay,az,gx,gy,gz,tempC,audioRMS")
        print("millis,ax,ay,az,gx,gy,gz,tempC,audioRMS")
    async for r in stream_rows(
        address,
        device_name=device_name,
        scan_timeout=scan_timeout,
        idle_timeout=idle_timeout,
    ):
        if drop_missing_audio and r.audioRMS < 0:
            logger.debug("audioRMS 欠損のためスキップ: millis=%d", r.millis)
            continue
        # 受信は自由フォーマットだが、こちらの出力は安定化しておく
        csv_line = f"{r.millis},{r.ax:.6f},{r.ay:.6f},{r.az:.6f},{r.gx:.6f},{r.gy:.6f},{r.gz:.6f},{r.tempC:.2f},{r.audioRMS:.2f}"
        logger.debug("CSV output: %s", csv_line)
        print(csv_line)


def run(
    address: Optional[str] = None,
    show_header: bool = True,
    drop_missing_audio: bool = False,
    device_name: str = DEVICE_NAME,
    scan_timeout: float = 10.0,
    idle_timeout: Optional[float] = None,
) -> int:
    """同期関数ラッパー。スクリプト/CLI から利用。終了コードを返す。

    戻り値:
        0: 正常に開始し、ユーザー終了（通常は Ctrl+C）
        1: エラー終了（スキャン/接続失敗など）
        130: Ctrl+C による中断
    """
    try:
        asyncio.run(
            print_stream(
                address,
                show_header=show_header,
                drop_missing_audio=drop_missing_audio,
                device_name=device_name,
                scan_timeout=scan_timeout,
                idle_timeout=idle_timeout,
            )
        )
        return 0
    except KeyboardInterrupt:
        # SIGINT: 慣例で 130 を返す
        return 130
    except Exception as e:
        logger.exception("致命的エラー: %s", e)
        return 1
