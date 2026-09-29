import multiprocessing
import time
import psutil
from smart_contract.sandbox_runner import sandbox_contract_runner

TIMEOUT = 20.0
MEMORY_LIMIT_MB = 500

def _failure(error):
    return {
        "success": False,
        "error": error,
        "state": None,
        "msg": None,
        "gas_used": 0
    }

class SecureContractExecutor:
    def __init__(self, code: str):
        self.code = code

    def _kill(self, process):
        """
            terminate() only asks. A contract that ignores SIGTERM, or that is
            stuck in a C call, used to be left running while we returned -
            leaking a process per invocation.
        """
        if not process.is_alive():
            return
        process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)

    def run(self, func_name: str, args, state):
        manager = multiprocessing.Manager()
        try:
            return_dict = manager.dict()

            process = multiprocessing.Process(
                target=sandbox_contract_runner,
                args=(self.code, func_name, args, state, return_dict)
            )

            process.start()
            start_time = time.time()

            while process.is_alive():
                if time.time() - start_time > TIMEOUT:
                    self._kill(process)
                    return _failure("Execution timeout")

                try:
                    proc = psutil.Process(process.pid)
                    mem_usage_mb = proc.memory_info().rss / (1024 * 1024)
                    if mem_usage_mb > MEMORY_LIMIT_MB:
                        self._kill(process)
                        return _failure(f"Memory limit exceeded ({int(mem_usage_mb)} MB)")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    break

                time.sleep(0.05)

            process.join(timeout=5)
            self._kill(process)

            # A contract that crashed the worker outright - a segfault, or the
            # kernel OOM killer - leaves return_dict untouched. Treating a
            # missing "error" key as success made such a run look like it
            # returned a null state.
            if "error" not in return_dict:
                return _failure(f"Contract worker died (exit code {process.exitcode})")

            return {
                "success": return_dict.get("error") is None,
                "error": return_dict.get("error"),
                "state": return_dict.get("state"),
                "msg": return_dict.get("msg"),
                "gas_used": return_dict.get("gas_used")
            }
        finally:
            manager.shutdown()
