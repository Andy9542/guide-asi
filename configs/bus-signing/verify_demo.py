#!/usr/bin/env python3
"""Проверка всех концов: что принимается, что отвергается и что не роняет процесс.

    python3 verify_demo.py <каталог_с_ключами>

Контроль, у которого проверена только сторона «блокирует плохое», наполовину не проверен.
Здесь проверяются обе, плюс поведение на заведомо враждебном входе.
"""
import copy
import json
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import signing

keys = sys.argv[1] if len(sys.argv) > 1 else "."
private = signing.load_private(f"{keys}/bus_private.pem")
public = signing.load_public(f"{keys}/bus_public.pem")

#: Получатель, от имени которого здесь проверяются конверты.
ME = "validator"
#: Один guard на получателя на весь поток сообщений — а не новый на каждый вызов:
#: guard, созданный на вызов, помнит один конверт и повтор не отличает от первого.
GUARD = signing.ReplayGuard()

task = {"task_id": "pay-1842", "action": "validate_transfer", "amount": 1250}

legit = signing.make_envelope(task, "orchestrator", ME, private_key=private,
                              meta={"priority": "normal"})
unsigned = signing.make_envelope(task, "orchestrator", ME)
forged = signing.make_envelope(task, "orchestrator", ME,
                               private_key=Ed25519PrivateKey.generate())

tampered_meta = copy.deepcopy(legit)
tampered_meta["meta"]["priority"] = "urgent"

tampered_payload = copy.deepcopy(legit)
tampered_payload["payload"]["amount"] = 999999

# Поле, которого в конверте не было: список подписываемых полей его бы не заметил.
smuggled = copy.deepcopy(legit)
smuggled["approved_by"] = "security-team"

no_recipient = copy.deepcopy(legit)
del no_recipient["recipient"]

# Положительные сценарии после первого — на свежих конвертах: nonce у legit один, и
# GUARD его уже запомнил.
fresh = signing.make_envelope(task, "orchestrator", ME, private_key=private)

checks = [
    ("подписанное настоящим ключом принимается",
     signing.verify(legit, public, recipient=ME, guard=GUARD) is True),
    ("неподписанное отвергается",
     signing.verify(unsigned, public, recipient=ME, guard=GUARD) is False),
    ("подписанное чужим ключом отвергается",
     signing.verify(forged, public, recipient=ME, guard=GUARD) is False),
    ("изменённая полезная нагрузка отвергается",
     signing.verify(tampered_payload, public, recipient=ME, guard=GUARD) is False),
    ("изменённое поле meta отвергается",
     signing.verify(tampered_meta, public, recipient=ME, guard=GUARD) is False),
    ("дописанное поле верхнего уровня отвергается",
     signing.verify(smuggled, public, recipient=ME, guard=GUARD) is False),
    ("конверт для другого получателя отвергается",
     signing.verify(legit, public, recipient="executor", guard=GUARD) is False),
    ("конверт без адресата отвергается",
     signing.verify(no_recipient, public, recipient=ME, guard=GUARD) is False),
    ("конверт, прошедший через json, принимается",
     signing.verify(json.loads(json.dumps(fresh)), public, recipient=ME,
                    guard=GUARD) is True),
]

# Повтор: тот же конверт, поданный дважды одному GUARD, второй раз не принимается.
replayed = signing.make_envelope(task, "orchestrator", ME, private_key=private)
first = signing.verify(replayed, public, recipient=ME, guard=GUARD)
second = signing.verify(copy.deepcopy(replayed), public, recipient=ME, guard=GUARD)
checks.append(("повтор того же конверта отвергается", first is True and second is False))

# Без guard сообщение не допускается: TypeError, а не молчаливое True (R5).
no_guard = []
for kwargs in ({}, {"guard": None}):
    try:
        signing.verify(fresh, public, recipient=ME, **kwargs)
        no_guard.append("принято")
    except TypeError:
        no_guard.append("TypeError")
checks.append(("verify без guard — TypeError, а не пропуск повтора",
               no_guard == ["TypeError", "TypeError"]))

# Переполнение: заполненный guard отказывает, а не вытесняет свежие записи. Здесь
# намеренно отдельный guard с крошечным limit — GUARD получателя не заполнить.
small = signing.ReplayGuard(limit=3)
burst = [signing.verify(signing.make_envelope(task, "orchestrator", ME,
                                              private_key=private),
                        public, recipient=ME, guard=small)
         for _ in range(4)]
checks.append(("заполненный ReplayGuard отказывает, а не растёт",
               burst == [True, True, True, False] and len(small) == 3))

# Время: bool — не число, nan и 10**400 не превращаются в момент времени.
bad_ts = [True, float("nan"), 10 ** 400]
checks.append(("нечисловое и невозможное время отвергается", all(
    signing.verify(signing.make_envelope(task, "orchestrator", ME,
                                         private_key=private, ts=value),
                   public, recipient=ME, guard=GUARD) is False
    for value in bad_ts)))

# Враждебный вход: verify обязан вернуть False, а не выбросить исключение.
# Полезная нагрузка глубиной 20 000 уровней: json.dumps в _canonical падает RecursionError,
# и verify обязан вернуть False, а не исключение.
deep = {}
node = deep
for _ in range(20_000):
    node["a"] = {}
    node = node["a"]
hostile = [
    None, "строка", 42, {},
    {"sig_present": True, "signature": None, "recipient": ME},
    {"sig_present": True, "signature": "не base64!!", "recipient": ME},
    {"sig_present": True, "signature": "AAAA", "recipient": ME},
    {"sig_present": True, "signature": "AAAA", "payload": object, "recipient": ME},
    {"sig_present": True, "signature": "AAAA", "recipient": ME, 42: "ключ не строка"},
    {"sig_present": True, "signature": "AAAA", "recipient": ME, "payload": deep},
]
ok = True
for bad in hostile:
    try:
        if signing.verify(bad, public, recipient=ME, guard=GUARD) is not False:
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
