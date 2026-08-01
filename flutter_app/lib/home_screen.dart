/// Главный экран — превью, график настроения, кнопка записи
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'api_service.dart';
import 'models.dart';
import 'record_screen.dart';
import 'history_screen.dart';
import 'search_screen.dart';
import 'biography_screen.dart';
import 'settings_screen.dart';
import 'auth_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _userName = '';
  Stats? _stats;
  List<DiaryEntry> _recentEntries = [];
  bool _isLoading = true;
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    try {
      _userName = (await ApiService.getUserName()) ?? 'Друг';
      _stats = await ApiService.getStats(period: 'month');
      _recentEntries = await ApiService.listEntries(limit: 5);
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  void _logout() async {
    await ApiService.logout();
    if (mounted) {
      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const AuthScreen()),
        (_) => false,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    final screens = <Widget>[
      _buildHomeTab(theme, cs),
      const HistoryScreen(),
      const SearchScreen(),
      const BiographyScreen(),
      SettingsScreen(onLogout: _logout),
    ];

    return Scaffold(
      body: IndexedStack(index: _currentIndex, children: screens),
      floatingActionButton: _currentIndex == 0
          ? FloatingActionButton.extended(
              onPressed: () async {
                await Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const RecordScreen()),
                );
                _loadData();
              },
              icon: const Icon(Icons.mic_rounded),
              label: const Text('Новая запись'),
            )
          : null,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex,
        onDestinationSelected: (i) => setState(() => _currentIndex = i),
        destinations: [
          NavigationDestination(icon: const Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home_rounded, color: cs.primary), label: 'Главная'),
          NavigationDestination(icon: const Icon(Icons.history_outlined), selectedIcon: Icon(Icons.history_rounded, color: cs.primary), label: 'История'),
          NavigationDestination(icon: const Icon(Icons.chat_bubble_outline), selectedIcon: Icon(Icons.chat_rounded, color: cs.primary), label: 'Поиск'),
          NavigationDestination(icon: const Icon(Icons.menu_book_outlined), selectedIcon: Icon(Icons.menu_book_rounded, color: cs.primary), label: 'Биография'),
          NavigationDestination(icon: const Icon(Icons.person_outline), selectedIcon: Icon(Icons.person_rounded, color: cs.primary), label: 'Профиль'),
        ],
      ),
    );
  }

  // ── Home tab ──────────────────────────────────────────
  Widget _buildHomeTab(ThemeData theme, ColorScheme cs) {
    return SafeArea(
      child: RefreshIndicator(
        onRefresh: _loadData,
        child: CustomScrollView(
          slivers: [
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Привет, $_userName!',
                      style: theme.textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: cs.onSurface,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _todayString(),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: cs.onSurfaceVariant,
                      ),
                    ),
                    const SizedBox(height: 24),

                    if (_stats != null) ...[
                      Row(
                        children: [
                          _statCard('Записей', '${_stats!.totalEntries}', Icons.note_rounded, cs),
                          const SizedBox(width: 12),
                          _statCard('Серия', '${_stats!.streak} 🔥', Icons.local_fire_department_rounded, cs),
                          const SizedBox(width: 12),
                          _statCard('Настроение', _stats!.avgMood.toStringAsFixed(1), Icons.mood_rounded, cs),
                        ],
                      ),
                      const SizedBox(height: 24),

                      if (_stats!.moodTrend.isNotEmpty) ...[
                        Text('График настроения', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: cs.onSurface)),
                        const SizedBox(height: 12),
                        SizedBox(height: 160, child: _moodChart(cs)),
                        const SizedBox(height: 24),
                      ],

                      if (_stats!.topTags.isNotEmpty) ...[
                        Text('Частые теги', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: cs.onSurface)),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          children: _stats!.topTags.take(8).map((t) => Chip(
                            label: Text('${t.tag} (${t.count})'),
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          )).toList(),
                        ),
                        const SizedBox(height: 24),
                      ],
                    ],

                    Text('Последние записи', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold, color: cs.onSurface)),
                    const SizedBox(height: 12),

                    if (_isLoading)
                      const Center(child: Padding(padding: EdgeInsets.all(40), child: CircularProgressIndicator()))
                    else if (_recentEntries.isEmpty)
                      Center(
                        child: Padding(
                          padding: const EdgeInsets.all(40),
                          child: Column(
                            children: [
                              Icon(Icons.mic_none_rounded, size: 48, color: cs.onSurfaceVariant),
                              const SizedBox(height: 12),
                              Text('Нажми «Новая запись»\nи расскажи о своём дне',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: cs.onSurfaceVariant)),
                            ],
                          ),
                        ),
                      )
                    else
                      ..._recentEntries.map((e) => _entryCard(e, cs)),

                    const SizedBox(height: 80),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statCard(String label, String value, IconData icon, ColorScheme cs) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
          child: Column(
            children: [
              Icon(icon, color: cs.primary, size: 28),
              const SizedBox(height: 8),
              Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: cs.onSurface)),
              const SizedBox(height: 4),
              Text(label, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _moodChart(ColorScheme cs) {
    final points = _stats!.moodTrend;
    final spots = <FlSpot>[];
    for (var i = 0; i < points.length; i++) {
      spots.add(FlSpot(i.toDouble(), points[i].mood.toDouble()));
    }
    return LineChart(
      LineChartData(
        minY: 0,
        maxY: 10,
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: 2,
          getDrawingHorizontalLine: (v) => FlLine(color: cs.onSurfaceVariant.withOpacity(0.1), strokeWidth: 1),
        ),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              interval: 5,
              getTitlesWidget: (v, _) => Text('${v.toInt()}', style: TextStyle(fontSize: 10, color: cs.onSurfaceVariant)),
              reservedSize: 28,
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              interval: (points.length / 5).ceilToDouble().clamp(1, 99999),
              getTitlesWidget: (v, _) {
                final i = v.toInt();
                if (i < 0 || i >= points.length) return const SizedBox.shrink();
                return Text(points[i].date, style: TextStyle(fontSize: 9, color: cs.onSurfaceVariant));
              },
              reservedSize: 24,
            ),
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: cs.primary,
            barWidth: 3,
            dotData: FlDotData(show: false),
            belowBarData: BarAreaData(show: true, color: cs.primary.withOpacity(0.1)),
          ),
        ],
      ),
    );
  }

  Widget _entryCard(DiaryEntry e, ColorScheme cs) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: cs.primaryContainer,
          child: Text(_moodEmoji(e.mood), style: const TextStyle(fontSize: 20)),
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
          _loadData();
        },
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

  String _todayString() {
    final now = DateTime.now();
    const months = ['', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
    const weekdays = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
    return '${weekdays[now.weekday - 1]}, ${now.day} ${months[now.month]}';
  }
}