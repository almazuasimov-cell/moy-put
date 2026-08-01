/// Экран записи голосом + просмотр/редактирование записи
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'api_service.dart';
import 'models.dart';

class RecordScreen extends StatefulWidget {
  final DiaryEntry? existingEntry;

  const RecordScreen({super.key, this.existingEntry});

  @override
  State<RecordScreen> createState() => _RecordScreenState();
}

class _RecordScreenState extends State<RecordScreen> {
  final _audioRecorder = AudioRecorder();
  final _textController = TextEditingController();

  bool _isRecording = false;
  bool _isProcessing = false;
  bool _hasProcessed = false;
  String? _recordingPath;

  ProcessResult? _result;
  int _mood = 5;
  List<String> _tags = [];
  String _aiSummary = '';
  String _reflection = '';

  @override
  void initState() {
    super.initState();
    if (widget.existingEntry != null) {
      final e = widget.existingEntry!;
      _textController.text = e.structuredText.isNotEmpty ? e.structuredText : e.transcriptText;
      _mood = e.mood;
      _tags = e.tags;
      _aiSummary = e.aiSummary;
      _reflection = e.reflection;
      _hasProcessed = true;
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    _audioRecorder.dispose();
    super.dispose();
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      await _stopRecording();
    } else {
      await _startRecording();
    }
  }

  Future<void> _startRecording() async {
    final status = await Permission.microphone.request();
    if (!status.isGranted) {
      _showError('Нужен доступ к микрофону');
      return;
    }
    try {
      final dir = await getTemporaryDirectory();
      final path = '${dir.path}/voice_diary_${DateTime.now().millisecondsSinceEpoch}.m4a';
      await _audioRecorder.start(
        RecordConfig(encoder: AudioEncoder.aacLc, bitRate: 128000, sampleRate: 44100),
        path: path,
      );
      setState(() {
        _isRecording = true;
        _recordingPath = path;
        _hasProcessed = false;
        _result = null;
      });
    } catch (e) {
      _showError('Ошибка записи: $e');
    }
  }

  Future<void> _stopRecording() async {
    try {
      await _audioRecorder.stop();
      setState(() => _isRecording = false);

      // Auto-transcribe
      if (_recordingPath != null) {
        setState(() => _isProcessing = true);
        try {
          final text = await ApiService.transcribeAudio(File(_recordingPath!));
          _textController.text = text;
          setState(() => _isProcessing = false);
          // Auto-process
          await _process();
        } catch (e) {
          setState(() => _isProcessing = false);
          _showError('Распознавание: $e');
        }
      }
    } catch (e) {
      setState(() => _isRecording = false);
      _showError('Ошибка остановки: $e');
    }
  }

  Future<void> _process() async {
    if (_textController.text.trim().isEmpty) {
      _showError('Сначала запиши или введи текст');
      return;
    }
    setState(() => _isProcessing = true);
    try {
      final result = await ApiService.processEntry(_textController.text);
      setState(() {
        _result = result;
        _mood = result.mood;
        _tags = result.tags;
        _aiSummary = result.aiSummary;
        _reflection = result.reflection;
        if (result.structuredText.isNotEmpty) {
          _textController.text = result.structuredText;
        }
        _hasProcessed = true;
      });
    } catch (e) {
      _showError('AI-обработка: $e');
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  Future<void> _save() async {
    if (_textController.text.trim().isEmpty) {
      _showError('Текст пустой');
      return;
    }
    setState(() => _isProcessing = true);
    try {
      final entry = DiaryEntry(
        transcriptText: _textController.text,
        structuredText: _textController.text,
        mood: _mood,
        tags: _tags,
        topics: _result?.topics ?? [],
        aiSummary: _aiSummary,
        reflection: _reflection,
      );
      if (widget.existingEntry?.id != null) {
        await ApiService.updateEntry(widget.existingEntry!.id!, entry);
      } else {
        await ApiService.createEntry(entry);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      _showError('Сохранение: $e');
    } finally {
      if (mounted) setState(() => _isProcessing = false);
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.red.shade700),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final isEditing = widget.existingEntry != null;

    return Scaffold(
      appBar: AppBar(
        title: Text(isEditing ? 'Запись' : 'Новая запись'),
        actions: [
          if (_hasProcessed)
            IconButton(
              onPressed: _isProcessing ? null : _save,
              icon: _isProcessing
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.check_rounded),
              tooltip: 'Сохранить',
            ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Record button
            if (!isEditing) ...[
              Center(
                child: GestureDetector(
                  onTap: _toggleRecording,
                  child: Container(
                    width: 100,
                    height: 100,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _isRecording ? Colors.red.shade400 : cs.primaryContainer,
                    ),
                    child: Icon(
                      _isRecording ? Icons.stop_rounded : Icons.mic_rounded,
                      size: 48,
                      color: _isRecording ? Colors.white : cs.primary,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  _isRecording ? 'Запись... (нажми чтобы остановить)' : 'Нажми чтобы записать',
                  style: TextStyle(color: cs.onSurfaceVariant),
                ),
              ),
              const SizedBox(height: 24),
            ],

            if (_isProcessing)
              const Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: Column(
                  children: [
                    CircularProgressIndicator(),
                    SizedBox(height: 12),
                    Text('AI обрабатывает...'),
                  ],
                )),
              )
            else ...[
              // Text field
              TextField(
                controller: _textController,
                maxLines: 8,
                decoration: InputDecoration(
                  labelText: 'Текст записи',
                  hintText: 'Расскажи о своём дне...',
                  border: const OutlineInputBorder(),
                  prefixIcon: const Icon(Icons.edit_note),
                  suffixIcon: IconButton(
                    onPressed: _process,
                    icon: const Icon(Icons.auto_awesome_rounded),
                    tooltip: 'AI-обработать',
                  ),
                ),
              ),
              const SizedBox(height: 16),

              if (_hasProcessed) ...[
                // Mood selector
                Text('Настроение: $_mood/10 ${_moodEmoji(_mood)}', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
                Slider(
                  value: _mood.toDouble(),
                  min: 1,
                  max: 10,
                  divisions: 9,
                  onChanged: (v) => setState(() => _mood = v.round()),
                ),
                const SizedBox(height: 8),

                // Tags
                if (_tags.isNotEmpty) ...[
                  Wrap(
                    spacing: 8,
                    children: _tags.map((t) => Chip(
                      label: Text(t),
                      onDeleted: () => setState(() => _tags.remove(t)),
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    )).toList(),
                  ),
                  const SizedBox(height: 8),
                ],

                // AI Summary
                if (_aiSummary.isNotEmpty) ...[
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(children: [
                            Icon(Icons.summarize_rounded, color: cs.primary, size: 20),
                            const SizedBox(width: 8),
                            Text('Саммари', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold)),
                          ]),
                          const SizedBox(height: 8),
                          Text(_aiSummary, style: theme.textTheme.bodyMedium),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                ],

                // Reflection
                if (_reflection.isNotEmpty) ...[
                  Card(
                    color: cs.secondaryContainer.withOpacity(0.5),
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(children: [
                            Icon(Icons.lightbulb_outline_rounded, color: cs.secondary, size: 20),
                            const SizedBox(width: 8),
                            Text('Вопрос для размышления', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold)),
                          ]),
                          const SizedBox(height: 8),
                          Text(_reflection, style: theme.textTheme.bodyMedium?.copyWith(fontStyle: FontStyle.italic)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                ],

                // Save button
                FilledButton.icon(
                  onPressed: _isProcessing ? null : _save,
                  icon: const Icon(Icons.check_rounded),
                  label: Text(isEditing ? 'Обновить' : 'Сохранить запись'),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  String _moodEmoji(int mood) {
    if (mood >= 9) return '😊';
    if (mood >= 7) return '🙂';
    if (mood >= 5) return '😐';
    if (mood >= 3) return '😟';
    return '😢';
  }
}