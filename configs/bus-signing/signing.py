"""Подпись сообщений межагентной шины на Ed25519.

Отправитель (оркестратор) держит приватный ключ и подписывает каждое сообщение;
получатели держат только публичный и проверяют подпись до того, как что-то сделать.
Атакующий, дотянувшийся до брокера, может положить сообщение в очередь, но не может
изготовить действительную подпись — ради этого всё и делается.

Главная строка здесь — `verify` возвращает False при ОТСУТСТВИИ подписи. Проверка,
которая на неподписанное сообщение отвечает «ну ладно», не проверка, а украшение.
"""
import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _canonical(payload: dict, sender: str) -> bytes:
    """Байты, которые покрывает подпись: только полезная нагрузка и отправитель.

    Сортировка ключей и отсутствие пробелов обязательны: подпись должна считаться
    одинаково у отправителя и получателя, а порядок ключей в словаре гарантий не даёт.
    """
    return json.dumps({"payload": payload, "sender": sender},
                      sort_keys=True, separators=(",", ":")).encode()


def load_private(path: str) -> Ed25519PrivateKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def load_public(path: str) -> Ed25519PublicKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_public_key(fh.read())


def make_envelope(payload: dict, sender: str, *,
                  private_key: Ed25519PrivateKey | None = None,
                  meta: dict | None = None) -> dict:
    """Конверт для шины. С приватным ключом — подписанный, без него — нет.

    Возможность собрать неподписанный конверт оставлена намеренно: именно так выглядит
    сообщение атакующего, и на нём проверяется, что получатель его отвергает.
    """
    envelope = {"payload": payload, "sender": sender, "sig_present": False,
                "signature": None, "meta": meta or {}}
    if private_key is not None:
        signature = private_key.sign(_canonical(payload, sender))
        envelope["signature"] = base64.b64encode(signature).decode()
        envelope["sig_present"] = True
    return envelope


def verify(envelope: dict, public_key: Ed25519PublicKey) -> bool:
    """True только для присутствующей и криптографически верной подписи."""
    if not envelope.get("sig_present") or not envelope.get("signature"):
        return False
    try:
        public_key.verify(
            base64.b64decode(envelope["signature"]),
            _canonical(envelope["payload"], envelope["sender"]),
        )
        return True
    except InvalidSignature:
        return False
