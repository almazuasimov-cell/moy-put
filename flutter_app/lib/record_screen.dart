/// Экран записи голосом + просмотр/редактирование записи
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:record/record.dart';
import 'package:audioplayers/audioplayers.dart';
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

class _RecordScreenState extends State<RecordScreen> with WidgetsBindingObserver {
  final _audioRecorder = AudioRecorder();
  final _audioPlayer = AudioPlayer();
  final _textController = TextEditingController();

  bool _isRecording = false;
  bool _isProcessing = false;
  bool _hasProcessed = false;
  bool _isPlaying = false;
  String? _recordingPath;
  String? _audioS3Key;

  ProcessResult? _result;
  int _mood = 5;
  List<String> _tags = [];
  String _aiSummary = '';
  String _reflection = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _audioPlayer.onPlayerComplete.listen((_) {
      if (mounted) setState(() => _isPlaying = false);
    });
    if (widget.existingEntry != null) {
      final e = widget.existingEntry!;
      _textController.text = e.structuredText.isNotEmpty ? e.structuredText : e.transcriptText;
      _mood = e.mood;
      _tags = e.tags;
      _aiSummary = e.aiSummary;
      _reflection = e.reflection;
      _audioS3Key = e.audioS3Key;
      _hasProcessed = true;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _textController.dispose();
    _audioRecorder.dispose();
    _audioPlayer.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Входящий звонок, сворачивание приложения и т.п. во время записи —
    // не оставляем recorder работать в никуда, аккуратно останавливаем.
    if (state == AppLifecycleState.paused && _isRecording) {
      _cancelRecording();
    }
  }

  Future<void> _togglePlayback() async {
    if (_recordingPath == null) return;
    if (_isPlaying) {
      await _audioPlayer.pause();
      if (mounted) setState(() => _isPlaying = false);
    } else {
      await _audioPlayer.play(DeviceFileSource(_recordingPath!));
      if (mounted) setState(() => _isPlaying = true);
    }
  }

  Future<void> _toggleRecording() async {
    if (_isRecording) {
      await _stopRecording();
    } else {
      await _startRecording();
    }
  }

  Future<void> _startRecording() async {
    if (_isPlaying) {
      await _audioPlayer.stop();
      _isPlaying = false;
    }
    final status = await Permission.microphone.request();
    if (!mounted) return;
    if (status.isPermanentlyDenied) {
      // Пользователь отказал "навсегда" (или запретил в системных
      // настройках) — повторный request() ничего не покажет, единственный
      // выход — открыть настройки приложения вручную.
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Доступ к микрофону запрещён. Открой настройки приложения, чтобы разрешить.'),
          backgroundColor: Colors.red.shade700,
          action: SnackBarAction(
            label: 'Настройки',
            onPressed: openAppSettings,
          ),
        ),
      );
      return;
    }
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
      if (!mounted) return;
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

  /// Отменить запись в процессе — остановить и удалить файл, без
  /// распознавания/сохранения. Также срабатывает при сворачивании
  /// приложения (входящий звонок и т.п.) во время записи.
  Future<void> _cancelRecording() async {
    try {
      final path = await _audioRecorder.stop();
      final file = File(path ?? _recordingPath ?? '');
      if (await file.exists()) await file.delete();
    } catch (_) {}
    if (mounted) {
      setState(() {
        _isRecording = false;
        _recordingPath = null;
      });
    }
  }

  Future<void> _stopRecording() async {
    try {
      await _audioRecorder.stop();
      if (!mounted) return;
      setState(() => _isRecording = false);

      // Auto-transcribe
      if (_recordingPath != null) {
        setState(() => _isProcessing = true);
        try {
          final (text, audioS3Key) = await ApiService.transcribeAudio(File(_recordingPath!));
          if (!mounted) return;
          _textController.text = text;
          _audioS3Key = audioS3Key;
          setState(() => _isProcessing = false);
          // Auto-process
          await _process();
        } catch (e) {
          if (!mounted) return;
          setState(() => _isProcessing = false);
          _showError('Распознавание: $e');
        }
      }
    } catch (e) {
      if (!mounted) return;
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
      if (!mounted) return;
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
        audioS3Key: _audioS3Key,
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
    if (!mounted) return;
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
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (_isRecording) ...[
                    IconButton(
                      onPressed: _cancelRecording,
                      icon: const Icon(Icons.close_rounded),
                      tooltip: 'Отменить запись',
                      style: IconButton.styleFrom(
                        backgroundColor: cs.surfaceContainerHighest,
                        minimumSize: const Size(48, 48),
                      ),
                    ),
                    const SizedBox(width: 20),
                  ],
                  GestureDetector(
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
                ],
              ),
              const SizedBox(height: 12),
              Center(
                child: Text(
                  _isRecording ? 'Запись... (нажми чтобы остановить)' : 'Нажми чтобы записать',
                  style: TextStyle(color: cs.onSurfaceVariant),
                ),
              ),
              if (!_isRecording && _recordingPath != null) ...[
                const SizedBox(height: 16),
                Center(
                  child: OutlinedButton.icon(
                    onPressed: _togglePlayback,
                    icon: Icon(_isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded),
                    label: Text(_isPlaying ? 'Пауза' : 'Прослушать запись'),
                  ),
                ),
              ],
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