#!/usr/bin/env python3
"""scan_result_test.py — проверки классификатора отчёта Semgrep.

  python3 scan_result_test.py

Фикстуры собраны по настоящим отчётам semgrep 1.176.1: ключи и формы те же
(`paths.scanned`, `paths.skipped` только с --verbose, `errors[].type` строкой у Timeout
и массивом у PartialParsing), длинные тексты сообщений сокращены.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.dont_write_bytecode = True  # иначе рядом с модулем остаётся __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scan_result  # noqa: E402  — путь добавляется выше


def report(scanned, results=(), errors=(), skipped=None):
    paths = {'scanned': list(scanned)}
    if skipped is not None:  # ключ появляется только при --verbose
        paths['skipped'] = list(skipped)
    return {'version': '1.176.1', 'results': list(results), 'errors': list(errors),
            'paths': paths, 'engine_requested': 'OSS', 'skipped_rules': []}


def finding(path):
    return {'check_id': 'rules.install-script-ci-token-exfil', 'path': path,
            'start': {'line': 2, 'col': 1, 'offset': 32},
            'end': {'line': 2, 'col': 72, 'offset': 103},
            'extra': {'message': 'Установочный скрипт берёт токен…', 'severity': 'ERROR',
                      'metadata': {'owasp': 'ASI04'}, 'fingerprint': 'requires login',
                      'lines': 'requires login', 'validation_state': 'NO_VALIDATOR',
                      'engine_kind': 'OSS'}}


def timeout(path):
    return {'code': 2, 'level': 'warn', 'type': 'Timeout',
            'rule_id': 'rules.install-script-ci-token-exfil',
            'message': 'Timeout when running rules.install-script-ci-token-exfil on %s:\n ' % path,
            'path': path}


def partial_parsing(path):
    span = {'path': path, 'start': {'line': 1, 'col': 1, 'offset': 0},
            'end': {'line': 1, 'col': 60, 'offset': 59}}
    return {'code': 3, 'level': 'warn', 'type': ['PartialParsing', [span]],
            'message': 'Syntax error at line %s:1' % path, 'path': path,
            'spans': [dict(span, file=path)]}


class ScanResultCase(unittest.TestCase):
    """Каждый случай — каталог на диске, отчёт рядом и один вызов main()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proj = os.path.join(self.tmp.name, 'proj')
        os.mkdir(self.proj)

    def touch(self, rel, body='console.log("ok");\n'):
        path = os.path.join(self.proj, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(body)
        return path

    def helper(self, rc, blob=None, text=None, path=None):
        """Возвращает (код, единственная строка stdout)."""
        if path is None:
            path = os.path.join(self.tmp.name, 'semgrep.json')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(text if text is not None else json.dumps(blob))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = scan_result.main(['scan_result.py', 'таргетные', self.proj, path, str(rc)])
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, 'в stdout должна быть ровно одна строка: %r' % out.getvalue())
        self.assertTrue(lines[0].startswith('scan_result: '), lines[0])
        return code, lines[0]

    # --- охват ---------------------------------------------------------------

    def test_skipped_by_size_without_verbose(self):
        self.touch('benign.js'); self.touch('install.js')
        code, line = self.helper(0, report(['/src/benign.js']))
        self.assertEqual(code, 3, line)
        self.assertIn('НЕПОЛНО', line)
        self.assertIn('/src/install.js', line)

    def test_skipped_by_size_with_verbose(self):
        self.touch('benign.js'); self.touch('install.js')
        code, line = self.helper(0, report(
            ['/src/benign.js'], skipped=[{'path': '/src/install.js', 'reason': 'exceeded_size_limit'}]))
        self.assertEqual(code, 3, line)
        self.assertIn('exceeded_size_limit', line)

    def test_timeout_with_rc_zero(self):
        self.touch('benign.js'); self.touch('install.js')
        code, line = self.helper(0, report(['/src/benign.js', '/src/install.js'],
                                           errors=[timeout('/src/install.js')]))
        self.assertEqual(code, 3, line)
        self.assertIn('Timeout', line)

    def test_partial_parsing_error(self):
        self.touch('binary.js')
        code, line = self.helper(0, report(['/src/binary.js'],
                                           errors=[partial_parsing('/src/binary.js')]))
        self.assertEqual(code, 3, line)
        self.assertIn('PartialParsing', line)

    def test_symlink_in_project(self):
        self.touch('benign.js')
        os.symlink(os.path.join(self.proj, 'benign.js'), os.path.join(self.proj, 'link.js'))
        code, line = self.helper(0, report(['/src/benign.js', '/src/link.js']))
        self.assertEqual(code, 3, line)
        self.assertIn('симлинк', line)

    def test_full_coverage_is_clean(self):
        self.touch('a.js'); self.touch('nested/b.ts')
        code, line = self.helper(0, report(['/src/a.js', '/src/nested/b.ts', '/src/package.json']))
        self.assertEqual(code, 0, line)
        self.assertIn('ЧИСТО', line)

    def test_git_directory_is_not_expected(self):
        self.touch('a.js'); self.touch('.git/hook.js')
        code, line = self.helper(0, report(['/src/a.js', '/src/.git/hook.js']))
        self.assertEqual(code, 0, line)

    def test_no_profile_files_at_all(self):
        self.touch('README', body='нет кода\n')
        code, line = self.helper(0, report([]))
        self.assertEqual(code, 4, line)
        self.assertIn('НЕТ ВХОДА', line)

    # --- пробелы обхода ------------------------------------------------------

    def locked(self, rel):
        """Каталог с правами 000. Под root таких не бывает — случай не о нём."""
        if os.geteuid() == 0:
            self.skipTest('root читает каталог с правами 000')
        path = os.path.join(self.proj, rel.replace('/', os.sep)) if rel else self.proj
        os.makedirs(path, exist_ok=True)
        self.addCleanup(os.chmod, path, 0o755)
        os.chmod(path, 0)

    def test_unreadable_subdirectory(self):
        # Обход каталога оборвался на подкаталоге, значит и список ожидаемых файлов
        # неполон: сверка «expected ⊆ scanned» сошлась бы сама с собой.
        self.touch('benign.js')
        self.locked('locked')
        code, line = self.helper(0, report(['/src/benign.js']))
        self.assertEqual(code, 3, line)
        self.assertIn('не прочитан', line)
        self.assertIn('/src/locked', line)

    def test_unreadable_project_root(self):
        self.touch('benign.js')
        self.locked('')
        code, line = self.helper(0, report(['/src/benign.js']))
        self.assertEqual(code, 3, line)
        self.assertIn('не прочитан', line)

    def test_skipped_without_access_is_a_gap(self):
        # Semgrep не от root сам сообщает о недоступном каталоге; на хосте он может
        # быть виден, и разность expected/scanned тогда пуста.
        self.touch('benign.js')
        code, line = self.helper(0, report(['/src/benign.js'], skipped=[
            {'path': '/src/locked', 'reason': 'insufficient_permissions'}]))
        self.assertEqual(code, 3, line)
        self.assertIn('insufficient_permissions', line)
        self.assertIn('/src/locked', line)

    def test_skipped_by_size_outside_profile_is_clean(self):
        # Файл вне профиля, пропущенный по размеру, файлов профиля не прячет.
        self.touch('a.js')
        code, line = self.helper(0, report(['/src/a.js'], skipped=[
            {'path': '/src/sub/notes.txt', 'reason': 'exceeded_size_limit'}]))
        self.assertEqual(code, 0, line)
        self.assertIn('ЧИСТО', line)

    def test_finding_wins_over_unreadable_directory(self):
        # В контейнере Semgrep работает от root и закрытый каталог дочитывает:
        # находка перекрывает неполноту, приоритет 1 > 3.
        self.touch('benign.js')
        self.locked('locked')
        code, line = self.helper(1, report(['/src/benign.js'],
                                           results=[finding('/src/benign.js')]))
        self.assertEqual(code, 1, line)
        self.assertIn('НАХОДКА', line)
        self.assertIn('неполно', line)
        self.assertIn('/src/locked', line)

    def test_symlink_with_finding_is_a_finding(self):
        self.touch('install.js')
        os.symlink(os.path.join(self.proj, 'install.js'), os.path.join(self.proj, 'link.js'))
        code, line = self.helper(1, report(['/src/install.js', '/src/link.js'],
                                           results=[finding('/src/install.js')]))
        self.assertEqual(code, 1, line)
        self.assertIn('НАХОДКА', line)
        self.assertIn('симлинк', line)

    # --- находки -------------------------------------------------------------

    def test_finding_with_rc_one(self):
        self.touch('install.js')
        code, line = self.helper(1, report(['/src/install.js'], results=[finding('/src/install.js')]))
        self.assertEqual(code, 1, line)
        self.assertIn('НАХОДКА', line)

    def test_finding_is_named_in_stderr(self):
        # Отчёт depscan.sh удаляет, поэтому файл и правило находки должны быть в stderr.
        self.touch('install.js')
        path = os.path.join(self.tmp.name, 'semgrep.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(report(['/src/install.js'], results=[finding('/src/install.js')]), fh)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = scan_result.main(['scan_result.py', 'таргетные', self.proj, path, '1'])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn('находка rules.install-script-ci-token-exfil в /src/install.js:2',
                      err.getvalue())
        self.assertEqual(len(out.getvalue().splitlines()), 1)

    def test_finding_wins_over_incomplete_but_says_so(self):
        self.touch('install.js'); self.touch('slow.js')
        code, line = self.helper(1, report(['/src/install.js', '/src/slow.js'],
                                           results=[finding('/src/install.js')],
                                           errors=[timeout('/src/slow.js')]))
        self.assertEqual(code, 1, line)
        self.assertIn('НАХОДКА', line)
        self.assertIn('неполно', line)

    def test_rc_zero_with_findings_is_contradiction(self):
        self.touch('install.js')
        code, line = self.helper(0, report(['/src/install.js'], results=[finding('/src/install.js')]))
        self.assertEqual(code, 3, line)

    def test_rc_one_without_findings_is_contradiction(self):
        self.touch('install.js')
        code, line = self.helper(1, report(['/src/install.js']))
        self.assertEqual(code, 3, line)

    def test_rc_two_is_not_a_verdict(self):
        self.touch('install.js')
        code, line = self.helper(2, report(['/src/install.js']))
        self.assertEqual(code, 3, line)

    # --- битый отчёт ---------------------------------------------------------

    def test_empty_report(self):
        self.touch('a.js')
        code, line = self.helper(0, text='')
        self.assertEqual(code, 3, line)

    def test_truncated_json(self):
        self.touch('a.js')
        code, line = self.helper(0, text='{')
        self.assertEqual(code, 3, line)

    def test_json_list(self):
        self.touch('a.js')
        code, line = self.helper(0, text='[]')
        self.assertEqual(code, 3, line)

    def test_json_null(self):
        self.touch('a.js')
        code, line = self.helper(0, text='null')
        self.assertEqual(code, 3, line)

    def test_report_without_paths(self):
        self.touch('a.js')
        code, line = self.helper(0, {'version': '1.176.1', 'results': [], 'errors': []})
        self.assertEqual(code, 3, line)

    def test_finding_wins_over_malformed_report_paths(self):
        # Испорченный skipped или scanned — пробел, но подтверждённая находка важнее него.
        self.touch('a.js')
        code, line = self.helper(1, report(['/src/a.js'], results=[finding('/src/a.js')],
                                           skipped=[{'path': '/src/locked'}]))
        self.assertEqual(code, 1, line)
        self.assertIn('НАХОДКА', line)
        self.assertIn('неполно', line)
        code, line = self.helper(1, report(['/src/a.js', 7], results=[finding('/src/a.js')]))
        self.assertEqual(code, 1, line)
        self.assertIn('не строкой', line)

    def test_malformed_skipped_is_incomplete(self):
        # По skipped читаются причины отсутствия доступа: испорченный список — не «пусто».
        self.touch('a.js')
        code, line = self.helper(0, report(['/src/a.js'], skipped={'path': '/src/locked'}))
        self.assertEqual(code, 3, line)
        self.assertIn('skipped', line)
        code, line = self.helper(0, report(['/src/a.js'], skipped=[{'path': '/src/locked'}]))
        self.assertEqual(code, 3, line)

    def test_missing_report_file(self):
        self.touch('a.js')
        code, line = self.helper(0, path=os.path.join(self.tmp.name, 'нет-такого.json'))
        self.assertEqual(code, 3, line)

    # --- вызов ---------------------------------------------------------------

    def test_wrong_argument_count(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(scan_result.main(['scan_result.py', 'таргетные']), 2)
        self.assertIn('usage', err.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
