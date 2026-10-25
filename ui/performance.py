"""Live performance readout and saved benchmark comparison."""
from PySide6.QtCore import Qt, Slot, Signal
from PySide6.QtWidgets import QWidget, QFormLayout, QLabel, QVBoxLayout, QPlainTextEdit, QGridLayout, QFrame, QScrollArea, QPushButton, QHBoxLayout
from core.preferences import read_json
from core.benchmark import compare_results
from ui.resource_graph import ResourceGraph


class LivePerformance(QWidget):
    def __init__(self, events, compact=False, parent=None, dashboard=False):
        super().__init__(parent)
        self.compact = compact
        self._labels = {}
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        charts=QGridLayout() if dashboard else QVBoxLayout();outer.addLayout(charts)
        definitions=[([('cpu_percent','CPU','accent')],'App CPU','%',100),([('memory_mb','RAM','accent')],'App RAM','MB',None)]
        if dashboard:definitions += [([('gpu_percent','Busiest engine','accent')],'App GPU: busiest engine','%',100),([('gpu_memory_mb','Dedicated memory','accent')],'App GPU memory','MB',None)]
        for index,(fields,title,unit,maximum) in enumerate(definitions):
            graph=ResourceGraph(events,fields,title,unit,maximum)
            if dashboard:
                frame=QFrame();frame.setObjectName('resourceCard');box=QVBoxLayout(frame);box.setContentsMargins(10,8,10,8);box.addWidget(graph);graph.setMinimumHeight(145);charts.addWidget(frame,index//2,index%2)
            else:
                if compact:graph.setMinimumHeight(82)
                charts.addWidget(graph)
        if not compact and not dashboard:
            outer.addWidget(ResourceGraph(events,[('gpu_percent','Busiest engine','accent')],'App GPU: busiest engine','%',100))
            outer.addWidget(ResourceGraph(events,[('stt_ms','Speech','accent'),('mt_ms','Translation','en')],'Last completed segment: speech / translation','ms'))
            hint=QLabel('Dotted markers: processing activity. Hover for values and events. Timings hold the last completed segment.')
            hint.setWordWrap(True);hint.setObjectName('hint');outer.addWidget(hint)
        layout = QFormLayout()
        outer.addLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        fields = [('resources', 'App resources'), ('backend', 'Active engine')]
        if not compact:
            fields += [('analysis','History analysis'),('recheck','Manual recheck')]
        if not compact:
            fields += [('health','Recommendation'), ('stages', 'Last speech segment'), ('delay', 'Subtitle delay'), ('queue', 'Live audio queue'),
                       ('gpu', 'GPU monitoring')]
        for key, title in fields:
            label = QLabel('Waiting for measurement',self)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.PlainText)
            self._labels[key] = label
            if not dashboard or key in ('backend','analysis','gpu','delay'):layout.addRow(title,label)
            else:label.hide()
        self.setToolTip('CPU is the share of total machine capacity used by GrammAI and its child processes. Timings exclude speech collection and queue wait.')
        events.metrics_changed.connect(self.update_metrics)
        history=events.property('resource_history') or ()
        if history:self.update_metrics(history[-1][1])

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
            status=data.get('analysis_status','Unloaded')
            duration=data.get('analysis_duration_ms')
            self._labels['analysis'].setText(status+(f' / Last analysis {duration/1000:.1f}s' if duration is not None else ''))
            recheck=data.get('recheck_duration_ms')
            self._labels['recheck'].setText(f'Last recheck {recheck/1000:.1f}s (includes model loading)' if recheck is not None else 'No manual recheck this session')
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
            gpu,vram=data.get('gpu_percent'),data.get('gpu_memory_mb')
            self._labels['gpu'].setText(f'Busiest app GPU engine {gpu:.1f}% / Dedicated GPU memory {vram:.0f} MB' if gpu is not None and vram is not None else 'GPU counters unavailable; verified backend status is shown separately.')


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


class ResourcesPage(QWidget):
    compare_requested=Signal()

    def __init__(self,events,parent=None):
        super().__init__(parent);self.setObjectName('resourcesPage')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(2,8,8,8);box.setSpacing(14)
        row=QHBoxLayout();heading=QLabel('App resources');heading.setObjectName('field');row.addWidget(heading);row.addStretch()
        span=QLabel('Last 2 minutes');span.setObjectName('hint');row.addWidget(span);box.addLayout(row)
        self.monitor=LivePerformance(events,parent=self,dashboard=True);box.addWidget(self.monitor)
        hint=QLabel('App and child processes. Hover a graph for values. Missing GPU counters are reported as unavailable.');hint.setObjectName('hint');hint.setWordWrap(True);box.addWidget(hint)
        compare=QPushButton('Compare configurations');compare.clicked.connect(self.compare_requested.emit);box.addWidget(compare,0,Qt.AlignmentFlag.AlignLeft);box.addStretch()
        scroll.setWidget(body);outer.addWidget(scroll)
