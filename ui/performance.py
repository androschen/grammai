"""Live performance readout and saved benchmark comparison."""
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QVBoxLayout, QPlainTextEdit
from core.preferences import read_json
from core.benchmark import compare_results


class LivePerformance(QWidget):
    def __init__(self, events, compact=False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self._labels = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        fields = [('resources', 'App resources'), ('backend', 'Active engine')]
        if not compact:
            fields += [('health','Recommendation'), ('stages', 'Last speech segment'), ('delay', 'Subtitle delay'), ('queue', 'Live audio queue'),
                       ('gpu', 'GPU monitoring')]
        for key, title in fields:
            label = QLabel('Waiting for measurement')
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            self._labels[key] = label
            layout.addRow(title, label)
        self.setToolTip('CPU is the share of total machine capacity used by GrammAI and its child processes. Timings exclude speech collection and queue wait.')
        events.metrics_changed.connect(self.update_metrics)

    @Slot(object)
    def update_metrics(self, data):
        if data.get('kind') != 'live':
            return
        cpu, ram = data.get('cpu_percent'), data.get('memory_mb')
        self._labels['resources'].setText(f'{cpu:.1f}% CPU  /  {ram:.0f} MB RAM' if cpu is not None and ram is not None else 'CPU / memory unavailable')
        engine = data.get('backend', 'Stopped')
        model = data.get('model', '')
        self._labels['backend'].setText(f'{engine} / {model}' if model else engine)
        if not self.compact:
            if not data.get('running'):
                self._labels['health'].setText('Start translation to measure live speech processing.')
            elif data.get('audio_seconds',0) and data.get('total_ms',0) > data['audio_seconds'] * 1000:
                self._labels['health'].setText('Processing is slower than incoming speech. Try Low resource or GPU mode.')
            elif data.get('backlog_seconds',0) > 1:
                self._labels['health'].setText('Audio is waiting. Try a lighter preset if the queue keeps growing.')
            else:
                self._labels['health'].setText('Watching live processing. Compare presets using the benchmark.')
            if 'stt_ms' in data:
                self._labels['stages'].setText(f"Speech {data['stt_ms']:.0f} ms / Translation {data['mt_ms']:.0f} ms / Total {data['total_ms']:.0f} ms")
            if "subtitle_delay_ms" in data:
                self._labels["delay"].setText(f"{data['subtitle_delay_ms']/1000:.1f}s from speech start (includes collection and queue)")
            self._labels['queue'].setText(f"{data.get('backlog_seconds',0):.1f}s waiting / {data.get('dropped_seconds',0):.1f}s dropped this session")
            self._labels['gpu'].setText('Utilization and VRAM unavailable; backend status is shown separately.')


class BenchmarkResults(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(130)
        runs = read_json('benchmarks.json', [])
        if isinstance(runs, list) and runs:
            self.show_result(runs[-1])
        else:
            self.setPlainText('No benchmark yet. Compare presets using the same English speech sample and English-to-Chinese translation text. Live translation pauses during the test.')

    @Slot(object)
    def show_result(self, result):
        if 'error' in result:
            self.setPlainText('Benchmark failed: ' + result['error'])
            return
        runs = read_json('benchmarks.json', [])
        previous = runs[-2] if len(runs)>1 and runs[-1].get('date')==result.get('date') else None
        lines = [compare_results(result,previous)]
        for item in reversed(runs[-2:] if runs else [result]):
            lines.append(f"\n{item['date'][:19]} UTC | {item['preset']} | {item['backend']}\n"
                f"Speech {item['stt_ms']:.0f} ms / Translation {item['mt_ms']:.0f} ms / Combined {item['total_ms']:.0f} ms\n"
                f"Model loading {item['loading_seconds']:.1f}s (separate) | Audio {item['audio_seconds']:.1f}s\n"
                f"CPU threads: speech {item['cpu_threads']}, translation {item['translation_threads']}\n"
                f"App CPU: {item.get('cpu_percent',0):.1f}% machine share / Sampled RAM: {item.get('memory_mb',0):.0f} MB\n"
                f"Recognized: {item['transcript']}\nTranslated: {item['translation']}")
        self.setPlainText('\n'.join(lines))
