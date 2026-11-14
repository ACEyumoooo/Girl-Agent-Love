# Modified for GalGameFramework 1.7.4 (2026-11-10): writable per-project settings fallback.
# Modified for GalGameFramework 1.7.3 (2026-11-10): reuse unique atomic writer; preserve backups.
init -9 python:
    """options.txt 的读写：启动读一次、内存是唯一真相、保存时整份原子重写、
    缺项用默认、非法值回退、未知键保留、密钥单独放 key.txt、退出时再写一次。"""

    import os
    import io
    import shutil
    import time
    import hashlib
    import sys

    OPTIONS_FILE_VERSION = 1
    OPTIONS_UNKNOWN = {}
    OPTIONS_SECRETS = {}
    OPTIONS_KEY_EXTRA = {}

    _OPTIONS_SELECTED_BASE = None

    def _options_writable(directory):
        temporary = None
        fd = None
        try:
            os.makedirs(directory, exist_ok=True)
            fd, temporary = exclusive_temp_file(directory, ".settings-probe-")
            stream = os.fdopen(fd, "wb")
            fd = None
            with stream:
                stream.write(b"settings")
                stream.flush()
                os.fsync(stream.fileno())
            return True
        except OSError:
            return False
        finally:
            if fd is not None:
                os.close(fd)
            if temporary is not None:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    def _options_platform_data():
        if sys.platform == "win32":
            return os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~/AppData/Local")
        if sys.platform == "darwin":
            return os.path.expanduser("~/Library/Application Support")
        return os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")

    def _options_base():
        global _OPTIONS_SELECTED_BASE
        if _OPTIONS_SELECTED_BASE is not None:
            return _OPTIONS_SELECTED_BASE
        basedir = getattr(renpy.config, "basedir", None) or os.getcwd()
        project = hashlib.sha256(os.path.normcase(os.path.realpath(basedir)).encode("utf-8")).hexdigest()[:20]
        candidates = [basedir]
        savedir = getattr(renpy.config, "savedir", None)
        if savedir:
            candidates.append(os.path.join(savedir, "settings", project))
        candidates.append(os.path.join(_options_platform_data(), "GalGameFramework", "settings", project))
        # Continue using saved fallback settings if install permissions change.
        established = [candidate for candidate in candidates[1:]
                       if any(os.path.isfile(os.path.join(candidate, name))
                              for name in ("options.txt", "key.txt"))]
        candidates = established + [candidate for candidate in candidates if candidate not in established]
        for candidate in candidates:
            if not _options_writable(candidate):
                continue
            _OPTIONS_SELECTED_BASE = candidate
            if os.path.realpath(candidate) != os.path.realpath(basedir):
                for name in ("options.txt", "key.txt"):
                    target = os.path.join(candidate, name)
                    source = os.path.join(basedir, name)
                    if os.path.lexists(target) or not os.path.isfile(source):
                        continue
                    try:
                        with open(source, "rb") as stream:
                            raw = stream.read()
                        atomic_write_file(target, raw, binary=True)
                    except OSError:
                        pass
            return candidate
        _OPTIONS_SELECTED_BASE = basedir
        return basedir

    def _options_file(name):
        return os.path.join(_options_base(), name)

    def options_log(msg):
        try:
            with io.open(_options_file("options.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + chr(10))
        except OSError:
            pass

    def _options_read(name):
        data = {}
        try:
            with io.open(_options_file(name), "r", encoding="utf-8-sig") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    data[k.strip()] = v.strip().strip('"').strip("'")
        except OSError:
            pass
        return data

    def _options_raw(name):
        try:
            with io.open(_options_file(name), "r", encoding="utf-8-sig") as f:
                return f.read()
        except OSError:
            return ""

    def _options_valid(kind, value):
        v = str(value or "").strip()
        if not v or kind == "secret":
            return True
        if kind == "switch":
            if v.lower() in ("0", "1", "true", "false", "yes", "no", "on", "off"):
                return True
            # 有些 0/1 默认值的项其实是计数（思考预算、临时角色上限），
            # 允许任何整数，只是界面上仍按开关展示。
            try:
                int(v)
                return True
            except ValueError:
                return False
        if kind == "int":
            try:
                int(v)
                return True
            except ValueError:
                return False
        if kind == "float":
            try:
                float(v)
                return True
            except ValueError:
                return False
        return True

    def _atomic_write(name, text, backup=True):
        path = _options_file(name)
        try:
            if backup and os.path.exists(path):
                shutil.copy2(path, path + ".bak")
            atomic_write_file(path, text)
            return True
        except OSError as exc:
            options_log("write %s fail: %s" % (name, exc))
            return False

    def options_write(values, unknown=None, key_extra=None):
        """整份重写。values 里包含普通项和密钥；密钥写进 key.txt。"""
        if unknown is None:
            unknown = OPTIONS_UNKNOWN
        if key_extra is None:
            key_extra = OPTIONS_KEY_EXTRA
        lines = ["GALGAME_OPTIONS_VERSION=%d" % OPTIONS_FILE_VERSION]
        for key in OPTIONS_KNOWN_KEYS:
            if key in OPTIONS_SECRET_KEYS:
                continue
            value = values.get(key, OPTIONS_DEFAULTS.get(key, ""))
            lines.append("%s=%s" % (key, str(value)))
        for key in sorted(unknown):
            lines.append("%s=%s" % (key, str(unknown[key])))
        ok = _atomic_write("options.txt", chr(10).join(lines) + chr(10))

        key_lines = []
        for key in OPTIONS_SECRET_KEYS:
            value = values.get(key, OPTIONS_SECRETS.get(key, ""))
            key_lines.append("%s=%s" % (key, str(value)))
        for key in sorted(key_extra):
            key_lines.append("%s=%s" % (key, str(key_extra[key])))
        ok_key = _atomic_write("key.txt", chr(10).join(key_lines) + chr(10))
        return ok and ok_key

    def options_boot():
        """启动时读入并迁移。返回合并后的配置字典。"""
        global OPTIONS_UNKNOWN, OPTIONS_SECRETS, OPTIONS_KEY_EXTRA
        data = _options_read("options.txt")
        keydata = _options_read("key.txt")
        raw = _options_raw("options.txt")

        unknown = {
            k: v for k, v in data.items()
            if k not in OPTIONS_KNOWN_KEYS and k != "GALGAME_OPTIONS_VERSION"
        }
        key_extra = {
            k: v for k, v in keydata.items()
            if k not in OPTIONS_SECRET_KEYS and v
        }
        secrets = {}
        moved_secret = False
        for key in OPTIONS_SECRET_KEYS:
            if keydata.get(key):
                secrets[key] = keydata[key]
            elif data.get(key):
                secrets[key] = data[key]
                moved_secret = True
                options_log("move %s from options.txt to key.txt" % key)

        clean = {}
        invalid = False
        for key in OPTIONS_KNOWN_KEYS:
            if key in OPTIONS_SECRET_KEYS or key not in data:
                continue
            value = data[key]
            kind = OPTIONS_KINDS.get(key, "text")
            if _options_valid(kind, value):
                clean[key] = value
            else:
                invalid = True
                options_log("invalid %s=%r, use default %r" % (key, value, OPTIONS_DEFAULTS.get(key, "")))

        has_version = ("GALGAME_OPTIONS_VERSION=" in raw)
        has_secret_lines = any(data.get(k) for k in OPTIONS_SECRET_KEYS)
        if (not raw) or (not has_version) or has_secret_lines or moved_secret or invalid:
            values = dict(clean)
            values.update(secrets)
            options_write(values, unknown, key_extra)

        OPTIONS_UNKNOWN = unknown
        OPTIONS_SECRETS = secrets
        OPTIONS_KEY_EXTRA = key_extra
        merged = dict(clean)
        merged.update(unknown)
        merged.update(secrets)
        merged.update(key_extra)
        return merged

    def options_current_values(cfg):
        """从内存配置取一份完整快照，缺项补默认值。"""
        values = {}
        for key in OPTIONS_KNOWN_KEYS:
            values[key] = str(cfg.get(key, OPTIONS_DEFAULTS.get(key, "")))
        return values
