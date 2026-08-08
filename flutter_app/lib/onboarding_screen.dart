/// Онбординг — 4 экрана при первом запуске (цитата + 3 про функции)
import 'dart:math';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';
import 'auth_screen.dart';
import 'config.dart';

/// Цитаты про память, историю и личный путь — задают тон перед разбором
/// функций приложения. Первая страница онбординга выбирается случайно
/// из этого списка при каждом первом запуске.
const _quotes = [
  (
    text: 'История — свидетель времён, свет истины, жизнь памяти, учительница жизни.',
    author: 'Цицерон',
  ),
  (
    text: 'Жизнь — не то, что прожил человек, а то, что он помнит и как помнит, чтобы рассказать.',
    author: 'Габриэль Гарсиа Маркес',
  ),
  (
    text: 'Тот, кто не помнит своего прошлого, обречён пережить его снова.',
    author: 'Джордж Сантаяна',
  ),
  (
    text: 'Жизнь можно понять, лишь оглядываясь назад, но прожить её нужно, глядя вперёд.',
    author: 'Сёрен Кьеркегор',
  ),
];

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _pageController = PageController();
  int _currentPage = 0;
  late final List<_OnboardingPage> _pages;

  @override
  void initState() {
    super.initState();
    final quote = _quotes[Random().nextInt(_quotes.length)];
    _pages = [
      _OnboardingPage(
        icon: Icons.format_quote_rounded,
        title: quote.text,
        description: '— ${quote.author}',
        color: const Color(0xFFB08968),
        isQuote: true,
      ),
      const _OnboardingPage(
        icon: Icons.mic_rounded,
        title: 'Рассказывай о себе',
        description:
            'Просто нажми на микрофон и говори.\nAI превратит твой голос в красивую\nдневниковую запись.',
        color: Color(0xFF6750A4),
      ),
      const _OnboardingPage(
        icon: Icons.auto_awesome_rounded,
        title: 'AI анализирует твой путь',
        description:
            'Настроение, теги, темы, вопросы\nдля размышления — AI помогает\nпонять себя глубже.',
        color: Color(0xFF386A20),
      ),
      const _OnboardingPage(
        icon: Icons.menu_book_rounded,
        title: 'Твоя биография\nрастёт с каждым днём',
        description:
            'Из всех записей AI напишет твою\nличную книгу. А позже — создаст\nфильм о твоей жизни.',
        color: Color(0xFF9C4040),
      ),
    ];
  }

  void _finish() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(AppConfig.onboardingDoneKey, true);
    // Notify server if logged in
    if (ApiService.isLoggedIn) {
      ApiService.completeOnboarding(); // fire-and-forget
    }
    if (mounted) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const AuthScreen()),
      );
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            // Skip button
            Align(
              alignment: Alignment.topRight,
              child: TextButton(
                onPressed: _finish,
                child: Text(
                  'Пропустить',
                  style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ),
            // Pages
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                itemCount: _pages.length,
                onPageChanged: (i) => setState(() => _currentPage = i),
                itemBuilder: (_, i) => _pages[i].build(context),
              ),
            ),
            // Indicators + button
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  // Dots
                  Row(
                    children: List.generate(
                      _pages.length,
                      (i) => AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        margin: const EdgeInsets.only(right: 8),
                        width: _currentPage == i ? 24 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: _currentPage == i
                              ? _pages[i].color
                              : theme.colorScheme.onSurfaceVariant.withOpacity(0.3),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                  ),
                  // Next / Start button
                  FilledButton(
                    onPressed: () {
                      if (_currentPage < _pages.length - 1) {
                        _pageController.nextPage(
                          duration: const Duration(milliseconds: 400),
                          curve: Curves.easeInOut,
                        );
                      } else {
                        _finish();
                      }
                    },
                    style: FilledButton.styleFrom(
                      backgroundColor: _pages[_currentPage].color,
                    ),
                    child: Text(
                      _currentPage < _pages.length - 1 ? 'Далее' : 'Начать',
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _OnboardingPage {
  final IconData icon;
  final String title;
  final String description;
  final Color color;
  final bool isQuote;

  const _OnboardingPage({
    required this.icon,
    required this.title,
    required this.description,
    required this.color,
    this.isQuote = false,
  });

  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 40),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          // Icon in circle
          Container(
            width: 140,
            height: 140,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withOpacity(0.1),
            ),
            child: Icon(icon, size: 64, color: color),
          ),
          const SizedBox(height: 48),
          // Title (цитата — курсивом и чуть меньше, обычный заголовок — жирным)
          Text(
            isQuote ? '«$title»' : title,
            textAlign: TextAlign.center,
            style: isQuote
                ? theme.textTheme.titleLarge?.copyWith(
                    fontStyle: FontStyle.italic,
                    color: theme.colorScheme.onSurface,
                    height: 1.5,
                  )
                : theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onSurface,
                  ),
          ),
          const SizedBox(height: 20),
          // Description
          Text(
            description,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              height: 1.6,
            ),
          ),
        ],
      ),
    );
  }
}
