"""LocalLLM — HuggingFace transformers backend with Rich progress bar."""

from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from ninurta.llm.base import BaseLLM, LLMResult

_console = Console()

DEFAULT_MODEL = "Qwen/Qwen3-4B"


class LocalLLM(BaseLLM):
    """Run a HuggingFace model locally via transformers.

    The model is loaded lazily on the first call to complete().
    A Rich progress bar replaces the default tqdm output.
    """

    def __init__(self, model_id: str = DEFAULT_MODEL) -> None:
        self.model_id = model_id
        self._model = None
        self._tokenizer = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._model is not None:
            return

        import torch  # noqa: PLC0415
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
        import transformers.utils.logging as hf_logging  # noqa: PLC0415
        import tqdm.auto as _tqdm_auto  # noqa: PLC0415

        _prog = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=_console,
            transient=True,
        )

        class _RichTqdm:
            """Drop-in tqdm shim — updates go to the Rich progress bar."""

            def __init__(self, iterable=None, *, desc="Loading…", total=None, **kw):
                self._iter = iterable
                self._task = _prog.add_task(desc, total=total)

            def __iter__(self):
                for item in (self._iter or []):
                    yield item
                    _prog.advance(self._task)
                _prog.stop_task(self._task)

            def update(self, n: int = 1) -> None:
                _prog.advance(self._task, n)

            def set_postfix(self, **kw) -> None: pass
            def set_description(self, s=None, **kw) -> None: pass

            def close(self) -> None:
                _prog.stop_task(self._task)

            def __enter__(self): return self
            def __exit__(self, *a): self.close()

        _orig = _tqdm_auto.tqdm
        hf_logging.enable_progress_bar()
        _tqdm_auto.tqdm = _RichTqdm

        try:
            with _prog:
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
                self._model = AutoModelForCausalLM.from_pretrained(
                    self.model_id,
                    torch_dtype="auto",
                    device_map="auto",
                )
        finally:
            _tqdm_auto.tqdm = _orig

        # Device / dtype report
        device = next(self._model.parameters()).device
        dtype  = next(self._model.parameters()).dtype

        if device.type == "cuda":
            gpu = torch.cuda.get_device_name(device.index or 0)
            _console.print(f"[bold green]⚡ GPU[/]  {gpu}  ([dim]{dtype}[/dim])")
        elif device.type == "mps":
            _console.print(f"[bold yellow]⚡ MPS[/]  Apple Silicon  ([dim]{dtype}[/dim])")
        else:
            _console.print(f"[bold red]⚠  CPU[/]  No GPU — inference will be slow  ([dim]{dtype}[/dim])")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict],
        max_tokens: int = 2048,
        thinking: bool = False,
        tools: list[dict] | None = None,
    ) -> LLMResult:
        self._load()

        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=thinking,
        )

        inputs = self._tokenizer([text], return_tensors="pt").to(self._model.device)

        with Live(
            Spinner("dots", text=f"[bold cyan]{self.model_id} thinking…[/]"),
            console=_console,
            refresh_per_second=12,
            transient=True,
        ):
            generated = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
            )

        output_ids = generated[0][len(inputs.input_ids[0]):]
        text = self._tokenizer.decode(output_ids, skip_special_tokens=True)
        self.usage.record(input_tokens=inputs.input_ids.shape[-1], output_tokens=len(output_ids))
        return LLMResult(text=text)
