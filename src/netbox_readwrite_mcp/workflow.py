"""Bounded Python-syntax workflow interpreter. No eval, exec, imports or host objects.

Only JSON values, arithmetic, control flow and explicitly supplied tool calls exist.
This is a small language, not a Python process with a blacklist.
"""

import ast
import operator


class Workflow:
    def __init__(self, call):
        self.call = call
        self.env = {"result": None}
        self.steps = 0

    def tick(self):
        self.steps += 1
        if self.steps > 10000:
            raise ValueError("Workflow exceeded 10000 interpreter steps")

    def expression(self, node):
        value = self._expression(node)
        # Bound JSON-like object graphs before serialization or sequence arithmetic.
        pending, count, size = [value], 0, 0
        while pending:
            child = pending.pop()
            count += 1
            if count > 20000 or size > 1000000:
                raise ValueError("Workflow value exceeds graph/size budget")
            if isinstance(child, dict):
                pending.extend(child.keys())
                pending.extend(child.values())
            elif isinstance(child, (list, tuple)):
                pending.extend(child)
            elif isinstance(child, str):
                size += len(child)
            elif isinstance(child, int) and child.bit_length() > 1024:
                raise ValueError("Workflow integer too large")
        return value

    def _expression(self, node):
        self.tick()
        if isinstance(node, ast.Constant) and type(node.value) in {str, int, float, bool, type(None)}:
            return node.value
        if isinstance(node, ast.Name) and not node.id.startswith("_"):
            return self.env[node.id]
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.expression(x) for x in node.elts]
        if isinstance(node, ast.Dict) and all(k is not None for k in node.keys):
            return {self.expression(k): self.expression(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.Subscript):
            return self.expression(node.value)[self.expression(node.slice)]
        if isinstance(node, ast.UnaryOp):
            functions = {ast.Not: operator.not_, ast.USub: operator.neg, ast.UAdd: operator.pos}
            if type(node.op) in functions:
                return functions[type(node.op)](self.expression(node.operand))
        if isinstance(node, ast.BoolOp):
            result = self.expression(node.values[0])
            for child in node.values[1:]:
                if (isinstance(node.op, ast.And) and not result) or (isinstance(node.op, ast.Or) and result):
                    break
                result = self.expression(child)
            return result
        if isinstance(node, ast.Compare):
            functions = {
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.Lt: operator.lt,
                ast.LtE: operator.le,
                ast.Gt: operator.gt,
                ast.GtE: operator.ge,
                ast.In: lambda a, b: a in b,
                ast.NotIn: lambda a, b: a not in b,
                ast.Is: operator.is_,
                ast.IsNot: operator.is_not,
            }
            left = self.expression(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.expression(comparator)
                if type(op) not in functions or not functions[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp) and isinstance(
            node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
        ):
            left, right = self.expression(node.left), self.expression(node.right)
            if isinstance(node.op, ast.Mult) and (
                not isinstance(left, (int, float)) or not isinstance(right, (int, float))
            ):
                raise ValueError("Multiplication is numeric only")
            if isinstance(node.op, ast.Mod) and not isinstance(left, (int, float)):
                raise ValueError("Modulo is numeric only")
            functions = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Mod: operator.mod,
            }
            value = functions[type(node.op)](left, right)
            return value
        if isinstance(node, ast.Call):
            args = [self.expression(x) for x in node.args]
            if any(k.arg is None for k in node.keywords):
                raise ValueError("Workflow does not support argument unpacking")
            kwargs = {k.arg: self.expression(k.value) for k in node.keywords}
            if isinstance(node.func, ast.Name):
                functions = {
                    "tool": self.call,
                    "len": len,
                    "str": str,
                    "int": int,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "sorted": sorted,
                }
                if node.func.id in functions:
                    return functions[node.func.id](*args, **kwargs)
                if node.func.id == "range":
                    value = range(*args)
                    if len(value) > 1000:
                        raise ValueError("range is limited to 1000 values")
                    return list(value)
            if isinstance(node.func, ast.Attribute):
                obj = self.expression(node.func.value)
                method = node.func.attr
                if type(obj) is dict and method == "get":
                    return obj.get(*args, **kwargs)
                if type(obj) is dict and method in {"keys", "values", "items"} and not args and not kwargs:
                    return list(getattr(obj, method)())
                if type(obj) is list and method == "append" and len(args) == 1 and not kwargs:
                    if len(obj) >= 1000:
                        raise ValueError("List exceeds 1000 values")
                    obj.append(args[0])
                    return None
        raise ValueError("Unsupported workflow expression: " + type(node).__name__)

    def block(self, statements):
        for node in statements:
            self.tick()
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and not node.targets[0].id.startswith("_")
            ):
                self.env[node.targets[0].id] = self.expression(node.value)
            elif isinstance(node, ast.Expr):
                self.expression(node.value)
            elif isinstance(node, ast.If):
                self.block(node.body if self.expression(node.test) else node.orelse)
            elif (
                isinstance(node, ast.For)
                and isinstance(node.target, ast.Name)
                and not node.target.id.startswith("_")
            ):
                values = self.expression(node.iter)
                if not isinstance(values, (list, dict)) or len(values) > 1000:
                    raise ValueError("for requires a list or dict of at most 1000 values")
                for value in list(values):
                    self.env[node.target.id] = value
                    self.block(node.body)
                self.block(node.orelse)
            else:
                raise ValueError("Unsupported workflow statement: " + type(node).__name__)

    def run(self, source):
        if not isinstance(source, str) or len(source) > 64000:
            raise ValueError("Workflow code must be at most 64000 characters")
        tree = ast.parse(source)
        # Reject forbidden constructs before executing even the first statement.
        forbidden = (
            ast.Import,
            ast.ImportFrom,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.Lambda,
            ast.While,
            ast.With,
            ast.Try,
            ast.Delete,
            ast.Global,
            ast.Nonlocal,
            ast.ListComp,
            ast.DictComp,
            ast.SetComp,
            ast.GeneratorExp,
        )
        if any(isinstance(n, forbidden) for n in ast.walk(tree)):
            raise ValueError("Workflow permits assignments, for/if, JSON expressions and tool calls only")
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and not (
                len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and not node.targets[0].id.startswith("_")
            ):
                raise ValueError(
                    "Workflow assignments require one public variable name; item assignment/unpacking is unsupported"
                )
            if isinstance(node, ast.For) and not (
                isinstance(node.target, ast.Name) and not node.target.id.startswith("_")
            ):
                raise ValueError("Workflow for targets require one public variable name")
            if isinstance(node, ast.Call) and any(k.arg is None for k in node.keywords):
                raise ValueError("Workflow does not support argument unpacking")
        self.block(tree.body)
        return self.env["result"]
