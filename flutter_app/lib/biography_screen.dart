/// Экран биографии — генерация, просмотр, экспорт PDF
import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
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

  Future<void> _exportPdf() async {
    try {
      final path = await ApiService.downloadFile('/biography/pdf', 'biography.pdf');
      if (!mounted) return;
      await OpenFilex.open(path);
    } catch (e) {
      _showError('Ошибка экспорта: $e');
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
        title: const Text('Моя биография'),
        actions: [
          if (_content.isNotEmpty && !_isEditing) ...[
            IconButton(
              onPressed: _exportPdf,
              icon: const Icon(Icons.picture_as_pdf_rounded),
              tooltip: 'Экспорт PDF',
            ),
            IconButton(
              onPressed: () => setState(() => _isEditing = true),
              icon: const Icon(Icons.edit_rounded),
              tooltip: 'Редактировать',
            ),
          ],
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
          : _buildBody(theme, cs),
    );
  }

  Widget _buildBody(ThemeData theme, ColorScheme cs) {
    // Empty state
    if (_content.isEmpty && !_isGenerating) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 100,
                height: 100,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: cs.primaryContainer.withOpacity(0.5),
                ),
                child: Icon(Icons.menu_book_rounded, size: 48, color: cs.primary),
              ),
              const SizedBox(height: 24),
              Text(
                'Твоя биография',
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: cs.onSurface,
                ),
              ),
              const SizedBox(height: 12),
              Text(
                'AI проанализирует все твои записи\nи напишет книгу о твоём пути.\n\nЧем больше записей — тем глубже история.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: cs.onSurfaceVariant,
                  height: 1.6,
                  fontSize: 15,
                ),
              ),
              const SizedBox(height: 32),
              FilledButton.icon(
                onPressed: _generate,
                icon: const Icon(Icons.auto_awesome_rounded),
                label: const Text('Создать биографию'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(52),
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Generating
    if (_isGenerating) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(40),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SizedBox(
                width: 60,
                height: 60,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
              const SizedBox(height: 24),
              Text(
                'AI пишет твою биографию...',
                style: theme.textTheme.titleMedium?.copyWith(
                  color: cs.onSurface,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Анализирую записи, нахожу закономерности,\nсоставляю историю. Это займёт около минуты.',
                textAlign: TextAlign.center,
                style: TextStyle(color: cs.onSurfaceVariant, height: 1.5),
              ),
            ],
          ),
        ),
      );
    }

    // Editing
    if (_isEditing) {
      return SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
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
          ],
        ),
      );
    }

    // Display biography — beautiful book-like layout
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Book cover card
          Card(
            elevation: 0,
            color: cs.primaryContainer.withOpacity(0.3),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Icon(Icons.menu_book_rounded, size: 40, color: cs.primary),
                  const SizedBox(height: 8),
                  Text(
                    'Мой путь',
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: cs.onSurface,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Автобиография',
                    style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          // Content — parse markdown sections
          ..._parseBiography(_content, theme, cs),

          const SizedBox(height: 24),

          // Actions
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _generate,
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  label: const Text('Обновить'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: FilledButton.icon(
                  onPressed: _exportPdf,
                  icon: const Icon(Icons.download_rounded, size: 18),
                  label: const Text('PDF'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 40),
        ],
      ),
    );
  }

  List<Widget> _parseBiography(String content, ThemeData theme, ColorScheme cs) {
    final widgets = <Widget>[];
    final lines = content.split('\n');

    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty) {
        widgets.add(const SizedBox(height: 8));
        continue;
      }

      if (trimmed.startsWith('## ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 20, bottom: 8),
          child: Text(
            trimmed.substring(3),
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: cs.primary,
            ),
          ),
        ));
      } else if (trimmed.startsWith('# ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 16, bottom: 8),
          child: Text(
            trimmed.substring(2),
            style: theme.textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.bold,
              color: cs.onSurface,
            ),
          ),
        ));
      } else {
        widgets.add(Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            trimmed,
            style: theme.textTheme.bodyLarge?.copyWith(
              height: 1.7,
              color: cs.onSurface,
            ),
          ),
        ));
      }
    }

    return widgets;
  }
}
