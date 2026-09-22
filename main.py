# astrbot_plugin_xb2img/main.py
# xb2img：APNG 第1帧=A、点开播B，原图直发，零多余残留。
import asyncio
import base64
import io
import tempfile
import time
import urllib.request
from contextlib import suppress
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star

try:
    from astrbot.api.message_components import Image as AstrImage
except Exception:
    AstrImage = None

PLUGIN_DIR = Path(__file__).resolve().parent
TMP_ROOT = PLUGIN_DIR / "tmp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

MAX_EDGE = 1080
MIN_EDGE = 128
MAX_FETCH_BYTES = 20 * 1024 * 1024
TARGET_BYTES = 1024 * 1024
B_MS = 10 * 1000
FIRST_MS = 500
MAX_B64_TOTAL = 1536 * 1024
MAX_WAIT = 4
QUEUE_TIMEOUT = 120
FETCH_TIMEOUT = 10
SEND_TIMEOUT = 20
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AstrBot-xb2img"
_PREFIXES = ("/xb2img", "xb2img")


def _parse(text):
    t = (text or "").strip()
    for p in _PREFIXES:
        if t.startswith(p):
            t = t[len(p):].strip()
            break
    apng, refs = False, []
    for tok in t.split():
        s = tok.strip("\"'")
        if not s:
            continue
        if s == "--apng":
            apng = True
        elif not s.startswith("--"):
            refs.append(s)
    return refs, apng


def _chain_images(event):
    refs = []
    chain = getattr(getattr(event, "message_obj", None), "message", None) or []
    for seg in chain:
        if not ((AstrImage is not None and isinstance(seg, AstrImage))
                or seg.__class__.__name__ == "Image"):
            continue
        for a in ("path", "url", "file"):
            v = getattr(seg, a, None)
            if isinstance(v, str) and v.strip():
                refs.append(v.strip())
                break
    return refs


def _fetch_bytes_sync(ref):
    ref = (ref or "").strip().strip("\"'")
    if ref.startswith("http://") or ref.startswith("https://"):
        req = urllib.request.Request(ref, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            blob = r.read(MAX_FETCH_BYTES + 1)
        if len(blob) > MAX_FETCH_BYTES:
            raise ValueError("下载超20MB限制")
        if len(blob) < 100:
            raise ValueError("下载内容过小或不是图片")
        return blob
    if ref.startswith("base64://"):
        return base64.b64decode(ref[len("base64://"):])
    if ref.startswith("data:image"):
        return base64.b64decode(ref.split(",", 1)[1])
    p = ref[7:] if ref.startswith("file://") else ref
    lp = Path(p).expanduser()
    if not lp.is_absolute():
        for base in (Path.cwd(), PLUGIN_DIR):
            t = (base / p).resolve()
            if t.is_file():
                lp = t
                break
    if not lp.is_file():
        raise FileNotFoundError("找不到图片")
    blob = lp.read_bytes()
    if len(blob) > MAX_FETCH_BYTES:
        raise ValueError("文件超20MB限制")
    if len(blob) < 100:
        raise ValueError("文件过小或不是图片")
    return blob


def _call(event):
    return getattr(getattr(getattr(event, "bot", None), "api", None), "call_action", None)


def _session_ids(event):
    gid, sid = "", ""
    with suppress(Exception):
        gid = (event.get_group_id() or "").strip()
    with suppress(Exception):
        sid = (event.get_sender_id() or "").strip()
    return gid, sid


async def _raw_send(event, segs):
    call = _call(event)
    if not callable(call):
        raise RuntimeError("非 aiocqhttp 平台，无法发送")
    gid, sid = _session_ids(event)
    if gid:
        return await asyncio.wait_for(call(
            "send_msg", message_type="group",
            group_id=int(gid), message=segs), SEND_TIMEOUT)
    if sid:
        return await asyncio.wait_for(call(
            "send_msg", message_type="private",
            user_id=int(sid), message=segs), SEND_TIMEOUT)
    raise RuntimeError("无法获取会话ID")


async def _recall(event, mid):
    if not mid:
        return
    call = _call(event)
    if callable(call):
        with suppress(Exception):
            await call("delete_msg", message_id=int(mid))


class _QueueFull(Exception):
    pass


class _QueueTimeout(Exception):
    pass


class _JobGate:
    def __init__(self, max_wait=MAX_WAIT):
        self._sem = asyncio.Semaphore(1)
        self._inside = 0
        self._max_wait = max_wait

    def enter(self):
        if self._inside > self._max_wait:
            raise _QueueFull()
        self._inside += 1
        return self._inside

    async def wait_turn(self, timeout=QUEUE_TIMEOUT):
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            self._inside -= 1
            raise _QueueTimeout() from None
        except BaseException:
            self._inside -= 1
            raise

    def leave(self):
        self._sem.release()
        self._inside -= 1


_GATE = _JobGate()


class Xb2imgPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.command("xb2img")
    async def xb2img(self, event: AstrMessageEvent):
        t0 = time.time()
        refs, apng = _parse(event.message_str or "")
        for r in _chain_images(event):
            if r not in refs:
                refs.append(r)
        if len(refs) < 2:
            yield event.plain_result(
                "用法：/xb2img <预览图A> <原图B> [--apng]\n"
                "示例：/xb2img ./a.jpg ./b.jpg\n"
                "也支持指令后直接附带两张图。\n"
                "合成 APNG 无限循环（第1帧=A，点开播B），默认 .png 发出；\n"
                "加 --apng 则改用 .apng 后缀。"
            )
            return
        try:
            pos = _GATE.enter()
        except _QueueFull:
            yield event.plain_result("任务已满（1 个在跑 + 4 个在等），稍后再试。")
            return
        if pos > 1:
            yield event.plain_result(f"排队中，前方还有 {pos - 1} 个任务，请稍候…")
        prog = None
        acquired = False
        out_path = None
        try:
            with suppress(Exception):
                r = await _raw_send(event, [{"type": "text", "data": {"text": "正在处理 xb2img 中..."}}])
                prog = (r or {}).get("message_id")
            try:
                await _GATE.wait_turn()
            except _QueueTimeout:
                await _recall(event, prog)
                prog = None
                yield event.plain_result("排队超时（120 秒没轮到），稍后再试。")
                return
            except BaseException:
                await _recall(event, prog)
                prog = None
                raise
            acquired = True
            try:
                a_blob, b_blob = await asyncio.gather(
                    asyncio.to_thread(_fetch_bytes_sync, refs[0]),
                    asyncio.to_thread(_fetch_bytes_sync, refs[1]),
                )
            except Exception:
                logger.exception("[xb2img] 读取失败")
                yield event.plain_result("图片读取失败（链接失效/文件缺失/超20MB/非图片）")
                return
            suffix = ".apng" if apng else ".png"
            fd, tmps = tempfile.mkstemp(prefix="xb2img_", suffix=suffix, dir=str(TMP_ROOT))
            try:
                import os as _os
                _os.close(fd)
            except Exception:
                pass
            out_path = Path(tmps)
            try:
                await asyncio.to_thread(
                    make_xb2img_apng_sync, a_blob, b_blob,
                    str(out_path), MAX_EDGE, TARGET_BYTES)
            except ImportError:
                yield event.plain_result("合成失败：缺 Pillow，请 pip install Pillow>=10.0.0")
                return
            except Exception as e:
                logger.exception("[xb2img] 合成失败")
                yield event.plain_result(f"合成失败：{type(e).__name__}")
                return
            size = out_path.stat().st_size
            seg = {"type": "image", "data": {
                "file": str(out_path.resolve()),
                "summary": "[动图]", "sub_type": 0}}
            try:
                await _raw_send(event, [seg])
                logger.info(f"[xb2img] 通道 file直发 {out_path.name} {time.time()-t0:.1f}s {size//1024}KB")
            except Exception:
                if size <= MAX_B64_TOTAL:
                    blob = await asyncio.to_thread(out_path.read_bytes)
                    seg["data"]["file"] = "base64://" + base64.b64encode(blob).decode()
                    try:
                        await _raw_send(event, [seg])
                        logger.info(f"[xb2img] 通道 base64重试 {out_path.name}")
                    except Exception as e2:
                        yield event.plain_result(f"发送失败：{type(e2).__name__}")
                        return
                else:
                    yield event.plain_result("发送失败且文件过大，无法 base64 重试。")
                    return
            # 成功不追加文本，零残留
        finally:
            if acquired:
                _GATE.leave()
            if out_path is not None:
                with suppress(Exception):
                    out_path.unlink(missing_ok=True)
            await _recall(event, prog)


def _decode_frame(blob):
    try:
        from PIL import Image, ImageOps
    except ImportError as e:
        raise ImportError("Pillow") from e
    with Image.open(io.BytesIO(blob)) as im:
        im = ImageOps.exif_transpose(im)
        return im.convert("RGBA")


def _fit_contain(im, target_size, resample):
    tw, th = target_size
    iw, ih = im.size
    if (iw, ih) == (tw, th):
        return im
    s = min(tw / iw, th / ih) if iw and ih else 1.0
    nw, nh = max(1, int(iw * s)), max(1, int(ih * s))
    small = im.resize((nw, nh), resample)
    if (nw, nh) == (tw, th):
        return small
    try:
        from PIL import Image as _I
    except ImportError as e:
        raise ImportError("Pillow") from e
    canvas = _I.new("RGBA", (tw, th), (0, 0, 0, 0))
    canvas.paste(small, ((tw - nw) // 2, (th - nh) // 2), small)
    return canvas


def make_xb2img_apng_sync(a_blob, b_blob, output_path,
                        max_edge=MAX_EDGE, target_bytes=TARGET_BYTES):
    # 解码只做一次；B 等比 contain 进 A 画布，避免拉伸；B 只存 1 帧。
    try:
        from PIL import Image
    except ImportError as e:
        raise ImportError("Pillow") from e
    im_a = _decode_frame(a_blob)
    im_b = _decode_frame(b_blob)
    try:
        w, h = im_a.size
        max_orig = max(w, h)
        edge = min(max_orig, max_edge) if max_orig > 0 else max_edge
        last_blob = None
        tries = 0
        while True:
            tries += 1
            scale = min(1.0, edge / max_orig) if max_orig > 0 else 1.0
            target_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            fa = im_a if target_size == im_a.size else im_a.resize(target_size, Image.LANCZOS)
            fb = _fit_contain(im_b, target_size, Image.LANCZOS)
            bio = io.BytesIO()
            fa.save(bio, format="PNG", save_all=True,
                    append_images=[fb],
                    duration=[FIRST_MS, B_MS],
                    loop=0, optimize=False)
            blob = bio.getvalue()
            if len(blob) <= target_bytes or edge <= MIN_EDGE or tries >= 6:
                if len(blob) <= target_bytes:
                    with suppress(Exception):
                        opt = io.BytesIO()
                        fa.save(opt, format="PNG", save_all=True,
                                append_images=[fb],
                                duration=[FIRST_MS, B_MS],
                                loop=0, optimize=True)
                        opt_blob = opt.getvalue()
                        if len(opt_blob) <= len(blob):
                            blob = opt_blob
                last_blob = blob
                break
            # 按面积比估算下一档，避免 8 档逐级试
            ratio = (target_bytes / len(blob)) ** 0.5 if len(blob) > 0 else 0.8
            ratio = min(0.9, max(0.5, ratio * 0.95))
            edge = max(MIN_EDGE, int(edge * ratio))
            if edge <= MIN_EDGE:
                last_blob = blob
                break
        with open(output_path, "wb") as f:
            f.write(last_blob)
        logger.info(f"[xb2img] APNG 输出 {len(last_blob)//1024}KB")
        return output_path
    finally:
        with suppress(Exception):
            im_a.close()
        with suppress(Exception):
            im_b.close()
