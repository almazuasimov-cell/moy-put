/// Экран истории записей с фильтрами
import 'package:flutter/material.dart';
import 'api_service.dart';
import 'models.dart';
import 'record_screen.dart';

class HistoryScreen extends StatefulWidget {
  const HistoryScreen({super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  List<DiaryEntry> _entries = [];
  bool _isLoading = true;
  String _searchText = '';
  String? _selectedTag;
  int? _moodFilter;

  @override
  void initState() {
    super.initState();
    _loadEntries();
  }

  Future<void> _loadEntries() async {
    setState(() => _isLoading = true);
    try {
      _entries = await ApiService.listEntries(
        limit: 200,
        moodMin: _moodFilter != null ? _moodFilter! : 0,
        tag: _selectedTag ?? '',
      );
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  List<DiaryEntry> get _filtered {
    if (_searchText.isEmpty) return _entries;
    return _entries.where((e) {
      final text = (e.structuredText + e.transcriptText).toLowerCase();
      return text.contains(_searchText.toLowerCase());
    }).toList();
  }

  Set<String> get _allTags {
    final tags = <String>{};
    for (final e in _entries) {
      tags.addAll(e.tags);
    }
    return tags;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('История'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(60),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: TextField(
              onChanged: (v) => setState(() => _searchText = v),
              decoration: InputDecoration(
                hintText: 'Поиск по тексту...',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _searchText.isNotEmpty
                    ? IconButton(onPressed: () => setState(() => _searchText = ''), icon: const Icon(Icons.clear))
                    : null,
                isDense: true,
                border: const OutlineInputBorder(),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              ),
            ),
          ),
        ),
      ),
      body: Column(
        children: [
          // Tag filters
          if (_allTags.isNotEmpty)
            SizedBox(
              height: 44,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  FilterChip(
                    label: const Text('Все'),
                    selected: _selectedTag == null,
                    onSelected: (_) { setState(() => _selectedTag = null); _loadEntries(); },
                  ),
                  ..._allTags.map((tag) => Padding(
                    padding: const EdgeInsets.only(left: 8),
                    child: FilterChip(
                      label: Text(tag),
                      selected: _selectedTag == tag,
                      onSelected: (_) { setState(() => _selectedTag = tag); _loadEntries(); },
                    ),
                  )),
                ],
              ),
            ),
          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _filtered.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.history_rounded, size: 48, color: cs.onSurfaceVariant),
                            const SizedBox(height: 12),
                            Text('Записей нет', style: TextStyle(color: cs.onSurfaceVariant)),
                          ],
                        ),
                      )
                    : ListView.builder(
                        itemCount: _filtered.length,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        itemBuilder: (ctx, i) {
                          final e = _filtered[i];
                          return Card(
                            margin: const EdgeInsets.only(bottom: 8),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: cs.primaryContainer,
                                child: Text(_moodEmoji(e.mood), style: const TextStyle(fontSize: 18)),
                              ),
                              title: Text(
                                e.structuredText.isNotEmpty ? e.structuredText : e.transcriptText,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(color: cs.onSurface),
                              ),
                              subtitle: Text(
                                '${e.formattedDate} ${e.formattedTime} • ${e.tags.take(3).join(', ')}',
                                style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant),
                              ),
                              onTap: () async {
                                await Navigator.push(
                                  context,
                                  MaterialPageRoute(builder: (_) => RecordScreen(existingEntry: e)),
                                );
                                _loadEntries();
                              },
                              trailing: IconButton(
                                icon: const Icon(Icons.delete_outline, color: Colors.red),
                                onPressed: () => _confirmDelete(e),
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }

  void _confirmDelete(DiaryEntry e) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить запись?'),
        content: const Text('Запись будет удалена навсегда.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Удалить', style: TextStyle(color: Colors.red))),
        ],
      ),
    );
    if (confirmed == true) {
      try {
        await ApiService.deleteEntry(e.id!);
        _loadEntries();
      } catch (err) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Ошибка: $err'), backgroundColor: Colors.red.shade700),
        );
      }
    }
  }

  String _moodEmoji(int mood) {
    if (mood >= 9) return '😊';
    if (mood >= 7) return '🙂';
    if (mood >= 5) return '😐';
    if (mood >= 3) return '😟';
    return '😢';
  }
}