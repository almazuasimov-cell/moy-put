/// Экран подписки — информация о тарифах и лимитах
import 'package:flutter/material.dart';
import 'api_service.dart';

class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key});

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  Map<String, dynamic>? _subInfo;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _isLoading = true);
    try {
      _subInfo = await ApiService.getSubscription();
    } catch (_) {}
    if (mounted) setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Подписка')),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : SingleChildScrollView(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Current plan
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        children: [
                          Icon(
                            _subInfo?['plan'] == 'premium'
                                ? Icons.diamond_rounded
                                : Icons.auto_awesome_rounded,
                            size: 48,
                            color: _subInfo?['plan'] == 'premium'
                                ? const Color(0xFF6750A4)
                                : cs.primary,
                          ),
                          const SizedBox(height: 12),
                          Text(
                            _subInfo?['plan'] == 'premium' ? 'Premium' : 'Бесплатный',
                            style: theme.textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          if (_subInfo?['expires_at'] != null) ...[
                            const SizedBox(height: 4),
                            Text(
                              'Действует до ${_subInfo!['expires_at'].toString().substring(0, 10)}',
                              style: TextStyle(color: cs.onSurfaceVariant),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),

                  // Limits
                  Text(
                    'Использование',
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  _limitRow(
                    'Голосовые записи',
                    _subInfo?['voice_entries_used'] ?? 0,
                    _subInfo?['voice_entries_limit'] ?? 3,
                    Icons.mic_rounded,
                    cs,
                  ),
                  _limitRow(
                    'Генерации биографии',
                    _subInfo?['biography_generations_used'] ?? 0,
                    _subInfo?['biography_generations_limit'] ?? 1,
                    Icons.menu_book_rounded,
                    cs,
                  ),
                  _limitRow(
                    'AI-поиски',
                    _subInfo?['ai_searches_used'] ?? 0,
                    _subInfo?['ai_searches_limit'] ?? 5,
                    Icons.search_rounded,
                    cs,
                  ),
                  const SizedBox(height: 32),

                  // Plans comparison
                  Text(
                    'Тарифы',
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(child: _planCard('Бесплатный', '0₽', [
                        '3 голосовые записи',
                        '1 биография',
                        '5 AI-поисков',
                        'Базовая статистика',
                      ], false, cs)),
                      const SizedBox(width: 12),
                      Expanded(child: _planCard('Premium', '299₽/мес', [
                        'Безлимит записей',
                        'Биография без ограничений',
                        'AI-поиск без ограничений',
                        'Экспорт PDF',
                        'Фильм по биографии (скоро)',
                      ], true, cs)),
                    ],
                  ),
                  const SizedBox(height: 24),

                  // Upgrade button
                  if (_subInfo?['plan'] != 'premium')
                    FilledButton.icon(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Оплата будет доступна в ближайшее время'),
                          ),
                        );
                      },
                      icon: const Icon(Icons.diamond_rounded),
                      label: const Text('Перейти на Premium — 299₽/мес'),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size.fromHeight(52),
                        backgroundColor: const Color(0xFF6750A4),
                      ),
                    ),
                ],
              ),
            ),
    );
  }

  Widget _limitRow(String label, int used, int limit, IconData icon, ColorScheme cs) {
    final progress = limit > 0 ? used / limit : 1.0;
    final isFull = used >= limit;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: isFull ? Colors.red.shade400 : cs.primary),
              const SizedBox(width: 8),
              Text(label, style: TextStyle(fontSize: 14, color: cs.onSurface)),
              const Spacer(),
              Text(
                '$used / $limit',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: isFull ? Colors.red.shade400 : cs.onSurfaceVariant,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: progress.clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: cs.onSurfaceVariant.withOpacity(0.1),
              valueColor: AlwaysStoppedAnimation(
                isFull ? Colors.red.shade400 : cs.primary,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _planCard(
    String name,
    String price,
    List<String> features,
    bool isPremium,
    ColorScheme cs,
  ) {
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: isPremium
            ? const BorderSide(color: Color(0xFF6750A4), width: 2)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(name, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: cs.onSurface)),
            const SizedBox(height: 4),
            Text(price, style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: cs.primary)),
            const SizedBox(height: 12),
            ...features.map((f) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.check_rounded, size: 16, color: cs.primary),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(f, style: TextStyle(fontSize: 12, color: cs.onSurfaceVariant)),
                      ),
                    ],
                  ),
                )),
          ],
        ),
      ),
    );
  }
}
