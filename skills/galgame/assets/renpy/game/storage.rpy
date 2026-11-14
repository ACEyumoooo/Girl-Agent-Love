# Modified for GalGameFramework 1.7.4 (2026-11-10): bounded exclusive temporary creation on denied Windows ACLs.
# Modified for GalGameFramework 1.7.3 (2026-11-10): shared durable atomic writes.
init -11 python:
    import os
    import uuid

    def exclusive_temp_file(directory, prefix):
        """Only name collisions retry; denied Windows ACLs must fail immediately."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        for _attempt in range(16):
            path = os.path.join(directory, prefix + uuid.uuid4().hex)
            try:
                return os.open(path, flags, 0o600), path
            except FileExistsError:
                continue
        raise FileExistsError("Could not create a unique temporary file after 16 attempts")

    def atomic_write_file(path, data, binary=False):
        """Replace a complete file using an exclusively created same-directory temp."""
        directory = os.path.dirname(os.path.abspath(path))
        fd, temporary = exclusive_temp_file(directory, os.path.basename(path) + ".tmp-")
        try:
            stream = os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8", "newline": "\n"}))
            fd = None
            with stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.remove(temporary)
            except FileNotFoundError:
                pass
