/// Экран настроек/профиля
import 'package:flutter/material.dart';

import 'api_service.dart';
import 'config.dart';
import 'subscription_screen.dart';
import 'referral_screen.dart';

class SettingsScreen extends StatelessWidget {
  final VoidCallback? onLogout;
  final bool isSetup;

  const SettingsScreen({super.key, this.onLogout, this.isSetup = false});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final urlController = TextEditingController(text: ApiService.apiUrl);

    return Scaffold(
      appBar: AppBar(title: Text(isSetup ? 'Настройка сервера' : 'Профиль')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Profile header
            if (!isSetup) ...[
              Center(
                child: Column(
                  children: [
                    CircleAvatar(
                      radius: 40,
                      backgroundColor: cs.primaryContainer,
                      child: Icon(Icons.person_rounded, size: 48, color: cs.primary),
                    ),
                    const SizedBox(height: 12),
                    FutureBuilder<String?>(
                      future: ApiService.getUserName(),
                      builder: (ctx, snap) => Text(
                        snap.data ?? 'Пользователь',
                        style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              // Subscription card
              Card(
                child: InkWell(
                  borderRadius: BorderRadius.circular(16),
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const SubscriptionScreen()),
                    );
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: const Color(0xFF6750A4).withOpacity(0.1),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.diamond_rounded, color: Color(0xFF6750A4)),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Подписка',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: cs.onSurface,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Управление тарифом и лимитами',
                                style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
                              ),
                            ],
                          ),
                        ),
                        Icon(Icons.chevron_right_rounded, color: cs.onSurfaceVariant),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Referral card
              Card(
                child: InkWell(
                  borderRadius: BorderRadius.circular(16),
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (_) => const ReferralScreen()),
                    );
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.amber.withOpacity(0.15),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.card_giftcard_rounded, color: Colors.amber),
                        ),
                        const SizedBox(width: 16),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Реферальная программа',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: cs.onSurface,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                'Пригласи друга — получите по 300₽',
                                style: TextStyle(fontSize: 13, color: cs.onSurfaceVariant),
                              ),
                            ],
                          ),
                        ),
                        Icon(Icons.chevron_right_rounded, color: cs.onSurfaceVariant),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 24),
            ],

            // Server URL
            Text('Подключение к серверу', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            TextField(
              controller: urlController,
              decoration: InputDecoration(
                labelText: 'API URL',
                hintText: 'http://IP:8001',
                border: const OutlineInputBorder(),
                prefixIcon: const Icon(Icons.dns_rounded),
              ),
            ),
            const SizedBox(height: 8),
            FilledButton(
              onPressed: () async {
                await ApiService.setApiUrl(urlController.text.trim());
                final ok = await ApiService.checkHealth();
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(ok ? 'Сервер доступен ✓' : 'Сервер недоступен ✗'),
                      backgroundColor: ok ? Colors.green.shade700 : Colors.red.shade700,
                    ),
                  );
                  if (ok && isSetup) {
                    Navigator.pop(context, urlController.text.trim());
                  }
                }
              },
              child: const Text('Проверить и сохранить'),
            ),
            const SizedBox(height: 32),

            // App info
            if (!isSetup) ...[
              Card(
                child: ListTile(
                  leading: Icon(Icons.info_outline, color: cs.primary),
                  title: Text(AppConfig.appName, style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text('Версия ${AppConfig.appVersion}'),
                ),
              ),
              const SizedBox(height: 16),

              // Logout
              FilledButton.tonalIcon(
                onPressed: () async {
                  final confirmed = await showDialog<bool>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('Выйти?'),
                      content: const Text('Потребуется снова войти.'),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
                        TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Выйти')),
                      ],
                    ),
                  );
                  if (confirmed == true && onLogout != null) {
                    onLogout!();
                  }
                },
                icon: const Icon(Icons.logout_rounded),
                label: const Text('Выйти из аккаунта'),
                style: FilledButton.styleFrom(backgroundColor: cs.errorContainer),
              ),
              const SizedBox(height: 12),

              // Delete account
              OutlinedButton.icon(
                onPressed: () async {
                  final confirmed = await showDialog<bool>(
                    context: context,
                    builder: (ctx) => AlertDialog(
                      title: const Text('Удалить аккаунт?'),
                      content: const Text(
                        'Все ваши данные будут безвозвратно удалены:\n'
                        '• Голосовые записи\n'
                        '• Тексты дневника\n'
                        '• Биография\n'
                        '• Статистика\n\n'
                        'Это действие нельзя отменить.',
                      ),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Отмена')),
                        TextButton(
                          onPressed: () => Navigator.pop(ctx, true),
                          child: const Text('Удалить', style: TextStyle(color: Colors.red)),
                        ),
                      ],
                    ),
                  );
                  if (confirmed == true) {
                    try {
                      await ApiService.deleteAccount();
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Аккаунт удалён. Все данные уничтожены.'),
                            backgroundColor: Colors.green,
                          ),
                        );
                        if (onLogout != null) onLogout!();
                      }
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text('Ошибка: $e'),
                            backgroundColor: Colors.red,
                          ),
                        );
                      }
                    }
                  }
                },
                icon: const Icon(Icons.delete_forever_rounded),
                label: const Text('Удалить аккаунт'),
                style: OutlinedButton.styleFrom(foregroundColor: cs.error),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
