#!/usr/bin/env python3
"""scan_result.py — вердикт этапа Semgrep по его JSON-отчёту и коду возврата.

  python3 scan_result.py <этап> <каталог_проекта> <semgrep.json> <код_semgrep>

Зачем отдельный разбор. «Ноль находок» и «файл не читали» в выводе Semgrep выглядят
одинаково: пропуск по размеру и тайм-аут правила оставляют код 0. Поэтому охват
считается не по отчёту, а по каталогу на хосте: каждый файл профиля обязан оказаться
в `paths.scanned`, а любая запись в `errors[]` означает, что вердикта нет.

stdout — ровно одна строка `scan_result: …`, всё остальное в stderr. Коды:
  0  ЧИСТО      охват полный, блокирующих находок нет
  1  НАХОДКА    есть ERROR; находка важнее неполноты, но неполнота названа в строке
  2  неверный вызов
  3  НЕПОЛНО    вердикта нет: пропуск, тайм-аут, ошибка разбора, симлинк, битый отчёт
  4  НЕТ ВХОДА  в каталоге нет ни одного файла профиля
"""
import json
import os
import sys

# Профиль расширений задан здесь и только здесь; шесть расширений, которые Semgrep
# 1.176.1 берёт в работу по правилу `languages: [javascript]`.
JS_EXTS = ('.js', '.cjs', '.mjs', '.jsx', '.ts', '.tsx')
MOUNT = '/src'  # каталог проекта монтируется в контейнер сюда
SHOWN = 5       # сколько путей и ошибок перечислять в строке вердикта


class Incomplete(Exception):
    """Вердикта нет: вход или отчёт не позволяют утверждать, что охват полный."""


def mounted(project_dir: str, path: str) -> str:
    """Путь на хосте → путь, под которым тот же файл виден Semgrep в контейнере."""
    return MOUNT + '/' + os.path.relpath(path, project_dir).replace(os.sep, '/')


def inventory(project_dir: str) -> set[str]:
    """Файлы профиля в каталоге. Симлинк не разрешается: это заявленная граница."""
    found = set()
    for root, dirs, files in os.walk(project_dir, followlinks=False):
        if '.git' in dirs:
            dirs.remove('.git')
        for name in dirs + files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                raise Incomplete('симлинк в каталоге: %s' % mounted(project_dir, path))
        for name in files:
            if name.endswith(JS_EXTS):
                found.add(mounted(project_dir, os.path.join(root, name)))
    return found


def load_report(path: str) -> dict:
    """Отчёт Semgrep. Всё, что не разбирается до нужных списков, — отсутствие вердикта."""
    try:
        with open(path, encoding='utf-8') as handle:
            text = handle.read()
    except OSError as exc:
        raise Incomplete('отчёт не прочитан: %s' % exc)
    if not text.strip():
        raise Incomplete('отчёт пуст: %s' % path)
    try:
        blob = json.loads(text)
    except ValueError as exc:
        raise Incomplete('отчёт не разобран как JSON: %s' % exc)
    if not isinstance(blob, dict):
        raise Incomplete('отчёт не объект JSON, а %s' % type(blob).__name__)
    for key in ('results', 'errors'):
        if not isinstance(blob.get(key), list):
            raise Incomplete('в отчёте нет списка %s' % key)
    paths = blob.get('paths')
    if not isinstance(paths, dict) or not isinstance(paths.get('scanned'), list):
        raise Incomplete('в отчёте нет списка paths.scanned')
    return blob


def severity(result: object) -> str:
    """Уровень одной находки. Запись без него — противоречие, а не «не находка»."""
    extra = result.get('extra') if isinstance(result, dict) else None
    if not isinstance(extra, dict) or not isinstance(extra.get('severity'), str):
        raise Incomplete('в results есть запись без extra.severity')
    return extra['severity']


def error_text(err: object) -> str:
    """Текст записи errors[]. Решает сам факт записи, вид — только для читателя."""
    if not isinstance(err, dict):
        return 'запись неизвестного вида'
    kind = err.get('type')
    if isinstance(kind, list) and kind:
        kind = kind[0]  # PartialParsing приезжает массивом [имя, [спаны]]
    if not isinstance(kind, str):
        kind = 'без типа'
    path = err.get('path')
    return '%s на %s' % (kind, path) if isinstance(path, str) else kind


def skip_reasons(report: dict) -> dict:
    """path → причина пропуска. Ключ `skipped` Semgrep пишет только с --verbose."""
    skipped = report['paths'].get('skipped')
    if not isinstance(skipped, list):
        return {}
    return {item['path']: item['reason'] for item in skipped
            if isinstance(item, dict) and isinstance(item.get('path'), str)
            and isinstance(item.get('reason'), str)}


def shorten(items: list[str], total: int) -> str:
    tail = '' if total <= SHOWN else ' и ещё %d' % (total - SHOWN)
    return ', '.join(items[:SHOWN]) + tail


def incompleteness(expected: set[str], report: dict) -> list[str]:
    """Причины, по которым охват нельзя назвать полным."""
    scanned = report['paths']['scanned']
    for path in scanned:
        if not isinstance(path, str):
            raise Incomplete('в paths.scanned не строка, а %s' % type(path).__name__)
    gaps = []
    missing = sorted(expected - set(scanned))
    if missing:
        reasons = skip_reasons(report)
        named = ['%s (%s)' % (p, reasons[p]) if p in reasons else p for p in missing]
        gaps.append('не просканировано %d из %d файлов профиля: %s'
                    % (len(missing), len(expected), shorten(named, len(missing))))
    errors = report['errors']
    if errors:
        gaps.append('ошибки сканера: %s'
                    % shorten([error_text(e) for e in errors], len(errors)))
    return gaps


def classify(expected: set[str], report: dict, rc: int) -> tuple[int, str]:
    """(код, строка вердикта без префикса). Находка важнее неполноты."""
    if rc not in (0, 1):
        return 3, 'НЕПОЛНО — semgrep завершился кодом %d' % rc
    findings = [r for r in report['results'] if severity(r) == 'ERROR']
    gaps = incompleteness(expected, report)
    if rc == 1 and findings:
        line = 'НАХОДКА — блокирующих находок %d' % len(findings)
        return 1, line + (' — неполно: %s' % '; '.join(gaps) if gaps else '')
    if findings or rc == 1:
        return 3, ('НЕПОЛНО — код semgrep %d не сходится с числом находок %d'
                   % (rc, len(findings)))
    if gaps:
        return 3, 'НЕПОЛНО — %s' % '; '.join(gaps)
    if not expected:
        return 4, 'НЕТ ВХОДА — в каталоге нет файлов профиля (%s)' % ' '.join(JS_EXTS)
    return 0, 'ЧИСТО — просканированы все %d файлов профиля, ошибок нет' % len(expected)


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print('usage: python3 scan_result.py <этап> <каталог_проекта> <semgrep.json> <код_semgrep>',
              file=sys.stderr)
        return 2
    stage, project_dir, report_path, rc_text = argv[1:]
    if not rc_text.isdigit():
        print('scan_result: код semgrep не число: %s' % rc_text, file=sys.stderr)
        return 2
    if not os.path.isdir(project_dir):
        print('scan_result: каталог не найден: %s' % project_dir, file=sys.stderr)
        return 2
    try:
        expected = inventory(project_dir)
        report = load_report(report_path)
        code, line = classify(expected, report, int(rc_text))
    except Incomplete as exc:
        code, line = 3, 'НЕПОЛНО — %s' % exc
    else:
        print('scan_result: %s: файлов профиля %d, просканировано %d, ошибок %d, код semgrep %s'
              % (stage, len(expected), len(report['paths']['scanned']),
                 len(report['errors']), rc_text), file=sys.stderr)
    print('scan_result: %s' % ' '.join(line.split()))  # вердикт — ровно одна строка
    return code


if __name__ == '__main__':
    # Вывод русский, а локаль раннера может быть C: без этого print упал бы на кодировке.
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main(sys.argv))
