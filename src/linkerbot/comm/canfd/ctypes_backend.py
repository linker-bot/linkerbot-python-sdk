"""ctypes wrapper for the vendor CANFD dynamic library.

The vendor library documents two process-level entry points in
``动态库接口函数使用说明`` §3.1/3.2:

- ``LibCANbus_Init`` allocates global system resources.
- ``LibCANbus_Exit`` releases them and explicitly "prevents memory leaks".

These must be called exactly once per loaded ``.so``/``.dll`` for the lifetime
of the process, regardless of how many ``CANFDInterface`` instances are open.
This module manages that lifecycle via a reference count keyed on the realpath
of the loaded library so that multiple interfaces (e.g. several L30 hands on
one bus) share a single Init/Exit pair.

Forking after a CANFDInterface is open is not supported: the refcount lives in
the parent's memory and child copies will desync. Call ``L30.close()`` before
``os.fork()`` if you must fork.
"""

import atexit
import ctypes
import logging
import os
import platform
import threading
from pathlib import Path
from typing import Any

from linkerbot.exceptions import CANError, ValidationError

from .types import CANFDConfigOptions, CANFDMessage, dlc_to_length

CANFD_DEFAULT_SEND_TIMEOUT_MS = 10
CANFD_DEFAULT_RECEIVE_TIMEOUT_MS = 10
CANFD_DEFAULT_MAX_RECEIVE_FRAMES = 64
CANFD_TRANSMIT_FRAME_COUNT = 1
# Vendor PDF §3.22: CANFD_Transmit's items parameter caps at 100 frames per
# call. We preallocate a buffer of this size so the batch path never has to
# malloc on the send hot path. Practical batches inside the dispatcher are
# bounded by SEND_BATCH_MAX (much smaller — typically 32).
CANFD_TRANSMIT_MAX_BATCH = 100
CANFD_EXTENDED_FRAME_FLAG = 1
CANFD_STANDARD_FRAME_FLAG = 0
CANFD_REMOTE_FRAME_DISABLED = 0
CANFD_STATUS_OK = 0
CANFD_SCAN_NO_DEVICE = 0
CANFD_FRAME_DATA_SIZE = 64
_DEV_INFO_FIELD_LENGTH = 32
_C_STRING_TERMINATOR = b"\x00"
_ENV_LIBRARY_PATH = "LINKERBOT_CANFD_LIB"
_LINUX_LIBRARY_NAME = "libcanbus.so"
_WINDOWS_LIBRARY_NAME = "HCanbus.dll"
_LINUX_USB_LIBRARY_NAME = "libusb-1.0.so.0"

_logger = logging.getLogger(__name__)

_lifecycle_lock = threading.Lock()
_lifecycle_refcount: dict[str, int] = {}
_lifecycle_lib: dict[str, Any] = {}
_finalize_safe = True


def _library_key(lib: Any) -> str:
    """Return a stable refcount key for the loaded vendor library.

    ``ctypes.CDLL`` exposes the resolved library path on ``_name``. We use the
    realpath so symlinks (``/usr/local/lib/libcanbus.so`` →
    ``/usr/local/lib/libcanbus.so.1``) collapse to one refcount slot. Test
    fakes typically have no ``_name``; fall back to ``id(lib)`` so each fake
    gets its own bucket and tests stay isolated.
    """
    name = getattr(lib, "_name", None)
    if name:
        try:
            return os.path.realpath(name)
        except OSError:
            return str(name)
    return f"id:{id(lib)}"


def _lifecycle_acquire(lib: Any) -> str:
    """Increment refcount, calling ``LibCANbus_Init`` on first acquire.

    Raises ``CANError`` if ``LibCANbus_Init`` returns non-zero on the first
    call; the refcount is not bumped in that case so a later acquire will
    retry. Subsequent acquires for the same library skip the vendor call.
    """
    key = _library_key(lib)
    with _lifecycle_lock:
        count = _lifecycle_refcount.get(key, 0)
        if count == 0:
            init_fn = getattr(lib, "LibCANbus_Init", None)
            if init_fn is None:
                raise CANError(
                    "vendor library is missing LibCANbus_Init; update libcanbus.so "
                    "to a version that exports the documented lifecycle entry points"
                )
            status = init_fn()
            if status != CANFD_STATUS_OK:
                raise CANError(f"LibCANbus_Init failed with status {status}")
            _lifecycle_lib[key] = lib
        _lifecycle_refcount[key] = count + 1
        return key


def _lifecycle_release(key: str | None) -> None:
    """Decrement refcount, calling ``LibCANbus_Exit`` when it reaches zero.

    No-op if ``key`` is ``None`` (constructor failed before acquire) or if the
    refcount is already zero (defensive — should not happen with paired
    acquire/release). Exceptions from ``LibCANbus_Exit`` are swallowed with a
    warning because they leave the SDK in a usable state and a stuck Exit
    should not break shutdown.
    """
    if key is None or not _finalize_safe:
        return
    with _lifecycle_lock:
        count = _lifecycle_refcount.get(key, 0)
        if count <= 0:
            return
        count -= 1
        _lifecycle_refcount[key] = count
        if count > 0:
            return
        lib = _lifecycle_lib.pop(key, None)
        _lifecycle_refcount.pop(key, None)
        if lib is None:
            return
        exit_fn = getattr(lib, "LibCANbus_Exit", None)
        if exit_fn is None:
            return
        # Keep acquire/release serialized through the vendor Exit call. If the
        # lock were released first, another thread could call Init and then have
        # this stale Exit tear down the resources underneath its live interface.
        try:
            status = exit_fn()
        except Exception as error:
            _logger.warning("LibCANbus_Exit raised: %s", error)
            return
        if status != CANFD_STATUS_OK:
            _logger.warning("LibCANbus_Exit returned status %s", status)


def _lifecycle_snapshot() -> dict[str, int]:
    """Return a copy of the current refcount table (testing helper)."""
    with _lifecycle_lock:
        return dict(_lifecycle_refcount)


class CanFDConfig(ctypes.Structure):
    """Vendor CANFD initialization structure."""

    _fields_ = [
        ("NomBaud", ctypes.c_uint),
        ("DatBaud", ctypes.c_uint),
        ("NomPre", ctypes.c_ushort),
        ("NomTseg1", ctypes.c_ubyte),
        ("NomTseg2", ctypes.c_ubyte),
        ("NomSJW", ctypes.c_ubyte),
        ("DatPre", ctypes.c_ubyte),
        ("DatTseg1", ctypes.c_ubyte),
        ("DatTseg2", ctypes.c_ubyte),
        ("DatSJW", ctypes.c_ubyte),
        ("Config", ctypes.c_ubyte),
        ("Model", ctypes.c_ubyte),
        ("Cantype", ctypes.c_ubyte),
    ]


class CanFDMsg(ctypes.Structure):
    """Vendor CANFD frame structure."""

    _fields_ = [
        ("ID", ctypes.c_uint),
        ("TimeStamp", ctypes.c_uint),
        ("FrameType", ctypes.c_ubyte),
        ("DLC", ctypes.c_ubyte),
        ("ExternFlag", ctypes.c_ubyte),
        ("RemoteFlag", ctypes.c_ubyte),
        ("BusSatus", ctypes.c_ubyte),
        ("ErrSatus", ctypes.c_ubyte),
        ("TECounter", ctypes.c_ubyte),
        ("RECounter", ctypes.c_ubyte),
        ("Data", ctypes.c_ubyte * 64),
    ]


class DevInfo(ctypes.Structure):
    """USB-CANFD adapter information returned by the vendor library."""

    _fields_ = [
        ("HW_Type", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("HW_Ser", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("HW_Ver", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("FW_Ver", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
        ("MF_Date", ctypes.c_char * _DEV_INFO_FIELD_LENGTH),
    ]


class CANFDInterface:
    """Low-level CANFD interface backed by libcanbus.so or HCanbus.dll.

    Concurrency model (changed in fix#141):

    - ``send()`` is protected by ``_tx_lock`` only — the vendor USB write
      endpoint is single-writer.
    - ``receive()`` is protected by ``_rx_lock`` only — the vendor USB read
      endpoint is single-reader. The two locks are independent so a long-
      running receive (the dispatcher's 10 ms timeout) never blocks send.
    - Transition of the open/closed flag is guarded by ``_state_lock`` and
      atomically reflected in ``_closed_event``. Every public method consults
      the event at entry, so a close cleanly cancels future calls without
      racing the per-direction locks. ``_close_complete_event`` separately
      records that device and process-level lifecycle cleanup has finished,
      allowing concurrent ``close()`` callers to wait for the owner.

    Close contract (mandatory ordering, encoded in :meth:`close`):

    1. Under ``_state_lock``, flip ``_closed_event`` and snapshot the previous
       state. Subsequent ``send/receive/read_dev_info`` calls fail fast.
    2. Briefly acquire ``_tx_lock`` then ``_rx_lock``. Any in-flight call from
       another thread has the matching lock; reacquiring forces ``close()`` to
       wait until the vendor call returns. With send timeout 10 ms and
       receive timeout 10 ms, the worst-case drain is ~20 ms.
    3. Call ``CAN_CloseDevice`` exactly once.
    4. Release the lifecycle refcount and notify concurrent close callers.

    When a dispatcher owns the interface, ``dispatcher.stop()`` joins both
    worker threads before calling ``close()``, so steps 2 sees no contention.
    """

    def __init__(
        self,
        device_index: int = 0,
        channel_index: int = 0,
        library_path: str | Path | None = None,
        config: CANFDConfigOptions | None = None,
    ) -> None:
        """Open and initialize a CANFD adapter channel.

        On success, holds a reference count on the vendor library so
        ``LibCANbus_Init`` runs exactly once per process and ``LibCANbus_Exit``
        runs exactly once after every interface is closed. If any step after
        the library is loaded fails, the refcount is released so partial
        initialization does not leak vendor resources.
        """
        if device_index < 0:
            raise ValidationError("device_index must be non-negative")
        if channel_index < 0:
            raise ValidationError("channel_index must be non-negative")

        self._device_index = device_index
        self._channel_index = channel_index
        self._config = config or CANFDConfigOptions()
        # Independent locks per direction. send and receive run truly
        # concurrently — they only contend at the per-direction lock, which
        # is itself uncontended in the dispatcher's one-thread-per-direction
        # model. See close contract in the class docstring.
        self._tx_lock = threading.Lock()
        self._rx_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._closed_event = threading.Event()
        self._close_complete_event = threading.Event()
        # Marks "uninitialized" before _open returns; flipped to False on
        # successful open and consulted by close to short-circuit a double-
        # close on a never-opened instance.
        self._closed_event.set()
        self._close_complete_event.set()
        self._lifecycle_key: str | None = None
        self._lib = _load_library(library_path)
        _bind_signatures(self._lib)
        # Hot-path zero-alloc buffers. The TX frame is reused across every
        # send under _tx_lock; the TX batch buffer is reused across every
        # send_batch under the same lock; the RX buffer is reused across
        # every receive under _rx_lock. Pre-allocating them eliminates
        # ~5 KB of ctypes allocation per receive cycle (100 Hz) and replaces
        # a Python for loop with ctypes.memmove on the send path.
        self._tx_frame = CanFDMsg()
        self._tx_batch = (CanFDMsg * CANFD_TRANSMIT_MAX_BATCH)()
        self._rx_buffer = (CanFDMsg * CANFD_DEFAULT_MAX_RECEIVE_FRAMES)()
        # acquire the vendor lifecycle refcount before any device-level call;
        # release it if anything below this point raises so we don't leak the
        # Init reference on a partially-initialized interface.
        self._lifecycle_key = _lifecycle_acquire(self._lib)
        try:
            self._open()
        except BaseException:
            _lifecycle_release(self._lifecycle_key)
            self._lifecycle_key = None
            raise

    @property
    def device_index(self) -> int:
        """Adapter device index passed to the vendor library."""
        return self._device_index

    @property
    def channel_index(self) -> int:
        """CANFD channel index passed to the vendor library."""
        return self._channel_index

    @property
    def config(self) -> CANFDConfigOptions:
        """CANFD configuration used to initialize this interface."""
        return self._config

    def _open(self) -> None:
        # _open runs once in __init__ before any worker thread has a reference
        # to the interface, so no other lock is required here.
        count = self._lib.CAN_ScanDevice()
        if count < CANFD_SCAN_NO_DEVICE:
            raise CANError(f"CAN_ScanDevice failed with status {count}")
        if count == CANFD_SCAN_NO_DEVICE:
            raise CANError("No CANFD adapter found")
        if self._device_index >= count:
            raise CANError(
                f"CANFD device_index {self._device_index} out of range; "
                f"found {count} adapter(s)"
            )

        status = self._lib.CAN_OpenDevice(self._device_index, self._channel_index)
        if status != CANFD_STATUS_OK:
            raise CANError(f"CAN_OpenDevice failed with status {status}")
        try:
            config = self._build_ctypes_config()
            status = self._lib.CANFD_Init(
                self._device_index, self._channel_index, ctypes.byref(config)
            )
            if status != CANFD_STATUS_OK:
                raise CANError(f"CANFD_Init failed with status {status}")
        except BaseException:
            try:
                self._lib.CAN_CloseDevice(self._device_index, self._channel_index)
            except Exception as close_error:
                _logger.warning(
                    "CAN_CloseDevice failed while rolling back CANFD_Init: %s",
                    close_error,
                )
            finally:
                self._closed_event.set()
            raise

        # _open is called from __init__ before the object is published. Clear
        # completion first so any later close owner always has an incomplete
        # event to publish when cleanup finishes.
        self._close_complete_event.clear()
        self._closed_event.clear()

    def _build_ctypes_config(self) -> CanFDConfig:
        return CanFDConfig(
            NomBaud=self._config.nom_baud,
            DatBaud=self._config.dat_baud,
            NomPre=0,
            NomTseg1=0,
            NomTseg2=0,
            NomSJW=0,
            DatPre=0,
            DatTseg1=0,
            DatTseg2=0,
            DatSJW=0,
            Config=self._config.config,
            Model=self._config.model,
            Cantype=self._config.cantype,
        )

    def send(
        self,
        message: CANFDMessage,
        timeout_ms: int = CANFD_DEFAULT_SEND_TIMEOUT_MS,
    ) -> None:
        """Transmit one CANFD frame through the vendor library.

        Holds ``_tx_lock`` only — independent of receive, so a long-running
        receive timeout does not block transmits. Reuses ``self._tx_frame``
        to avoid allocating a fresh ``CanFDMsg`` on every send.
        """
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")
        # Fail fast if close has been initiated; we may still race with close
        # acquiring _tx_lock, but the lock acquisition itself is bounded by
        # the vendor send timeout (10 ms default) so close drains cleanly.
        self._ensure_open()
        with self._tx_lock:
            self._ensure_open()
            self._fill_tx_frame(message)
            sent = self._lib.CANFD_Transmit(
                self._device_index,
                self._channel_index,
                ctypes.byref(self._tx_frame),
                CANFD_TRANSMIT_FRAME_COUNT,
                timeout_ms,
            )
            if sent != CANFD_TRANSMIT_FRAME_COUNT:
                raise CANError(
                    "CANFD_Transmit failed: expected "
                    f"{CANFD_TRANSMIT_FRAME_COUNT} frame, got {sent}"
                )

    def send_batch(
        self,
        messages: list[CANFDMessage],
        timeout_ms: int = CANFD_DEFAULT_SEND_TIMEOUT_MS,
    ) -> None:
        """Transmit multiple CANFD frames in a single vendor call.

        Vendor PDF §3.22 documents that ``CANFD_Transmit`` accepts an array
        of up to 100 frames in one call. At 17-joint PVT @ 100 Hz this turns
        3 USB control transfers per cycle (position+speed+torque) into 1,
        cutting USB protocol overhead by roughly 3×.

        Order is preserved on the wire: frame ``messages[i]`` is transmitted
        before ``messages[j]`` for ``i < j``. This matters for protocols
        like L30 where the device expects target updates in a specific
        sequence within a control cycle.

        ``messages[i]`` is filled into preallocated slot ``self._tx_batch[i]``
        so this path stays alloc-free for batches up to ``CANFD_TRANSMIT_MAX_BATCH``.

        Args:
            messages: Frames to transmit, in order. Length must be in
                ``[0, CANFD_TRANSMIT_MAX_BATCH]``. Empty list is a no-op.
            timeout_ms: Vendor send timeout for the batched call.

        Raises:
            ValidationError: If ``len(messages) > CANFD_TRANSMIT_MAX_BATCH``
                or ``timeout_ms`` is negative.
            CANError: If the interface is closed or the vendor library
                reports a short send (``sent != len(messages)``).
        """
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")
        count = len(messages)
        if count == 0:
            return
        if count > CANFD_TRANSMIT_MAX_BATCH:
            raise ValidationError(
                f"send_batch supports at most {CANFD_TRANSMIT_MAX_BATCH} "
                f"frames per call (vendor limit), got {count}"
            )
        if count == 1:
            # Reuse the single-frame fast path which writes into _tx_frame
            # and avoids touching the larger batch buffer.
            self.send(messages[0], timeout_ms)
            return

        self._ensure_open()
        with self._tx_lock:
            self._ensure_open()
            for index, message in enumerate(messages):
                self._fill_frame(self._tx_batch[index], message)
            sent = self._lib.CANFD_Transmit(
                self._device_index,
                self._channel_index,
                self._tx_batch,
                count,
                timeout_ms,
            )
            if sent != count:
                raise CANError(
                    f"CANFD_Transmit batch short send: expected {count}, got {sent}"
                )

    def receive(
        self,
        max_frames: int = CANFD_DEFAULT_MAX_RECEIVE_FRAMES,
        timeout_ms: int = CANFD_DEFAULT_RECEIVE_TIMEOUT_MS,
    ) -> list[CANFDMessage]:
        """Receive up to max_frames CANFD frames from the vendor library.

        Holds ``_rx_lock`` only — independent of send. The vendor library is
        single-reader per channel, so the lock prevents accidental concurrent
        callers from corrupting its internal ring buffer.

        Reuses ``self._rx_buffer`` when ``max_frames`` fits the preallocated
        capacity (the common case — the dispatcher uses the default). Larger
        requests allocate a fresh array. Returned messages are independent
        immutable copies, so callers may keep them after the next receive
        overwrites the buffer.
        """
        if max_frames <= 0:
            raise ValidationError("max_frames must be positive")
        if timeout_ms < 0:
            raise ValidationError("timeout_ms must be non-negative")

        self._ensure_open()
        with self._rx_lock:
            self._ensure_open()
            if max_frames <= CANFD_DEFAULT_MAX_RECEIVE_FRAMES:
                buffer = self._rx_buffer
            else:
                buffer = (CanFDMsg * max_frames)()
            received = self._lib.CANFD_Receive(
                self._device_index,
                self._channel_index,
                buffer,
                max_frames,
                timeout_ms,
            )
            if received < CANFD_STATUS_OK:
                raise CANError(f"CANFD_Receive failed with status {received}")
            if received == CANFD_STATUS_OK:
                return []
            if received > max_frames:
                raise CANError(
                    "CANFD_Receive returned more frames than requested: "
                    f"requested {max_frames}, got {received}"
                )
            return [self._frame_to_message(buffer[i]) for i in range(received)]

    def read_dev_info(self) -> dict[str, str]:
        """Read USB-CANFD adapter information from the vendor library.

        Uses ``_tx_lock`` because the vendor library treats CAN_ReadDevInfo as
        another control-endpoint write.
        """
        self._ensure_open()
        with self._tx_lock:
            self._ensure_open()
            info = DevInfo()
            status = self._lib.CAN_ReadDevInfo(self._device_index, ctypes.byref(info))
            if status != CANFD_STATUS_OK:
                raise CANError(f"CAN_ReadDevInfo failed with status {status}")
            return {
                "hw_type": _decode_c_string(info.HW_Type),
                "hw_serial": _decode_c_string(info.HW_Ser),
                "hw_version": _decode_c_string(info.HW_Ver),
                "fw_version": _decode_c_string(info.FW_Ver),
                "manufacture_date": _decode_c_string(info.MF_Date),
            }

    def close(self) -> None:
        """Close the CANFD adapter channel and release the vendor refcount.

        Mandatory ordering (see class docstring):

        1. Flip ``_closed_event`` under ``_state_lock``; from this point any
           future send/receive call from any thread fails fast.
        2. Drain in-flight send/receive by briefly acquiring ``_tx_lock`` and
           ``_rx_lock``. Any thread that entered the vendor call before step 1
           will return within its bounded timeout (≤10 ms each) and release
           the lock; close then proceeds.
        3. Call ``CAN_CloseDevice``.
        4. Release lifecycle refcount and notify any concurrent close callers.

        ``CAN_CloseDevice`` failure is surfaced as ``CANError``, but step 4
        runs regardless so the Init reference is never permanently leaked.
        """
        # Step 1: atomically select one cleanup owner. Other close callers must
        # wait for the owner rather than treating "closing" as "closed" and
        # returning while vendor or lifecycle cleanup is still in progress.
        with self._state_lock:
            if self._closed_event.is_set():
                owns_close = False
            else:
                self._closed_event.set()
                owns_close = True

        if not owns_close:
            self._close_complete_event.wait()
            return

        try:
            # Step 2: drain. Acquiring then immediately releasing each
            # direction lock waits out any in-flight vendor call.
            with self._tx_lock:
                pass
            with self._rx_lock:
                pass

            # Step 3: actually close the vendor side.
            try:
                close_status = self._lib.CAN_CloseDevice(
                    self._device_index, self._channel_index
                )
            except Exception as error:
                raise CANError(f"CAN_CloseDevice failed: {error}") from error
            finally:
                # Step 4: lifecycle release, including when the vendor call
                # raises. Completion is not published until this returns, so
                # a waiter can safely acquire/reopen the same library.
                if self._lifecycle_key is not None:
                    _lifecycle_release(self._lifecycle_key)
                    self._lifecycle_key = None

            if close_status != CANFD_STATUS_OK:
                raise CANError(f"CAN_CloseDevice failed with status {close_status}")
        finally:
            # Every owner exit path, including vendor and lifecycle exceptions,
            # must wake callers already waiting in close().
            self._close_complete_event.set()

    def _ensure_open(self) -> None:
        if self._closed_event.is_set():
            raise CANError("CANFD interface is closed")

    def _fill_frame(self, target: "CanFDMsg", message: CANFDMessage) -> None:
        """Populate ``target`` (a vendor ``CanFDMsg`` slot) for transmission.

        Generic helper shared by single-frame :meth:`send` (which writes into
        the preallocated ``self._tx_frame``) and batch :meth:`send_batch`
        (which writes into successive slots of ``self._tx_batch``). Uses
        ``ctypes.memmove`` for the payload instead of a Python for-loop —
        at 17×PVT @ 100 Hz this is the difference between ~50 µs and ~5 µs
        of CPU per frame. The tail beyond ``len(data)`` is zeroed so the
        vendor library never observes stale bytes from a previous frame's
        DLC padding.
        """
        target.ID = message.arbitration_id
        target.TimeStamp = 0
        target.FrameType = (
            message.frame_type
            if message.frame_type is not None
            else self._config.frame_type
        )
        target.DLC = message.dlc or 0
        target.ExternFlag = (
            CANFD_EXTENDED_FRAME_FLAG
            if message.is_extended_id
            else CANFD_STANDARD_FRAME_FLAG
        )
        target.RemoteFlag = CANFD_REMOTE_FRAME_DISABLED
        target.BusSatus = CANFD_STATUS_OK
        target.ErrSatus = CANFD_STATUS_OK
        target.TECounter = 0
        target.RECounter = 0
        data = message.data
        length = len(data)
        data_addr = ctypes.addressof(target.Data)
        if length:
            ctypes.memmove(data_addr, data, length)
        if length < CANFD_FRAME_DATA_SIZE:
            ctypes.memset(data_addr + length, 0, CANFD_FRAME_DATA_SIZE - length)

    def _fill_tx_frame(self, message: CANFDMessage) -> None:
        """Compatibility shim: fill the preallocated ``_tx_frame``."""
        self._fill_frame(self._tx_frame, message)

    def _message_to_frame(self, message: CANFDMessage) -> CanFDMsg:
        """Build a stand-alone ``CanFDMsg`` (compat path).

        The hot send path uses :meth:`_fill_tx_frame` against the preallocated
        ``_tx_frame``. This wrapper is preserved so test suites that monkeypatch
        the ctypes layer or call the helper directly keep working.
        """
        frame = CanFDMsg()
        saved = self._tx_frame
        self._tx_frame = frame
        try:
            self._fill_tx_frame(message)
        finally:
            self._tx_frame = saved
        return frame

    def _frame_to_message(self, frame: CanFDMsg) -> CANFDMessage:
        length = dlc_to_length(frame.DLC)
        # ctypes.string_at copies length bytes in a single C call; the previous
        # ``bytes(frame.Data[:length])`` materializes a Python list first which
        # is multiple times slower at 64-byte payloads.
        if length:
            payload = ctypes.string_at(ctypes.addressof(frame.Data), length)
        else:
            payload = b""
        return CANFDMessage(
            arbitration_id=frame.ID,
            data=payload,
            dlc=frame.DLC,
            is_extended_id=bool(frame.ExternFlag),
            frame_type=frame.FrameType,
            timestamp=frame.TimeStamp,
        )

    def __enter__(self) -> "CANFDInterface":
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and close the CANFD interface."""
        self.close()

    def __del__(self) -> None:
        """Best-effort close on garbage collection.

        ``__del__`` runs at unpredictable times — possibly during interpreter
        shutdown when ``ctypes`` or the vendor library is already unloaded.
        Swallow every exception so we never produce ``Exception ignored in
        __del__`` noise; the module-level ``_finalize_safe`` flag short-circuits
        the lifecycle release path during shutdown.
        """
        try:
            closed = getattr(self, "_closed_event", None)
            if closed is None or closed.is_set():
                return
            self.close()
        except BaseException:
            pass


def _load_library(library_path: str | Path | None) -> Any:
    _preload_vendor_dependencies()
    errors: list[str] = []
    for candidate in _library_candidates(library_path):
        try:
            return _ctypes_loader()(str(candidate))
        except OSError as error:
            errors.append(f"{candidate}: {error}")

    attempted = "\n".join(errors) if errors else "no candidates"
    raise CANError(
        "Unable to load CANFD vendor library. The system loader is tried by default; "
        "pass library_path=... or set "
        f"{_ENV_LIBRARY_PATH} to the libcanbus.so/HCanbus.dll path if the library is "
        f"not installed in a system search path. Attempted:\n{attempted}"
    )


def _preload_vendor_dependencies() -> None:
    if platform.system() != "Linux":
        return
    try:
        ctypes.CDLL(_LINUX_USB_LIBRARY_NAME, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        return


def _library_candidates(library_path: str | Path | None) -> list[str | Path]:
    library_name = _default_library_name()
    candidates: list[str | Path] = []
    if library_path is not None:
        candidates.append(Path(library_path))
    env_path = os.environ.get(_ENV_LIBRARY_PATH)
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(library_name)

    package_root = Path(__file__).resolve().parents[2]
    candidates.append(Path("/usr/local/lib") / library_name)
    candidates.append(package_root / "vendor" / "libcanbus" / library_name)
    candidates.append(package_root / "hand" / library_name)
    candidates.append(Path.cwd() / library_name)
    return candidates


def _default_library_name() -> str:
    return (
        _WINDOWS_LIBRARY_NAME if platform.system() == "Windows" else _LINUX_LIBRARY_NAME
    )


def _ctypes_loader() -> Any:
    if platform.system() == "Windows":
        # WinDLL is intentionally resolved lazily because ctypes does not
        # expose it on non-Windows hosts where this module is type-checked.
        return getattr(ctypes, "WinDLL")  # noqa: B009
    return ctypes.CDLL


def _bind_signatures(lib: Any) -> None:
    # Vendor process-level lifecycle (PDF §3.1/3.2). The library is expected to
    # always export these — calling LibCANbus_Init exactly once per process and
    # LibCANbus_Exit on shutdown is what prevents the documented memory leak.
    if hasattr(lib, "LibCANbus_Init"):
        lib.LibCANbus_Init.restype = ctypes.c_int
        lib.LibCANbus_Init.argtypes = []
    if hasattr(lib, "LibCANbus_Exit"):
        lib.LibCANbus_Exit.restype = ctypes.c_int
        lib.LibCANbus_Exit.argtypes = []

    lib.CAN_ScanDevice.restype = ctypes.c_int
    lib.CAN_ScanDevice.argtypes = []

    lib.CAN_OpenDevice.restype = ctypes.c_int
    lib.CAN_OpenDevice.argtypes = [ctypes.c_uint, ctypes.c_uint]

    lib.CAN_CloseDevice.restype = ctypes.c_int
    lib.CAN_CloseDevice.argtypes = [ctypes.c_uint, ctypes.c_uint]

    lib.CAN_ReadDevInfo.restype = ctypes.c_int
    lib.CAN_ReadDevInfo.argtypes = [ctypes.c_uint, ctypes.POINTER(DevInfo)]

    lib.CANFD_Init.restype = ctypes.c_int
    lib.CANFD_Init.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDConfig),
    ]

    lib.CANFD_Transmit.restype = ctypes.c_int
    lib.CANFD_Transmit.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDMsg),
        ctypes.c_uint,
        ctypes.c_int,
    ]

    lib.CANFD_Receive.restype = ctypes.c_int
    lib.CANFD_Receive.argtypes = [
        ctypes.c_uint,
        ctypes.c_uint,
        ctypes.POINTER(CanFDMsg),
        ctypes.c_uint,
        ctypes.c_int,
    ]


def _decode_c_string(value: bytes) -> str:
    return bytes(value).split(_C_STRING_TERMINATOR, 1)[0].decode(errors="replace")


def _mark_finalize_unsafe() -> None:
    """Module teardown hook: stop touching the vendor library at exit.

    By the time interpreter shutdown reaches the per-object ``__del__`` of an
    abandoned ``CANFDInterface``, ``ctypes`` and the vendor ``.so`` may already
    be unloaded. Flipping this flag turns the lifecycle release path into a
    no-op so we never re-enter a torn-down vendor library.
    """
    global _finalize_safe
    _finalize_safe = False


atexit.register(_mark_finalize_unsafe)
