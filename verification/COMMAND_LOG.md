# Clean-Terminal Command Log

Timestamp: 2026-09-29 21:39:58 +05:30

Re-verification: 2026-09-29 21:56:37 +05:30 against `origin/main` commit `144ae83`

Shell: PowerShell

Result legend: PASS means the exact documented command completed successfully; FAIL means it did not.

## Checklist

| # | Documented command or required process | Result | Finding |
|---:|---|---|---|
| 1 | `git clone https://github.com/TatHack-Tathva/Blockchain-Simulation.git` | PASS | Cloned into `Blockchain-Simulation`. |
| 2 | `cd BlockChain_Prototype` | FAIL | README directory name does not match the clone output. |
| 3 | `python -m venv venv` | FAIL | `python` is not available on `PATH`. |
| 4 | `venv\Scripts\activate` | FAIL | No virtual environment exists; this is also not the normal PowerShell activation spelling. |
| 5 | `pip install -r requirements.txt` | FAIL | `pip` is not available on `PATH`. |
| 6 | `python -m signalling --config "C:\Users\rishav raj\Desktop\project\block chain\Blockchain-Simulation\verification\runtime\signalling-config.json"` | FAIL | Command is documented on latest main, but `python` is unavailable. |
| 7 | first AgentGuard node start | FAIL | No composed application/node launch command is documented. |
| 8 | second AgentGuard node start | FAIL | No composed application/node launch command is documented. |
| 9 | third AgentGuard node start | FAIL | No composed application/node launch command is documented. |
| 10 | dashboard start | FAIL | No implementation or command is documented. |
| 11 | `python start_peer.py` | FAIL | `python` is not available on `PATH`; this is the legacy interactive peer, not the specified AgentGuard node service. |
| 12 | `python -m unittest discover -s tests -p "test_*.py"` | FAIL | Backend tests exist on latest main, but `python` is unavailable. |
| 13 | `python -m unittest discover -s tests -p "test_*.py" -v` | FAIL | Developer 2's documented test command fails because `python` is unavailable. |

## Verbatim output

### 1. Clone

```text
Cloning into 'Blockchain-Simulation'...
```

### 2. Enter project folder

```text
Set-Location:
Line |
   2 |  cd BlockChain_Prototype
     |  ~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot find path 'C:\Users\rishav raj\.codex\visualizations\2026\09\29\01a0ede9-68d7-78b1-87eb-eb932bd003f4\BlockChain_Prototype' because it does not exist.
```

### 3. Create virtual environment

```text
python:
Line |
   2 |  python -m venv venv
     |  ~~~~~~
     | The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 4. Activate virtual environment

```text
venv\Scripts\activate:
Line |
   2 |  venv\Scripts\activate
     |  ~~~~~~~~~~~~~~~~~~~~~
     | The module 'venv' could not be loaded. For more information, run 'Import-Module venv'.
```

### 5. Install dependencies

```text
pip:
Line |
   2 |  pip install -r requirements.txt
     |  ~~~
     | The term 'pip' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 6. Start the legacy terminal peer

```text
python:
Line |
   2 |  python start_peer.py
     |  ~~~~~~
     | The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 7. Run the documented test command

```text
python:
Line |
   2 |  python -m unittest discover -s tests -p "test_*.py"
     |  ~~~~~~
     | The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 8. Start signalling on latest main with runtime-supplied configuration

```text
python:
Line |
   2 |  python -m signalling --config "C:\Users\rishav raj\Desktop\project\bl …
     |  ~~~~~~
     | The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

### 9. Run Developer 2's verbose backend test command

```text
python:
Line |
   2 |  python -m unittest discover -s tests -p "test_*.py" -v
     |  ~~~~~~
     | The term 'python' is not recognized as a name of a cmdlet, function, script file, or executable program.
Check the spelling of the name, or if a path was included, verify that the path is correct and try again.
```

## Missing-command evidence

Latest `origin/main` contains `signalling/`, `agentguard/`, `api/`, and backend `tests/`. It still has no `frontend/`, `dashboard/`, `package.json`, HTML, JavaScript, TypeScript, or TSX file. There is no documented composition/start command for the application API with a real node adapter, no three-node command set, and no dashboard command.

The clone command targets the public `TatHack-Tathva` repository and produced commit `e038144`. The active workspace instead tracks the `minnhaaaaa` fork (`rishav` at `7aa609e`, latest `origin/main` at `144ae83`), so the documented clean-clone command does not reproduce the release candidate being reviewed.
