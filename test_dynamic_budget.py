import ast
import pathlib
import types
import unittest

source = pathlib.Path(__file__).with_name('serve_api_090_dynamic.py').read_text()
tree = ast.parse(source)
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in ('request_budget', 'remaining_budget')]
class HTTPException(Exception):
    pass
scope = {'HTTPException': HTTPException}
exec(compile(ast.Module(body=functions, type_ignores=[]), '<budget>', 'exec'), scope)

class BudgetTests(unittest.TestCase):
    def test_lengths(self):
        for prompt in (16, 16384, 32768, 65536, 131072, 196608, 261119):
            self.assertEqual(scope['remaining_budget'](prompt, 262144, 262144),
                             262144 - prompt - 1024)

    def test_full_context(self):
        for prompt in (261120, 262144, 300000):
            with self.assertRaises(HTTPException):
                scope['remaining_budget'](prompt, 262144, 262144)

    def test_cap(self):
        self.assertEqual(scope['remaining_budget'](16, 262144, 65536), 65536)

    def test_explicit_and_omitted(self):
        for name in ('max_tokens', 'max_completion_tokens', 'max_output_tokens'):
            req = types.SimpleNamespace(model_fields_set={name}, **{name: 65536})
            self.assertEqual(scope['request_budget'](req, 65536), 65536)
            setattr(req, name, None)
            self.assertIsNone(scope['request_budget'](req, 65536))
        req = types.SimpleNamespace(model_fields_set=set(), max_tokens=262144)
        self.assertIsNone(scope['request_budget'](req, 262144))

if __name__ == '__main__':
    unittest.main()
