from RestrictedPython import compile_restricted
from RestrictedPython.Eval import default_guarded_getiter, default_guarded_getitem
from RestrictedPython.Guards import (
    safe_builtins,
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
)
from smart_contract.gas_meter import GasMeter
import math

class ContractEnvironment:
    def __init__(self, code: str):
        self.code = code

        extended_builtins = dict(safe_builtins)
        extended_builtins.update({
            'set': set,
            'dict': dict,
            'list': list,
            'len': len,
            'range': range,
            'min': min,
            'max': max,
            'sum': sum,
            'abs': abs,
            'sorted': sorted,
            'enumerate': enumerate,
            'zip': zip,
            'any': any,
            'all': all,

            # math functions
            'sqrt': math.sqrt,
            'ceil': math.ceil,
            'floor': math.floor,
            'pow': pow,
            'fabs': math.fabs,
            'log': math.log,
            'log10': math.log10,
            'exp': math.exp,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'degrees': math.degrees,
            'radians': math.radians,
            'pi': math.pi,
            'e': math.e,
            'isclose': math.isclose,
            'gcd': math.gcd,
            'factorial': math.factorial,
        })

        self.globals = {
            '__builtins__': extended_builtins,
            # RestrictedPython's own guards. The previous `_write_` and
            # `_getitem_` here were identity/passthrough functions, which
            # switched off the write protection completely: contract code
            # could assign to attributes and items of any object it could
            # reach, including objects handed to it by the host.
            '_getiter_': default_guarded_getiter,
            '_getitem_': default_guarded_getitem,
            '_write_': full_write_guard,
            '_iter_unpack_sequence_': guarded_iter_unpack_sequence,
            '_unpack_sequence_': guarded_unpack_sequence,
        }
        self.locals = {}
        self._compile()

    def _compile(self):
        self.compiled = compile_restricted(self.code, filename='<contract>', mode='exec')
        # Module level statements are contract supplied code too, so they are
        # metered like anything else. Running the module body outside the gas
        # meter let a contract put an unbounded loop at the top level and skip
        # the gas limit entirely.
        gas_meter = GasMeter()
        try:
            gas_meter.start()
            exec(self.compiled, self.globals, self.locals)
        finally:
            gas_meter.stop()
        self.setup_gas_used = gas_meter.gas_used

    def run_contract(self, func_name: str, args, state):
        func = self.locals.get(func_name)
        if not func:
            raise Exception(f"Function '{func_name}' not found in contract.")
        if not callable(func):
            raise Exception(f"'{func_name}' is not callable.")

        gas_meter = GasMeter()
        gas_meter.gas_used = self.setup_gas_used

        try:
            gas_meter.start()
            state, msg = func(*args, state)
        finally:
            gas_meter.stop()

        return state, msg, gas_meter.gas_used
