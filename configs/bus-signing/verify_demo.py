#!/usr/bin/env python3
"""Проверка всех концов: что принимается, что отвергается и что не роняет процесс.

    python3 verify_demo.py <каталог_с_ключами>

Контроль, у которого проверена только сторона «блокирует плохое», наполовину не проверен.
Здесь проверяются обе, плюс поведение на заведомо враждебном входе.
"""
import copy
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import signing

keys = sys.argv[1] if len(sys.argv) > 1 else "."
private = signing.load_private(f"{keys}/bus_private.pem")
public = signing.load_public(f"{keys}/bus_public.pem")

task = {"task_id": "pay-1842", "action": "validate_transfer", "amount": 1250}

legit = signing.make_envelope(task, "orchestrator", private_key=private,
                              meta={"priority": "normal"})
unsigned = signing.make_envelope(task, "orchestrator")
forged = signing.make_envelope(task, "orchestrator", private_key=Ed25519PrivateKey.generate())

tampered_meta = copy.deepcopy(legit)
tampered_meta["meta"]["priority"] = "urgent"

tampered_payload = copy.deepcopy(legit)
tampered_payload["payload"]["amount"] = 999999

checks = [
    ("подписанное настоящим ключом принимается",
     signing.verify(legit, public) is True),
    ("неподписанное отвергается",
     signing.verify(unsigned, public) is False),
    ("подписанное чужим ключом отвергается",
     signing.verify(forged, public) is False),
    ("изменённая полезная нагрузка отвергается",
     signing.verify(tampered_payload, public) is False),
    ("изменённое поле meta отвергается",
     signing.verify(tampered_meta, public) is False),
]

# Повтор: тот же конверт, поданный дважды, второй раз не принимается.
guard = signing.ReplayGuard()
first = signing.verify(copy.deepcopy(legit), public, guard=guard)
second = signing.verify(copy.deepcopy(legit), public, guard=guard)
checks.append(("повтор того же конверта отвергается", first is True and second is False))

# Враждебный вход: verify обязан вернуть False, а не выбросить исключение.
hostile = [
    None, "строка", 42, {}, {"sig_present": True, "signature": None},
    {"sig_present": True, "signature": "не base64!!"},
    {"sig_present": True, "signature": "AAAA"},
    {"sig_present": True, "signature": "AAAA", "payload": object},
]
ok = True
for bad in hostile:
    try:
        if signing.verify(bad, public) is not False:
            ok = False
    except Exception as exc:                      # noqa: BLE001 — здесь ловим намеренно
        print(f"  ИСКЛЮЧЕНИЕ на {bad!r}: {type(exc).__name__}")
        ok = False
checks.append(("враждебный вход даёт False, а не исключение", ok))

failed = 0
for name, passed in checks:
    print(f"[{'ok' if passed else 'ПРОВАЛ'}] {name}")
    failed += not passed

raise SystemExit(1 if failed else 0)
