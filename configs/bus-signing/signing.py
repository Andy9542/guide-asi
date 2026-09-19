"""Подпись сообщений межагентной шины на Ed25519.

Отправитель (оркестратор) держит приватный ключ и подписывает каждое сообщение;
получатели держат только публичный и проверяют подпись до того, как что-то сделать.
Атакующий, дотянувшийся до брокера, может положить сообщение в очередь, но не может
изготовить действительную подпись — ради этого всё и делается.

Четыре вещи, которые легко упустить и каждая из которых сводит подпись на нет:

1. **Подписывать надо ВСЁ, что получатель прочитает.** Первая редакция перечисляла
   подписываемые поля списком, и любое поле мимо списка — например, дописанное
   `approved_by` — конверт нёс без подписи. Список здесь запретный: подпись покрывает
   всё, кроме самой подписи, и новое поле попадает под неё само.
2. **Конверт без адресата действителен для кого угодно.** Сообщение, снятое с шины и
   переложенное другому получателю, проходит проверку подписи: она говорит, кто
   отправил, и молчит о том, кому. Поэтому `recipient` лежит в конверте под подписью,
   а `verify()` требует назвать себя.
3. **Подпись без одноразового идентификатора не защищает от повтора.** Снятый с шины
   легитимный конверт можно положить в очередь ещё раз, и он пройдёт проверку. Для
   «переведи 1250» это ровно та атака, ради которой всё затевалось.
4. **verify() обязан возвращать False, а не падать.** На вход приходит враждебный
   объект: без ключей, с не-base64 подписью, с чем угодно. Исключение вместо False —
   это отказ обслуживания, а при неаккуратном except — пропуск сообщения.
"""
import base64
import heapq
import json
import math
import secrets
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

#: Единственные поля конверта, которые подпись НЕ покрывает: они и есть её результат.
#: Список запретный, а не разрешительный — поле, о котором здесь забыли, окажется
#: подписанным, а не бесконтрольным.
UNSIGNED_FIELDS = frozenset({"signature", "sig_present"})


def _canonical(envelope: dict) -> bytes:
    """Байты, которые покрывает подпись: весь конверт, кроме UNSIGNED_FIELDS.

    Сортировка ключей и отсутствие пробелов обязательны: подпись должна считаться
    одинаково у отправителя и получателя, а порядок ключей в словаре гарантий не даёт.
    Сама канонизация Python-специфична (json.dumps), поэтому получателю на другом языке
    пересобирать её не надо: конверт передаётся байтами как есть, и проверяются они.
    """
    body = {k: v for k, v in envelope.items() if k not in UNSIGNED_FIELDS}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def load_private(path: str) -> Ed25519PrivateKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def load_public(path: str) -> Ed25519PublicKey:
    with open(path, "rb") as fh:
        return serialization.load_pem_public_key(fh.read())


def make_envelope(payload: dict, sender: str, recipient: str, *,
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
        "recipient": recipient,
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

    Держит окно свежести и множество увиденных nonce; limit — жёсткий потолок памяти:
    заполненный guard отказывает (fail closed), а не вытесняет записи, иначе поток
    свежих конвертов вымывает из памяти тот самый nonce, ради которого всё и заведено.
    В продакшене состояние должно быть общим для всех экземпляров получателя и
    переживать перезапуск — иначе рестарт открывает окно для повтора. Здесь оно в
    памяти: этого хватает для одного процесса и честно называется своим именем.
    """

    def __init__(self, window_seconds: float = 300.0, limit: int = 100_000,
                 skew_seconds: float = 30.0):
        self.window = window_seconds
        self.limit = limit
        self.skew = skew_seconds
        self._seen: set[str] = set()
        #: Куча (ts + window, nonce): просроченные выталкиваются за O(log n), а не
        #: пересборкой всего множества.
        self._expiry: list[tuple[float, str]] = []

    def __len__(self) -> int:
        return len(self._seen)

    def accept(self, envelope: dict, *, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        ts = envelope.get("ts")
        nonce = envelope.get("nonce")
        if not isinstance(nonce, str) or not nonce:
            return False
        # bool — подкласс int, и True прошёл бы как момент времени 1970-01-01T00:00:01.
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            return False
        try:
            ts = float(ts)
        except OverflowError:
            return False
        # ts из будущего дальше skew отвергается: иначе его запись жила бы до 2·window.
        if not math.isfinite(ts) or ts > now + self.skew or now - ts > self.window:
            return False
        while self._expiry and self._expiry[0][0] < now:
            _, expired = heapq.heappop(self._expiry)
            self._seen.discard(expired)
        if nonce in self._seen or len(self._seen) >= self.limit:
            return False
        self._seen.add(nonce)
        heapq.heappush(self._expiry, (ts + self.window, nonce))
        return True


def verify(envelope: dict, public_key: Ed25519PublicKey, *, recipient: str,
           guard: "ReplayGuard | None" = None) -> bool:
    """True только для присутствующей, верной, адресованной вам и не повторной подписи.

    recipient — кто проверяет: конверт, выписанный другому получателю, отвергается.
    Никогда не выбрасывает исключение на враждебном входе: любой мусор — это False.
    Ошибка вызывающего — другое дело: без recipient проверка бессмысленна, поэтому
    здесь TypeError, а не молчаливое True.
    """
    if not isinstance(recipient, str) or not recipient:
        raise TypeError("recipient: непустая строка — имя того, кто проверяет конверт")
    if not isinstance(envelope, dict):
        return False
    if not envelope.get("sig_present") or not isinstance(envelope.get("signature"), str):
        return False
    if envelope.get("recipient") != recipient:
        return False
    try:
        signature = base64.b64decode(envelope["signature"], validate=True)
        public_key.verify(signature, _canonical(envelope))
    # binascii.Error — подкласс ValueError, отдельно ловить не нужно.
    # RecursionError: полезная нагрузка глубиной в десятки тысяч уровней роняет json.dumps —
    # это тоже мусор на входе, а не повод для исключения.
    except (InvalidSignature, ValueError, TypeError, RecursionError):
        return False
    if guard is not None and not guard.accept(envelope):
        return False
    return True
