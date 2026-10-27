"""Russian and English (i18n.py): every Russian text in airmouse/ has its English line."""

import ast
import re
import string
import unittest
from pathlib import Path

from airmouse import i18n
from airmouse.i18n import EN, _

SOURCE = Path(__file__).resolve().parent.parent / "airmouse"
CYRILLIC = re.compile("[А-Яа-яЁё]")


def russian_texts():
    """(file, line, text) of every Russian string in the code, docstrings left out."""
    found = []
    for path in sorted(SOURCE.glob("*.py")):
        if path.name == "i18n.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(node.value) for node in ast.walk(tree)
                      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr) and any(
                    isinstance(v, ast.Constant) and CYRILLIC.search(str(v.value)) for v in node.values):
                found.append((path.name, node.lineno, "<f-string>"))
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
                  and CYRILLIC.search(node.value)):
                found.append((path.name, node.lineno, node.value))
    return found


def fields(text):
    return sorted(name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name is not None)


class TranslationTest(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("ru")

    def test_every_russian_text_has_an_english_one(self):
        texts = russian_texts()
        self.assertGreater(len(texts), 200)
        f_strings = [(f, line) for f, line, text in texts if text == "<f-string>"]
        self.assertEqual(f_strings, [], "a text with numbers: _(\"… {} …\").format(…), not an f-string")
        missing = sorted({text for _f, _line, text in texts if text not in EN})
        self.assertEqual(missing, [])

    def test_english_has_the_same_blanks_and_no_russian(self):
        for ru, en in EN.items():
            self.assertEqual(fields(ru), fields(en), ru)
            self.assertIsNone(CYRILLIC.search(en), en)
            self.assertEqual(ru.count("\n"), en.count("\n"), ru)

    def test_switching(self):
        self.assertEqual(_("Старт"), "Старт")
        i18n.set_language("en")
        self.assertEqual(_("Старт"), "Start")
        self.assertEqual(_("{:.0f} кадр/с").format(29.6), "30 fps")
        self.assertEqual(_("текст, которого нет в словаре"), "текст, которого нет в словаре")
        i18n.set_language("de")                     # unknown: back to Russian
        self.assertEqual(i18n.language(), "ru")

    def test_first_language_is_one_of_the_two(self):
        self.assertIn(i18n.system_language(), dict(i18n.LANGUAGES))


if __name__ == "__main__":
    unittest.main()
