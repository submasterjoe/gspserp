import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/api_models.dart';
import '../services/auth_store.dart';
import '../widgets/app_shell.dart';
import '../widgets/gsps_card.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key, required this.auth});
  final AuthStore auth;

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  MeOut? _me;
  String? _error;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final api = ApiClient(widget.auth);
      final res = await api.dio.get('/me');
      final me = MeOut.fromJson(res.data as Map<String, dynamic>);
      _me = me;
      final active = await widget.auth.getActiveCompanyId();
      if (active == null && me.companies.isNotEmpty) {
        await widget.auth.setActiveCompanyId(me.companies.first.id);
      }
    } on DioException catch (e) {
      _error = e.response?.data?.toString() ?? e.message;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppShell(
      auth: widget.auth,
      title: 'Profile',
      child: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_busy) const LinearProgressIndicator(),
            if (_error != null)
              GspsCard(
                title: 'Error',
                subtitle: 'Pull down to retry.',
                child: Text(_error!),
              ),
            if (_me != null) ...[
              GspsCard(
                title: _me!.fullName,
                subtitle: 'Account details',
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Username: ${_me!.username}'),
                    Text('Role: ${_me!.role}'),
                    Text('Preferred currency: ${_me!.preferredCurrency}'),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              GspsCard(
                title: 'Active company',
                subtitle: 'Used for schedule, leave and clock events.',
                child: FutureBuilder<int?>(
                  future: widget.auth.getActiveCompanyId(),
                  builder: (context, snap) {
                    final active = snap.data;
                    return DropdownButtonFormField<int>(
                      value: active ?? _me!.companies.first.id,
                      items: _me!.companies
                          .map(
                            (c) => DropdownMenuItem(
                              value: c.id,
                              child: Text('${c.name} (${c.docPrefix})'),
                            ),
                          )
                          .toList(),
                      onChanged: _busy
                          ? null
                          : (v) async {
                              if (v == null) return;
                              await widget.auth.setActiveCompanyId(v);
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('Company changed')),
                                );
                              }
                            },
                    );
                  },
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

