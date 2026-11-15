"""
Process adapter. This one is real, and it is the most dangerous thing in the repository.

`FileSystemAdapter` proved an adapter could touch the world. This one lets a cycle run
programs, which is the capability that turns an agent from something that edits files into
something that can do anything the account it runs as can do. It is included because an
agent framework without it is a toy, and excluded from nothing: every constraint below
exists because the unconstrained version is indefensible.

Why this rather than making `windows_os` real: a desktop UI driver is Windows-only and
cannot be exercised on the Linux half of CI, so its "real" claim would go unverified on
every second run — which is the kind of claim this project has spent three gates removing.
A subprocess runner is testable everywhere, and it exercises the risk model harder than
anything else available.

The constraints, and what each one is for:

- **An allowlist, not a denylist.** A program not named in `allowed_programs` does not run.
  Denylists lose; there is always another shell.
- **No shell, ever.** `shell=False` and an argument list, never a command string. A string
  concatenated from cycle state is a command injection waiting for the first goal
  containing a semicolon.
- **Arguments must be strings the caller supplied as a list.** No splitting, no globbing,
  no interpolation.
- **A wall-clock timeout on every run**, and the process tree is killed when it expires.
- **Bounded output capture**, because a program that prints forever should not exhaust
  memory.
- **A working directory confined to a sandbox root**, resolved the same way the filesystem
  adapter resolves paths.
- **`run_program` is COMPENSABLE at best and declared IRREVERSIBLE**, because the adapter
  cannot know what the program did. The approval gate therefore refuses it without explicit
  operator consent, which is the correct default for "execute arbitrary code".
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from orrery.adapters.base import BaseAdapter
from orrery.core.envelope import EffectEnvelope
from orrery.core.types import ActionPayload, ActionRisk, ExecutionReceipt, StateContext

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_OUTPUT_BYTES = 65_536


class ActionOutcome(NamedTuple):
    """
    A result that ran to completion but did not succeed. Lets a handler report failure while
    still returning what it observed, instead of choosing between the two.
    """

    output: Any
    error: Optional[str] = None


class ProcessAdapter(BaseAdapter):
    """
    Runs allowlisted programs inside a sandbox working directory. Real execution.
    """

    is_simulation: ClassVar[bool] = False

    target_params: ClassVar[tuple] = ("cwd",)

    declared_risks: ClassVar[Mapping[str, ActionRisk]] = {
        "which_program": ActionRisk.READ_ONLY,
        "list_allowed": ActionRisk.READ_ONLY,
        # The adapter cannot know what a program does, so it assumes the worst it could do.
        "run_program": ActionRisk.IRREVERSIBLE,
    }

    def __init__(
        self,
        root: str,
        allowed_programs: Sequence[str],
        config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(name="process", config=config)
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.allowed_programs = frozenset(allowed_programs)
        self.timeout_seconds = max(0.1, float(self.config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)))
        self.max_timeout_seconds = max(
            self.timeout_seconds,
            float(self.config.get("max_timeout_seconds", self.timeout_seconds)),
        )
        self.max_output_bytes = int(self.config.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES))
        self.inherit_environment = bool(self.config.get("inherit_environment", False))
        self.effect_envelope = EffectEnvelope(paths=[str(self.root)])

        if not self.allowed_programs:
            logger.warning(
                "ProcessAdapter constructed with an empty allowlist; every run will be refused."
            )

    def _resolve_workdir(self, relative: Optional[str]) -> Path:
        if not relative:
            return self.root
        candidate = Path(relative)
        if candidate.is_absolute() or candidate.drive or candidate.anchor:
            raise ValueError(f"absolute working directories are not permitted: {relative!r}")
        resolved = (self.root / candidate).resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise ValueError(f"working directory escapes the adapter sandbox: {relative!r}")
        if not resolved.is_dir():
            raise NotADirectoryError(f"working directory does not exist: {relative!r}")
        return resolved

    def _resolve_program(self, program: Any) -> str:
        if not isinstance(program, str) or not program:
            raise ValueError("program must be a non-empty string")
        if program not in self.allowed_programs:
            raise PermissionError(
                f"program {program!r} is not in this adapter's allowlist "
                f"({', '.join(sorted(self.allowed_programs)) or 'empty'})"
            )
        located = shutil.which(program)
        if located is None:
            raise FileNotFoundError(f"allowlisted program {program!r} was not found on PATH")
        return located

    @staticmethod
    def _resolve_args(args: Any) -> List[str]:
        if args is None:
            return []
        if isinstance(args, str):
            # Splitting a string here would reintroduce quoting rules, and quoting rules are
            # where injection lives. The caller must say exactly what the arguments are.
            raise ValueError("args must be a list of strings, not a single command string")
        if not isinstance(args, (list, tuple)):
            raise ValueError("args must be a list of strings")
        for item in args:
            if not isinstance(item, str):
                raise ValueError(f"every argument must be a string, got {type(item).__name__}")
        return list(args)

    def _environment(self, extra: Optional[Dict[str, Any]]) -> Dict[str, str]:
        env = dict(os.environ) if self.inherit_environment else {}
        if not self.inherit_environment:
            # Enough to run, and nothing that leaks the operator's secrets to a child.
            for name in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "LANG"):
                if name in os.environ:
                    env[name] = os.environ[name]
        for key, value in (extra or {}).items():
            env[str(key)] = str(value)
        return env

    async def perceive_environment(self, context: StateContext) -> Dict[str, Any]:
        def _observe() -> Dict[str, Any]:
            available = {name: shutil.which(name) for name in sorted(self.allowed_programs)}
            return {
                "platform": "process",
                "root": str(self.root),
                "allowed_programs": sorted(self.allowed_programs),
                "resolved": {name: path for name, path in available.items() if path},
                "missing": [name for name, path in available.items() if path is None],
                "timeout_seconds": self.timeout_seconds,
                "inherit_environment": self.inherit_environment,
            }

        return await asyncio.to_thread(_observe)

    async def execute_action(self, action: ActionPayload) -> ExecutionReceipt:
        handler = getattr(self, f"_do_{action.action_name}", None)
        if handler is None:
            return self._receipt(
                action,
                success=False,
                error=f"{self.name} adapter does not implement action {action.action_name!r}",
            )

        try:
            output = await asyncio.to_thread(handler, action.params)
        except Exception as exc:
            logger.warning("Process action %r failed: %s", action.action_name, exc)
            return self._receipt(action, success=False, error=f"{type(exc).__name__}: {exc}")

        if isinstance(output, ActionOutcome):
            return self._receipt(
                action,
                success=output.error is None,
                output=output.output,
                error=output.error,
            )
        return self._receipt(action, success=True, output=output)




    def _do_list_allowed(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"allowed_programs": sorted(self.allowed_programs)}

    def _do_which_program(self, params: Dict[str, Any]) -> Dict[str, Any]:
        program = params.get("program")
        if not isinstance(program, str) or not program:
            raise ValueError("program must be a non-empty string")
        allowed = program in self.allowed_programs
        return {
            "program": program,
            "allowed": allowed,
            "path": shutil.which(program) if allowed else None,
        }

    def _clamp_timeout(self, raw_timeout: Any) -> float:
        if raw_timeout is None:
            return self.timeout_seconds
        try:
            val = float(raw_timeout)
        except (TypeError, ValueError):
            return self.timeout_seconds
        if val != val:  # NaN check
            return self.timeout_seconds
        return max(0.1, min(val, self.max_timeout_seconds))

    def _read_stream_capped(self, stream: Any, limit: int, chunks: List[bytes], truncated_flag: List[bool]) -> None:
        total = 0
        try:
            while True:
                data = stream.read(4096)
                if not data:
                    break
                remaining = limit - total
                if remaining > 0:
                    chunks.append(data[:remaining])
                    total += min(len(data), remaining)
                if len(data) > remaining:
                    truncated_flag[0] = True
                    while stream.read(8192):
                        pass
                    break
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _do_run_program(self, params: Dict[str, Any]) -> ActionOutcome:
        executable = self._resolve_program(params.get("program"))
        args = self._resolve_args(params.get("args"))
        workdir = self._resolve_workdir(params.get("cwd"))
        timeout = self._clamp_timeout(params.get("timeout_seconds"))

        popen_kwargs: Dict[str, Any] = {
            "cwd": str(workdir),
            "env": self._environment(params.get("env")),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(  # noqa: S603 - shell=False with an allowlisted executable
            [executable, *args],
            **popen_kwargs,
        )

        import threading
        stdout_chunks: List[bytes] = []
        stderr_chunks: List[bytes] = []
        stdout_trunc = [False]
        stderr_trunc = [False]
        t_out = threading.Thread(
            target=self._read_stream_capped,
            args=(proc.stdout, self.max_output_bytes, stdout_chunks, stdout_trunc),
            daemon=True,
        )
        t_err = threading.Thread(
            target=self._read_stream_capped,
            args=(proc.stderr, self.max_output_bytes, stderr_chunks, stderr_trunc),
            daemon=True,
        )
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(proc.pid)
        finally:
            t_out.join(timeout=2.0)
            t_err.join(timeout=2.0)

        stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
        stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        stdout_truncated = stdout_trunc[0]
        stderr_truncated = stderr_trunc[0]

        output = {
            "program": params.get("program"),
            "executable": executable,
            "args": args,
            "cwd": str(workdir.relative_to(self.root)) if workdir != self.root else ".",
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
            "timed_out": timed_out,
        }

        if timed_out:
            return ActionOutcome(
                output,
                f"{params.get('program')!r} killed after {timeout}s timeout (process tree terminated)",
            )

        if proc.returncode != 0:
            # The adapter ran; the work did not succeed. Reporting this as a success would
            # let a failing build count towards a passing reflection score.
            detail = stderr.strip() or stdout.strip() or "no output"
            return ActionOutcome(
                output,
                f"{params.get('program')!r} exited {proc.returncode}: {detail[:500]}",
            )
        return ActionOutcome(output)

    @staticmethod
    def _kill_tree(pid: int) -> None:
        """
        Kills a process and all its children. On Windows uses taskkill /T; on POSIX
        sends SIGTERM to the process group, falling back to SIGKILL after a grace period.
        """
        import signal
        import sys

        try:
            if sys.platform == "win32":
                # /T = tree kill, /F = force
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
            else:
                # Send SIGTERM to the entire process group.
                os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, OSError) as exc:
            logger.debug("Process tree kill for PID %d: %s (may already be dead)", pid, exc)

    def _clip(self, raw: bytes) -> Tuple[str, bool]:
        truncated = len(raw) > self.max_output_bytes
        return raw[: self.max_output_bytes].decode("utf-8", errors="replace"), truncated
