"""Conservative CAD syntax gate. Defense in depth, NOT an execution sandbox."""
import ast


class CodeRejected(ValueError):
    pass


ALLOWED_METHODS = frozenset({"Workplane", "box", "rect", "circle", "extrude", "faces", "edges", "vertices",
    "workplane", "hole", "cutThruAll", "cutBlind", "cut", "union", "fillet", "chamfer", "translate",
    "rotate", "center", "pushPoints", "cylinder", "moveTo", "lineTo", "close", "polyline", "slot2D"})
SAFE_NAMES = frozenset({"cq", "params", "abs", "min", "max", "float", "int", "range"})
ALLOWED_NODES = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.AugAssign,
    ast.Return, ast.Expr, ast.Name, ast.Load, ast.Store, ast.Constant, ast.Call, ast.Attribute,
    ast.keyword, ast.Subscript, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd, ast.Tuple, ast.List, ast.Dict,
    ast.If, ast.IfExp, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.BoolOp, ast.And, ast.Or, ast.Not, ast.For, ast.Pass)


def validate_code(code: str) -> None:
    if len(code.encode()) > 50000:
        raise CodeRejected("Generated CAD source exceeds the prototype size limit")
    try:
        tree = ast.parse(code)
    except (SyntaxError, RecursionError) as error:
        raise CodeRejected("Generated CAD source is not valid Python") from error
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise CodeRejected("Source must contain only def build(params)")
    function = tree.body[0]
    args = function.args
    if (function.name != "build" or function.decorator_list or function.returns is not None or
        len(args.args) != 1 or args.args[0].arg != "params" or args.args[0].annotation or
        args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg or args.defaults):
        raise CodeRejected("Required interface: def build(params), without decorators/defaults/annotations")
    names = SAFE_NAMES | {n.id for n in ast.walk(function) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise CodeRejected(f"Unsupported CAD syntax: {type(node).__name__}")
        if isinstance(node, ast.FunctionDef) and node is not function:
            raise CodeRejected("Nested functions are not supported")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id not in names):
            raise CodeRejected(f"Unknown or prohibited name: {node.id}")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in SAFE_NAMES:
            raise CodeRejected("CAD code cannot rebind trusted names")
        if isinstance(node, ast.Attribute) and (node.attr not in ALLOWED_METHODS or not isinstance(node.ctx, ast.Load)):
            raise CodeRejected(f"Unsupported CAD attribute: {node.attr}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise CodeRejected("Indirect function calls are not supported")
            if isinstance(node.func, ast.Name) and node.func.id not in SAFE_NAMES - {"params", "cq"}:
                raise CodeRejected("Only approved numeric helpers and CadQuery methods can be called")
    if not any(isinstance(node, ast.Return) for node in ast.walk(function)):
        raise CodeRejected("build(params) must return a CadQuery shape")
