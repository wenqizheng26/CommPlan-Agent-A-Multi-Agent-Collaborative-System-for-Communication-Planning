"""Windows file-payload observations and controlled archive/restore primitives."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import unicodedata
import zipfile

SCHEMA = "commplan-history-file-payload-v1"
CHUNK_SIZE = 1024 * 1024
ALGORITHMS = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
REPARSE_ATTRIBUTE = 0x400
KNOWN_REPARSE = {0xA0000003: "junction", 0xA000000C: "symlink"}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DEVICE = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?\Z", re.I)


class ArchiveError(ValueError):
    """An explicit archive gap, unsafe path or integrity failure."""


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ArchiveError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid(value):
        raise ArchiveError("non-finite JSON number: " + value)

    with open(path, "r", encoding="utf-8") as source:
        return json.load(source, object_pairs_hook=pairs, parse_constant=invalid)


def write_exclusive(path, data):
    with open(path, "xb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())


def sha256_file(path):
    digest = hashlib.sha256()
    count = 0
    with open(path, "rb") as source:
        while block := source.read(CHUNK_SIZE):
            digest.update(block)
            count += len(block)
    return count, digest.hexdigest()


def is_reparse(path):
    value = Path(path).lstat()
    return stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & REPARSE_ATTRIBUTE)


def plain_absolute(path, *, must_exist=True):
    """Reject reparse ancestors before resolving, including an existing final path."""
    path = Path(path)
    if not path.is_absolute():
        raise ArchiveError("absolute path required: " + str(path))
    path = Path(os.path.abspath(path))
    for component in reversed((path, *path.parents)):
        try:
            if is_reparse(component):
                raise ArchiveError("reparse path component: " + str(component))
        except FileNotFoundError:
            if must_exist or component != path:
                raise
    if must_exist and not path.exists():
        raise ArchiveError("missing path: " + str(path))
    return path


def plain_resolved(path, *, must_exist=True):
    """Expand existing aliases only after refusing reparse ancestors; keep source paths elsewhere."""
    path = plain_absolute(path, must_exist=must_exist)
    resolved = path.resolve(strict=must_exist)
    return plain_absolute(resolved, must_exist=must_exist)


def within(path, root):
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


def safe_member(name, directory=False):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ArchiveError("invalid ZIP path")
    body = name[:-1] if directory and name.endswith("/") else name
    if not body or name.startswith("/") or (name.endswith("/") and not directory):
        raise ArchiveError("non-relative ZIP path: " + name)
    for component in body.split("/"):
        if (not component or component in {".", ".."} or ":" in component
                or component[-1:] in {" ", "."} or DEVICE.fullmatch(component)
                or any(ord(c) < 32 or c in '<>"|?*' for c in component)):
            raise ArchiveError("unsafe Windows member: " + name)
    return body


def member_table(items):
    """Validate complete member names, Windows collisions and file-prefix conflicts."""
    result = {}
    canonical = {}
    for name, directory in items:
        body = safe_member(name, directory)
        key = unicodedata.normalize("NFC", body).casefold()
        if name in result or key in canonical:
            raise ArchiveError("duplicate/colliding member: " + name)
        result[name] = directory
        canonical[key] = directory
    for key in canonical:
        components = key.split("/")
        for index in range(1, len(components)):
            parent = "/".join(components[:index])
            if parent in canonical and not canonical[parent]:
                raise ArchiveError("file/directory prefix conflict: " + key)
    return result


def publish(part, destination):
    """Same-volume non-overwriting hardlink publication; preserve part on failure."""
    plain_absolute(Path(destination).parent)
    os.link(part, destination)
    Path(part).unlink()


if os.name == "nt":
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    class FileInfo(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("creation", wintypes.FILETIME),
                    ("access", wintypes.FILETIME), ("write", wintypes.FILETIME),
                    ("volume", wintypes.DWORD), ("size_high", wintypes.DWORD),
                    ("size_low", wintypes.DWORD), ("links", wintypes.DWORD),
                    ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD)]

    class StreamInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", wintypes.WCHAR * 296)]

    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInfo)]
    kernel.FindFirstStreamW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(StreamInfo), wintypes.DWORD]
    kernel.FindFirstStreamW.restype = wintypes.HANDLE
    kernel.FindNextStreamW.argtypes = [wintypes.HANDLE, ctypes.POINTER(StreamInfo)]
    kernel.FindClose.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD,
                                           ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
                                           ctypes.POINTER(ctypes.c_void_p)]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD)]
    advapi.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.WORD),
                                                   ctypes.POINTER(wintypes.DWORD)]


def _windows():
    if os.name != "nt":
        raise ArchiveError("GAP: Windows identity/streams/ACL APIs required")


def _extended(path):
    text = str(path)
    if text.startswith("\\\\?\\"):
        return text
    return "\\\\?\\UNC\\" + text[2:] if text.startswith("\\\\") else "\\\\?\\" + text


def _handle(path, access=0, *, share=7, creation=3):
    _windows()
    value = kernel.CreateFileW(_extended(path), access, share, None, creation, 0x02200000, None)
    if value == INVALID_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def _handle_info(handle):
    value = FileInfo()
    if not kernel.GetFileInformationByHandle(handle, ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def file_identity(path):
    handle = _handle(path)
    try:
        value = _handle_info(handle)
        return {"status": "READ", "api": "GetFileInformationByHandle",
                "volume_serial": value.volume, "file_id": (value.index_high << 32) | value.index_low,
                "link_count": value.links}
    finally:
        kernel.CloseHandle(handle)


def enumerate_streams(path):
    _windows()
    value = StreamInfo()
    handle = kernel.FindFirstStreamW(_extended(path), 0, ctypes.byref(value), 0)
    if handle == INVALID_HANDLE:
        error = ctypes.get_last_error()
        if error == 38:
            return {"status": "NO_STREAMS", "api": "FindFirstStreamW", "error_code": error, "names": []}, []
        status = "UNSUPPORTED" if error == 87 else "ERROR"
        raise ArchiveError(f"GAP: stream enumeration {status}, Win32 {error}: {path}")
    rows = []
    try:
        while True:
            name = value.name
            stream_path(path, name)  # Validate the actual names before using them.
            if value.size < 0:
                raise ArchiveError("negative stream size")
            rows.append({"name": name, "size": value.size, "is_default": name == "::$DATA"})
            if not kernel.FindNextStreamW(handle, ctypes.byref(value)):
                error = ctypes.get_last_error()
                if error != 38:
                    raise ArchiveError(f"GAP: FindNextStreamW error {error}: {path}")
                break
    finally:
        kernel.FindClose(handle)
    rows.sort(key=lambda item: item["name"])
    if len({item["name"] for item in rows}) != len(rows):
        raise ArchiveError("duplicate stream name")
    return {"status": "READ", "api": "FindFirstStreamW/FindNextStreamW", "error_code": 0,
            "names": [item["name"] for item in rows]}, rows


def stream_path(host, name):
    if name == "::$DATA":
        return str(host)
    if (not isinstance(name, str) or not name.startswith(":") or not name.endswith(":$DATA")
            or not name[1:-6] or any(c in ":/\\\0" or ord(c) < 32 for c in name[1:-6])):
        raise ArchiveError("unsafe $DATA stream mapping")
    return str(host) + name


def _allocated_text(function, *args):
    pointer = ctypes.c_void_p()
    if not function(*args, ctypes.byref(pointer)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.wstring_at(pointer)
    finally:
        kernel.LocalFree(pointer)


def security_metadata(path):
    _windows()
    owner, group, dacl, descriptor = (ctypes.c_void_p() for _ in range(4))
    result = advapi.GetNamedSecurityInfoW(_extended(path), 1, 7, ctypes.byref(owner), ctypes.byref(group),
                                          ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if result:
        raise ArchiveError(f"GAP: owner/group/DACL read Win32 {result}: {path}")
    try:
        owner_text = _allocated_text(advapi.ConvertSidToStringSidW, owner) if owner else None
        group_text = _allocated_text(advapi.ConvertSidToStringSidW, group) if group else None
        text, length = ctypes.c_void_p(), wintypes.DWORD()
        if not advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor, 1, 4,
                                                                           ctypes.byref(text), ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            dacl_text = ctypes.wstring_at(text)
        finally:
            kernel.LocalFree(text)
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {"status": "RECORD_ONLY", "api": "GetNamedSecurityInfoW", "owner_sid": owner_text,
                "group_sid": group_text, "dacl_sddl": dacl_text, "dacl_control": control.value,
                "dacl_protected": bool(control.value & 0x1000), "sacl": "NOT_READ", "error_code": 0}
    finally:
        kernel.LocalFree(descriptor)


def open_source(host, name="::$DATA"):
    """Open the stream without following a final reparse object; caller checks parents."""
    import msvcrt
    plain_absolute(Path(host).parent)
    if is_reparse(host):
        raise ArchiveError("source changed to reparse object: " + str(host))
    handle = _handle(stream_path(host, name), 0x80000000)
    try:
        if _handle_info(handle).attributes & REPARSE_ATTRIBUTE:
            raise ArchiveError("opened source is a reparse object")
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    return os.fdopen(descriptor, "rb")


@contextmanager
def locked_parent(path, root):
    """Keep the new root/parent chain ordinary and deny directory replacement while writing."""
    _windows()
    path, root = Path(path), plain_absolute(root)
    if not within(path, root) or path == root:
        raise ArchiveError("restore path is outside its new root")
    components = [root]
    for part in path.parent.relative_to(root).parts:
        components.append(components[-1] / part)
    with ExitStack() as stack:
        for directory in components:
            plain_absolute(directory)
            handle = _handle(directory, share=3)  # Do not share DELETE: no rename/reparse swap.
            stack.callback(kernel.CloseHandle, handle)
            attributes = _handle_info(handle).attributes
            if attributes & REPARSE_ATTRIBUTE or not attributes & 0x10:
                raise ArchiveError("restore parent is not an ordinary directory")
        yield


def open_destination(host, name="::$DATA"):
    """CREATE_NEW, no-follow stream write; caller holds locked_parent through close."""
    import msvcrt
    host = Path(host)
    if name != "::$DATA":
        plain_absolute(host)
    else:
        try:
            host.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ArchiveError("restore file already exists: " + str(host))
    handle = _handle(stream_path(host, name), 0x40000000, share=0, creation=1)
    try:
        if _handle_info(handle).attributes & REPARSE_ATTRIBUTE:
            raise ArchiveError("opened restore stream is a reparse object")
        descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(handle)
        raise
    return os.fdopen(descriptor, "wb")


def create_mapped_link(path, target, reparse_type, *, target_is_directory):
    """Create only a new link to an already checked ordinary target in the restore root."""
    path, target = Path(path), plain_absolute(target)
    if reparse_type == "symlink":
        os.symlink(target, path, target_is_directory=target_is_directory)
        return
    if reparse_type != "junction" or not target_is_directory:
        raise ArchiveError("GAP: unsupported restored reparse type/target")
    path.mkdir()  # Exclusive. A failed reparse write leaves an explicit incomplete directory.
    printable = str(target)
    substitute = "\\??\\UNC\\" + printable[2:] if printable.startswith("\\\\") else "\\??\\" + printable
    substitute_bytes, printable_bytes = substitute.encode("utf-16-le"), printable.encode("utf-16-le")
    names = substitute_bytes + b"\0\0" + printable_bytes + b"\0\0"
    data = struct.pack("<IHHHHHH", 0xA0000003, 8 + len(names), 0,
                       0, len(substitute_bytes), len(substitute_bytes) + 2, len(printable_bytes)) + names
    function = kernel.DeviceIoControl
    function.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    function.restype = wintypes.BOOL
    handle = _handle(path, 0x40000000, share=0)
    try:
        if _handle_info(handle).attributes & REPARSE_ATTRIBUTE:
            raise ArchiveError("new junction directory was replaced before reparse creation")
        buffer, returned = ctypes.create_string_buffer(data), wintypes.DWORD()
        if not function(handle, 0x000900A4, buffer, len(data), None, 0, ctypes.byref(returned), None):
            raise ArchiveError(f"GAP: junction creation Win32 {ctypes.get_last_error()}")
    finally:
        kernel.CloseHandle(handle)


BASIC_ATTRIBUTE_MASK = 0x27  # READONLY, HIDDEN, SYSTEM, ARCHIVE; structural/other flags are separate.


def apply_basic_metadata(path, observation):
    """Restore only the promised modification time and four writable basic flags."""
    path = plain_absolute(path)
    os.utime(path, ns=(observation["mtime_ns"], observation["mtime_ns"]))
    function = kernel.SetFileAttributesW
    function.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    function.restype = wintypes.BOOL
    attributes = observation["file_attributes"] & BASIC_ATTRIBUTE_MASK
    if not function(_extended(path), attributes or 0x80):
        raise ArchiveError(f"GAP: basic attributes restore Win32 {ctypes.get_last_error()}")


def hash_source(host, name):
    digest, size = hashlib.sha256(), 0
    with open_source(host, name) as source:
        while block := source.read(CHUNK_SIZE):
            digest.update(block)
            size += len(block)
    return size, digest.hexdigest()


def observe(path, *, hashes=True):
    value = Path(path).lstat()
    reparse = stat.S_ISLNK(value.st_mode) or bool(getattr(value, "st_file_attributes", 0) & REPARSE_ATTRIBUTE)
    result = {"size": value.st_size, "mtime_ns": value.st_mtime_ns, "ctime_ns": value.st_ctime_ns,
              "file_attributes": getattr(value, "st_file_attributes", 0), "file_identity": file_identity(path)}
    if reparse:
        tag = getattr(value, "st_reparse_tag", 0)
        if tag not in KNOWN_REPARSE:
            raise ArchiveError(f"GAP: unknown reparse tag {tag:#x}: {path}")
        result.update(kind="link_record", reparse_type=KNOWN_REPARSE[tag], reparse_tag=tag,
                      target_text=os.readlink(path), streams=[],
                      stream_enumeration={"status": "NOT_RUN_NOFOLLOW", "names": []},
                      security_metadata={"status": "NOT_READ_NOFOLLOW", "sacl": "NOT_READ"})
        return result
    if not (stat.S_ISREG(value.st_mode) or stat.S_ISDIR(value.st_mode)):
        raise ArchiveError("GAP: unsupported source type: " + str(path))
    kind = "regular_file" if stat.S_ISREG(value.st_mode) else "directory"
    enumeration, streams = enumerate_streams(path)
    if kind == "regular_file" and [s for s in streams if s["is_default"]] == []:
        raise ArchiveError("GAP: ordinary file has no enumerated default stream")
    for stream in streams:
        if hashes:
            size, digest = hash_source(path, stream["name"])
            if size != stream["size"]:
                raise ArchiveError("source stream size changed during observation: " + str(path))
            stream["sha256"] = digest
    result.update(kind=kind, stream_enumeration=enumeration, streams=streams,
                  security_metadata=security_metadata(path))
    return result


def compression(member, size):
    extension = Path(member).suffix.lower()
    return zipfile.ZIP_STORED if size >= 128 * 1024 * 1024 or extension in {
        ".zip", ".tar", ".gz", ".7z", ".gguf", ".mp4", ".png", ".jpg", ".pdf"} else zipfile.ZIP_DEFLATED
