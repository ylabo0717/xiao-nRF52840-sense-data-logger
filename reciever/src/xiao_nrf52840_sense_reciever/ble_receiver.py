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
from dataclasses import dataclass
import logging
import sys
from typing import AsyncIterator, Iterable, Optional

from bleak import BleakClient, BleakScanner
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


logger = logging.getLogger(__name__)


async def find_device(
    *,
    device_name: str = DEVICE_NAME,
    service_uuid: str = NUS_SERVICE,
    timeout: float = 10.0,
):
    """指定条件で BLE デバイスをスキャンし、最初に見つかったものを返す。"""
    logger.info("BLE スキャン開始: name='%s' service='%s' timeout=%.1fs", device_name, service_uuid, timeout)
    try:
        # bleak 0.22+ では BLEDevice に metadata が無い。
        # 広告データを得るため return_adv=True を指定して取得する。
        devices_adv = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except BleakError as e:
        raise RuntimeError(
            "BLE スキャナの起動に失敗しました。以下を確認してください:\n"
            "- Windows の『Bluetooth』がオン\n"
            "- Windows の『位置情報サービス』がオン（BLE スキャンに必要）\n"
            "- 仮想環境/WSL ではないこと（Windows ネイティブで実行）\n"
            "- リモートデスクトップ接続では一部環境でスキャン不可\n"
            "- Bluetooth アダプタ/ドライバが正しく認識\n"
        ) from e
    # devices_adv: dict[address, (BLEDevice, AdvertisementData)]
    logger.debug("スキャン結果件数: %d", len(devices_adv))
    for dev, adv in devices_adv.values():
        # 名称優先
        logger.debug("検出: addr=%s name=%s rssi=%s uuids=%s", getattr(dev, "address", "?"), getattr(dev, "name", None), getattr(adv, "rssi", None), getattr(adv, "service_uuids", None))
        if dev.name == device_name:
            logger.info("デバイス名一致で選択: %s (%s)", dev.name, dev.address)
            return dev
        # Service UUID による一致も許容
        uuids: Iterable[str] = (adv.service_uuids or [])
        if any(u.lower() == service_uuid.lower() for u in uuids):
            logger.info("Service UUID一致で選択: %s (%s)", dev.name, dev.address)
            return dev
    return None


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

    if address is None:
        dev = await find_device(
            device_name=device_name, service_uuid=service_uuid, timeout=scan_timeout
        )
        if not dev:
            raise RuntimeError(
                "対象デバイスが見つかりませんでした。スキャン条件や距離を確認してください。"
            )
        address = dev.address
        logger.info("接続先アドレス: %s (name=%s)", address, getattr(dev, "name", None))

    buffer = bytearray()
    # デバッグ用: 区切り未検出でバッファが肥大したとき、一度だけHEXプレビューを出す
    debug_hex_dumped = False

    # 切断通知コールバック
    disconnected = asyncio.Event()

    def on_disconnect(_client: BleakClient):
        logger.warning("BLE が切断されました（コールバック）")
        disconnected.set()

    logger.info("BLE 接続開始: %s", address)
    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        if not client.is_connected:
            raise RuntimeError("BLE 接続に失敗しました。")
        logger.info("BLE 接続完了: %s", address)

        # データ行を受け取るキュー。切断時は None を流して終了を知らせる。
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        # 待機中の consumer を起こすためのヘルパー
        def wake_consumer():
            try:
                queue.put_nowait(None)
            except Exception:
                pass

        def handle(data: bytearray):
            nonlocal buffer, debug_hex_dumped
            logger.debug("Notify 受信: %d bytes", len(data))
            buffer.extend(data)
            # 改行区切りで行に切る。LF(\n)/CR(\r)/CRLF/NUL(\x00)に加え、
            # 一般的なレコード/ユニットセパレータ RS(0x1E)/US(0x1F)、GS(0x1D)、
            # 制御系では ETX(0x03)/EOT(0x04) も候補に含める。
            while True:
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
                        if not debug_hex_dumped and len(buffer) >= 256:
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
                            logger.debug(
                                "HEXプレビュー(head): %s | ASCII: %s",
                                hex_str(head), ascii_str(head)
                            )
                            if tail:
                                logger.debug(
                                    "HEXプレビュー(tail): %s | ASCII: %s",
                                    hex_str(tail), ascii_str(tail)
                                )
                            debug_hex_dumped = True
                        # バッファ暴走防止のソフトガード（64KB超で先頭を少し捨てる）
                        if len(buffer) > 64 * 1024:
                            drop = len(buffer) - 64 * 1024
                            logger.warning("区切り未検出でバッファ肥大のため %d bytes を切り詰め", drop)
                            del buffer[:drop]
                    break
                # 最も早く現れた区切り
                idx, token, token_name = min(candidates, key=lambda t: t[0])
                # CRLF は 2 文字消費、それ以外は 1 文字
                consume = 1
                delim_name = token_name
                if token == b"\r" and idx + 1 < len(buffer) and buffer[idx + 1:idx + 2] == b"\n":
                    consume = 2
                    delim_name = "CRLF"
                # 1 行取り出し（末尾の CR は落とす）
                line = buffer[:idx].rstrip(b"\r")
                del buffer[: idx + consume]
                try:
                    text = line.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    logger.error("UTF-8 デコード失敗: %r", line)
                    continue
                # 空白とカンマのみの行や空行はノイズとして破棄
                if text.strip() == "" or text.replace(",", "").strip() == "":
                    logger.debug("ノイズ行をスキップ: %r", text)
                    continue
                logger.debug("行確定(区切り=%s): %s", delim_name, text)
                queue.put_nowait(text)

            # 受信が断続的に途絶えた場合に備え、切断時は consumer を起こす
            if disconnected.is_set():
                wake_consumer()

        logger.info("Notify 購読開始: char=%s", tx_char_uuid)
        await client.start_notify(tx_char_uuid, lambda _, data: handle(data))

        try:
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
                except Exception as ex:
                    # 変換失敗はスキップ（ログを出す場合はここで print 可）
                    logger.warning("CSV 解析失敗: %s (err=%s)", line, ex)
                    continue
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
):
    """受信行を CSV として標準出力へ流すヘルパー。"""
    if show_header:
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
        print(
            f"{r.millis},{r.ax:.6f},{r.ay:.6f},{r.az:.6f},{r.gx:.6f},{r.gy:.6f},{r.gz:.6f},{r.tempC:.2f},{r.audioRMS:.2f}"
        )


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
