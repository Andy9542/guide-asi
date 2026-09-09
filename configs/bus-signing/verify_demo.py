#!/usr/bin/env python3
"""Проверка обоих концов: подписанное принимается, неподписанное и чужое — нет.

    python3 verify_demo.py <каталог_с_ключами>

Контроль, у которого проверена только сторона «блокирует плохое», наполовину не проверен.
"""
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import signing

keys = sys.argv[1] if len(sys.argv) > 1 else "."
private = signing.load_private(f"{keys}/bus_private.pem")
public = signing.load_public(f"{keys}/bus_public.pem")

task = {"task_id": "pay-1842", "action": "validate_transfer", "amount": 1250}

legit = signing.make_envelope(task, "orchestrator", private_key=private)
unsigned = signing.make_envelope(task, "orchestrator")
forged = signing.make_envelope(task, "orchestrator", private_key=Ed25519PrivateKey.generate())

checks = [
    ("подписанное настоящим ключом принимается", signing.verify(legit, public) is True),
    ("неподписанное отвергается", signing.verify(unsigned, public) is False),
    ("подписанное чужим ключом отвергается", signing.verify(forged, public) is False),
]

failed = 0
for name, ok in checks:
    print(f"[{'ok' if ok else 'ПРОВАЛ'}] {name}")
    failed += not ok

raise SystemExit(1 if failed else 0)
