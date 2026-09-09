"""Подпись сообщений межагентной шины на Ed25519.

Отправитель (оркестратор) держит приватный ключ и подписывает каждое сообщение;
получатели держат только публичный и проверяют подпись до того, как что-то сделать.
Атакующий, дотянувшийся до брокера, может положить сообщение в очередь, но не может
изготовить действительную подпись — ради этого всё и делается.

Три вещи, которые легко упустить и каждая из которых сводит подпись на нет:

1. **Подписывать надо ВСЁ, что получатель прочитает.** Первая редакция покрывала только
   payload и sender, а поле meta оставляла снаружи — его можно было переписать целиком,
   и подпись оставалась верной.
2. **Подпись без одноразового идентификатора не защищает от повтора.** Снятый с шины
   легитимный конверт можно положить в очередь ещё раз, и он пройдёт проверку. Для
   «переведи 1250» это ровно та атака, ради которой всё затевалось.
3. **verify() обязан возвращать False, а не падать.** На вход приходит враждебный
   объект: без ключей, с не-base64 подписью, с чем угодно. Исключение вместо False —
   это отказ обслуживания, а при неаккуратном except — пропуск сообщения.
"""
import base64
import json
import secrets
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: Поля конверта, которые покрывает подпись. signature и sig_present исключены —
#: они и есть результат подписи. Всё остальное, что читает получатель, входит сюда.
SIGNED_FIELDS = ("payload", "sender", "meta", "nonce", "ts")


def _canonical(envelope: dict) -> bytes:
    """Байты, которые покрывает подпись.

    Сортировка ключей и отсутствие пробелов обязательны: подпись должна считаться
    одинаково у отправителя и получателя, а порядок ключей в словаре гарантий не даёт.
    """
    body = {k: envelope.get(k) for k in SIGNED_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def load_private(path: str) -> Ed25519PrivateKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def load_public(path: str) -> Ed25519PublicKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_public_key(fh.read())


def make_envelope(payload: dict, sender: str, *,
                  private_key: Ed25519PrivateKey | None = None,
                  meta: dict | None = None,
                  nonce: str | None = None,
                  ts: float | None = None) -> dict:
    """Конверт для шины. С приватным ключом — подписанный, без него — нет.

    Возможность собрать неподписанный конверт оставлена намеренно: именно так выглядит
    сообщение атакующего, и на нём проверяется, что получатель его отвергает.
    """
    envelope = {
        "payload": payload,
        "sender": sender,
        "meta": meta or {},
        # secrets, а не hash(): hash() рандомизируется от запуска к запуску, но внутри
        # одного процесса детерминирован, и на одинаковой нагрузке в одну наносекунду
        # дал бы совпадающий nonce.
        "nonce": nonce if nonce is not None else secrets.token_urlsafe(16),
        "ts": ts if ts is not None else time.time(),
        "sig_present": False,
        "signature": None,
    }
    if private_key is not None:
        envelope["signature"] = base64.b64encode(
            private_key.sign(_canonical(envelope))).decode()
        envelope["sig_present"] = True
    return envelope


class ReplayGuard:
    """Отсекает повторную подачу уже принятого конверта.

    Держит окно свежести и множество увиденных nonce. В продакшене состояние должно
    быть общим для всех экземпляров получателя и переживать перезапуск — иначе рестарт
    открывает окно для повтора. Здесь оно в памяти: этого хватает для одного процесса
    и честно называется своим именем.
    """

    def __init__(self, window_seconds: float = 300.0, limit: int = 100_000):
        self.window = window_seconds
        self.limit = limit
        self._seen: dict[str, float] = {}

    def accept(self, envelope: dict, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        ts = envelope.get("ts")
        nonce = envelope.get("nonce")
        if not isinstance(ts, (int, float)) or not isinstance(nonce, str) or not nonce:
            return False
        if abs(now - ts) > self.window:
            return False
        if nonce in self._seen:
            return False
        if len(self._seen) >= self.limit:
            cutoff = now - self.window
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        self._seen[nonce] = now
        return True


def verify(envelope: dict, public_key: Ed25519PublicKey,
           guard: "ReplayGuard | None" = None) -> bool:
    """True только для присутствующей, верной и (если передан guard) не повторной подписи.

    Никогда не выбрасывает исключение на враждебном входе: любой мусор — это False.
    """
    if not isinstance(envelope, dict):
        return False
    if not envelope.get("sig_present") or not isinstance(envelope.get("signature"), str):
        return False
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        public_key.verify(signature, _canonical(envelope))
    # binascii.Error — подкласс ValueError, отдельно ловить не нужно.
    except (InvalidSignature, ValueError, TypeError):
        return False
    if guard is not None and not guard.accept(envelope):
        return False
    return True
