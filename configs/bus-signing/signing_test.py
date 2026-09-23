#!/usr/bin/env python3
"""Регрессии на защиту от повтора: R5 (guard обязателен) и R6 (атомарность ReplayGuard).

    python3 signing_test.py         # 0 — все девять тестов сошлись; ключи не нужны

Пара Ed25519 генерируется в памяти. Конкурентные тесты утверждают число принятых
конвертов и согласованность хранилища, а не наличие Lock в исходнике: проверяется
поведение, а не способ его получить.

Барьер стоит на старте потоков, до вызова verify(): барьер внутри критической секции
после исправления дал бы тупик, а не проверку. Но окно между «nonce не видел» и «nonce
запомнил» — пара байткодов, и планировщик в него практически не попадает: на коде без
блокировки барьер на старте не поймал гонку ни разу из 20 прогонов даже при 200 потоках.
Поэтому окно расширяется медленным множеством: `in` и `len` спят несколько миллисекунд.
Без блокировки все потоки проходят проверку разом и все регистрируются; с блокировкой —
по одному.

Чередование на границе истечения окна планировщику не доверено вовсе: часы подменены, а
обёртка над настоящей блокировкой guard останавливает поток ровно на входе в критическую
секцию. Поэтому порядок «свежесть проверена до истечения — запись вытолкнута — секция
занята» воспроизводится каждый прогон, а не изредка.
"""
import copy
import threading
import time
import unittest
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import signing

ME = "validator"
#: Потоки и барьер — с таймаутом: зависший тест должен падать, а не висеть в CI.
JOIN_TIMEOUT = 10.0


class SlowSet(set):
    """set, у которого `in` и `len` спят: расширяет окно гонки, не трогая код guard."""

    def __init__(self, delay):
        super().__init__()
        self.delay = delay

    def __contains__(self, item):
        hit = super().__contains__(item)
        time.sleep(self.delay)
        return hit

    def __len__(self):
        size = super().__len__()
        time.sleep(self.delay)
        return size


def widen(guard, delay=0.005):
    """Подменяет множество увиденных nonce медленным: окно гонки — миллисекунды."""
    guard._seen = SlowSet(delay)
    return guard


class GatedLock:
    """Обёртка над настоящей блокировкой guard: один вход выбранного потока ждёт.

    Останавливает поток `ident` ровно на входе в критическую секцию и ровно один раз:
    len(guard) и приём соседнего конверта берут ту же блокировку из главного потока и
    должны проходить насквозь, иначе тест встал бы на собственной двери.
    """

    def __init__(self, lock):
        self._lock = lock
        #: Поток, который надо остановить; проставляет он сам, перед вызовом verify().
        self.ident = None
        self.at_door = threading.Event()
        self.resume = threading.Event()
        self._gated = False

    def __enter__(self):
        if threading.get_ident() == self.ident and not self._gated:
            self._gated = True
            self.at_door.set()
            if not self.resume.wait(JOIN_TIMEOUT):
                raise AssertionError("поток не отпущен от двери за таймаут")
        return self._lock.__enter__()

    def __exit__(self, *exc_info):
        return self._lock.__exit__(*exc_info)

    def acquire(self, *args, **kwargs):
        return self._lock.acquire(*args, **kwargs)

    def release(self):
        self._lock.release()


def run_threads(n, target):
    """n потоков стартуют по общему барьеру; возвращает результаты, ошибки и зависших."""
    barrier = threading.Barrier(n, timeout=JOIN_TIMEOUT)
    results = [None] * n
    errors = []

    def worker(i):
        try:
            barrier.wait()
            results[i] = target(i)
        except Exception as exc:                  # noqa: BLE001 — падение потока = провал
            errors.append((i, repr(exc)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT)
    hung = [thread.name for thread in threads if thread.is_alive()]
    return results, errors, hung


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = Ed25519PrivateKey.generate()
        cls.public = cls.private.public_key()

    def envelope(self, **kw):
        return signing.make_envelope({"action": "validate_transfer", "amount": 1250},
                                     "orchestrator", ME, private_key=self.private, **kw)

    def test_sequential_replay_rejected(self):
        guard = signing.ReplayGuard()
        env = self.envelope()
        got = [signing.verify(copy.deepcopy(env), self.public, recipient=ME, guard=guard)
               for _ in range(2)]
        self.assertEqual(got, [True, False])
        self.assertEqual(len(guard), 1)

    def test_guard_is_required(self):
        # Пропуск аргумента и явный None — ошибка интеграции, а не свойство конверта.
        env = self.envelope()
        with self.assertRaises(TypeError):
            signing.verify(env, self.public, recipient=ME)
        with self.assertRaises(TypeError):
            signing.verify(env, self.public, recipient=ME, guard=None)

    def test_verify_signature_does_not_guard_replay(self):
        # Ограниченный контракт назван явно: подпись и адресат — да, повтор — нет.
        env = self.envelope()
        got = [signing.verify_signature(env, self.public, recipient=ME) for _ in range(2)]
        self.assertEqual(got, [True, True])
        self.assertFalse(signing.verify_signature(env, self.public, recipient="executor"))
        with self.assertRaises(TypeError):
            signing.verify_signature(env, self.public, recipient="")

    def test_concurrent_same_envelope_accepted_once(self):
        guard = widen(signing.ReplayGuard())
        env = self.envelope()
        n = 8
        results, errors, hung = run_threads(
            n, lambda i: signing.verify(copy.deepcopy(env), self.public,
                                        recipient=ME, guard=guard))
        self.assertEqual(errors, [])
        self.assertEqual(hung, [])
        self.assertEqual(results.count(True), 1, results)
        self.assertEqual(results.count(False), n - 1, results)
        self.assertEqual(len(guard), 1)
        self.assertEqual(len(guard._expiry), 1)

    def test_concurrent_fill_respects_limit(self):
        limit = 10
        guard = widen(signing.ReplayGuard(limit=limit))
        envelopes = [self.envelope() for _ in range(4 * limit)]
        results, errors, hung = run_threads(
            len(envelopes), lambda i: signing.verify(envelopes[i], self.public,
                                                     recipient=ME, guard=guard))
        self.assertEqual(errors, [])
        self.assertEqual(hung, [])
        self.assertEqual(results.count(True), limit, results.count(True))
        self.assertEqual(len(guard), limit)
        self.assertEqual(len(guard._expiry), len(guard._seen))

    def test_concurrent_fill_real_structures(self):
        # Настоящий set без задержек: лимит и согласованность set/кучи под нагрузкой.
        limit = 50
        guard = signing.ReplayGuard(limit=limit)
        envelopes = [self.envelope() for _ in range(4 * limit)]
        results, errors, hung = run_threads(
            len(envelopes), lambda i: signing.verify(envelopes[i], self.public,
                                                     recipient=ME, guard=guard))
        self.assertEqual(errors, [])
        self.assertEqual(hung, [])
        self.assertEqual(results.count(True), limit)
        self.assertEqual(len(guard), limit)
        self.assertEqual(len(guard._expiry), len(guard._seen))

    def test_expiry_boundary_race(self):
        """Повтор на границе истечения окна при чередовании потоков (аудит 23.09.2026).

        Поток A проверяет свежесть E в 1299.9 и встаёт перед блокировкой; в 1300.1
        соседний конверт выталкивает истёкший nonce E. Пока момент времени брался до
        входа в секцию, A шёл дальше со старым `now`, nonce не находил и принимал
        повтор: одним проходом он миновал и «уже видел», и «слишком стар».
        """
        clock = {"now": 1000.0}
        env = self.envelope(ts=1000.0)
        replayed = []

        def present(envelope, guard):
            return signing.verify(copy.deepcopy(envelope), self.public,
                                  recipient=ME, guard=guard)

        with mock.patch.object(signing.time, "time", lambda: clock["now"]):
            guard = signing.ReplayGuard()
            self.assertTrue(present(env, guard))
            # Контроль: до истечения окна повтор отсекается по nonce.
            clock["now"] = 1200.0
            self.assertFalse(present(env, guard))
            # Контроль: после истечения окна E не свеж и без всякого чередования.
            clock["now"] = 1301.0
            self.assertFalse(present(env, signing.ReplayGuard()))

            clock["now"] = 1299.9
            gate = GatedLock(guard._lock)
            guard._lock = gate

            def replay():
                gate.ident = threading.get_ident()
                replayed.append(present(env, guard))

            thread = threading.Thread(target=replay)
            thread.start()
            self.assertTrue(gate.at_door.wait(JOIN_TIMEOUT), "A не дошёл до блокировки")
            clock["now"] = 1300.1
            self.assertTrue(present(self.envelope(ts=1300.1), guard))
            # Соседний конверт вытолкнул истёкшую запись E: в guard остался один nonce.
            self.assertEqual(len(guard), 1)
            gate.resume.set()
            thread.join(timeout=JOIN_TIMEOUT)
            self.assertFalse(thread.is_alive(), "A завис на блокировке")
        self.assertEqual(replayed, [False])
        self.assertEqual(len(guard), 1)

    def test_forged_with_legit_nonce_does_not_block_legit(self):
        # Криптопроверка идёт до регистрации: подделка не занимает место в guard.
        guard = signing.ReplayGuard()
        legit = self.envelope()
        forged = signing.make_envelope(legit["payload"], "orchestrator", ME,
                                       private_key=Ed25519PrivateKey.generate(),
                                       nonce=legit["nonce"], ts=legit["ts"])
        self.assertFalse(signing.verify(forged, self.public, recipient=ME, guard=guard))
        self.assertEqual(len(guard), 0)
        self.assertTrue(signing.verify(legit, self.public, recipient=ME, guard=guard))

    def test_signature_and_recipient_checks_survive(self):
        guard = signing.ReplayGuard()
        legit = self.envelope()
        tampered = copy.deepcopy(legit)
        tampered["payload"]["amount"] = 999999
        smuggled = copy.deepcopy(legit)
        smuggled["approved_by"] = "security-team"
        self.assertFalse(signing.verify(tampered, self.public, recipient=ME, guard=guard))
        self.assertFalse(signing.verify(smuggled, self.public, recipient=ME, guard=guard))
        self.assertFalse(signing.verify(legit, self.public, recipient="executor",
                                        guard=guard))
        for value in (True, float("nan"), 10 ** 400):
            self.assertFalse(signing.verify(self.envelope(ts=value), self.public,
                                            recipient=ME, guard=guard))
        for bad in (None, "строка", 42, {},
                    {"sig_present": True, "signature": "AAAA", "recipient": ME}):
            self.assertFalse(signing.verify(bad, self.public, recipient=ME, guard=guard))
        # Ни один отвергнутый конверт не занял места: место занимают только принятые.
        self.assertEqual(len(guard), 0)


if __name__ == "__main__":
    unittest.main()
