/// Экран биографии — генерация и просмотр
import 'package:flutter/material.dart';
import 'api_service.dart';

class BiographyScreen extends StatefulWidget {
  const BiographyScreen({super.key});

  @override
  State<BiographyScreen> createState() => _BiographyScreenState();
}

class _BiographyScreenState extends State<BiographyScreen> {
  String _content = '';
  bool _isLoading = true;
  bool _isGenerating = false;
  final _editController = TextEditingController();
  bool _isEditing = false;

  @override
  void initState() {
    super.initState();
    _loadBiography();
  }

  @override
  void dispose() {
    _editController.dispose();
    super.dispose();
  }

  Future<void> _loadBiography() async {
    setState(() => _isLoading = true);
    try {
      _content = await ApiService.getBiography();
      _editController.text = _content;
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  Future<void> _generate() async {
    setState(() => _isGenerating = true);
    try {
      _content = await ApiService.generateBiography();
      _editController.text = _content;
    } catch (e) {
      _showError(e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _isGenerating = false);
    }
  }

  Future<void> _saveEdit() async {
    try {
      await ApiService.updateBiography(_editController.text);
      _content = _editController.text;
      setState(() => _isEditing = false);
      _showSuccess('Сохранено');
    } catch (e) {
      _showError('Ошибка сохранения');
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.red.shade700),
    );
  }

  void _showSuccess(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.green.shade700),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Биография'),
        actions: [
          if (_content.isNotEmpty && !_isEditing)
            IconButton(
              onPressed: () => setState(() => _isEditing = true),
              icon: const Icon(Icons.edit_rounded),
              tooltip: 'Редактировать',
            ),
          if (_isEditing)
            IconButton(
              onPressed: _saveEdit,
              icon: const Icon(Icons.check_rounded),
              tooltip: 'Сохранить',
            ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_content.isEmpty && !_isGenerating) ...[
                    const SizedBox(height: 80),
                    Icon(Icons.menu_book_rounded, size: 64, color: cs.onSurfaceVariant),
                    const SizedBox(height: 16),
                    Text(
                      'Биография ещё не создана',
                      textAlign: TextAlign.center,
                      style: theme.textTheme.titleMedium?.copyWith(color: cs.onSurfaceVariant),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'AI проанализирует все твои записи\nи составит историю твоего пути',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: cs.onSurfaceVariant),
                    ),
                    const SizedBox(height: 32),
                    FilledButton.icon(
                      onPressed: _generate,
                      icon: const Icon(Icons.auto_awesome_rounded),
                      label: const Text('Создать биографию'),
                    ),
                  ] else if (_isGenerating) ...[
                    const SizedBox(height: 80),
                    const Center(child: CircularProgressIndicator()),
                    const SizedBox(height: 16),
                    Center(
                      child: Text('AI пишет биографию...\nЭто может занять минуту',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: cs.onSurfaceVariant),
                      ),
                    ),
                  ] else if (_isEditing) ...[
                    TextField(
                      controller: _editController,
                      maxLines: null,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        labelText: 'Редактирование биографии',
                      ),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton(
                      onPressed: () => setState(() => _isEditing = false),
                      child: const Text('Отмена'),
                    ),
                  ] else ...[
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Text(
                          _content,
                          style: theme.textTheme.bodyLarge?.copyWith(height: 1.6),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    OutlinedButton.icon(
                      onPressed: _generate,
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('Обновить'),
                    ),
                  ],
                ],
              ),
            ),
    );
  }
}