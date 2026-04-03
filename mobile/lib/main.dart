import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'screens/clock_screen.dart';
import 'screens/leave_screen.dart';
import 'screens/login_screen.dart';
import 'screens/profile_screen.dart';
import 'screens/schedule_screen.dart';
import 'services/auth_store.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const GspsApp());
}

class GspsApp extends StatefulWidget {
  const GspsApp({super.key});

  @override
  State<GspsApp> createState() => _GspsAppState();
}

class _GspsAppState extends State<GspsApp> {
  final _auth = AuthStore();

  late final GoRouter _router = GoRouter(
    initialLocation: '/login',
    refreshListenable: _auth,
    redirect: (context, state) async {
      final loggedIn = await _auth.hasToken();
      final goingToLogin = state.matchedLocation == '/login';
      if (!loggedIn && !goingToLogin) return '/login';
      if (loggedIn && goingToLogin) return '/clock';
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => LoginScreen(auth: _auth),
      ),
      GoRoute(
        path: '/clock',
        builder: (context, state) => ClockScreen(auth: _auth),
      ),
      GoRoute(
        path: '/schedule',
        builder: (context, state) => ScheduleScreen(auth: _auth),
      ),
      GoRoute(
        path: '/leave',
        builder: (context, state) => LeaveScreen(auth: _auth),
      ),
      GoRoute(
        path: '/profile',
        builder: (context, state) => ProfileScreen(auth: _auth),
      ),
    ],
  );

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'GSPS Mobile',
      theme: AppTheme.light(),
      routerConfig: _router,
    );
  }
}

