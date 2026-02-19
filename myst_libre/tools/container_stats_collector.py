"""
container_stats_collector.py

Background container resource monitoring via Docker stats API.
Collects CPU and memory samples, then displays a summary table
and time-series chart after the build completes.
"""

import time
import threading
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

import docker.errors


@dataclass
class StatsSample:
    """A single stats measurement from a Docker container."""
    timestamp: float
    cpu_percent: float
    memory_bytes: int
    memory_limit: int


def _format_size(size_bytes: int) -> str:
    """Format byte count to human-readable string."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{size_bytes} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


class ContainerStatsCollector:
    """
    Collects CPU and memory statistics from a running Docker container
    in a background daemon thread.
    """

    def __init__(self, container, logger: logging.Logger, console, interval: float = 5.0):
        """
        Args:
            container: Docker SDK container object
            logger: Logger instance
            console: Rich Console instance for display output
            interval: Seconds between stat polls
        """
        self._container = container
        self._logger = logger
        self._console = console
        self._interval = interval

        self._samples: List[StatsSample] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_time: Optional[float] = None

    def start(self) -> None:
        """Start background stats collection. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._start_time = time.time()
        self._thread = threading.Thread(
            target=self._collect_loop,
            name="container-stats-collector",
            daemon=True,
        )
        self._thread.start()
        self._logger.info("Started container stats collection")

    def stop(self) -> None:
        """Signal the collection thread to stop and wait for it."""
        if self._thread is None:
            return

        self._stop_event.set()
        self._thread.join(timeout=self._interval * 2)
        if self._thread.is_alive():
            self._logger.warning("Stats collection thread did not stop cleanly")
        self._thread = None

    def is_collecting(self) -> bool:
        """Return True if the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def get_summary(self) -> Optional[Dict[str, Any]]:
        """
        Compute summary statistics from collected samples.

        Returns:
            Dict with duration, peak/avg CPU %, peak/avg memory, memory limit.
            None if no samples were collected.
        """
        with self._lock:
            samples = list(self._samples)

        if not samples:
            return None

        duration = samples[-1].timestamp - samples[0].timestamp
        cpu_values = [s.cpu_percent for s in samples]
        mem_values = [s.memory_bytes for s in samples]

        return {
            'duration_seconds': duration,
            'num_samples': len(samples),
            'peak_cpu_percent': max(cpu_values),
            'avg_cpu_percent': sum(cpu_values) / len(cpu_values),
            'peak_memory_bytes': max(mem_values),
            'avg_memory_bytes': sum(mem_values) // len(mem_values),
            'memory_limit': samples[-1].memory_limit,
        }

    def display_report(self) -> None:
        """Print a Rich Table summary and plotext time-series chart."""
        summary = self.get_summary()
        if summary is None:
            self._console.print("[yellow]No container stats were collected.[/yellow]")
            return

        self._display_table(summary)
        self._display_chart()

    def _display_table(self, summary: Dict[str, Any]) -> None:
        """Print a Rich Table with resource usage summary."""
        from rich.table import Table

        duration_min = summary['duration_seconds'] / 60

        table = Table(title="Container Resource Usage")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")

        table.add_row("Duration", f"{duration_min:.1f} min")
        table.add_row("Samples", str(summary['num_samples']))
        table.add_row("Peak CPU", f"{summary['peak_cpu_percent']:.1f}%")
        table.add_row("Avg CPU", f"{summary['avg_cpu_percent']:.1f}%")
        table.add_row("Peak Memory", _format_size(summary['peak_memory_bytes']))
        table.add_row("Avg Memory", _format_size(summary['avg_memory_bytes']))
        if summary['memory_limit'] > 0:
            table.add_row("Memory Limit", _format_size(summary['memory_limit']))

        self._console.print(table)

    def _display_chart(self) -> None:
        """Print a plotext time-series chart of CPU and memory usage."""
        with self._lock:
            samples = list(self._samples)

        if len(samples) < 2:
            self._console.print("[yellow]Not enough data points for chart.[/yellow]")
            return

        try:
            import plotext as plt
        except ImportError:
            self._console.print(
                "[yellow]plotext not installed — skipping chart. "
                "Install with: pip install plotext[/yellow]"
            )
            return

        start = samples[0].timestamp
        minutes = [(s.timestamp - start) / 60.0 for s in samples]
        cpu_vals = [s.cpu_percent for s in samples]
        mem_gb_vals = [s.memory_bytes / (1024 ** 3) for s in samples]

        plt.clear_figure()
        plt.theme("dark")
        plt.plot_size(80, 20)
        plt.title("Container Resource Usage Over Time")
        plt.xlabel("Time (minutes)")

        plt.plot(minutes, cpu_vals, label="CPU %")
        plt.ylabel("CPU %")

        plt.plot(minutes, mem_gb_vals, label="Memory (GB)")
        plt.ylabel("Memory (GB)", yside="right")

        plt.show()

    @staticmethod
    def _compute_cpu_percent(stats_dict: dict) -> float:
        """
        Compute CPU usage percentage from a Docker stats response.

        Uses the standard delta method matching `docker stats` output.
        """
        cpu_stats = stats_dict.get('cpu_stats', {})
        precpu_stats = stats_dict.get('precpu_stats', {})

        cpu_delta = (
            cpu_stats.get('cpu_usage', {}).get('total_usage', 0)
            - precpu_stats.get('cpu_usage', {}).get('total_usage', 0)
        )
        system_delta = (
            cpu_stats.get('system_cpu_usage', 0)
            - precpu_stats.get('system_cpu_usage', 0)
        )

        num_cpus = cpu_stats.get('online_cpus')
        if not num_cpus:
            percpu = cpu_stats.get('cpu_usage', {}).get('percpu_usage')
            num_cpus = len(percpu) if percpu else 1

        if system_delta > 0 and cpu_delta >= 0:
            return (cpu_delta / system_delta) * num_cpus * 100.0
        return 0.0

    def _collect_loop(self) -> None:
        """
        Main loop for the background thread.

        Polls container.stats(stream=False) at the configured interval.
        Exits gracefully if the container is stopped or removed.
        """
        while not self._stop_event.is_set():
            try:
                stats = self._container.stats(stream=False)

                cpu_pct = self._compute_cpu_percent(stats)
                mem_stats = stats.get('memory_stats', {})
                mem_usage = mem_stats.get('usage', 0)
                # Subtract cache for more accurate active memory reading
                cache = mem_stats.get('stats', {}).get('cache', 0)
                mem_usage = max(0, mem_usage - cache)
                mem_limit = mem_stats.get('limit', 0)

                sample = StatsSample(
                    timestamp=time.time(),
                    cpu_percent=cpu_pct,
                    memory_bytes=mem_usage,
                    memory_limit=mem_limit,
                )
                with self._lock:
                    self._samples.append(sample)

            except (docker.errors.APIError, docker.errors.NotFound) as e:
                self._logger.debug(f"Stats collection ended: {e}")
                break
            except Exception as e:
                self._logger.debug(f"Stats collection error: {e}")
                break

            self._stop_event.wait(self._interval)
