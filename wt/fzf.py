import subprocess
from typing import Optional


class FzfAborted(Exception):
    pass


def run_fzf(
    choices: list[str],
    prompt: str = "> ",
    preview_cmd: Optional[str] = None,
    delimiter: Optional[str] = None,
    with_nth: Optional[str] = None,
    height: str = "50%",
    reverse: bool = True,
) -> str:
    cmd = ["fzf", f"--prompt={prompt}", f"--height={height}"]
    if reverse:
        cmd.append("--reverse")
    if preview_cmd:
        cmd += ["--preview", preview_cmd]
    if delimiter:
        cmd += ["--delimiter", delimiter]
    if with_nth:
        cmd += ["--with-nth", with_nth]

    result = subprocess.run(
        cmd,
        input="\n".join(choices),
        stdout=subprocess.PIPE,
        text=True,
    )

    if result.returncode in (1, 130):
        raise FzfAborted()

    return result.stdout.strip()
