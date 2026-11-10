# -*- coding: utf-8 -*-
"""把 send_bodies_9.json 的 9 条真源正文段逐字节落成 paste_<id>.txt，供发图时逐字复制。

不加工：只从存档 body 字段原样写出，写完回读比对 sha256，防写出侧字符损坏。
"""
import hashlib
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with io.open(os.path.join(HERE, "send_bodies_9.json"), encoding="utf-8") as fh:
    BODIES = json.load(fh)

for loc_id in sorted(BODIES):
    body = BODIES[loc_id]["body"]
    path = os.path.join(HERE, "paste_%s.txt" % loc_id)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(body)
    with io.open(path, encoding="utf-8") as _fh:
        back = _fh.read()
    assert back == body, loc_id
    print("%s %s %d 字 %s" % (loc_id, BODIES[loc_id]["size"], len(body),
                              hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]))
